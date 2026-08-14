# AI4SE 课程交付打包清单

更新日期：2026-08-14
适用项目：Personal AI Knowledge Agent（B 类应用项目）

## 一、在 SE Learning 并列提交的两个文件

### 1. 源码压缩包

建议文件名：

```text
Personal-AI-Knowledge-Agent-course-final.zip
```

压缩包应来自最终提交 commit，推荐在提交并推送完成后执行：

```powershell
git archive --format=zip --output Personal-AI-Knowledge-Agent-course-final.zip HEAD
```

该方式只打包 Git 已跟踪内容，不包含 `.git`、虚拟环境、本地数据库和未跟踪秘密。

### 2. `submission.jsonc`

必须保持文件名 `submission.jsonc`，与源码压缩包并列提交，不能放进源码压缩包。当前下载目录模板中的正确结构应为：

```jsonc
{
  "id": "241830179",
  "name": "崔杰",
  "repo_url": "https://github.com/smwy-cj/Personal-AI-Knowledge-Agent.git",
  "is_deployed": false,
  "deploy_release_url": "最终 GitHub Release 链接"
}
```

最终课程 Release 是：

```text
https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.1
```

`v0.1.0` 保留为首次发布的历史基线；不得移动或覆盖旧 tag。`submission.jsonc` 的 `deploy_release_url` 应填写上面的 `v0.1.1` 链接。

## 二、源码压缩包必须包含

### 课程核心文档

- `SPEC.md`；
- `SPEC_v2.md`；
- `PLAN.md`；
- `SPEC_PROCESS.md`；
- `REFLECTION.md`；
- `README.md`；
- `README_COURSE.md`；
- `AGENT_LOG.md` 及后续真实阶段日志；
- `LICENSE`。

### 完整源码与测试

- `src/`：应用源码；
- `tests/`：单元、集成、Web、安全和交付契约测试；
- `scripts/`：一键验收和秘密扫描；
- `evaluations/`：固定评测数据与配置；
- `course_demo/`：脱敏演示 Vault 和配置，但不含运行时数据库；
- `pyproject.toml`；
- `agent.config.example.json`。

### 分发与 CI

- `Dockerfile`；
- `Dockerfile.verify`；
- `Dockerfile.verify.dockerignore`；
- `.dockerignore`；
- `docker-compose.example.yml`；
- `.env.example`（只能包含假值/占位符）；
- `.github/workflows/`；
- `.gitlab-ci.yml`，并保留名为 `unit-test` 的 job；
- `render.yaml`；
- `RELEASE_NOTES_v0.1.0.md` 与 `RELEASE_NOTES_v0.1.1.md`。

### 课程证据

保留整个 `docs/` 目录，其中重点包括：

- `docs/DOCUMENTATION_INDEX.md`；
- `docs/PROJECT_STATUS.md`；
- `docs/course/ARCHITECTURE.md`；
- `docs/course/COLD_START_VALIDATION.md`；
- `docs/course/GITHUB_RELEASE_EVIDENCE.md`；
- `docs/course/CI_CD_EVIDENCE_v2.md`；
- `docs/course/CLEAN_MACHINE_VERIFICATION_v2.md`；
- `docs/course/SECRET_SCAN_EVIDENCE.md`；
- `docs/course/DEMO_GUIDE_v2.md`；
- `docs/course/DISTRIBUTION_AND_DEPLOYMENT.md`。

历史证据中出现旧测试数量或旧状态是正常的，应通过 `docs/DOCUMENTATION_INDEX.md` 判断其时间属性，不应在打包前删除或改写。

## 三、不要放入源码压缩包

- `.git/`：提交历史通过 GitHub 仓库链接查看；
- `.venv/`、`__pycache__/`、`.pytest_cache/`、覆盖率和检查器缓存；
- `build/`、`dist/`、`*.egg-info/`；
- `data/`、`course_demo/runtime/`、任何 `*.sqlite3` 或临时数据库；
- `.env`、`agent.config.json`、真实 API key、Cookie、Token 或个人 Vault；
- `secret-scan-report.json` 等本地临时报告；
- `submission.jsonc`：它必须在压缩包外并列提交；
- 下载目录中的草稿 `REFLECTION_完善草稿.md`：正式版本已经是仓库根目录的 `REFLECTION.md`；
- 本地 Docker 镜像层；Release 链接用于取得正式附件。

## 四、GitHub 侧应当保留

- 公开仓库链接；
- 完整 commit 历史；
- Draft PR #1 及后续真实 review/合并记录；
- GitHub Actions 最终通过记录；
- `v0.1.0` 历史 Release；
- 包含最终反思和文档的 `v0.1.1` Release。

## 五、打包前最终检查

```powershell
python scripts/verify.py
python scripts/scan_secrets.py --working-tree --git-history
git status --short
```

人工确认：

- `REFLECTION.md` 为 1500–2500 字并保留 AI 润色说明；
- `submission.jsonc` 的学号、姓名、仓库和 Release 链接正确；
- `is_deployed` 为 `false`，因为当前没有公开 WebUI；
- 源码压缩包能够解压，顶层文件齐全；
- Release 链接无需登录即可访问；
- 压缩包和 `submission.jsonc` 在 SE Learning 中并列出现。
