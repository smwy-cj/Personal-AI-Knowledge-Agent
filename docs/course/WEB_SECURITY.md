# Web 安全与可访问性边界

## 1. 保护目标

当前 WebUI 面向单用户课程演示，主要保护：

- 防止第三方网页借用已打开的浏览器会话触发 Research、取消或记忆写回；
- 防止超大请求消耗不必要资源；
- 防止笔记、模型结果和错误详情进入可执行 HTML 或错误页面；
- 防止演示配置误指向个人 Vault 或根目录外的运行数据；
- 为键盘和屏幕阅读器用户保留基础导航、标签和错误反馈。

当前不宣称提供账号系统、多用户授权或互联网级抗滥用能力。

## 2. CSRF

所有 `POST`、`PUT`、`PATCH`、`DELETE` 请求默认要求会话中的随机 token：

- HTML 表单使用隐藏字段 `_csrf_token`；
- API 客户端可使用 `X-CSRF-Token`；
- 使用常量时间比较；
- 缺失、错误或旧 token 返回安全中文 400；
- 校验失败时不调用 Application Service。

测试可显式设置 `CSRF_ENABLED=False` 以隔离非安全单元测试；生产默认始终开启。

## 3. 会话与 Cookie

- `HttpOnly=true`；
- `SameSite=Lax`；
- 当 `PERSONAL_AGENT_HTTPS=1` 时 `Secure=true`；
- `PERSONAL_AGENT_WEB_SECRET` 用于签名会话，不能进入 Git 或 JSON 配置；
- 未配置时进程生成临时随机密钥，适用于单进程本地演示，但重启会使现有表单 token 失效。

## 4. 安全响应头

所有正常与错误响应统一增加：

- `Content-Security-Policy`：仅允许同源资源，禁用 object 和 frame ancestor；
- `X-Content-Type-Options: nosniff`；
- `X-Frame-Options: DENY`；
- `Referrer-Policy: no-referrer`；
- 限制 camera、microphone、geolocation、payment 和 USB 的 `Permissions-Policy`；
- `Cross-Origin-Opener-Policy: same-origin`；
- `Cache-Control: no-store`；
- HTTPS 请求增加一年期 HSTS。

CSP 不允许内联脚本；当前页面也不依赖 JavaScript。

## 5. 输入与错误边界

- HTTP 请求体最大 64 KiB，超限返回中文 413；
- Search、Research 和各筛选字段继续执行领域长度与类型验证；
- Jinja 自动转义笔记、摘要、候选记忆和路径；
- 未处理异常只展示随机关联 ID；
- Task 持久错误只展示 `error_type`，隐藏可能含 Provider 正文、Prompt、路径或敏感输入的 message；
- JSON 错误只返回稳定错误代码和必要关联 ID。

## 6. 演示数据隔离

默认工厂在 `DEMO_MODE` 下强制要求 `PERSONAL_AGENT_DEMO_DATA_ROOT`：

- 该目录必须已存在；
- `vault_path` 和 `data_directory` 解析后的真实路径都必须位于根目录内；
- 任一越界时在应用启动阶段失败；
- 演示 Research 使用确定性本地模型，不选择配置中的真实 Provider；
- 受控 Memory Writer 本身仍限制写入 `managed_memory_directory`，因此最终写入同时受 Vault 内部边界和演示根目录边界约束。

测试注入 fake port 时不检查文件系统，因为 fake 不具有真实写入能力。默认生产 adapter 路径必须通过检查。

## 7. 基础可访问性

- 页面提供“跳到主要内容”链接；
- 主区域有稳定目标和可聚焦属性；
- 导航有可读标签；
- 表单控件使用显式 label；
- 错误使用 `role=alert`、稳定 ID 和 `aria-describedby`；
- 输入、文本框、按钮、链接和 details summary 都有明显焦点轮廓；
- 页面语言固定为 `zh-CN`，布局支持窄屏。

当前仅完成结构与自动化契约验证，尚未运行 WCAG 全量人工审查或浏览器自动扫描。

## 8. 剩余风险

- 公开部署前仍需生产 WSGI、HTTPS 终止和反向代理配置；
- 若横向扩容，多实例必须共享稳定 Web Secret，部署时还应评估服务端会话；
- 没有身份认证时，不应把含个人数据的实例暴露到不可信网络；
- 没有限流、验证码或账户级配额，无法抵御公开滥用；
- HSTS 是否生效取决于应用正确识别 HTTPS，反向代理场景需在 T10/T12 明确信任边界。
