# Personal AI Knowledge Agent — AI4SE 课程交付入口

本文件面向助教和首次使用者。截至 2026-08-14，源码、本地 WebUI、Docker/Python 包分发、GitHub Actions、凭据治理、自动测试和学生反思已经完成，并已发布 [`v0.1.0`](https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.0)。当前没有公开 WebUI；按照教师补充说明，提交采用 GitHub Release 路线并填写 `is_deployed=false`。最终人工评审仍待完成。

## 项目简介

Personal AI Knowledge Agent 是一个面向 Obsidian 用户的本地优先知识研究应用。它把零散 Markdown 笔记增量索引为可引用的知识库，支持关键词/向量混合检索，并用受治理的固定工作流完成“检索—摘要—记忆候选—人工审批—受控写回”。

它不是开放式自主智能体：当前计划由应用代码预定义，模型不能任意选择工具或路径。工程重点是让每一步可暂停、可验证、可恢复、可取消并留下隐私最小化记录。即使移除真实 LLM，核心调度、引用校验、记忆审批和写回机制仍可通过确定性 fake Provider 测试。

30 秒价值说明：用户不用把完整私人笔记上传到外部平台，就能在本机搜索带原文位置的证据、生成有引用的研究摘要，并在任何新记忆写回 Obsidian 前逐条批准或拒绝。

核心模块包括：

- Obsidian 摄取与可引用检索；
- 固定计划的 Research Workflow 与引用完整性验证；
- 记忆候选、人工审批和受控原子写回；
- 模型路由、预算、重试、限流和凭据解析；
- 任务状态、Checkpoint、租约、取消、观测和质量门禁；
- Flask/Jinja WebUI 与完整 CLI。

## 安装

### 源码安装

前提：Python 3.9–3.13、Git。推荐使用独立虚拟环境。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Linux/macOS 激活命令为 `source .venv/bin/activate`。安装后提供三个入口：`personal-ai-agent`、`personal-ai-agent-web` 和 `personal-ai-agent-demo`。

### Docker 安装

前提：Docker Engine 或 Docker Desktop。

```powershell
docker build -t personal-ai-knowledge-agent:course .
```

仓库提供可复现的镜像构建方式，但没有公开容器 registry。正式 GitHub Release 已包含源码归档、wheel、source distribution 和 SHA-256 校验文件；不要把本地容器镜像误写为 registry 发布物。

## 运行与演示

### 最短课程演示路径

以下方式使用仓库内脱敏样例、确定性 fake Provider，不需要付费 API key：

```powershell
$env:PERSONAL_AGENT_CONFIG = "course_demo/config.json"
$env:PERSONAL_AGENT_DEMO_MODE = "1"
$env:PERSONAL_AGENT_DEMO_DATA_ROOT = (Resolve-Path "course_demo").Path
personal-ai-agent-demo
```

浏览器打开 `http://127.0.0.1:8000/`，建议依次演示：

1. 首页确认“演示模式”和知识库状态；
2. 搜索 `memory approval`，查看文件与行号引用；
3. 在 Research 中提交 `How does the agent protect memory writeback?`；
4. 查看任务状态、摘要和引用；
5. 进入 Memory Review，明确批准或拒绝每个候选；
6. 查看 `course_demo/vault/Agent/Memory/` 中的受控写回结果。

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

更完整的演示步骤见 `docs/course/DEMO_GUIDE_v2.md`。公开演示 URL 尚未生成，当前只能声明本地 WebUI 已验证。

### 本地个人知识库

复制并编辑无秘密配置，不要把个人路径或密钥提交到仓库：

```powershell
Copy-Item course_demo/config.json agent.local.config.json
personal-ai-agent --config agent.local.config.json config-validate
personal-ai-agent --config agent.local.config.json sync
$env:PERSONAL_AGENT_CONFIG = (Resolve-Path agent.local.config.json).Path
personal-ai-agent-web
```

个人模式会读取你明确配置的 Vault。首次使用真实 Provider 前，请先按照下文通过系统密钥环录入凭据。

## 分发

### 单条 Docker 运行

```powershell
$secret = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
docker run --rm -p 127.0.0.1:8000:8000 -e PERSONAL_AGENT_WEB_SECRET=$secret personal-ai-knowledge-agent:course
```

容器默认以非 root 用户运行，内置健康检查，使用固定脱敏演示 Vault；端口只绑定本机。容器删除或平台重启后，未挂载的数据会消失。

### Docker Compose

```powershell
Copy-Item .env.example .env
# 将 .env 中的占位值替换为本机生成的长随机值；绝不提交 .env
docker compose -f docker-compose.example.yml up --build
```

Compose 使用只读根文件系统、去除 Linux capabilities、禁止提权，并把演示 runtime 放入命名卷。完整说明见 `docs/course/DISTRIBUTION_AND_DEPLOYMENT.md`。

### Python 包

```powershell
python -m pip install build
python -m build
```

可生成 wheel 和 source distribution。当前尚未发布到 PyPI；课程分发入口是 GitHub Release，Dockerfile 与本地可构建 Python 包用于复现和演示。

## 目录结构

```text
src/personal_ai_agent/       核心应用、工作流、存储、Provider、CLI
src/personal_ai_agent/web/   Flask 应用工厂、端口、模板和样式
tests/                       确定性单元/集成/交付契约测试
evaluations/                 版本化评测数据、样例 Vault 和基线
course_demo/                 无真实凭据的课程演示配置与知识库
scripts/                     一键验收与密钥扫描
docs/course/                 分阶段课程证据和操作指南
Dockerfile                   最小运行镜像
Dockerfile.verify            独立 Linux 干净环境验收镜像
.gitlab-ci.yml               unit-test、package、container、deploy 契约
render.yaml                  Render 免费 Web Service Blueprint
```

系统组件和数据流见 `docs/course/ARCHITECTURE.md`。

## 凭据与安全边界

### 安全录入、查看、更新、清除

源码运行时，首选操作系统密钥环：Windows Credential Manager、macOS Keychain 或 Linux Secret Service。录入命令使用隐藏输入，不接受命令行明文参数。

```powershell
personal-ai-agent --config agent.local.config.json credential-set PROVIDER_ID
personal-ai-agent --config agent.local.config.json credential-status PROVIDER_ID
personal-ai-agent --config agent.local.config.json credential-delete PROVIDER_ID
```

再次执行 `credential-set` 即为更新。状态只显示 `keyring`、`environment` 或 `none`，绝不回显明文、长度、前后缀或掩码值。

解析顺序是：系统密钥环优先；只有 Provider 配置显式声明 `credential_env` 时才读取相应环境变量。容器/云部署可用平台 Secret 注入环境变量，但进程环境可见，安全性低于合适的系统密钥环。`.env` 是本地明文便利方案，只允许留在受控机器并已被 Git 忽略。

### 明确安全边界

- 配置文件拒绝 API key 等秘密字段；远程带凭据请求必须使用 HTTPS；
- 日志与错误不记录 Prompt、证据正文、Provider 响应或凭据；
- Web 状态变更受 CSRF 保护，请求大小有限制，错误只返回安全信息和关联 ID；
- 公网 `demo_mode` 禁止真实 Provider 和凭据操作，只能访问固定脱敏数据；
- 本地个人模式没有多用户登录系统，默认只应绑定 `127.0.0.1`；不要直接暴露到局域网或公网；
- Memory 只能写入配置的受管目录，使用所有权标记、内容漂移检查和原子替换；
- 自动扫描覆盖当前工作区和 Git 历史中的高置信度令牌格式，但不能替代人工审查或独立熵扫描工具。

威胁模型和复验证据见 `SPEC.md`、`SPEC_v2.md`、`docs/course/WEB_SECURITY.md` 与 `docs/course/SECRET_SCAN_EVIDENCE.md`。

## 测试与验收

一键本地验收：

```powershell
python scripts/verify.py
```

该命令运行完整测试、编译检查、CLI 烟雾测试、样例 Vault 同步、成本/账单核对和质量基线流程。2026-08-14 的最新结果为：

```text
Ran 228 tests
OK
```

文档收口继续增加一致性测试，最终数量应以当前命令输出为准；228 是已发布 `v0.1.0` 的固定基线。

密钥扫描：

```powershell
python scripts/scan_secrets.py --working-tree --git-history
```

独立 Linux 干净环境验收：

```powershell
docker build -f Dockerfile.verify -t personal-ai-knowledge-agent:verification .
```

GitHub Actions 会先安装完整运行依赖，再执行同一验收入口和秘密扫描；Linux Python 3.9/3.11/3.13 与 Windows Python 3.11 均已通过。`.gitlab-ci.yml` 仍保留课程要求的 `unit-test`、package、container 和 deploy 契约，但当前仓库没有声称执行过 GitLab 远程 pipeline。

## 已知限制与未完成项

- 没有公开 HTTPS WebUI URL；教师确认的 Release 替代路线下应填写 `is_deployed=false`；
- 没有公开容器 registry 或 PyPI 地址，但已有可提交的 GitHub Release 分发链接；
- 当前存在 Draft PR #1，但还没有真实的人工 review/批准或合并证据；
- GitHub Actions 已通过；GitLab 配置只代表可审查契约，不代表真实 GitLab pipeline；
- `REFLECTION.md` 已由学生完整初稿整理形成，并在文末披露 AI 仅参与结构、语言和事实核对；
- 免费 Render 实例可能冷启动，文件系统可能重置，公开演示只适合脱敏样例；
- 当前 Research 使用固定五步计划，不提供开放式动态 Planner；
- 真实模型质量、费用和延迟依赖用户选择的兼容 Provider，离线测试不代表供应商 SLA；
- 项目未使用课程建议的 Superpowers，相关偏离必须在最终反思和过程材料中如实说明。

## 课程证据导航

- 规格与边界：`SPEC.md`、`SPEC_v2.md`
- 实现计划：`PLAN.md`
- 规格过程：`SPEC_PROCESS.md`、`docs/course/COLD_START_VALIDATION.md`
- 演示：`docs/course/DEMO_GUIDE_v2.md`
- 安全：`docs/course/WEB_SECURITY.md`、`docs/course/SECRET_SCAN_EVIDENCE.md`
- 分发与部署：`docs/course/DISTRIBUTION_AND_DEPLOYMENT.md`、`docs/course/RENDER_DEPLOYMENT_GUIDE.md`
- CI/CD：`docs/course/CI_CD_EVIDENCE.md`（历史 GitLab 配置快照）、`docs/course/CI_CD_EVIDENCE_v2.md`（当前 GitHub Actions 证据）
- Release：`docs/course/GITHUB_RELEASE_EVIDENCE.md`
- 干净环境：`docs/course/CLEAN_MACHINE_VERIFICATION.md`
- 阶段日志：`AGENT_LOG.md` 至 `AGENT_LOG_v12.md`

## 许可证与第三方依赖

项目采用仓库 `LICENSE` 所示许可证。运行时直接依赖 Flask、keyring 和 Waitress；它们各自适用其上游许可证。提交前应由学生再次核验锁定版本、许可证兼容性和最终仓库可见内容。
