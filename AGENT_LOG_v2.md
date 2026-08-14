# Agent 协作与人工决策日志 v2

本文续接 `AGENT_LOG.md`，不修改原日志。

## 2026-08-13｜COURSE-T3｜陌生智能体冷启动验证

- 输入：仅 `SPEC.md` 与 `PLAN.md`。
- 隔离：不同模型、全新会话、无历史上下文、只读任务。
- 结果：正确识别 5 个阻塞性歧义并停止，没有猜测实现或修改文件。
- 人工/主 Agent 决策：冻结 Flask 3.x、受限 demo mode、WebApplicationPort、keyring 命名空间和环境变量后备规则。
- 产出：`docs/course/COLD_START_VALIDATION.md`、`SPEC_v2.md`。
- commit/PR：尚未创建。

## 2026-08-13｜COURSE-T4｜凭据存储抽象

- 红灯：`personal_ai_agent.credentials` 不存在。
- 实现：CredentialStore 协议、CredentialStatus、内存 store 和 OS keyring adapter。
- 验证：7 项专项测试通过；完整回归 156 项通过。
- 安全：测试没有访问真实密钥环；状态与错误不包含凭据。
- 产出：新代码、测试和 `docs/course/T4_CREDENTIAL_STORE_EVIDENCE.md`。
- commit/PR：尚未创建。

## 2026-08-13｜COURSE-T5｜凭据 CLI 与 Provider 接入

- 红灯：CLI 不接受 credential store/secret reader 注入；CredentialResolver 不存在。
- 实现：隐藏录入、状态、删除、keyring 优先、显式环境变量后备，以及模型/Embedding 接入。
- 回归问题：首次完整回归发现无认证 localhost Provider 被误要求凭据。
- 修复：将“解析凭据”和“是否必需”分离，保留无认证本地 Provider 行为。
- 验证：31 项相关测试通过；完整 165 项测试通过。
- 依赖判断：根据 PyPI 元数据选用 `keyring>=25.7,<26`，匹配 Python 3.9+。
- 产出：新测试、指南和 `docs/course/T5_CREDENTIAL_LIFECYCLE_EVIDENCE.md`。
- commit/PR：尚未创建。
