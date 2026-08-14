# GitHub Release v0.1.0 证据

发布日期：2026-08-14
仓库：<https://github.com/smwy-cj/Personal-AI-Knowledge-Agent>
Release：<https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.0>

## 发布对象

- Tag：`v0.1.0`；
- Commit：`9b13b1bf4dac37ef72b2e004b5af32440dd754aa`；
- Release 名称：`Personal AI Knowledge Agent v0.1.0`；
- 状态：正式发布，非 draft、非 prerelease；
- PR：<https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/pull/1>（仍为 draft，未伪造人工评审或合并）。

远程 tag 与本地已验证 commit 一致：

```text
9b13b1bf4dac37ef72b2e004b5af32440dd754aa refs/tags/v0.1.0
```

## 发布附件

| 附件 | 大小 | SHA-256 |
|---|---:|---|
| `personal_ai_knowledge_agent-0.1.0-py3-none-any.whl` | 114,244 B | `f78ae236a9376f3175dd23a711fae3cf4b748abe9ff5d986bdd291f1a532822c` |
| `personal_ai_knowledge_agent-0.1.0.tar.gz` | 149,502 B | `6d8380700db9adc79ee9983803eca73e477f4367e1c8dce091d416a6d0655cc3` |
| `SHA256SUMS.txt` | 224 B | GitHub 记录 `0d701b991a3adbe1981b30defc63ff2cd76a43c7bf895d79744200ec6f6e031b` |

三个附件发布后已重新下载。wheel 与 source distribution 的本地 SHA-256 和 `SHA256SUMS.txt` 完全一致。wheel 内容已核对包含 Web 模板、静态资源、三个命令入口和许可证。

GitHub 还自动提供完整 tag 源码压缩包，可用于课程平台源码提交：

<https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/archive/refs/tags/v0.1.0.zip>

## GitHub Actions

最初远程矩阵失败，根因是旧工作流使用 `pip install --no-deps .`，新增的 Flask 等运行依赖没有安装。修正为安装声明依赖，并在验收前增加秘密扫描后重新推送。

最终矩阵全部通过：

- Ubuntu / Python 3.9；
- Ubuntu / Python 3.11；
- Ubuntu / Python 3.13；
- Windows / Python 3.11。

tag 触发的第二组同矩阵检查也全部通过。修复提交与 Release tag 均指向 `9b13b1b`。

## 发布前验证

- `python scripts/verify.py`：228 项测试通过；
- `python scripts/scan_secrets.py --working-tree --git-history`：0 个发现；
- `docker build -f Dockerfile.verify ...`：独立 Linux 环境 228 项通过；
- `python -m build --no-isolation`：wheel 与 sdist 成功；
- Release 附件重新下载和哈希复核：通过。

## 课程提交字段

在 `submission.jsonc` 中应填写：

```jsonc
"repo_url": "https://github.com/smwy-cj/Personal-AI-Knowledge-Agent",
"is_deployed": false,
"deploy_release_url": "https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.0"
```

学号和姓名必须由学生本人填写。`submission.jsonc` 与源码压缩包并列上传，不放入压缩包或 Git 仓库。

## 边界

Release 证明 CLI/WebUI 源码和 Python 包可获取，不代表公开 WebUI 已部署。当前选择教师聊天记录允许的 Release 方案，因此 `is_deployed=false`。PR 仍为 draft，人工评审尚未完成；最终反思已基于学生本人初稿整理并披露 AI 辅助范围。
