# CI/CD 当前证据

更新日期：2026-08-14
适用发布：`v0.1.1`（`v0.1.0` 远程基线已通过；最终 tag 将复用同一矩阵）

## 当前结论

GitHub Actions 已在真实远程环境通过以下矩阵：

| 平台 | Python | 结果 |
|---|---:|---|
| Ubuntu | 3.9 | 通过 |
| Ubuntu | 3.11 | 通过 |
| Ubuntu | 3.13 | 通过 |
| Windows | 3.11 | 通过 |

工作流执行安装、完整 `scripts/verify.py` 验收、安装后命令检查和秘密扫描。Release tag 对应 commit 为 `fc43cbcce436779f883d8188fc60270735dbd329`。

## 修复记录

首轮远程 CI 暴露的问题不是业务测试失败，而是工作流使用 `pip install --no-deps .`，导致全新 runner 缺少 Flask、keyring 和 Waitress。修复为 `pip install .` 后，四个矩阵任务全部通过。该修复也证明本地已有依赖不能替代干净环境安装验证。

已核验的相关 GitHub Actions run 包括 `31769285514`、`31769288572` 和 tag 后的 `31778147451`。最终判定以 GitHub 仓库 Actions 页面和对应 commit check 为准。

## GitLab 边界

`.gitlab-ci.yml` 保留 `unit-test`、package、container 和 deploy 的课程契约，历史配置证据见 `CI_CD_EVIDENCE.md`。当前没有 GitLab 远程 pipeline 运行记录，因此本文不把配置测试表述为 GitLab 执行成功。

## 可复验命令

```powershell
python scripts/verify.py
python scripts/scan_secrets.py --working-tree --git-history
```

Release 与附件校验见 `GITHUB_RELEASE_EVIDENCE.md`。
