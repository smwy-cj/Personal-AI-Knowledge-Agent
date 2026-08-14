# Personal AI Knowledge Agent

面向 Obsidian 的本地优先知识研究应用：增量摄取 Markdown，执行带来源定位的检索与研究，在任何长期记忆写回前要求人工逐项审批。

[GitHub Release v0.1.0](https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.0) · [课程验收入口](README_COURSE.md) · [架构说明](docs/course/ARCHITECTURE.md) · [完整文档索引](docs/DOCUMENTATION_INDEX.md)

## 为什么有人会使用它

个人知识库通常包含不适合直接交给第三方 SaaS 的笔记。本项目让用户在本机建立可搜索索引，得到带文件和行号的证据，生成有引用的研究摘要，并在新知识进入 Obsidian 前保留最终决定权。

项目不是用角色提示词包装的开放式多 Agent。当前 Research 采用固定且可验证的五步计划：

```text
retrieve → summarize → propose → persist → writeback
```

模型只参与受约束的摘要步骤；调度、状态、预算、重试、引用校验、记忆治理、审批和写回由项目自身实现。移除真实 LLM 后，这些机制仍能通过确定性 fake Provider 测试。

## 当前发布状态

- 版本：`v0.1.0`；
- Release commit：`9b13b1bf4dac37ef72b2e004b5af32440dd754aa`；
- Python：3.9–3.13；
- 运行依赖：Flask、keyring、Waitress；
- 自动验收：Release 基线 228 项；当前工作区加入文档一致性检查后为 232 项，全部通过；
- GitHub Actions：Linux Python 3.9/3.11/3.13 与 Windows Python 3.11 全部通过；
- 独立 Linux Docker 验证：通过；
- 当前工作区和完整 Git 历史高置信度秘密扫描：0 个发现；
- 分发：GitHub 自动源码包、wheel、source distribution 和 SHA-256 校验文件。

Release 是可获取的分发链接，不等于已经部署公开 WebUI。当前 `is_deployed` 应填写 `false`。

## 核心能力

### 知识摄取与检索

- Obsidian Markdown 增量同步、删除检测和稳定 Note/Chunk ID；
- Frontmatter、标题层级、标签、Wiki Link 和 1-based 行号；
- FTS5 关键词检索及确定性回退；
- Provider 版本化向量缓存、精确余弦检索和加权 RRF 混合排序；
- 每个结果保留 Vault、相对路径、Chunk、行号、内容哈希和命中方式。

### 受治理 Research Workflow

- 结构化 Task State、DAG 计划、显式状态机和预算；
- SQLite 快照、追加式 Checkpoint、执行租约、心跳、过期接管与取消；
- Evidence Pack 和 Citation Integrity Verifier；
- 结构化摘要 schema 与确定性引用渲染；
- 来源漂移、引用篡改、预算耗尽和租约丢失显式失败。

### 记忆与写回

- 从已验证摘要生成带来源的 Memory Candidate；
- 敏感、重复和同主题冲突检查；
- 任务在 `WAITING_USER` 暂停，所有候选必须批准或拒绝；
- 只持久化批准内容；
- 写回限制在 Vault 内受管目录，使用安全文件名、所有权标记、原子替换、收据和漂移检测；
- 写回后重新增量索引。

### Provider 治理与观测

- OpenAI-compatible Chat Completions 与 Embeddings adapter；
- 能力、上下文、成本和隐私级别路由；
- HTTPS、超时、有界回退、指数退避、`Retry-After` 和 Embedding 413 拆批；
- SQLite 跨进程请求/Token/并发限流、共享冷却和 Usage 校正；
- 隐私最小化事件、成本报告、供应商账单差异核对和保留策略；
- 检索、摘要引用、记忆治理和运行指标的版本化质量门禁。

### CLI 与 WebUI

- CLI 覆盖配置、同步、检索、Research、任务、记忆、评测、成本和运维；
- Flask/Jinja/Waitress WebUI 覆盖首页、搜索、Research、任务详情、取消和 Memory Review；
- Web 路由只依赖 `WebApplicationPort`，不直接访问 Vault、Repository 或 Provider；
- CSRF、请求大小限制、安全响应头、Cookie 策略和错误脱敏；
- 无付费 key 的脱敏课程 demo mode。

## 快速开始

### 方式一：GitHub Release

打开 [v0.1.0 Release](https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.0)，可下载：

- `personal_ai_knowledge_agent-0.1.0-py3-none-any.whl`；
- `personal_ai_knowledge_agent-0.1.0.tar.gz`；
- `SHA256SUMS.txt`；
- GitHub 自动生成的完整 Source code zip/tar.gz。

安装 wheel：

```powershell
python -m pip install .\personal_ai_knowledge_agent-0.1.0-py3-none-any.whl
personal-ai-agent --help
personal-ai-agent-web --help
```

### 方式二：源码安装

```powershell
git clone https://github.com/smwy-cj/Personal-AI-Knowledge-Agent.git
cd Personal-AI-Knowledge-Agent
git switch --detach v0.1.0
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Linux/macOS 激活命令为 `source .venv/bin/activate`。

## 无 key 本地演示

仓库的 `course_demo/` 只包含脱敏样例和确定性 fake Provider：

```powershell
$env:PERSONAL_AGENT_CONFIG = "course_demo/config.json"
$env:PERSONAL_AGENT_DEMO_MODE = "1"
$env:PERSONAL_AGENT_DEMO_DATA_ROOT = (Resolve-Path "course_demo").Path
$env:PERSONAL_AGENT_WEB_SECRET = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
personal-ai-agent-demo
```

打开 `http://127.0.0.1:8000/`，依次演示搜索、Research、任务详情、Memory Review 和受控写回。健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

详细脚本见 [课程演示指南](docs/course/DEMO_GUIDE_v2.md)。

## Docker 分发

```powershell
docker build -t personal-ai-knowledge-agent:course .
$secret = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
docker run --rm -p 127.0.0.1:8000:8000 -e PERSONAL_AGENT_WEB_SECRET=$secret personal-ai-knowledge-agent:course
```

镜像以非 root 用户运行，包含健康检查和固定脱敏 demo。不要将容器端口绑定到公网接口。

Compose：

```powershell
Copy-Item .env.example .env
# 替换 .env 中的随机 Web secret；不要提交 .env
docker compose -f docker-compose.example.yml up --build
```

## 个人 Vault 与凭据

创建不含秘密的本地配置，设置 Vault 和独立数据目录：

```powershell
Copy-Item course_demo/config.json agent.local.config.json
personal-ai-agent --config agent.local.config.json config-validate
personal-ai-agent --config agent.local.config.json sync
personal-ai-agent --config agent.local.config.json search "memory governance" --limit 5
```

真实 Provider 凭据首选 OS keyring。录入使用隐藏输入，不接受命令行明文：

```powershell
personal-ai-agent --config agent.local.config.json credential-set PROVIDER_ID
personal-ai-agent --config agent.local.config.json credential-status PROVIDER_ID
personal-ai-agent --config agent.local.config.json credential-delete PROVIDER_ID
```

再次执行 `credential-set` 即更新。状态只返回来源和是否已配置，不显示秘密、掩码、长度、前后缀。

解析顺序：OS keyring 优先；只有配置显式声明 `credential_env` 时才使用环境变量后备。`.env` 是明文文件，只适合受控本机便利配置且必须保持未跟踪。

## 安全边界

- 配置拒绝 token/password/secret/API key 等字段；
- 带凭据的远程请求必须使用 HTTPS；
- 日志与错误不记录 Prompt、Evidence、Provider 正文或凭据；
- 本地个人 WebUI 没有多用户身份系统，只应监听 `127.0.0.1`；
- 公开 demo mode 禁止真实 Provider 和凭据操作，只允许固定脱敏数据与临时写回；
- Memory 只能写入配置的受管目录，任何路径越界或内容漂移均拒绝；
- 秘密扫描面向高置信度已知格式，不能替代人工审查和独立熵扫描。

完整威胁模型见 [SPEC](SPEC.md) 与 [Web 安全说明](docs/course/WEB_SECURITY.md)。

## 测试与质量

```powershell
python scripts/verify.py
python scripts/scan_secrets.py --working-tree --git-history
```

独立 Linux 复验：

```powershell
docker build -f Dockerfile.verify -t personal-ai-knowledge-agent:verification .
```

一键验收覆盖 228 项单元/集成/契约测试、源码编译、安装后 CLI、固定 Vault 同步、成本/账单核对、质量基线和历史比较。GitHub Actions 在四个平台矩阵上执行同一验收并先扫描工作树。

## 项目结构

```text
src/personal_ai_agent/       运行时、工作流、存储、Provider 与 CLI
src/personal_ai_agent/web/   Flask 应用工厂、端口、模板和样式
tests/                       单元、集成、安全和交付契约测试
evaluations/                 评测数据、基线和脱敏 Vault fixture
course_demo/                 无真实凭据的课程演示配置与 Vault
scripts/                     一键验收和秘密扫描
docs/                        架构、状态、计划与课程证据
Dockerfile                   运行镜像
Dockerfile.verify            干净 Linux 验证镜像
.github/workflows/ci.yml     GitHub Actions 多平台验收
.gitlab-ci.yml               课程要求的 GitLab CI 配置契约
render.yaml                  可选 Render demo Blueprint
```

## 文档入口

- [完整文档索引](docs/DOCUMENTATION_INDEX.md)
- [课程版 README](README_COURSE.md)
- [最终架构](docs/course/ARCHITECTURE.md)
- [项目状态](docs/PROJECT_STATUS.md)
- [实施计划](docs/IMPLEMENTATION_PLAN.md)
- [规格与澄清](SPEC.md)、[SPEC v2](SPEC_v2.md)
- [课程任务计划](PLAN.md)
- [GitHub Release 证据](docs/course/GITHUB_RELEASE_EVIDENCE.md)
- [分发与部署](docs/course/DISTRIBUTION_AND_DEPLOYMENT.md)
- [凭据 CLI](docs/course/CREDENTIAL_CLI_GUIDE.md)
- [演示指南](docs/course/DEMO_GUIDE_v2.md)

## 已知限制

- Research 使用固定计划，不提供开放式动态 Planner；
- SQLite 精确向量扫描面向个人规模，不是大规模 ANN 服务；
- 同步 HTTP 请求不能安全强杀，只能依赖 Provider timeout 并在边界响应取消；
- 当前没有多用户身份、租户隔离或公开个人模式；
- demo 数据和免费平台文件系统可能在重启后重置；
- 静态价格只能估算费用，不能替代供应商正式账单；
- `REFLECTION.md` 已基于学生本人初稿整理完成，并在文末披露 AI 辅助范围。

## 许可证

项目采用 [MIT License](LICENSE)。直接运行依赖 Flask、keyring 和 Waitress，各自适用其上游许可证。
