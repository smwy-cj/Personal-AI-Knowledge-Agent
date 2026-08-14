# 最终交付剩余文件清单 v3

盘点日期：2026-08-14。本文件在课程入口、最终架构和反思指南生成后创建，不修改旧版清单。

## 数量结论

离完整交付还缺 **4 个核心文件**：其中 **3 个依赖真实外部状态的证据文件**，以及 **1 个必须由学生本人撰写的反思文件**。

| 序号 | 文件 | 当前阻塞条件 |
|---:|---|---|
| 1 | `REFLECTION.md` | 必须由学生本人完成 1500–2500 字正文并核对真实性 |
| 2 | `docs/course/DEPLOYMENT_EVIDENCE.md` | 必须先取得并复验公开 HTTPS WebUI URL |
| 3 | `docs/course/PR_AND_REVIEW_EVIDENCE.md` | 必须先形成真实 commit、推送、PR/MR 和评审记录 |
| 4 | `docs/course/FINAL_ACCEPTANCE.md` | 只能在最终远程 CI、部署、评审和学生反思全部齐备后生成 |

## 本轮已完成

- `README_COURSE.md`；
- `REFLECTION_GUIDE.md`；
- `docs/course/ARCHITECTURE.md`；
- `AGENT_LOG_v11.md`。

## 文件之外的硬性外部状态

1. 整理当前变更为真实、可解释的多次 commit；
2. 推送到课程要求的远程仓库；
3. 创建 PR/MR 并保留 spec 合规与代码质量评审证据；
4. 让最终远程 GitLab pipeline 对最终提交保持 pass；
5. 发布可获取的容器/包，或按课程认可方式提供分发产物；
6. 部署并复验公开 HTTPS WebUI；
7. 学生本人完成反思和最终人工安全检查。

在这些事实发生前，剩余证据文件不应预先生成带有“已完成”结论的版本。

