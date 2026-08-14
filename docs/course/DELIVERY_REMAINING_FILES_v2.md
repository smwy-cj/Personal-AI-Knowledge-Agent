# 最终交付剩余文件清单 v2

盘点日期：2026-08-14。此版本在干净环境验证与密钥扫描完成后生成，不修改旧版盘点。

## 数量结论

离完整交付还缺 **7 个核心文件**：其中 **6 个项目流程文件**，以及 **1 个必须由学生本人撰写的反思文件**。

| 序号 | 文件 | 形成条件 |
|---:|---|---|
| 1 | `README_COURSE.md` | 汇总安装、运行、演示、安全、部署和验收入口 |
| 2 | `REFLECTION_GUIDE.md` | 提供真实项目事实与学生写作提纲 |
| 3 | `REFLECTION.md` | 学生本人根据课程要求撰写，不能由 AI 代写 |
| 4 | `docs/course/DEPLOYMENT_EVIDENCE.md` | 获得并复验公开 HTTPS WebUI URL 后生成 |
| 5 | `docs/course/ARCHITECTURE.md` | 汇总最终组件、数据流、信任边界和部署结构 |
| 6 | `docs/course/PR_AND_REVIEW_EVIDENCE.md` | 形成真实 commit、PR/MR 和评审记录后生成 |
| 7 | `docs/course/FINAL_ACCEPTANCE.md` | 上述材料、远程 CI、部署与学生反思均齐备后生成 |

## 已从旧清单移除

- `docs/course/CLEAN_MACHINE_VERIFICATION.md`：已完成；
- `docs/course/SECRET_SCAN_EVIDENCE.md`：已完成；
- `AGENT_LOG_v10.md`：本阶段新建，不再计为缺失。

## 文件之外仍未完成的外部状态

- 将最终变更整理为真实提交并推送到课程要求的远程仓库；
- 创建 PR/MR，保留评审或自审证据；
- 让最终远程 CI 对最终提交通过；
- 部署公开 HTTPS WebUI 并复验健康检查与主要演示路径；
- 学生本人完成反思并进行最终人工检查。

因此下一阶段应优先生成助教入口文档和架构文档；部署证据、评审证据与最终验收只能在对应外部事实真实存在后完成。

