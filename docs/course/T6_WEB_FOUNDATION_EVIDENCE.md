# T6 Web Foundation 实施证据

## 1. 任务状态

- 日期：2026-08-13
- 对应计划：T6
- 对应规格：`SPEC.md`、`SPEC_v2.md`
- 状态：本地实现与验证完成，尚未提交 commit 或创建 PR

## 2. 红灯

新增 `tests/test_web_foundation.py` 后运行：

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_web_foundation -v
```

得到：

```text
ModuleNotFoundError: No module named 'personal_ai_agent.web'
```

失败来自尚未实现的 Web 包。

## 3. 依赖与安装

`pyproject.toml` 增加：

```toml
"Flask>=3.1,<3.2"
```

沙箱内首次安装因网络权限失败；获得依赖下载授权后安装 Flask 3.1.3 及其依赖成功。没有升级 pip，也没有安装与任务无关的软件包。

## 4. 实现内容

新增：

- `src/personal_ai_agent/web/__init__.py`；
- `src/personal_ai_agent/web/ports.py`；
- `src/personal_ai_agent/web/templates/index.html`；
- `src/personal_ai_agent/web/templates/error.html`；
- `tests/test_web_foundation.py`；
- `docs/course/WEB_ARCHITECTURE.md`。

实现能力：

- application factory；
- per-app port 注入；
- `WebApplicationPort`；
- `ApplicationServiceWebAdapter`；
- 首页和 demo mode 标记；
- 无 Provider 调用的 `/health`；
- 安全 404；
- 脱敏 500 与随机关联 ID。

## 5. 专项测试

测试覆盖：

1. 健康检查返回 JSON；
2. 健康检查只调用注入 port；
3. 首页说明项目价值和演示边界；
4. 每个 app 实例使用独立 port；
5. 404 不泄漏内部路径；
6. 500 不泄漏异常中的路径或 Prompt；
7. 生产 adapter 的健康检查只使用公开 `validate()`。

初次 5 项测试通过；补充生产 adapter 边界后共有 6 项 Web foundation 测试。

## 6. 完整回归

在前 5 项 Web 测试版本上运行：

```powershell
python scripts/verify.py
```

结果：

```text
Ran 170 tests in 11.650s
OK
```

退出码：0。

补充生产 adapter 边界测试后再次运行：

```text
Ran 6 tests in 0.031s
OK

Ran 171 tests in 12.265s
OK
```

最终完整验证退出码为 0。

## 7. 未完成边界

- 没有搜索 WebUI；
- 没有 Research 或 Memory 审批 WebUI；
- 没有 CSRF、安全 headers 或生产 Cookie 配置；
- 没有生产 WSGI server；
- 没有公开 URL；
- 没有 commit、PR 或远程 CI 证据。

因此本任务只完成 T6，不代表整个 WebUI 或公开部署已经完成。
