# Python 包与 Docker 分发指南

## 1. 分发产物

项目提供两种本地交付方式：

- Python wheel/sdist：适合已有 Python 3.9+ 环境；
- Docker 镜像：课程演示首选，内含脱敏 Vault、离线模型和生产 WSGI server。

当前没有发布到 PyPI 或远程镜像仓库。`dist/` 是本地生成目录，不进入 Git。

## 2. Python 包

安装构建工具并生成产物：

```powershell
python -m pip install build
python -m build
```

网络受限但当前环境已满足打包后端时，可以使用：

```powershell
python -m build --no-isolation
```

安装 wheel 后提供三个入口：

- `personal-ai-agent`：CLI；
- `personal-ai-agent-web`：Waitress WSGI WebUI；
- `personal-ai-agent-demo`：同步演示 Vault 后启动 Waitress。

生产 Web 命令：

```powershell
$env:PERSONAL_AGENT_CONFIG = "course_demo/config.json"
$env:PERSONAL_AGENT_DEMO_MODE = "1"
$env:PERSONAL_AGENT_DEMO_DATA_ROOT = (Resolve-Path "course_demo").Path
$env:PERSONAL_AGENT_WEB_SECRET = "使用密码生成器生成的长随机值"
personal-ai-agent-web --host 127.0.0.1 --port 8000 --threads 4
```

## 3. Docker 构建

```powershell
docker build -t personal-ai-knowledge-agent:course .
```

镜像属性：

- 基于 `python:3.12-slim`；
- 以 `agent` 非 root 用户运行；
- 不复制 `.git`、测试、本地数据、真实配置或 `.env`；
- 内置三篇脱敏 Markdown；
- runtime 位于 `/app/course_demo/runtime`；
- 默认执行 `personal-ai-agent-demo`；
- 内置 `/health` 检查。

## 4. 单容器运行

```powershell
$secret = "使用密码生成器生成的长随机值"
docker run --rm `
  -p 127.0.0.1:8000:8000 `
  -e PERSONAL_AGENT_WEB_SECRET=$secret `
  personal-ai-knowledge-agent:course
```

访问 `http://127.0.0.1:8000/`。端口默认只绑定本机，避免把无身份认证的课程演示暴露到局域网或公网。

## 5. Compose

先在当前 PowerShell 会话中设置 Secret：

```powershell
$env:PERSONAL_AGENT_WEB_SECRET = "使用密码生成器生成的长随机值"
docker compose -f docker-compose.example.yml up --build
```

Compose 特性：

- runtime 使用命名卷；
- `course_demo/vault` 从宿主机挂载，批准的 Memory 可以在宿主机查看；
- 容器根文件系统只读；
- `/tmp` 使用受限 tmpfs；
- 删除全部 Linux capabilities；
- 开启 `no-new-privileges`；
- 未设置 Web Secret 时 Compose 在启动前报错。

宿主机挂载的演示 Vault 会被应用写入 `course_demo/vault/Agent/Memory/`。它只包含脱敏演示数据，但仍应在演示前确认目录内容。

## 6. HTTPS 部署变量

TLS 应由部署平台或受控反向代理终止。使用 HTTPS 时设置：

```text
PERSONAL_AGENT_HTTPS=1
```

这会给会话 Cookie 增加 `Secure`。反向代理场景还需要确认应用收到正确的 HTTPS 语义；当前没有自动信任任意代理头，避免客户端伪造。

## 7. 健康检查

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

预期：

```json
{
  "config_loaded": true,
  "demo_mode": true,
  "status": "ok",
  "storage_ready": true
}
```

健康检查不调用模型、不读取密钥、不产生费用。

## 8. 当前限制

- 没有登录与多用户授权，公开部署只能使用脱敏演示数据；
- 没有发布到外部包或镜像仓库；
- 容器启动会同步小型演示 Vault，不是大规模生产迁移方案；
- Linux 容器通常没有桌面 keyring；演示模式不需要凭据，真实 Provider 应通过合适的部署 Secret 集成另行设计；
- CI、远程镜像构建和部署属于 T11–T12。
