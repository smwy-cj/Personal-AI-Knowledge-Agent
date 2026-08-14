# 外部交付与证据采集操作手册

> 执行更新（2026-08-14）：GitHub 推送、Draft PR、远程 Actions 与最终 `v0.1.1` Release 已完成；`v0.1.0` 保留为历史版本。公开 WebUI 未部署；课程提交采用教师确认的 Release 路线。本文其余命令保留为复验/后续部署手册，不代表所有可选平台步骤都已执行。

日期：2026-08-14

本文只描述将当前本地成果转化为真实课程交付所需的操作和证据，不表示这些操作已经执行。

## 1. 需要学生提供或确认的信息

开始外部操作前必须确认：

1. NJU Git/GitLab 仓库 HTTPS 或 SSH URL；
2. 课程要求的目标分支名和是否禁止直接 push；
3. 是否保留现有 GitHub `origin`；
4. PR/MR 的实际评审人或允许的自审方式；
5. Render 账户是否已连接课程仓库，以及允许创建免费 Web Service；
6. 容器 registry 的选择和命名空间；
7. 学生已经完成或计划完成 `REFLECTION.md` 的时间。

这些信息会改变远程状态和提交组织，不能由智能体猜测。

## 2. 远程仓库准备

推荐保留 GitHub `origin` 并新增课程远程：

```powershell
git remote add nju <NJU_GIT_URL>
git remote -v
git ls-remote nju
```

首次推送前应再次运行秘密扫描和完整验收。推送应使用明确分支，不使用强制推送：

```powershell
git push -u nju agent/iteration-18-delivery-baseline
```

上述命令只有在学生确认 URL、分支和授权推送后才能执行。

## 3. PR/MR 与评审证据

创建 PR/MR 时使用仓库 `.github/pull_request_template.md` 的字段；GitLab 可复制同一内容。记录：

- PR/MR URL 与编号；
- source/target branch；
- head commit SHA；
- 创建时间；
- 规格合规评审人、发现和处理；
- 代码质量评审人、发现和处理；
- 最终批准或合并状态。

截图不是唯一证据，优先保留可访问 URL、commit SHA 和文字化评审结论。个人信息或平台 token 必须从截图和日志中遮除。

## 4. 远程 CI

当前 `.gitlab-ci.yml` 要求：

- `unit-test`：安装包、秘密扫描、一键验收和 CLI/Web 帮助；
- `package-build`：生成 wheel 与 source distribution；
- `container-build`：用 Kaniko 无特权构建镜像；
- `deploy-demo`：仅受保护 tag 手动触发，并验证公开 `/health`。

证据必须对应最终提交或最终 tag：

- pipeline URL、ID、commit SHA、触发时间；
- 四个 job 的状态；
- `unit-test` 的测试数量；
- package artifact 名称；
- container build 摘要或日志；
- 最后一次 pipeline 的整体 pass 状态。

若课程平台不允许 Kaniko 或 artifact 设置，应新建修订配置和证据，不能把本地契约测试当作远程 pass。

## 5. Render WebUI 部署

仓库已有 `render.yaml`。实际操作前确认服务只使用：

- `course_demo` 脱敏 Vault；
- `PERSONAL_AGENT_DEMO_MODE=1`；
- `PERSONAL_AGENT_HTTPS=1`；
- 平台生成的 `PERSONAL_AGENT_WEB_SECRET`；
- fake Provider，无付费 API key。

部署后记录服务 URL、部署 commit SHA 和时间，并至少验证：

```powershell
$demoUrl = "https://实际服务地址"
Invoke-RestMethod "$demoUrl/health"
Invoke-WebRequest -UseBasicParsing "$demoUrl/"
```

随后人工走通首页、搜索、Research、任务详情、Memory Review，并确认页面明确标注 demo mode。不要把个人 Vault 上传到平台。

## 6. 分发产物

课程要求别人能获取并运行。至少保留一种真实可获取方式：

- 在远程 CI 提供 wheel/sdist artifact；或
- 把容器镜像推送到公开 registry，并记录不可变 digest。

仅存在 Dockerfile 属于“可构建说明”，不等于公开分发已经完成。发布证据记录地址、版本/tag、digest、目标架构、发布时间和一次全新机器拉取/运行结果。

## 7. 学生反思

学生根据 `REFLECTION_GUIDE.md` 本人完成 `REFLECTION.md`。加入仓库前检查：

- 1500–2500 字；
- 如实披露未使用 Superpowers；
- 不虚构 subagent、TDD、PR、CI 或部署经历；
- 不包含 API key、私人路径或个人 Vault 正文；
- 如有 AI 语言润色，按课程要求标注范围。

## 8. 最终证据文件的生成条件

- `docs/course/PR_AND_REVIEW_EVIDENCE.md`：PR/MR 和两阶段评审真实存在后；
- `docs/course/DEPLOYMENT_EVIDENCE.md`：公开 HTTPS URL 经自动与人工复验后；
- `docs/course/FINAL_ACCEPTANCE.md`：反思、最终提交、远程 CI、分发、PR/MR 和部署全部齐备后。

每个证据文件都应引用真实 URL、SHA、时间和验证结果，并明确免费平台冷启动、临时文件系统等限制。
