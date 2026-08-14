# Agent 协作与人工决策日志 v8

本文续接 `AGENT_LOG_v7.md`，不修改原日志。

## 2026-08-14｜COURSE-T11｜GitLab CI/CD 与交付缺口盘点

- 课程冲突判断：测试章节要求 GitHub Actions，最终交付清单明确要求 `.gitlab-ci.yml` 与 `unit-test`；保留既有 GitHub Actions并新增 GitLab CI，满足两者。
- 仓库事实：当前仅有 GitHub `origin`，没有 GitLab remote；课程改动尚未 commit/push，因此不能声明远程 CI pass。
- 红灯：新增 CI 契约后因 `.gitlab-ci.yml` 不存在而在 setup 阶段失败。
- 单测网络判断：“不调用真实付费 API”不等于禁用依赖下载；全新 runner 需从 registry 安装 Flask/keyring/Waitress，但测试自身只使用 fake、stub 和本地确定性模型。
- 实现：四阶段、四 job；准确命名 `unit-test`；package artifact；Kaniko `--no-push`；受保护 tag 人工部署。
- 安全判断：不用 dind/privileged；不归档 runtime/Vault/.env；deploy variables 不写入仓库或输出；部署并发由 resource group 限制。
- 保护修正：仅限制 tag 不够，部署规则补充 `CI_COMMIT_REF_PROTECTED=true`。
- 本地验证：PyYAML 解析通过；6 项 CI 契约通过；完整 211 项测试通过。
- 性能观察：最后一次全量验证耗时 1029.946 秒，远高于此前约 18 秒但无测试失败；T13 必须复测，不能直接归因。
- 用户约束：继续忽略 Superpowers，不安装或调用；偏离课程强制工具链的事实保留在过程证据中。
- 交付盘点：T11 文档完成后，仍缺 8 个项目过程/最终文件和 1 个学生本人 `REFLECTION.md`，合计 9 个文件；另有 GitLab pass、公开 URL、registry、commit/MR 等非文件阻塞。
- 原文档保护：CI 证据、剩余清单和本日志全部新建，没有修改既有 Markdown。
- commit/PR：尚未创建。
