# 文档索引与维护规则

更新日期：2026-08-14
当前发布：[`v0.1.0`](https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.0)

仓库包含活文档、规格版本、阶段证据、历史日志和测试语料。它们用途不同，不能把历史快照机械改写成当前状态，也不能为了统一措辞修改测试语料。

## 当前权威入口

| 文档 | 用途 |
|---|---|
| `README.md` | 用户、开发者和 GitHub 的统一主入口 |
| `README_COURSE.md` | 助教验收、提交与课程约束入口 |
| `docs/course/ARCHITECTURE.md` | 当前组件、数据流、持久化、信任边界和部署架构 |
| `docs/PROJECT_STATUS.md` | 当前功能、发布、验证和缺口状态 |
| `SPEC.md` + `SPEC_v2.md` | 已接受规格及后续澄清；冲突主题以 v2 为准 |
| `PLAN.md` | 课程交付任务及真实执行状态 |
| `docs/IMPLEMENTATION_PLAN.md` | 长期产品/工程路线，不等于课程完成清单 |
| `RELEASE_NOTES_v0.1.0.md` | 当前 Release 资产、能力和限制 |
| `docs/course/GITHUB_RELEASE_EVIDENCE.md` | Release、tag、CI 和附件校验事实 |

## 操作指南

- `docs/course/DEMO_GUIDE_v2.md`：当前推荐演示路径；`DEMO_GUIDE.md` 为旧版。
- `docs/course/CREDENTIAL_CLI_GUIDE.md`：凭据录入、查看状态、更新和删除。
- `docs/course/DISTRIBUTION_AND_DEPLOYMENT.md`：Python、Docker 与 Compose。
- `docs/course/RENDER_DEPLOYMENT_GUIDE.md`：可选公开 WebUI 部署；当前 Release 方案不代表已部署。
- `docs/course/WEB_SECURITY.md`：Web 威胁和控制。
- `docs/course/WEB_ARCHITECTURE.md`：Web 子系统详细端口与路由结构。
- `docs/course/WEB_SEARCH_ACCEPTANCE.md`：搜索 UI 验收。

## 课程过程与计划

- `COURSE_COMPLETION_PLAN.md`：课程差距分析和收口路线，属于计划基线；
- `SPEC_PROCESS.md`：规格形成、冷启动反馈与决策；
- `docs/course/COLD_START_VALIDATION.md`：陌生智能体冷启动证据及限制；
- `docs/course/COMMIT_AND_REVIEW_PLAN.md`：提交整理方案，主要步骤已经执行；
- `docs/course/EXTERNAL_DELIVERY_RUNBOOK.md`：外部发布操作手册，Release 部分已执行；
- `docs/course/CI_CD_EVIDENCE_v2.md`：当前 GitHub Actions 远程通过证据；
- `docs/course/CLEAN_MACHINE_VERIFICATION_v2.md`：当前 232 项干净 Linux 验收；
- `docs/course/DELIVERY_REMAINING_FILES_v4.md`：当前最终剩余文件清单；
- `docs/course/SUBMISSION_PACKAGE_CHECKLIST.md`：SE Learning 压缩包、外置 `submission.jsonc` 与排除项清单；
- `.github/pull_request_template.md`：PR/MR 评审字段模板；
- `REFLECTION.md`：由学生初稿整理形成的正式反思；文末披露 AI 仅进行结构、语言和事实核对。
- `REFLECTION_GUIDE.md`：反思要求和提交前自查指南，保留用于验收核对。

## 阶段证据与历史快照

以下文件记录特定时点的真实命令、测试数量、失败和判断。旧测试数量或“尚未执行”描述在其时间点可能正确，不应改写为当前结论：

- `docs/course/TEST_EVIDENCE.md`；
- `docs/course/T4_CREDENTIAL_STORE_EVIDENCE.md`；
- `docs/course/T5_CREDENTIAL_LIFECYCLE_EVIDENCE.md`；
- `docs/course/T6_WEB_FOUNDATION_EVIDENCE.md`；
- `docs/course/T7_WEB_SEARCH_EVIDENCE.md`；
- `docs/course/T8_RESEARCH_MEMORY_EVIDENCE.md`；
- `docs/course/T9_WEB_SECURITY_EVIDENCE.md`；
- `docs/course/T10_DISTRIBUTION_EVIDENCE.md`；
- `docs/course/CI_CD_EVIDENCE.md`（T11 GitLab 配置快照）；
- `docs/course/T12_RENDER_DEPLOYMENT_READINESS.md`；
- `docs/course/CLEAN_MACHINE_VERIFICATION.md`；
- `docs/course/SECRET_SCAN_EVIDENCE.md`；
- `docs/course/T14_HANDOFF_EVIDENCE.md`；
- `docs/course/DELIVERY_REMAINING_FILES.md`、`v2`、`v3`（逐阶段盘点）；
- `AGENT_LOG.md` 至 `AGENT_LOG_v12.md`；`AGENT_LOG_v13.md` 为当前文档收口记录。

当前结论必须看本索引、主 README、项目状态、Release 证据和最新剩余清单，而不是从某个旧快照单独推断。

## 架构研究材料

- `Personal_AI_Knowledge_Agent_Agent_Architecture_Design.md`：早期总体设计；
- `Personal_AI_Knowledge_Agent_架构深度评估与工程化建议.md`：早期深度评估与演进建议。

这些文件用于解释设计来源，不覆盖当前实现事实；当前架构以 `docs/course/ARCHITECTURE.md` 为准。

## 测试语料

以下 Markdown 是产品和评测输入，不是说明文档：

- `course_demo/vault/Architecture.md`、`Memory.md`、`Research.md`；
- `evaluations/fixtures/vault/Architecture.md`、`Memory.md`、`Research.md`。

修改测试语料会改变检索结果、引用行号和基线，因此只允许在同步更新数据集与期望值时修改。

## 维护规则

1. 当前事实只更新活文档；历史证据保持原时间点内容。
2. 架构或安全边界改变时，同时更新 SPEC 修订、架构、README 和相应契约测试。
3. 测试数量以最新 `python scripts/verify.py` 输出为准。
4. Release/CI/部署只记录真实 URL、tag、SHA 和远程状态。
5. 新版指南使用版本号或明确替代关系，避免旧文件被误当作最新入口。
6. `REFLECTION.md` 必须源自学生本人观点和初稿；当前正文已在文末标注 AI 的整理与事实核对范围。
