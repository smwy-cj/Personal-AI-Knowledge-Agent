# 干净环境验证证据

验证日期：2026-08-14（Asia/Shanghai）

## 结论

项目已在独立的 Linux 容器环境中完成从依赖安装到验收测试的复验。最终构建成功，225 项测试全部通过，命令行帮助、示例知识库同步、成本报告、账单核对与质量基线流程均通过烟雾检查。

## 验证环境

- 主机：Windows，Docker Desktop Linux 容器
- 基础镜像：`python:3.12-slim`
- 验证定义：仓库根目录的 `Dockerfile.verify`
- 工作目录：容器内 `/verification`
- 安装方式：只依据 `pyproject.toml` 从源码安装
- 最终镜像：`personal-ai-knowledge-agent:verification`
- 镜像摘要：`sha256:b3b8dbb41417e92da1e27dc7660c352417dd237a870df2cf8f41c4208339255c`
- 镜像大小：87,711,491 字节

## 验证命令

```powershell
docker build -f Dockerfile.verify -t personal-ai-knowledge-agent:verification .
```

镜像构建阶段依次执行：

```text
python -m scripts.scan_secrets --working-tree
python -m scripts.verify
```

最终结果：

```text
secret scan: 0 finding(s) across working-tree
Ran 225 tests in 20.912s
OK
```

主机环境也再次运行 `python scripts/verify.py`，结果为 225 项测试全部通过（18.557 秒）。

## 发现并修正的问题

第一次 Linux 复验暴露出验证上下文缺少必要文件；补齐后，又发现 `scripts` 与 `tests` 在不同启动方式下的模块导入差异。最终通过显式包标记、模块方式调用以及在验证入口加入项目根目录解决。期间未出现核心业务测试失败。

这些问题说明本次验证不是对已有本机环境的简单重复，而是实际覆盖了 Linux 文件布局和模块解析差异。

## 边界

- 本证据证明当前源码可在全新 Linux 镜像中安装并通过自动验收，不等同于真实公网平台已经部署。
- 构建依赖 Docker 可访问 Python 基础镜像和依赖源；离线环境需预先缓存依赖。
- 外部模型调用不是通过条件；演示与验收默认使用离线、无付费密钥路径。

