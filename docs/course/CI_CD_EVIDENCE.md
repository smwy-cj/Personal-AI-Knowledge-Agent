# T11 GitLab CI/CD 配置与证据

## 1. 当前结论

- 日期：2026-08-14
- `.gitlab-ci.yml`：本地实现并通过静态/语法/测试验证
- 远程 GitLab pipeline：尚未运行，不能声明 pass
- 当前 Git remote：只有 GitHub `origin`
- 当前课程改动：尚未 commit 或 push

因此 T11 的“配置实现”已完成，但课程要求的“最后一次 CI/CD 为 pass”仍需要 NJU GitLab 仓库、提交与真实 Runner 结果。

## 2. 红灯

新增 `tests/test_gitlab_ci_contract.py` 后，测试在 `setUpClass` 即失败：根目录不存在 `.gitlab-ci.yml`。

这证明 GitLab 配置在测试前不存在。

## 3. 流水线结构

四个阶段：

1. `test`；
2. `package`；
3. `container`；
4. `deploy`。

四个 job：

- `unit-test`：安装包，运行 `python scripts/verify.py`，检查 CLI 与 Web 命令；
- `package-build`：运行 `python -m build`，保存 `dist/` 14 天；
- `container-build`：使用 Kaniko 构建 Dockerfile，默认 `--no-push`；
- `deploy-demo`：仅受保护 tag、手动触发，调用部署 webhook 后检查公开 `/health`。

## 4. 安全选择

- 单元测试不配置真实模型/API 凭据；当前 211 项测试全部使用 fake、stub 或本地确定性模型；
- cache 仅包含 pip 下载缓存，不缓存 SQLite、Vault、`.env` 或 keyring；
- artifacts 仅保存 `dist/`；
- 容器构建不使用 `docker:dind` 或 privileged runner；
- deploy 不回显 webhook，不在 YAML 中存 Secret；
- `DEPLOY_WEBHOOK_URL` 与 `DEMO_PUBLIC_URL` 必须在 GitLab CI/CD Variables 配置；
- deploy 只允许 `CI_COMMIT_TAG` 且 `CI_COMMIT_REF_PROTECTED=true`，并要求人工点击；
- `resource_group` 防止两个部署同时覆盖环境。

## 5. 本地验证

PyYAML 解析：

```text
gitlab-yaml-parse-ok jobs=unit-test,package-build,container-build,deploy-demo
```

CI 契约：

```text
Ran 6 tests in 0.003s
OK
```

CI + distribution 联合契约：

```text
Ran 13 tests in 0.012s
OK
```

完整回归：

```text
Ran 211 tests in 1029.946s
OK
```

本次完整回归异常耗时约 17 分钟，但无失败。需要在 T13 干净环境再次测量，以区分临时机器负载/等待与稳定性能问题。

## 6. 远程验收待办

以下内容只能在用户提供/创建 NJU GitLab 仓库并授权 push 后完成：

1. 增加 GitLab remote；
2. 按真实工作拆分 commit；
3. push 分支并创建 MR；
4. 验证 `unit-test`、`package-build`、`container-build` 均 pass；
5. 保存 pipeline URL、commit SHA、job URL 和 artifact 事实；
6. 部署完成后配置受保护变量与 tag，人工触发 `deploy-demo`；
7. 确认最后一次 pipeline 对最终提交为 pass；
8. 如实创建新的 `CI_CD_EVIDENCE_v2.md`，不覆盖本文。

当前没有 GitLab URL 或认证，因此本文不包含伪造链接与状态。
