# Personal AI Knowledge Agent 课程项目规格澄清 v2

状态：Accepted clarification；已实现于 `v0.1.0`
日期：2026-08-13  
基础规格：`SPEC.md`（已接受并实现）
产生原因：陌生智能体冷启动验证暴露阻塞性歧义

## 1. 使用规则

本文是独立新增的规格澄清，不修改或覆盖 `SPEC.md`。

后续实现必须同时遵守 `SPEC.md` 与本文。两者发生冲突时，仅对本文明确列出的主题以本文为准；其他主题继续以 `SPEC.md` 为准。

## 2. Web 技术选型

课程 WebUI 固定使用：

- Flask 3.x；
- Jinja 服务器渲染模板；
- Flask 应用工厂；
- Flask 测试客户端；
- 不引入独立 SPA、Node.js 构建链或浏览器直连 Provider。

选择理由：当前界面以搜索、任务状态和审批表单为主，服务器渲染能以较小依赖和攻击面复用 Python Application Service。

开发默认监听 `127.0.0.1:8000`；容器通过显式启动参数监听 `0.0.0.0:8000`。

## 3. Web 业务端口

Web 层唯一允许依赖的业务契约命名为 `WebApplicationPort`，至少包含：

```text
health()
knowledge_status()
search(...)
run_research(...)
show_task(...)
cancel_task(...)
pending_memory_candidates(...)
resolve_memory(...)
observability_summary(...)
```

规则：

- 生产 adapter 包装现有 `ApplicationService`；
- 测试注入 fake port；
- 路由不得直接构造 Repository；
- 路由不得直接读取 Vault 文件；
- 路由不得直接调用 Model/Embedding Provider；
- `health()` 不调用付费 Provider，只检查配置和本地存储准备状态。

## 4. Web 错误契约

| 错误类别 | HTTP 状态 | 对用户输出 |
|---|---:|---|
| 输入或安全配置错误 | 400 | 字段级安全提示 |
| 资源不存在 | 404 | 通用不存在页面 |
| Task 状态/租约冲突 | 409 | 可恢复的冲突说明 |
| 请求过大 | 413 | 大小限制说明 |
| Provider 暂时不可用 | 503 | 稍后重试提示 |
| 未分类异常 | 500 | 仅关联 ID，不含内部信息 |

所有错误页面和 JSON 均不得包含堆栈、绝对路径、Prompt、Evidence 正文、Provider 响应正文或凭据。

## 5. 公网演示安全模式

课程公开部署使用 `demo_mode`，不实现多用户账户系统。

在 `demo_mode` 下：

- 禁止凭据录入、更新和删除；
- 禁止配置真实远程 Provider；
- Research 只使用确定性 fake Provider；
- 搜索只使用固定脱敏示例 Vault；
- Memory 审批可演示，但只能写入实例专属临时目录；
- 禁止用户选择或提交任意宿主机路径；
- 数据可以在实例重启或定时任务后重置；
- 页面必须明确标注“演示模式”和 fake Provider。

本地部署不启用 `demo_mode` 时，用户可以使用自己的 Vault 和凭据，但仍必须遵守原规格安全边界。

## 6. 凭据命名空间

- keyring service name：`personal-ai-knowledge-agent`
- keyring username/key：`provider:<provider_id>`
- Provider ID 使用通过现有配置校验的原始字符串；
- Provider ID 区分大小写；
- 不执行大小写折叠、Unicode 归一化或字符替换；
- 配置内 Provider ID 必须唯一；
- Model 和 Embedding Profile 复用 Provider ID 时共享凭据；需要不同凭据时必须使用不同 Provider ID。

## 7. 凭据存储与解析

### 7.1 存储

- OS adapter 使用 Python `keyring`；
- 禁止使用明文文件 keyring backend；
- backend 不可用或不安全时明确失败；
- `credential set` 不接受明文命令行参数，只接受隐藏交互输入；
- 本地设置不会静默写入 `.env`。

### 7.2 Provider 解析顺序

1. 查找 OS keyring 的 `provider:<provider_id>`；
2. 若不存在，并且 Provider 配置显式声明 `credential_env`，读取该环境变量；
3. 两者都不存在则返回安全的缺失凭据错误。

环境变量后备适用于 Docker/云平台 secret 注入和兼容现有配置。后备来源必须显示为 `environment`，但不得输出变量值。

### 7.3 状态契约

`CredentialStatus` 只包含：

```text
provider_id
configured
source              # keyring | environment | none
backend_available
```

不得包含明文、掩码 key、key 长度、前缀或后缀。

### 7.4 边界行为

- 空或全空白凭据拒绝；
- 非空 Unicode 凭据原样保存；
- 重复删除返回 `deleted: false`，不报错；
- 更新失败不得主动删除旧凭据；
- 错误、`repr`、stdout/stderr 和事件不得包含输入凭据。

## 8. T4/T6 启动条件

完成本文后，以下阻塞项视为已冻结：

- Web 框架；
- Web/Application Service 端口；
- Web 错误映射；
- 公网危险写操作策略；
- keyring service name；
- Provider ID 碰撞策略；
- keyring 依赖和环境变量后备条件。

T4 和 T6 可以分别进入失败测试阶段。任何改变上述决定的工作必须创建新的规格版本，不得直接修改本文。
