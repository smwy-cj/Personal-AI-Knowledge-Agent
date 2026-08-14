# Agent 协作与人工决策日志 v7

本文续接 `AGENT_LOG_v6.md`，不修改原日志。

## 2026-08-14｜COURSE-T10｜Python 包与 Docker 分发

- 任务边界：实现本地 wheel/sdist、生产 WSGI、非 root Docker 和脱敏演示资产，不提前声称远程发布或 CI 完成。
- 红灯：7 项分发契约全部失败，确认核心交付文件与入口当时不存在。
- WSGI 判断：使用轻量 Waitress，保持 Python 3.9+ 和 Windows/Linux 兼容；Flask 内置服务器不进入容器默认命令。
- 资产判断：模板与 CSS 必须显式进入 package data，不能依赖源码 checkout。
- 演示判断：镜像只包含新建的三篇脱敏笔记；`.dockerignore` 排除 Git、本地 data、真实配置、数据库、测试和过程文档。
- 容器安全：非 root、只读 Compose 根文件系统、受限 tmpfs、删除 capabilities、no-new-privileges、本机端口绑定。
- 持久化判断：runtime 使用命名卷；演示 Vault 显式挂载以便展示 Memory 写回，但只允许使用脱敏目录。
- 构建问题：隔离构建首先被本机网络沙箱和旧 setuptools 阻塞；经用户许可安装工具后，wheel/sdist 实际构建成功。
- 验证纠正：第一次 venv 故意不装依赖导致 Web 入口缺 Flask；第二次补齐运行依赖并逐步检查退出码，三个命令与资产通过。
- 脚本纠正：容器首页验证第一次误用 PowerShell 只读变量 `$HOME`；随后使用任务专用变量重新执行，记录首页 200 和 CSP，并确认容器删除。
- 最终验证：7 项分发契约与完整 205 项测试通过；镜像实际构建和启动通过。
- 原文档保护：所有分发指南、证据和日志均使用新文件。
- commit/PR：尚未创建。
