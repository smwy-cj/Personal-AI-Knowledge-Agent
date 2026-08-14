# Agent 协作与人工决策日志 v5

本文续接 `AGENT_LOG_v4.md`，不修改原日志。

## 2026-08-13｜COURSE-T8｜Research、Task 与 Memory 审批 WebUI

- 任务边界：实现研究提交、持久 Task 详情、取消、逐项记忆审批和写回收据，不提前实现 T9 公网安全或 T10 分发。
- 红灯一：Research、Task、Memory 路由不存在，10 个初始场景全部因 404 失败。
- 实现一：新增四组路由、三个页面、port 调用、输入校验、303 重定向和安全状态映射。
- 集成补强：增加临时 Vault → 真实 Application Service → Orchestrator → WAITING_USER → Web 审批 → Memory Repository → 受控 Vault 写回测试。
- 人工判断：只在测试中替换 HTTP 响应不足以证明课程现场可重复演示，不能将 T8 直接标为完成。
- 红灯二：无 Provider 的默认 `DEMO_MODE` Research 返回 500。
- 实现二：增加只复制已检索证据的确定性 `demo-model`，通过 `PERSONAL_AGENT_DEMO_MODE=1` 启用；明确它不是大模型质量演示。
- 安全判断：所有笔记与模型文本依赖 Jinja 自动转义；重复审批返回 409；取消只允许 POST。CSRF 和公网写入隔离留给 T9，所以当前只允许本地演示。
- 验证：25 项 Web 测试通过；完整 190 项测试通过；`scripts/verify.py` 退出码为 0。
- 陌生智能体：按用户指示，本轮没有因不可调用陌生智能体而阻塞工作，也没有新增该步骤。
- 原文档保护：所有说明、证据与日志使用新文件，没有修改既有 Markdown 文档。
- commit/PR：尚未创建。
