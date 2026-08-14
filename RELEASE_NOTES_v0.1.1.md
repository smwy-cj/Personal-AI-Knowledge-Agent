# Personal AI Knowledge Agent v0.1.1

课程最终交付版本。在 `v0.1.0` 的完整应用能力上，补齐学生反思、当前文档统一、Release/CI 证据、干净环境 v2 记录和 SE Learning 打包清单。

## 相比 v0.1.0 的变化

- 新增学生本人初稿整理形成的 `REFLECTION.md`，并披露 AI 仅进行结构、语言和事实核对；
- 重写主 README，使安装、演示、凭据、安全、测试和 Release 状态与实际项目一致；
- 新增文档索引，区分当前权威文档、阶段历史快照和检索测试语料；
- 更新 SPEC、PLAN、项目状态、架构和课程入口的真实完成状态；
- 新增 GitHub Actions、Release、干净 Linux 和最终剩余项证据；
- 新增 SE Learning 源码压缩包与外置 `submission.jsonc` 的打包清单；
- 新增 4 项文档一致性测试，并让干净验证镜像覆盖正式反思和当前文档。

## Release 资产

- `personal_ai_knowledge_agent-0.1.1-py3-none-any.whl`；
- `personal_ai_knowledge_agent-0.1.1.tar.gz`；
- `SHA256SUMS.txt`；
- GitHub 自动生成的 Source code 压缩包。

## 验证状态

- 232 项自动化测试通过；
- 独立 Python 3.12 Linux 验证镜像通过；
- GitHub Actions 覆盖 Linux Python 3.9/3.11/3.13 与 Windows Python 3.11；
- 工作区与完整 Git 历史秘密扫描均为 0；
- Markdown 本地链接检查为 0 个缺失目标。

## 安装

```text
python -m pip install personal_ai_knowledge_agent-0.1.1-py3-none-any.whl
personal-ai-agent --help
personal-ai-agent-web --help
```

## 已知限制

- Release 是可获取的分发链接，不代表公开 WebUI 已部署；提交时使用 `is_deployed=false`；
- 本地个人模式没有多用户身份系统，只应绑定回环地址；
- Research 是受治理的固定工作流，不是开放式动态 Planner；
- 项目未使用 Superpowers，偏离已在过程材料与反思中如实说明；
- Draft PR 的真实人工 review/批准/合并仍需后续发生。
