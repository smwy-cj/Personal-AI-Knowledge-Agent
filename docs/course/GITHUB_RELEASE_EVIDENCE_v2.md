# GitHub Release v0.1.1 证据

发布日期：2026-08-14
仓库：<https://github.com/smwy-cj/Personal-AI-Knowledge-Agent>
Release：<https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.1>

## 版本范围

- Tag：`v0.1.1`；
- Python 包版本：`0.1.1`；
- 目标：在 `v0.1.0` 应用基线上加入最终反思、文档统一、当前验证证据与 SE Learning 打包清单；
- `v0.1.0` tag 保持不变。

## 验证基线

- 本机完整验收：232 项测试通过；
- 干净 Python 3.12 Linux 镜像：232 项测试通过；
- GitHub Actions：Linux Python 3.9/3.11/3.13 和 Windows Python 3.11；
- 工作区及完整 Git 历史秘密扫描：0 个发现；
- Markdown 本地链接：0 个缺失目标。

## Release 资产

正式发布包含：

| 资产 | 大小 | SHA-256 |
|---|---:|---|
| `personal_ai_knowledge_agent-0.1.1-py3-none-any.whl` | 108,137 B | `8f8289ac5a74cec3807fafb9206b4117ebbbc931a52982d8b3d5797c285020c0` |
| `personal_ai_knowledge_agent-0.1.1.tar.gz` | 137,588 B | `37b9c9d9cea4e8c0bd2cba0587b90b66ed4bed9e442ce62500f93fbea6b58451` |
| `SHA256SUMS.txt` | 发布时核对 | 由 GitHub 附件摘要核对 |

此外包括：

- GitHub 自动生成的 Source code zip/tar.gz。

Release commit 以不可变 tag `v0.1.1` 的 GitHub ref 为准；最终 Actions run 与附件摘要在创建后通过 GitHub API 复核。

## 提交边界

Release 是分发链接，不是公开 WebUI。`submission.jsonc` 使用：

```jsonc
"is_deployed": false,
"deploy_release_url": "https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.1"
```

`submission.jsonc` 必须在 SE Learning 中与源码压缩包并列提交，不能放入仓库或源码压缩包。
