# 交付剩余项 v4

盘点日期：2026-08-14
基线：最终课程发布 `v0.1.1`，远程 GitHub Actions 使用同一多平台矩阵。

## 已具备

- 可提交 Release：<https://github.com/smwy-cj/Personal-AI-Knowledge-Agent/releases/tag/v0.1.1>；
- Release 附件与 SHA-256：见 `GITHUB_RELEASE_EVIDENCE.md`；
- 完整本地与干净 Linux 验收证据；
- GitHub Actions 多平台/多版本通过证据；
- Draft PR #1 与真实 commit 历史；
- 课程 README、演示、安全、架构、凭据和分发说明；
- `submission.jsonc` 的填写规则已明确。

## 仍需形成的 2 份最终文件

`REFLECTION.md` 已根据学生本人提供的完整初稿整理完成，并在文末披露 AI 的结构、语言和事实核对范围。

1. `docs/course/PR_AND_REVIEW_EVIDENCE.md`
   - 等真实人工 review、批准、修改或合并发生后再记录；
   - 当前只能如实写“Draft PR 已创建，尚无人工 review”。
2. `docs/course/FINAL_ACCEPTANCE.md`
   - 在反思、人工评审决定、最终测试、秘密扫描和提交包检查完成后生成；
   - 应记录最终 commit/tag、测试数、提交清单和已知限制。

## 不再作为本路线阻塞项

教师聊天记录确认：只提供 CLI/本地 WebUI 时，可以提交托管平台的 GitHub Release 链接；若没有公开 WebUI，`submission.jsonc` 中填写 `is_deployed:false`。因此公开部署 URL 和 `DEPLOYMENT_EVIDENCE.md` 不是当前 Release 路线的必交阻塞项。

如果以后另行部署公开 WebUI，再新增部署证据；不得把 Release URL 伪装成 WebUI URL。

## 提交包外部文件

`submission.jsonc` 必须与源码压缩包并列提交，不能改名，也不能放进源码压缩包。当前下载目录中的模板仍含学号、姓名和链接占位符，必须由学生填入真实信息。
