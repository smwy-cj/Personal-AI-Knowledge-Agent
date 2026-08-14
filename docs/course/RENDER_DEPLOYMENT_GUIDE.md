# Render 公开课程演示部署指南

## 1. 当前状态

`render.yaml` 与容器已经准备好，但截至 2026-08-14 尚未获得公开 URL，也没有连接用户的 Render 账号。本文是可执行部署说明，不是已部署成功证明。

## 2. 为什么选择 Render

本项目需要运行 Python 服务端和 Docker，不适合静态托管。Render 支持：

- 直接从仓库 Dockerfile 构建；
- Blueprint `render.yaml`；
- 免费 Web Service；
- 托管 HTTPS；
- `/health` 健康检查；
- 自动生成 Web session secret；
- GitHub/GitLab 连接和自动部署。

选择免费实例是为了课程演示控制成本，而非生产可用性承诺。

## 3. 免费实例的重要限制

Render 免费 Web Service 连续 **15 分钟**没有入站流量后会休眠，下一次访问冷启动可能需要约一分钟。

免费实例使用**临时文件系统**：重启、重新部署或休眠恢复后，本地 SQLite 数据和审批写回文件可能丢失。当前容器每次启动都会重新同步镜像中的三篇样例笔记，因此搜索和 Research 可以恢复，但此前的 Task、审批记录和 Memory 写回不保证长期保存。

因此：

- 这是可重置的脱敏课程演示；
- 不得使用个人 Vault；
- 不得配置真实付费模型凭据；
- 页面必须继续显示演示模式；
- 不应把它描述为持久个人知识服务；
- 如需长期持久化，需选择付费磁盘或将状态迁移到托管数据库/对象存储，这超出当前课程演示范围。

## 4. Blueprint 内容

`render.yaml` 定义一个 Singapore 区域的免费 Docker Web Service：

- `healthCheckPath: /health`；
- 从根目录 `Dockerfile` 构建；
- 使用 `PERSONAL_AGENT_DEMO_MODE=1`；
- 使用镜像内 `/app/course_demo`；
- `PERSONAL_AGENT_HTTPS=1`；
- `PERSONAL_AGENT_WEB_SECRET` 由 Render 生成，不进入 Git；
- 监听 Render 提供的 `PORT`。

## 5. 用户需要执行的部署步骤

部署前必须先把当前改动 commit 并 push 到可连接的 GitHub 或 GitLab 仓库。

1. 登录 Render Dashboard。
2. 选择 **New → Blueprint**。
3. 连接包含本项目的 GitHub/GitLab 仓库。
4. 选择包含 `render.yaml` 的最终分支。
5. 检查只创建一个 `personal-ai-knowledge-agent-demo` 免费 Web Service。
6. 确认没有填写任何 API key、个人 Vault 或真实数据路径。
7. 点击 Deploy Blueprint。
8. 等待 Docker build 与 `/health` 通过。
9. 记录 `https://...onrender.com` URL、部署 commit SHA 和部署时间。

Render Blueprint 与 Web Service 文档：

- <https://render.com/docs/infrastructure-as-code>
- <https://render.com/docs/blueprint-spec>
- <https://render.com/docs/web-services>
- <https://render.com/docs/free>

## 6. 部署后验收

在 PowerShell 中：

```powershell
$demoUrl = "https://你的服务.onrender.com"
Invoke-RestMethod "$demoUrl/health"
$response = Invoke-WebRequest -UseBasicParsing "$demoUrl/"
$response.StatusCode
$response.Headers["Content-Security-Policy"]
```

还要通过浏览器验证：

1. 首页明确显示演示模式；
2. 搜索能找到三篇脱敏笔记；
3. Research Provider 字段留空时进入 `WAITING_USER`；
4. Memory 批准/拒绝后任务完成；
5. 页面不出现个人路径、真实 key、Prompt 或堆栈；
6. HTTPS Cookie 包含 Secure；
7. 休眠冷启动限制已在 README_COURSE 中披露。

## 7. 生成正式部署证据

部署完成后新建 `docs/course/DEPLOYMENT_EVIDENCE.md`，记录：

- 公开 URL；
- 部署平台与区域；
- commit SHA；
- 首次部署时间与最近复验时间；
- build/deploy 状态；
- `/health` 实际响应；
- 首页、搜索、Research、审批结果；
- 冷启动与临时文件系统限制；
- 是否使用任何付费资源。

没有真实 URL 时，不得提前创建声称成功的部署证据。
