# 最终交付剩余文件清单

盘点日期：2026-08-14。依据课程通用要求、B 类项目要求与当前仓库实际文件，不把远程 URL、commit、PR 或 CI 状态当作文件数量。

## 1. 数量结论

从当前状态到“具备最终提交文档集合”，还需要新增 **9 个由项目流程产生的文件**，以及 **1 个必须由学生本人撰写的 `REFLECTION.md`**。

合计缺少 **10 个文件**。

其中 T11 本轮新建的 `docs/course/CI_CD_EVIDENCE.md` 已存在，因此不再计入缺失数；远程 GitLab pass 后还应新建它的 v2 版本，这属于证据更新，暂不重复计入核心文件数。

## 2. 九个项目文件

| 序号 | 文件 | 产生阶段 | 当前缺失原因 |
|---:|---|---|---|
| 1 | `README_COURSE.md` | T14 | 需要汇总最终安装、运行、分发、安全、部署 URL 和验收路径 |
| 2 | `REFLECTION_GUIDE.md` | T14 | 只能提供提纲与真实事实素材，不能代写学生反思 |
| 3 | `docs/course/DEPLOYMENT_EVIDENCE.md` | T12 | 尚无公开 HTTPS WebUI URL |
| 4 | `docs/course/CLEAN_MACHINE_VERIFICATION.md` | T13 | 尚未在独立干净环境完成复验 |
| 5 | `docs/course/SECRET_SCAN_EVIDENCE.md` | T13 | 当前树与历史的正式秘密扫描尚未执行/记录 |
| 6 | `docs/course/ARCHITECTURE.md` | T14 | 需要面向助教汇总最终组件、数据流和部署边界 |
| 7 | `docs/course/PR_AND_REVIEW_EVIDENCE.md` | T14 | 当前改动尚无 commit、PR/MR 与两阶段评审证据 |
| 8 | `docs/course/FINAL_ACCEPTANCE.md` | T15 | 只能在最终 commit、CI、部署、反思全部齐备后生成 |
| 9 | `AGENT_LOG_v8.md` 或下一版本 | T11 收尾 | 记录本轮 CI 判断、偏离与剩余文件盘点 |

本轮会创建第 9 项，因此在 T11 完成后，实际继续缺失的是 **8 个项目文件 + 1 个学生文件 = 9 个文件**。

## 3. 一个学生本人文件

`REFLECTION.md`，1500–2500 字，必须由学生本人撰写。AI 可以：

- 提供结构提纲；
- 列出本项目真实事件、失败和人工决策；
- 检查是否覆盖课程问题；
- 在学生明确标注 AI 润色的前提下做语言润色。

AI 不应代写完整反思。该文件在学生完成前始终计为缺失。

## 4. 不是“文件”，但仍是硬性阻塞

即使补齐上述文件，也必须完成以下外部状态：

1. 将代码放入课程要求的 NJU Git 仓库；
2. 建立真实的多 commit / MR 或 PR 历史；
3. 最后一次 GitLab pipeline 对最终 commit 为 pass；
4. 发布容器镜像到公开 registry，或按课程接受的分发渠道提供可获取产物；
5. 提供截止前可访问的 HTTPS WebUI URL；
6. 学生本人完成最终代码、文档和安全检查；
7. 根据用户要求，Superpowers 不使用的偏离需要在最终过程材料中继续如实说明。

## 5. 推荐完成顺序

1. T12：选择部署平台并产生 URL、`DEPLOYMENT_EVIDENCE.md`；
2. 建立 GitLab remote、commit/MR、真实 pipeline，随后新建 `CI_CD_EVIDENCE_v2.md`；
3. T13：干净环境与 secret scan，产生两个文件；
4. T14：生成 `README_COURSE.md`、`ARCHITECTURE.md`、PR/MR 证据和 `REFLECTION_GUIDE.md`；
5. 学生本人写 `REFLECTION.md`；
6. T15：最终审计，产生 `FINAL_ACCEPTANCE.md`。

## 6. 当前交付成熟度

代码、凭据、WebUI、安全、Python 分发、Docker 和本地 CI 契约已经具备客观测试证据。剩余风险主要集中在：

- 远程仓库过程证据；
- 公开部署；
- 干净机器复验；
- 学生本人反思；
- 最终助教入口文档。

因此剩余工作以发布、证据和提交组织为主，而不是再增加核心功能。
