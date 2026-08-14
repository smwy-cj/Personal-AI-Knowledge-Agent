# T8 Research、Task 与 Memory WebUI 实施证据

## 1. 任务状态

- 日期：2026-08-13
- 对应计划：T8
- 状态：本地实现与验证完成，尚未提交 commit 或创建 PR

## 2. 红灯证据

首次新增 `tests/test_web_research.py` 和 `tests/test_web_memory.py` 时，10 个测试全部失败，因为 `/research`、Task 与 Memory 路由尚不存在并返回 404。

完成基础闭环后又发现 `DEMO_MODE` 只是页面标识，不能在无 Provider 环境运行 Research。新增离线演示验收测试后，预期 303、实际 500；随后才加入确定性 `demo-model` 和环境变量启动入口。

这两次红灯分别证明页面闭环与可重复离线演示能力均由测试先行驱动。

## 3. 实现内容

新增：

- `src/personal_ai_agent/web/demo.py`；
- `src/personal_ai_agent/web/templates/research.html`；
- `src/personal_ai_agent/web/templates/task.html`；
- `src/personal_ai_agent/web/templates/memory_review.html`；
- `tests/test_web_research.py`；
- `tests/test_web_memory.py`；
- `docs/course/DEMO_GUIDE.md`；
- 本证据文件。

修改本轮新建的 Web 文件：

- Web 应用工厂新增 Research、Task、取消和 Memory 审批路由；
- Web port 连接 Application Service 的公开业务方法；
- 基础模板增加入口，样式增加 Task、审批和状态展示；
- `ApplicationService` 增加可选 Model Gateway 工厂注入点，正常 CLI/Provider 路径保持默认行为；
- `PERSONAL_AGENT_DEMO_MODE=1` 使默认 Web 工厂使用离线确定性模型。

没有修改任何原有 Markdown 文档。

## 4. Web 闭环

实现的路由：

- `GET/POST /research`：输入验证并创建研究任务；
- `GET /tasks/<task_id>`：展示状态、步骤统计、摘要、引用、错误与记忆收据；
- `POST /tasks/<task_id>/cancel`：持久取消；
- `GET/POST /tasks/<task_id>/memory`：列出所有待审候选并一次性提交决定。

输入边界：

- goal 必填且最多 2000 字符；
- Thread ID 必填且最多 100 字符；
- 检索数量只接受 1–20 整数；
- 所有候选必须明确批准或拒绝；
- 已完成审批的重复提交返回 409，不会再次调用写回；
- 取消只允许 POST；
- 不存在的任务映射为不含内部异常的 404。

## 5. 展示安全

摘要标题、正文、路径、候选内容和冲突信息均使用 Jinja 默认自动转义。测试注入 `<script>` 后，页面只出现 `&lt;script&gt;`，不出现可执行脚本。

未处理异常继续只显示关联 ID。CSRF 和完整安全响应头尚未实现，明确留给 T9，当前服务不得作为公网生产服务使用。

## 6. 真实业务集成证据

第一条集成测试在临时目录中完成：

1. 创建真实 Markdown Vault 和无密钥本地 Provider 配置；
2. 使用真实 Application Service 同步 Vault；
3. 只替换 Provider HTTP 响应为结构化假响应；
4. 从 Web 提交 Research，真实 Orchestrator 运行至 `WAITING_USER`；
5. 从真实 Memory Repository 获取候选；
6. 通过 Web 批准候选；
7. 验证 Task 为 `COMPLETED`、治理状态为 `VAULT_WRITTEN`；
8. 验证受控 Vault 目录中确实产生 Markdown 文件。

第二条集成测试使用无任何 Provider 的配置，并将网络访问替换为“调用即失败”。设置 `PERSONAL_AGENT_DEMO_MODE=1` 后，Research 仍到达 `WAITING_USER`，页面展示本地证据与引用，证明默认离线演示不依赖网络或 API key。

## 7. 测试结果

Web foundation + search + research + memory：

```text
Ran 25 tests in 1.496s
OK
```

完整回归：

```text
Ran 190 tests in 13.359s
OK
```

`python scripts/verify.py` 退出码为 0。

`git diff --check` 在文档写入前通过；最终文件检查见本任务收尾记录。

## 8. 尚未完成

- T9：CSRF、安全响应头、请求体上限、演示目录强制隔离和可访问性验收；
- T10：生产 WSGI、Python 包和 Docker 分发；
- T11：GitLab CI/CD；
- T12：HTTPS 公开演示部署；
- commit、PR 和远程流水线证据。
