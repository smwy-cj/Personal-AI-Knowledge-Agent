# Agent 协作与人工决策日志 v9

本文续接 `AGENT_LOG_v8.md`，不修改原日志。

## 2026-08-14｜COURSE-T12｜Render 公开部署就绪

- 平台调研：基于官方资料比较 Render 与 Fly.io；Render 有免费 Docker Web Service、托管 HTTPS、Blueprint 和健康检查，Fly.io 新用户无免费层。
- 持久化判断：Render 免费文件系统是临时的，SQLite、Task 和 Memory 会重置；因此公开站只定位为可重置脱敏演示，不声称长期个人知识服务。
- 红灯一：部署契约因缺 `render.yaml` 失败。
- 实现一：增加 Render Blueprint、平台 PORT 解析、生成式 Web Secret 和部署指南。
- 红灯二：第一次 `PORT=10000` 容器模拟无法访问，发现 Dockerfile 固定 8000 覆盖平台端口。
- 实现二：移除固定项目端口，server 与 healthcheck 动态读取 `PORT`；第二次模拟健康检查与首页均通过。
- 代理安全判断：Render TLS 在代理层终止，显式 HTTPS 配置现在同时控制 Secure cookie 与 HSTS。
- 依赖判断：新测试最初使用本机 PyYAML，但 CI 项目依赖未声明；改为标准库文本契约，避免干净 runner 隐式依赖。
- 验证：6 项 Render 测试、28 项联合契约、完整 218 项测试通过；T11 的异常长耗时未复现。
- 外部阻塞：没有 commit/push 和 Render 账号授权，无法获得真实 URL；没有伪造部署完成证据。
- 用户约束：继续忽略 Superpowers。
- 原文档保护：部署指南、就绪证据和本日志均新建。
- commit/PR：尚未创建。
