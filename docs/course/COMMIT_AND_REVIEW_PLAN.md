# Commit、PR/MR 与评审执行方案

> 执行更新（2026-08-14）：分阶段 commit 已完成并推送到 `agent/iteration-18-delivery-baseline`，Draft PR #1 已创建，`v0.1.0` Release 已发布。当前尚无真实人工 review/批准/合并证据；相关事件发生前不得提前填写。Release 事实见 `GITHUB_RELEASE_EVIDENCE.md`。

日期：2026-08-14  
当前分支：`agent/iteration-18-delivery-baseline`  
当前基线：`8b102d0`

## 1. 审计结论

当前工作区包含 6 个已修改文件和 87 个未跟踪文件，覆盖凭据、WebUI、分发、CI、部署、测试和课程文档。把这些变更压成一个提交会违反课程对完整历史和可评审变更的要求，也会让回滚与问题定位困难。

当前 `origin` 为 GitHub：

```text
https://github.com/smwy-cj/Personal-AI-Knowledge-Agent.git
```

课程最终要求通过 NJU Git 仓库交付并提供 `.gitlab-ci.yml` 最后一次 pass 记录。因此需要学生提供课程仓库 URL，并决定：

- 保留 GitHub 为 `origin`，把课程仓库新增为 `nju`；或
- 把课程仓库设为新的 `origin`，将 GitHub 改名为 `github`。

推荐第一种，避免破坏已有 GitHub 引用。任何远程修改、提交和推送都应在学生明确授权后执行。

## 2. 提交原则

- 每个提交只表达一个可审查目的；
- 实现与其测试放在同一提交；
- 提交前运行该组聚焦测试，提交后运行完整验收；
- 不提交 `.env`、SQLite、个人 Vault、扫描报告、构建产物或缓存；
- 不伪造每个历史 task 使用了独立 worktree；只能说明本次整理出的实际边界；
- commit message 标注 AI 辅助范围，PR 描述列出学生人工复核和修改；
- 不通过修改旧日志来制造先前不存在的过程证据。

## 3. 推荐提交序列

### Commit 1：冻结课程规格与交付计划

建议消息：

```text
docs(course): define delivery specification and implementation plan
```

包含：

```text
SPEC.md
SPEC_v2.md
SPEC_PROCESS.md
PLAN.md
COURSE_COMPLETION_PLAN.md
docs/course/COLD_START_VALIDATION.md
```

复核重点：Agent 定位是否夸大、Superpowers 偏离是否真实、冷启动验证是否只记录已发生事实。

### Commit 2：实现安全凭据生命周期

建议消息：

```text
feat(credentials): add keyring lifecycle and provider resolution
```

包含：

```text
pyproject.toml
src/personal_ai_agent/credentials.py
src/personal_ai_agent/application.py
src/personal_ai_agent/cli.py
src/personal_ai_agent/provider_adapters.py
tests/test_credentials.py
tests/test_credential_cli.py
tests/test_credential_resolution.py
docs/course/CREDENTIAL_CLI_GUIDE.md
docs/course/T4_CREDENTIAL_STORE_EVIDENCE.md
docs/course/T5_CREDENTIAL_LIFECYCLE_EVIDENCE.md
```

注意：`pyproject.toml` 同时包含 Web 依赖和入口，若要保持提交完全原子，需要用交互式暂存拆分其 hunks，或把依赖配置移到下一提交。执行者必须在暂存后检查 `git diff --cached`。

聚焦验证：

```powershell
python -m unittest tests.test_credentials tests.test_credential_cli tests.test_credential_resolution -v
```

### Commit 3：交付 WebUI 搜索与研究审批闭环

建议消息：

```text
feat(web): add secure search research and memory review UI
```

包含：

```text
src/personal_ai_agent/web/
src/personal_ai_agent/web_server.py
src/personal_ai_agent/container_entrypoint.py
course_demo/
tests/test_web_foundation.py
tests/test_web_search.py
tests/test_web_research.py
tests/test_web_memory.py
tests/test_web_security.py
docs/course/WEB_ARCHITECTURE.md
docs/course/WEB_SEARCH_ACCEPTANCE.md
docs/course/WEB_SECURITY.md
docs/course/DEMO_GUIDE.md
docs/course/DEMO_GUIDE_v2.md
docs/course/T6_WEB_FOUNDATION_EVIDENCE.md
docs/course/T7_WEB_SEARCH_EVIDENCE.md
docs/course/T8_RESEARCH_MEMORY_EVIDENCE.md
docs/course/T9_WEB_SECURITY_EVIDENCE.md
```

聚焦验证：

```powershell
python -m unittest tests.test_web_foundation tests.test_web_search tests.test_web_research tests.test_web_memory tests.test_web_security -v
```

### Commit 4：增加可复现分发、CI 与部署配置

建议消息：

```text
build(delivery): add package container CI and Render deployment
```

包含：

```text
.dockerignore
.env.example
.gitignore
.gitlab-ci.yml
Dockerfile
docker-compose.example.yml
render.yaml
LICENSE
tests/test_distribution_contract.py
tests/test_gitlab_ci_contract.py
tests/test_render_deployment_contract.py
docs/course/DISTRIBUTION_AND_DEPLOYMENT.md
docs/course/CI_CD_EVIDENCE.md
docs/course/RENDER_DEPLOYMENT_GUIDE.md
docs/course/T10_DISTRIBUTION_EVIDENCE.md
docs/course/T12_RENDER_DEPLOYMENT_READINESS.md
```

聚焦验证：

```powershell
python -m unittest tests.test_distribution_contract tests.test_gitlab_ci_contract tests.test_render_deployment_contract -v
docker build -t personal-ai-knowledge-agent:course .
```

### Commit 5：增加秘密扫描与干净环境验收

建议消息：

```text
test(delivery): add secret scanning and clean Linux verification
```

包含：

```text
scripts/__init__.py
scripts/scan_secrets.py
scripts/verify.py
tests/__init__.py
tests/test_secret_scanner.py
tests/test_clean_delivery_contract.py
Dockerfile.verify
docs/course/SECRET_SCAN_EVIDENCE.md
docs/course/CLEAN_MACHINE_VERIFICATION.md
```

注意：当前 `Dockerfile.verify` 还引用下一提交的课程文档。为了让 Commit 5 独立通过，可在提交 5 暂时只复制现存 Render 指南，并在 Commit 6 加入课程文档 COPY；或者把 `Dockerfile.verify` 放到 Commit 6。推荐后者。

聚焦验证：

```powershell
python -m unittest tests.test_secret_scanner tests.test_clean_delivery_contract -v
python scripts/scan_secrets.py --working-tree --git-history
```

### Commit 6：完成助教入口和最终课程材料

建议消息：

```text
docs(course): add handoff architecture and verified evidence
```

包含：

```text
README_COURSE.md
REFLECTION_GUIDE.md
docs/course/ARCHITECTURE.md
docs/course/TEST_EVIDENCE.md
docs/course/T14_HANDOFF_EVIDENCE.md
docs/course/DELIVERY_REMAINING_FILES*.md
tests/test_course_handoff_contract.py
Dockerfile.verify
AGENT_LOG*.md
```

聚焦验证：

```powershell
python -m unittest tests.test_course_handoff_contract -v
docker build -f Dockerfile.verify -t personal-ai-knowledge-agent:verification .
```

### Commit 7：提交学生反思与真实外部证据

只能在对应事实产生后创建。建议消息：

```text
docs(course): add reflection and final delivery evidence
```

候选文件：

```text
REFLECTION.md
docs/course/DEPLOYMENT_EVIDENCE.md
docs/course/PR_AND_REVIEW_EVIDENCE.md
docs/course/FINAL_ACCEPTANCE.md
```

该提交不得由当前准备阶段提前制造。

## 4. 每次提交的安全执行模板

以下是操作步骤，不代表已执行：

```powershell
git status --short
git add -- <本提交的明确文件列表>
git diff --cached --stat
git diff --cached
python scripts/scan_secrets.py --working-tree --git-history
python scripts/verify.py
git commit -m "<message>"
```

不要使用 `git add .`，因为当前工作区范围很大。若暂存内容不符合边界，应只取消对应文件的暂存，不能丢弃工作区内容。

## 5. 两阶段评审清单

### 阶段一：规格合规

- 是否满足对应 SPEC/PLAN 的输入、行为、输出、错误和安全边界？
- 是否把固定工作流误称为开放式自主 Agent？
- 是否存在未授权的文件、网络或 Provider 调用？
- 是否存在无法由测试或实际命令支持的完成声明？
- 是否遗漏课程要求的凭据、分发、WebUI 或 CI 行为？

### 阶段二：代码质量

- 状态、错误、重试、预算和并发边界是否明确？
- 凭据、Prompt、Evidence、绝对路径是否可能进入输出或日志？
- 测试是否验证行为而非过度绑定实现文字？
- 是否有平台依赖、临时目录泄漏或非确定性测试？
- 公开 demo mode 与本地个人模式是否严格隔离？
- 文档命令是否与当前代码、端口和文件名一致？

每个发现记录文件、位置、严重级别、处理决定和复验结果。没有实际评审记录前，不得生成“评审已通过”的证据。

## 6. PR/MR 组织建议

理想历史是每个独立功能对应 PR，但当前大量变更已在同一工作区形成，不能倒推并虚构多个并行 worktree。可采用一个诚实的交付 PR，内部保留上述多个原子提交，并在描述中说明：

- 当前 PR 是课程收口分支；
- 早期未完整采用每任务 PR，这是已知过程偏离；
- 提交序列按真实功能边界整理；
- 学生完成最终逐提交和整体评审；
- 所有本地验证、远程 CI、部署和未完成项分别列出。

PR 目标分支应由学生根据课程仓库规则确认，不能默认直接合入 `main`。
