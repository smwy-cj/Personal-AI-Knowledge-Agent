# 课程 WebUI 本地演示指南

## 1. 演示目标

用一条可重复的浏览器流程展示：本地知识搜索、证据约束研究、持久任务状态、人工记忆审批，以及批准后写回受控 Vault 目录。

当前指南仅用于本机演示。T9 完成 CSRF、安全响应头和公开演示写入限制之前，不应把该开发服务器直接暴露到公网。

## 2. 准备独立演示数据

不要直接使用个人 Vault。复制三篇脱敏样例笔记到一个单独目录，并创建一个新的本地配置，例如：

```json
{
  "vault_path": "./course-demo-vault",
  "data_directory": "./course-demo-runtime",
  "managed_memory_directory": "Agent/Memory",
  "observability_retention_days": 30
}
```

配置不需要 Model Provider、Embedding Provider 或 API key。`data_directory` 必须位于 Vault 外部。

建议从 `evaluations/fixtures/vault/` 复制样例，而不是在原样例目录中演示写回。

## 3. 安装与首次同步

在项目根目录执行：

```powershell
python -m pip install -e .
personal-ai-agent --config course.demo.config.json config-validate
personal-ai-agent --config course.demo.config.json sync
```

首次同步后应看到新增笔记数，并且失败数为 0。

## 4. 启动离线演示模式

```powershell
$env:PERSONAL_AGENT_CONFIG = "course.demo.config.json"
$env:PERSONAL_AGENT_DEMO_MODE = "1"
python -m flask --app personal_ai_agent.web:create_app run --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000/`。

离线演示模型的边界：

- 只复制已经检索到的本地证据并生成合法结构；
- 每段保留对应引用编号；
- 不访问网络，不读取凭据，不产生费用；
- 不代表真实大模型推理质量，页面会显示演示模式；
- 如果研究表单提供 Model Provider 字段，应留空，让系统选择 `demo-model`。

## 5. 五分钟演示脚本

1. 首页：说明这是本地优先、带引用和人工治理的个人知识 Agent。
2. 搜索：进入“知识搜索”，搜索 `checkpoint` 或样例笔记中的词，展示文件路径与行号。
3. Research：进入“研究任务”，输入与样例内容相关的目标，Thread ID 保持默认，模型字段留空。
4. Task：提交后展示 `WAITING_USER`、研究摘要、证据来源、工具步骤、模型调用和 Token 统计。
5. Memory：点击“审查记忆候选”，逐项选择批准或拒绝；所有候选必须明确选择。
6. 收据：提交后回到 Task 页，状态变为 `COMPLETED`，批准项显示 `VAULT_WRITTEN`，拒绝项显示 `REJECTED`。
7. Vault：在 `course-demo-vault/Agent/Memory/` 中展示批准项生成的新 Markdown 文件。

## 6. 取消操作

非终态 Task 页面提供“取消任务”按钮。取消请求只允许 POST；任务空闲时可立即进入 `CANCELLED`，执行器持有任务时则记录持久取消请求，并在安全步骤边界停止。

## 7. 演示后的清理

演示数据位于专用的 `course-demo-vault` 和 `course-demo-runtime`。确认其中没有个人数据后，可人工删除这两个演示目录；不要删除真实 Vault 或共用运行目录。

## 8. 已知限制

- 当前没有自动刷新或后台任务队列，Research 请求在服务端同步执行；
- 当前只有关键词搜索页面，混合检索 Web 控件尚未实现；
- T9 前没有 CSRF 防护和完整安全响应头；
- Flask 内置服务器仅用于本地开发；生产 WSGI、Docker、GitLab CI 和公开部署分别属于 T10–T12；
- 演示模式使用确定性证据复制器，真实 Provider 流程仍需要配置 Provider 和凭据。
