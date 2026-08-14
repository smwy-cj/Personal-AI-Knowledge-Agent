# Agent Log v11 — 助教入口、架构与反思指南

日期：2026-08-14

## 本轮目标

完成不依赖外部账号状态的 T14 文档：课程版 README、最终架构说明和学生反思写作指南。继续遵守“只生成新文档、不修改原文档”，并按用户要求忽略 Superpowers。

## 事实核对

本轮重新读取两份课程要求、现有 README、包配置、Docker/Compose/Render 配置、Web 路由、演示指南、安全与干净环境证据。特别区分：

- 已有本地测试和镜像证据；
- 尚未产生的公开 URL、registry、远程 CI pass 和 PR/MR；
- 可以由 AI 整理的事实材料；
- 必须由学生本人形成的反思观点。

## TDD 记录

先新增 3 项课程交付契约测试，分别要求 README 的必需章节与安全命令、架构文档的组件/数据流/信任边界，以及反思指南的学生署名边界和课程必答问题。首次执行 3 项均因目标文件不存在而失败；随后才创建正文。

## 新增文档

- `README_COURSE.md`：助教入口、安装、演示、分发、安全、目录、验收和限制；
- `docs/course/ARCHITECTURE.md`：组件图、数据流、持久化、信任边界、部署与取舍；
- `REFLECTION_GUIDE.md`：1500–2500 字结构、可核验事实、必答问题和自查表；
- `docs/course/DELIVERY_REMAINING_FILES_v3.md`：更新完成后的剩余交付状态。

## 人工所有权边界

没有创建 `REFLECTION.md`。指南明确要求学生本人形成观点，并要求如实说明本项目未使用 Superpowers。没有虚构部署 URL、远程 CI、registry、commit 或 PR 证据。

