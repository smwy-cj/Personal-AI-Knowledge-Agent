# T7 Web 知识搜索实施证据

## 1. 任务状态

- 日期：2026-08-13
- 对应计划：T7
- 状态：本地实现与验证完成，尚未提交 commit 或创建 PR

## 2. 红灯

新增 `tests/test_web_search.py` 后，6 个场景共出现 8 个断言失败，全部因为 `/search` 尚不存在并返回 404。

这证明测试先于搜索路由和页面实现。

## 3. 实现内容

新增：

- `src/personal_ai_agent/web/templates/base.html`；
- `src/personal_ai_agent/web/templates/search.html`；
- `src/personal_ai_agent/web/static/app.css`；
- `tests/test_web_search.py`；
- `docs/course/WEB_SEARCH_ACCEPTANCE.md`；
- 本证据文件。

修改：

- Web 应用工厂增加 `/search`；
- 新首页增加搜索入口并复用基础模板；
- 新错误页复用基础模板。

没有修改任何原有 Markdown 文档。

## 4. 输入和调用边界

- 查询去除首尾空白；
- 空查询拒绝；
- 查询最大 500 字符；
- limit 只接受 1–50 整数；
- path prefix 和重复 tag 参数传给 port；
- 失败校验不会调用业务层；
- Application Service 的领域校验继续保留。

## 5. 展示与转义

搜索结果显示路径、行号、标题层级、匹配方式和相关度。

测试把 `<script>` 同时放入标题和正文，页面只包含 `&lt;script&gt;`，不包含可执行 `<script>alert`。模板没有使用 `safe`。

## 6. 真实集成链路

新增测试在临时目录中：

1. 创建真实 Markdown Vault；
2. 写入 `Architecture.md`；
3. 创建无 Provider 配置；
4. 使用 Application Service 同步；
5. 使用生产 `ApplicationServiceWebAdapter`；
6. 从 Flask test client 请求 `/search?q=durable+recovery`；
7. 验证页面包含文件名和原始正文。

该测试证明 Web 搜索不是只对 fake port 有效，而且关键词路径不依赖 API key。

## 7. 测试结果

Web foundation + search：

```text
Ran 13 tests in 0.312s
OK
```

完整回归：

```text
Ran 178 tests in 11.879s
OK
```

`python scripts/verify.py` 退出码为 0。

## 8. 未完成

- Research 提交与 Task 页面；
- Memory 审批；
- 混合检索 Web 控件；
- CSRF 和完整安全 headers；
- 生产 WSGI server 和公开部署；
- commit、PR、远程 CI。
