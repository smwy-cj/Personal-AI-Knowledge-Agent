# 课程 WebUI 本地演示指南 v2

本文替代 `DEMO_GUIDE.md` 中的启动说明，但不修改原文件。v2 增加了 T9 的 CSRF、HTTPS Cookie 和演示目录隔离要求。

## 1. 演示目录

为演示创建一个独立根目录，所有可写数据都必须位于其中：

```text
course-demo/
├── config.json
├── vault/
│   ├── Architecture.md
│   ├── Memory.md
│   └── Research.md
└── runtime/               # 首次启动时自动创建
```

从 `evaluations/fixtures/vault/` 复制三篇脱敏样例到 `course-demo/vault/`。不要直接使用个人 Vault，也不要在原样例目录中演示写回。

`course-demo/config.json`：

```json
{
  "vault_path": "./vault",
  "data_directory": "./runtime",
  "managed_memory_directory": "Agent/Memory",
  "observability_retention_days": 30
}
```

## 2. 安装与同步

在项目根目录执行：

```powershell
python -m pip install -e .
personal-ai-agent --config course-demo/config.json config-validate
personal-ai-agent --config course-demo/config.json sync
```

同步失败数应为 0。

## 3. 设置安全环境变量

```powershell
$env:PERSONAL_AGENT_CONFIG = "course-demo/config.json"
$env:PERSONAL_AGENT_DEMO_MODE = "1"
$env:PERSONAL_AGENT_DEMO_DATA_ROOT = (Resolve-Path "course-demo").Path
$env:PERSONAL_AGENT_WEB_SECRET = "请替换为本次部署生成的长随机值"
```

约束：

- `PERSONAL_AGENT_DEMO_DATA_ROOT` 必须是已经存在的目录；
- Vault 和 runtime 必须都位于该目录下，否则应用拒绝启动；
- `PERSONAL_AGENT_WEB_SECRET` 只放在进程环境或部署平台的 Secret 管理中，不写入配置或 Git；
- 单进程本地演示即使省略 Web Secret 也会自动生成临时值，但重启后会话失效，多进程部署必须显式配置；
- HTTPS 部署还需设置 `PERSONAL_AGENT_HTTPS=1`，使会话 Cookie 带 `Secure`。

## 4. 启动本地演示

```powershell
python -m flask --app personal_ai_agent.web:create_app run --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000/`。Flask 内置服务器只用于本机演示，不能作为公开部署服务器。

离线演示模型只复制已检索的本地证据、保留引用，不访问网络或凭据，也不代表真实大模型推理质量。Research 表单中的 Provider 字段应留空。

## 5. 演示流程

1. 首页说明本地优先、可追溯和人工治理价值。
2. 搜索样例中的 `checkpoint` 等词，展示路径与行号。
3. 创建与样例内容相关的 Research，Provider 字段留空。
4. Task 页展示 `WAITING_USER`、摘要、引用和执行统计。
5. 进入 Memory 审批，为每个候选明确批准或拒绝。
6. 提交后 Task 进入 `COMPLETED`；批准项显示 `VAULT_WRITTEN`。
7. 在 `course-demo/vault/Agent/Memory/` 中展示写回文件。

所有 POST 表单都带会话绑定的 CSRF token。页面过期或应用重启后若出现“请求验证失败”，刷新表单后重新提交即可。

## 6. 当前安全边界

- 请求体最大 64 KiB；
- 页面默认禁止第三方脚本、对象和 iframe 嵌入；
- 响应使用 CSP、nosniff、DENY frame、no-referrer、Permissions Policy 和 no-store；
- HTTPS 请求返回 HSTS；
- 会话 Cookie 为 HttpOnly、SameSite=Lax，设置 HTTPS 模式后同时为 Secure；
- 未处理错误只展示关联 ID；Task 错误只展示类型，不展示 Provider 正文、Prompt 或路径；
- 演示模式不使用配置中的真实模型 Provider，写入范围受演示根目录约束。

## 7. 尚未覆盖

- 用户账号、登录、角色和多租户授权；
- 分布式 CSRF 会话密钥轮换；
- 反向代理可信来源配置；
- 自动化浏览器无障碍扫描；
- 生产 WSGI、容器、CI 和 HTTPS 部署。

这些内容不影响受控本机课程演示；公开部署仍需完成 T10–T12 并按部署平台复核。
