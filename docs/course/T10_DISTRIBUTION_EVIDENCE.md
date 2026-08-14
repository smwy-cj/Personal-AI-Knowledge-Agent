# T10 Python 与 Docker 分发实施证据

## 1. 任务状态

- 日期：2026-08-14
- 对应计划：T10
- 状态：本地实现和实际构建验证完成，尚未提交 commit、创建 PR 或发布远程镜像

## 2. 环境审计

开始时：

- `pyproject.toml` 只有 CLI entrypoint；
- 没有 Waitress、Dockerfile、`.dockerignore`、Compose、`.env.example`、LICENSE 或打包的演示 Vault；
- 本机最初没有 `build` 和 Waitress；
- Docker 客户端存在，首次沙箱内检查不能访问 Engine。

在获得允许后安装构建工具并连接 Docker Engine。没有安装 Superpowers，也没有调用陌生智能体。

## 3. 红灯

新增 `tests/test_distribution_contract.py` 后 7 个场景全部失败：1 个断言失败、6 个文件不存在错误。

失败证明当时缺失：生产入口、包内 Web 资产、Docker ignore、非 root 镜像、无密钥样例、Compose 安全边界和许可证。

## 4. 实现内容

新增：

- `src/personal_ai_agent/web_server.py`；
- `src/personal_ai_agent/container_entrypoint.py`；
- `Dockerfile`；
- `.dockerignore`；
- `.env.example`；
- `docker-compose.example.yml`；
- `course_demo/config.json`；
- `course_demo/vault/` 三篇脱敏笔记；
- `LICENSE`；
- `tests/test_distribution_contract.py`；
- `docs/course/DISTRIBUTION_AND_DEPLOYMENT.md`；
- 本证据文件。

修改 `pyproject.toml`：

- 增加 Waitress 依赖；
- 增加 Web 与 demo console scripts；
- 把 Jinja 模板和 CSS 纳入 wheel。

没有修改既有 Markdown 文档。

## 5. Python 构建证据

隔离构建首次因为本机网络沙箱与旧打包后端失败，错误未被伪装为成功。获得允许后安装 `build`、Waitress 和新版 setuptools，再执行本机构建。

生成：

```text
personal_ai_knowledge_agent-0.1.0-py3-none-any.whl  114203 bytes
personal_ai_knowledge_agent-0.1.0.tar.gz            145534 bytes
```

wheel 检查：

- 52 个归档项；
- 包含 `web/templates/base.html`；
- 包含 `web/static/app.css`；
- 包含 MIT LICENSE；
- 包含三个 console scripts。

随后在新建临时 venv 中从 wheel 安装，验证三个命令的 `--help` 与包内模板/CSS。最终输出：

```text
installed-wheel-entrypoints-and-assets-ok
```

首次隔离 venv 使用 `--no-deps`，Web 入口因缺 Flask 失败；这是验证环境缺运行依赖，不是 wheel 元数据问题。第二次 venv 使用已有运行依赖并对每步检查退出码后通过，过程如实保留。

## 6. Docker 构建与运行证据

实际命令：

```text
docker build -t personal-ai-knowledge-agent:course .
```

结果：退出码 0。

镜像检查：

```text
ID=sha256:93fd2a398f515d3b51466d253aa90c307b9b2ee4633a004de5d1687a73ac4c1a
SIZE=52557319
USER=agent
```

一次性容器内：

```text
uid=999(agent) gid=999(agent) groups=999(agent)
```

运行验证：

```text
HEALTH={"config_loaded":true,"demo_mode":true,"status":"ok","storage_ready":true}
HOME_STATUS=200
CSP=default-src 'self'; ...; frame-ancestors 'none'
```

验证容器已删除，没有遗留同名容器。Compose 使用临时测试 Secret 执行 `config --quiet`，退出码为 0。

## 7. 测试结果

分发契约：

```text
Ran 7 tests in 0.008s
OK
```

完整回归：

```text
Ran 205 tests in 17.548s
OK
```

`python scripts/verify.py` 退出码为 0，`git diff --check` 在最终收尾执行。

## 8. 尚未完成

- 远程 Python registry 或容器 registry 发布；
- GitLab CI 中的可重复 package/container job；
- 镜像 SBOM、签名和漏洞扫描；
- HTTPS 公开演示部署；
- commit、PR 与远程 CI 证据。
