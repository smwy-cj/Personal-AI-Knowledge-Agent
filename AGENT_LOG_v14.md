# AGENT_LOG v14：v0.1.1 最终课程发布

日期：2026-08-14

## 目标

在不移动 `v0.1.0` tag 的前提下，将最终反思、统一文档、当前证据和课程打包清单纳入新的 `v0.1.1` Release。

## 版本与文档

- Python 包版本从 `0.1.0` 更新为 `0.1.1`；
- 新增 `RELEASE_NOTES_v0.1.1.md` 和 `docs/course/GITHUB_RELEASE_EVIDENCE_v2.md`；
- 当前 README、课程入口、状态、计划、架构和打包清单指向 `v0.1.1`；
- `v0.1.0` Release notes 与证据保留为历史记录。

## 验证过程

1. 主机完整验收通过 232 项测试，工作区与 Git 历史秘密扫描为 0。
2. wheel 和 source distribution 成功构建，包版本及 Web 模板、静态资源、许可证和命令入口已核对。
3. 首次 `v0.1.1` 干净 Linux 构建出现 1 项失败：验证镜像只复制旧 `GITHUB_RELEASE_EVIDENCE.md`，没有复制新增的 v2 证据。
4. 将 Dockerfile.verify 改为复制两个版本化 Release 证据后重新构建，232 项测试全部通过。

该失败属于发布验证上下文遗漏，不是应用运行时失败；保留红灯和修复原因有助于证明干净环境检查确实覆盖最终文档。

## 分发资产

- `personal_ai_knowledge_agent-0.1.1-py3-none-any.whl`；
- `personal_ai_knowledge_agent-0.1.1.tar.gz`；
- `SHA256SUMS.txt`。

Release 创建后仍需核对远程 Actions、附件大小/摘要和公开下载链接。
