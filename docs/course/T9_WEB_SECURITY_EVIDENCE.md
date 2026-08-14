# T9 Web 安全、可访问性与错误边界实施证据

## 1. 任务状态

- 日期：2026-08-13
- 对应计划：T9
- 状态：本地实现与验证完成，尚未提交 commit 或创建 PR

## 2. 红灯

新增 `tests/test_web_security.py` 后共运行 8 个测试：7 个失败、1 个错误。

失败事实包括：

- 无 token 的取消请求仍返回 303；
-页面没有 CSRF token；
- 响应缺少安全头；
- HTTPS 响应没有安全会话 Cookie；
- 413 使用默认英文页面；
- demo 配置可以指向允许根目录之外；
- Task 页面展示持久错误 message；
- 页面没有 skip link 和可访问错误关联。

## 3. 实现

新增：

- `tests/test_web_security.py`；
- `docs/course/WEB_SECURITY.md`；
- `docs/course/DEMO_GUIDE_v2.md`；
- 本证据文件。

修改新 Web 实现与测试：

- 应用工厂增加会话 CSRF、请求上限和统一响应头；
- 增加安全中文 413；
- Web adapter 启动时验证 demo root；
- Research、Task cancel、Memory 表单加入 CSRF token；
- Task 错误不再渲染 message；
- 模板加入 skip link、主内容焦点、错误关联；
- CSS 增加键盘焦点样式；
- T8 非安全关注测试显式关闭 CSRF，T9 单独验证默认开启，避免测试职责混淆；
- T8 默认离线 demo 集成测试增加显式 demo root。

没有修改任何原有 Markdown 文档。

## 4. 安全验证覆盖

自动化测试证明：

1. 缺失 CSRF 的 Research/Cancel 被拒绝且 port 不被调用；
2. 合法 token 可以完成 Research 和 Memory 写操作；
3. HTTP/HTTPS 均返回 CSP、nosniff、frame deny、no-referrer、Permissions Policy、COOP 和 no-store；
4. HSTS 仅在 HTTPS 请求返回；
5. HTTPS 会话 Cookie 包含 Secure、HttpOnly、SameSite=Lax；
6. 超过配置上限的请求在业务调用前返回 413；
7. 未处理异常和 Task 持久错误不展示测试标记 secret、Windows 绝对路径或 Prompt；
8. demo Vault 越出演示根目录时应用拒绝启动；
9. Research 表单存在 skip link、main target、label、role=alert 和 aria error association。

## 5. 测试结果

T9 专项：

```text
Ran 8 tests in 0.098s
OK
```

全部 Web：

```text
Ran 33 tests in 1.725s
OK
```

完整回归：

```text
Ran 198 tests in 13.756s
OK
```

`python scripts/verify.py` 退出码为 0。

## 6. 尚未完成

- 生产 WSGI 与反向代理 HTTPS 识别；
- 登录、角色和多租户授权；
- 公开服务的速率限制和滥用防护；
- 浏览器级 WCAG 自动扫描与人工审查；
- Docker、GitLab CI 与公开部署；
- commit、PR 和远程 CI 证据。

因此当前满足本地受控演示的安全基线，但不宣称已达到不受限公网生产安全等级。
