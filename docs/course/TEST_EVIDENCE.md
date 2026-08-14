# 当前工程基线与测试证据

## 1. 记录目的

本文记录课程完善工作开始时的不可变工程基线，用于区分既有能力与后续新增能力。本文不替代 CI/CD 在线记录，也不把未验证的远程平台状态写成事实。

记录日期：2026-08-13（Asia/Shanghai）

## 2. Git 基线

- 仓库：`Personal-AI-Knowledge-Agent`
- 当前分支：`agent/iteration-18-delivery-baseline`
- 基线 commit：`8b102d0ef76637037e4d1aef9640b47ac0a7a4b7`
- 基线 commit 说明：`Add provider quota observability`
- 远程仓库：`https://github.com/smwy-cj/Personal-AI-Knowledge-Agent.git`
- 课程完善开始时存在一个未跟踪的新文件：`COURSE_COMPLETION_PLAN.md`

本地 Git 历史显示当前基线之前包含多个增量 commit，但本记录不据此推断远程 PR、worktree、人工评审或 CI 运行状态。相关事实必须在远程平台单独核验。

## 3. 自动化测试基线

统一验证命令：

```powershell
python scripts/verify.py
```

2026-08-13 本地执行结果：

- 测试文件：23 个；
- 测试方法：149 个；
- 执行结果：149 项通过，0 项失败；
- `unittest` 运行时间：18.686 秒；
- 验证脚本总耗时约 28.4 秒；
- CLI `--help` 冒烟检查通过；
- 固定示例 Vault 同步结果：新增 3，更新 0，删除 0，失败 0；
- 进程退出码：0。

上述时间只描述本次机器和本次运行，不能作为其他机器的性能承诺。

## 4. 当前测试覆盖的主要能力

### 4.1 应用与 CLI

- 配置校验、Vault 同步与检索命令链；
- 向量同步、混合检索和 Research 运行；
- Task 展示、列表与持久化取消；
- Memory 审批、写回和重新索引；
- 观测摘要、成本报告、账单对账和事件保留；
- 检索、Research、Memory 质量门禁及退出码。

### 4.2 Agent 工作流与可靠性

- 依赖调度和循环计划拒绝；
- 工具调用预算、Token 预算和有限重试；
- 确定性失败不重试；
- 状态转换合法性；
- Checkpoint、恢复和已完成步骤跳过；
- 执行租约、心跳、过期接管和旧 owner 写保护；
- 持久化取消在步骤边界生效。

### 4.3 知识检索与引用

- Obsidian Markdown 解析、增量摄取和删除同步；
- FTS5 与确定性关键词回退；
- 向量缓存、余弦检索和混合 RRF；
- Research Evidence Pack；
- 引用来源漂移、篡改和未知引用检测。

### 4.4 记忆治理与写回

- 敏感候选拒绝；
- 重复和冲突识别；
- 所有待审批候选必须获得明确决定；
- 受控目录、路径穿越防护和 Obsidian 内部目录拒绝；
- 原子写入、幂等、用户修改漂移和非托管文件冲突。

### 4.5 Provider、安全与成本

- 配置文件拒绝密钥字段且异常不回显密钥值；
- 凭据在调用时从指定环境变量读取；
- 携带凭据的 Provider 要求 HTTPS；
- HTTP 错误不读取或持久化响应正文；
- 能力、上下文、成本和隐私约束路由；
- 请求、Token、并发限流、共享冷却和 Usage 校正；
- 脱敏观测、成本聚合和账单差异门禁。

## 5. 当前 CI 配置事实

仓库存在 `.github/workflows/ci.yml`，配置事实如下：

- push 和 pull request 触发；
- Ubuntu 上测试 Python 3.9、3.11、3.13；
- Windows 上测试 Python 3.11；
- 安装本项目后运行 `python scripts/verify.py`；
- 检查安装后的 `personal-ai-agent --help`。

本记录没有访问远程 GitHub Actions 页面，因此不声明最新远程流水线是否通过。课程指定的 `.gitlab-ci.yml` 和名为 `unit-test` 的 job 在基线时不存在。

## 6. 当前分发事实

基线已具备：

- `pyproject.toml`；
- setuptools 构建后端；
- `personal-ai-agent` console script；
- Python 3.9+ 声明；
- 安装后命令的本地/CI 配置检查。

基线尚未发现：

- `Dockerfile`；
- 已发布的 PyPI 包证据；
- 公开容器 registry 地址；
- 干净机器安装记录；
- `LICENSE`；
- WebUI 或在线演示 URL。

## 7. 当前凭据安全边界

已经实现：

- 配置文档只保存环境变量名称，不保存凭据值；
- 配置拒绝 `api_key`、`secret`、`token`、`password` 等字段；
- URL 不允许嵌入用户名或密码；
- 带凭据的远程 Provider 必须使用 HTTPS；
- 缺失凭据的错误只报告环境变量名；
- 测试验证凭据不出现在错误文本中。

尚未实现：

- 系统密钥环安全持久化；
- 首次运行隐藏录入；
- 凭据状态查看；
- 凭据更新；
- 凭据清除。

因此，当前实现不能被描述为已经完整满足课程凭据生命周期要求。

## 8. 基线缺口

课程完善开始时的主要缺口：

1. 缺少课程指定的 `SPEC.md`、`PLAN.md`、`SPEC_PROCESS.md`、`AGENT_LOG.md` 和学生本人撰写的 `REFLECTION.md`。
2. 缺少 WebUI 和公开在线演示 URL。
3. 缺少系统密钥环及完整凭据生命周期。
4. 缺少课程指定 GitLab CI 配置。
5. 缺少正式公开分发和干净机器验证证据。
6. 缺少可核验的冷启动、PR、两阶段评审和人工干预证据整理。
7. 当前工作流计划由应用代码预定义，尚无动态 Planner 或通用自主工具选择，不应描述为完全自主 Agent。

## 9. 证据限制

- 本文基于本地工作区和本地命令结果。
- 本文没有验证 GitHub/NJU Git 的网页状态、PR、权限或线上 CI。
- 本文没有调用真实付费 Provider。
- 本文没有使用真实个人 Vault 做验收。
- 后续新增测试必须与本基线分开记录，并注明对应 commit。
