# Personal AI Knowledge Agent v0.1.0

首个课程交付版本，提供 CLI、本地 WebUI、Docker 演示镜像和 Python 分发包。

## 主要能力

- 增量摄取 Obsidian Markdown，并返回文件与行号级引用；
- 关键词、向量和混合检索；
- 固定计划的 Research Workflow，支持状态、预算、重试、Checkpoint 与取消；
- 带引用校验的研究摘要；
- 记忆候选敏感/重复/冲突检查、人工审批和受控写回；
- Provider 路由、共享限流、Token/费用观测和账单核对；
- OS keyring 优先的凭据录入、状态、更新和删除；
- Flask/Jinja/Waitress WebUI，覆盖搜索、研究、任务和 Memory Review；
- 无付费 API key 的脱敏课程 demo mode。

## Release 资产

- `personal_ai_knowledge_agent-0.1.0-py3-none-any.whl`：Python wheel；
- `personal_ai_knowledge_agent-0.1.0.tar.gz`：Python source distribution；
- `SHA256SUMS.txt`：上述附件的 SHA-256 校验值；
- GitHub 自动生成的 Source code 压缩包：包含完整仓库源码、课程文档、Dockerfile 和测试。

Python 3.9–3.13 安装示例：

```text
python -m pip install personal_ai_knowledge_agent-0.1.0-py3-none-any.whl
personal-ai-agent --help
personal-ai-agent-web --help
```

Docker 演示请下载 GitHub 自动生成的源码压缩包后执行：

```text
docker build -t personal-ai-knowledge-agent:course .
docker run --rm -p 127.0.0.1:8000:8000 -e PERSONAL_AGENT_WEB_SECRET=<本机生成的长随机值> personal-ai-knowledge-agent:course
```

随后访问 `http://127.0.0.1:8000/`。

## 验证状态

- 228 项自动化测试通过；
- 独立 Linux 验证镜像通过；
- 当前工作区和完整 Git 历史高置信度秘密扫描为 0 个发现；
- wheel 已确认包含 Web 模板、静态资源、许可证和三个命令行入口。

## 安全提示

- Release 不包含真实 API key、`.env`、个人 Vault、SQLite 或用户数据；
- 公开/课程演示只使用固定脱敏 Vault 和 fake Provider；
- 本地个人模式默认只绑定回环地址，不应直接暴露到公网；
- 真实 Provider 凭据应使用系统密钥环，容器或云平台可使用 Secret 环境变量注入；
- `.env` 是明文文件，只能作为本地便利方案且不得提交。

## 已知限制

- 该版本没有多用户身份系统；
- Research 使用固定工作流，不是开放式动态 Planner；
- GitHub Release 是本版本的分发链接，不代表已经存在公开 WebUI 部署；
- 免费部署平台可能冷启动并重置临时数据。

