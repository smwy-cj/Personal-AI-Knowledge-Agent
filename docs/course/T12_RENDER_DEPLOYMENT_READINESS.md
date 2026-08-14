# T12 Render 部署就绪证据

## 1. 结论

- 日期：2026-08-14
- 平台：Render 免费 Docker Web Service
- 部署配置：完成
- 本地平台模拟：通过
- 真实公开 HTTPS URL：尚未取得
- T12 状态：`BLOCKED ON EXTERNAL AUTHORIZATION`，不是完整 DONE

阻塞原因不是代码失败，而是当前改动尚未 commit/push，且没有用户 Render 账号授权或可操作的 Render API credential。根据安全边界，不能替用户创建账号、连接仓库或接受潜在计费条款。

## 2. 平台选择依据

官方文档确认：

- Render 可从 Dockerfile 构建 Web Service；
- Blueprint 默认使用根目录 `render.yaml`；
- Web Service 提供公开域名与托管 TLS；
- Blueprint 支持 `healthCheckPath` 和随机生成 Secret；
- 免费 Web Service 支持课程预览，但 15 分钟无流量会休眠；
- 免费实例的本地文件系统在重启、休眠或部署后会丢失，不能附加持久磁盘。

参考：

- <https://render.com/docs/web-services>
- <https://render.com/docs/free>
- <https://render.com/docs/blueprint-spec>
- <https://render.com/docs/infrastructure-as-code>

Fly.io 官方资料表明新用户没有免费层，因此未选用 Fly.io。

## 3. 红灯与修复

### 红灯一：缺少 Blueprint

新增 Render 部署契约后，测试因 `render.yaml` 不存在而在 setup 阶段失败。

修复：新增单服务 Blueprint、免费 Docker runtime、Singapore 区域、健康检查和自动生成 Web Secret。

### 红灯二：平台 PORT 被镜像覆盖

第一次真实容器模拟设置 `PORT=10000`，镜像虽然构建成功，但服务无法从映射端口访问。根因是 Dockerfile 固定 `PERSONAL_AGENT_WEB_PORT=8000`，其优先级高于平台变量。

新增失败测试后修复：

- Dockerfile 不再固定项目端口；
- Web server 在无项目专用端口时读取 `PORT`；
- Docker healthcheck 动态读取 `PORT`；
- 项目专用 `PERSONAL_AGENT_WEB_PORT` 仍可显式覆盖平台端口。

### 代理 HTTPS 修正

Render 在负载均衡器终止 TLS 后向容器转发 HTTP。应用现在在 `PERSONAL_AGENT_HTTPS=1` 时即发送 HSTS，并将 session cookie 设为 Secure，不依赖容器内 `request.is_secure`。

## 4. Blueprint 安全边界

`render.yaml`：

- 不含真实 key、token、密码或个人路径；
- 强制 `PERSONAL_AGENT_DEMO_MODE=1`；
- 只使用镜像内 `/app/course_demo`；
- Web Secret 由平台生成；
- 健康检查为 `/health`；
- 不配置任何真实 Model/Embedding Provider；
- 不创建数据库、磁盘或其他可能收费的资源；
- 免费实例只承载三篇脱敏样例。

## 5. 本地 Render 模拟

使用实际新镜像并模拟平台变量：

```text
PORT=10000
PERSONAL_AGENT_HTTPS=1
```

结果：

```text
RENDER_PORT_HEALTH={"config_loaded":true,"demo_mode":true,"status":"ok","storage_ready":true}
RENDER_PORT_HOME=200
```

验证容器使用一次性名称并在测试后删除。

## 6. 自动化验证

Render 专项：

```text
Ran 6 tests in 0.010s
OK
```

部署、安全、分发和 CI 联合契约：

```text
Ran 28 tests in 0.226s
OK
```

完整回归：

```text
Ran 218 tests in 18.055s
OK
```

T11 中约 17 分钟的异常耗时未复现；本轮恢复约 18 秒，支持“临时环境延迟”而非稳定性能回退的判断。

## 7. 完成公开部署所需的用户动作

1. 允许整理 commit 并 push 到 Render 可访问的最终仓库；
2. 用户登录 Render 并连接该仓库；
3. 从 `render.yaml` 创建 Blueprint；
4. 确认只创建一个 free Web Service；
5. 等待部署与健康检查通过；
6. 将公开 URL 提供回来；
7. 再执行远程首页、搜索、Research、Memory、HTTPS Cookie 和安全头验收；
8. 新建 `docs/course/DEPLOYMENT_EVIDENCE.md`，不得覆盖本文。

没有完成这些外部动作前，不声明课程要求的线上部署已经完成。
