# 陌生智能体冷启动验证记录

## 1. 验证信息

- 执行日期：2026-08-13（Asia/Shanghai）
- 对应任务：PLAN T3
- 验证类型：不同模型、全新会话、无历史上下文的只读规格评审
- 输入文件：仅 `SPEC.md` 与 `PLAN.md`
- 评审范围：T4 凭据存储抽象、T6 Web 应用边界与框架
- 文件权限：要求不修改、不创建任何文件
- 停止规则：遇到任何阻塞性歧义时停止设计，不猜测实现
- 执行结果：成功调用并完成评审；没有跳过

## 2. 向陌生智能体提供的任务

要求陌生智能体：

1. 用自己的话说明项目边界以及 T4/T6 的预期结果；
2. 判断只凭 SPEC/PLAN 是否足以安全开始实现；
3. 区分阻塞性歧义和非阻塞性问题；
4. 存在阻塞项时立即停止，不猜测实现；
5. 没有阻塞项时只列失败测试，不实现；
6. 明确实际读取的文件和未读取其他材料的事实。

## 3. 对项目边界的复述结果

陌生智能体正确理解了项目的主要边界：

- 本地优先地索引 Obsidian Markdown；
- 提供可追溯搜索和带引用 Research；
- 记忆必须经过人工审批；
- Provider 调用受预算、取消、隐私和审计约束；
- 项目不是通用自主 Agent；
- 课程演示不展示真实个人 Vault 或真实凭据。

它对任务结果的理解也与计划一致：

- T4 应交付可 fake 测试的存储协议、状态对象、内存 fake 和 OS 密钥环适配器，不接入 CLI；
- T6 应交付轻量 Web 框架上的应用工厂和适配边界，只通过 Application Service 工作，包含首页、健康检查和安全错误响应。

这说明项目定位与两个任务的高层目标已经足够清楚。

## 4. 暴露的阻塞性歧义

### 4.1 Web 框架未选定

SPEC 只写了“轻量 Python Web 框架”，PLAN 又明确要求智能体不能自行决定。因此无法开始建立具体应用工厂、测试客户端和依赖配置。

处理决定：课程 WebUI 使用 Flask 3.x 和 Jinja 服务器渲染。选择理由是应用规模小、以表单和页面为主、无需单独前端构建链，并且容易通过应用工厂和测试客户端隔离 Application Service。

### 4.2 公网身份认证与危险写操作策略未定

SPEC 提供了“禁用危险写操作或增加访问控制”两个方向，但没有做出唯一选择。

处理决定：课程公开演示使用受限演示模式，不引入多用户认证。公开演示中：

- 禁止凭据录入、更新和删除；
- 禁止配置真实远程 Provider；
- Research 使用确定性 fake Provider；
- Memory 审批允许执行，但只能写入每个演示实例的临时示例目录；
- 禁止访问宿主机任意路径；
- 演示数据允许定期或重启时重置。

真实 Provider 和真实 Vault 仅在用户本地部署中启用。

### 4.3 Web 与 Application Service 的适配契约缺失

“只调用 Application Service”尚不足以定义 Web 边界，特别是构造、健康检查、副作用和错误映射。

处理决定：新增 `WebApplicationPort` 协议作为 Web 层唯一业务依赖。最小方法集合固定为：

- `health()`：只检查进程、配置和本地存储可用性，不调用 Provider；
- `knowledge_status()`：返回公开的 Vault ID、索引统计和同步状态；
- `search(...)`；
- `run_research(...)`；
- `show_task(...)`；
- `cancel_task(...)`；
- `pending_memory_candidates(...)`；
- `resolve_memory(...)`；
- `observability_summary(...)`。

生产适配器包装现有 `ApplicationService`；测试使用 fake port。Web 路由不得直接创建 SQLite repository、读取 Vault 文件或调用 Provider Adapter。

错误映射固定为：

- 输入/配置错误：400；
- 资源不存在：404；
- Task 状态冲突或租约冲突：409；
- 请求过大：413；
- Provider 暂时不可用：503；
- 未分类异常：500，并仅向用户显示关联 ID。

### 4.4 密钥环 service name 与 Provider ID 规则缺失

命名空间一旦发布便不适合随意改变，否则用户升级后会找不到旧 key。

处理决定：

- keyring service name 固定为 `personal-ai-knowledge-agent`；
- username/key 固定为 `provider:<provider_id>`；
- Provider ID 使用配置中已经接受的原始标识符，区分大小写；
- 不执行大小写折叠、Unicode 归一化或字符替换；
- 只接受现有配置校验器可接受的 Provider ID；
- 同一配置内 Provider ID 必须唯一；
- 模型与 Embedding 若复用同一 Provider ID，则共享同一凭据；需要不同 key 时必须使用不同 Provider ID。

该方案避免额外规范化造成碰撞。

### 4.5 OS 密钥环依赖与后备策略未定

容器或无桌面 Linux 环境不一定存在系统 Secret Service，不能静默假定 keyring 可用。

处理决定：

- 使用 Python `keyring` 作为 OS 密钥环适配库；
- T4 的 OS adapter 在 backend 不可用或优先级不足时返回明确的 backend-unavailable 错误；
- 不使用明文文件后端；
- Provider 解析顺序为 OS keyring 优先，其次是该 Provider 配置声明的 `credential_env`；
- 只有配置显式声明 `credential_env` 时才允许环境变量后备；
- 后备发生时状态输出来源为 `environment`，但不输出变量值；
- Docker/云端通过平台 secret 注入环境变量，不在容器中伪造桌面密钥环；
- 本地首次设置命令默认要求可用 OS keyring，不静默把 key 写入 `.env`。

## 5. 非阻塞问题及处理方向

- `CredentialStatus` 字段：固定为 `provider_id`、`configured`、`source`、`backend_available`，不包含明文或掩码值。
- 空凭据：拒绝空白输入；Unicode 和任意非空字符允许原样保存。
- 重复删除：返回 `deleted: false`，不作为异常。
- 覆盖失败：保留旧值并返回安全错误；具体事务能力取决于 backend。
- 健康检查：返回 JSON，包含 `status`、`config_loaded`、`storage_ready`、`demo_mode`，不探测付费 Provider。
- 健康检查分层：课程初版只提供 `/health`，暂不区分 liveness/readiness。
- 默认开发地址：`127.0.0.1:8000`；容器监听地址由启动参数设为 `0.0.0.0:8000`。
- 模板、CSS 和更完整的可访问性由 T7/T9 处理。

## 6. 与原意不一致的解读

陌生智能体没有明显误读项目目标，但它正确拒绝自行选择 Web 框架和安全策略。这不是智能体能力问题，而是规格确实提供了多个可选方向而未做唯一决策。

原规格中“待实现时确认”的表述对人工讨论足够，但对一次性自主实现不够。冷启动验证证明，任务必须在进入编码前冻结依赖、命名空间和公网写入边界。

## 7. 产出与预期差距

预期结果是：陌生智能体若发现阻塞歧义，应暂停并提出问题，而不是猜测。

实际结果完全符合该预期：

- 正确复述项目边界；
- 识别 5 个阻塞点；
- 没有生成实现代码；
- 没有列出假装可执行的测试；
- 明确只读取 `SPEC.md` 与 `PLAN.md`；
- 没有修改或创建文件。

## 8. 修订方式

遵循“旧文档只读、所有修订创建新文档”的约束：

- 不修改 `SPEC.md`；
- 不修改 `PLAN.md`；
- 新建 `SPEC_v2.md` 记录权威澄清；
- 后续实现同时以 `SPEC.md` 和 `SPEC_v2.md` 为准；
- 若两者冲突，`SPEC_v2.md` 中明确列出的决定优先。

## 9. 冷启动验收结论

T3 验证执行成功，并有效暴露规格缺陷。完成本记录和 `SPEC_v2.md` 后，T4 与 T6 的阻塞问题视为已解决，可以进入正式 TDD 实现。

该结论不代表 T4/T6 已实现，也不代表任何实现测试或 PR 已产生。
