# Agent 协作与人工决策日志 v6

本文续接 `AGENT_LOG_v5.md`，不修改原日志。

## 2026-08-13｜COURSE-T9｜Web 安全与错误边界

- 任务边界：只实现课程本地/受控演示所需的 CSRF、请求上限、响应头、错误脱敏、演示目录隔离和基础无障碍，不引入账号系统。
- 红灯：8 个新场景中 7 失败、1 错误，客观确认所有目标保护最初均不存在。
- CSRF 判断：使用 Flask 已有签名会话和标准库随机 token，避免为单一能力新增大型扩展；所有状态改变方法默认保护。
- Cookie 判断：本机 HTTP 不强制 Secure；`PERSONAL_AGENT_HTTPS=1` 的部署明确开启 Secure，HTTPS 响应才发送 HSTS。
- 隐私判断：持久 Task error message 可能含 Provider 正文或路径，因此页面只显示稳定的 error type，详细排查留在受控本地存储。
- 演示隔离判断：仅用页面 `DEMO_MODE` 标识不构成写入限制；默认 adapter 现在要求显式 demo root，并同时校验 Vault 与 runtime 的解析路径。
- 测试职责：旧 Web 功能测试显式关闭 CSRF以继续关注领域行为；T9 测试完整验证默认安全行为和合法 token 路径。
- 可访问性：新增 skip link、主内容目标、表单错误关联与完整焦点轮廓；没有虚构 WCAG 人工审计结果。
- 验证：8 项安全测试、33 项 Web 测试、完整 198 项测试全部通过。
- 原文档保护：新建 `DEMO_GUIDE_v2.md` 而未修改 v1；其他说明和证据同样使用新文件。
- commit/PR：尚未创建。
