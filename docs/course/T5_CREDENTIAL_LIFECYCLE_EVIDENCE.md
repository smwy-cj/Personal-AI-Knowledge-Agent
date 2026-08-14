# T5 凭据生命周期与 Provider 接入证据

## 1. 任务状态

- 日期：2026-08-13
- 对应计划：T5
- 对应规格：`SPEC.md`、`SPEC_v2.md`
- 状态：本地实现和验证完成，尚未提交 commit 或创建 PR

## 2. 实现范围

新增：

- `tests/test_credential_cli.py`
- `tests/test_credential_resolution.py`
- `docs/course/CREDENTIAL_CLI_GUIDE.md`
- 本证据文件

修改代码/配置：

- `src/personal_ai_agent/credentials.py`
- `src/personal_ai_agent/cli.py`
- `src/personal_ai_agent/application.py`
- `src/personal_ai_agent/provider_adapters.py`
- `pyproject.toml`

没有修改任何原有 Markdown 文档。

## 3. 红灯证据

新增测试首次运行得到：

```text
TypeError: main() got an unexpected keyword argument 'credential_store'
ImportError: cannot import name 'CredentialResolver'
```

共 5 项错误，证明 CLI 注入边界和解析器尚未实现。

## 4. 实现结果

### 4.1 CLI

新增命令：

```text
credential-set <provider-id>
credential-status <provider-id>
credential-delete <provider-id>
```

- `set` 通过 `getpass` 隐藏读取；
- 未知 Provider 在读取 secret 前失败；
- 重复 set 覆盖旧值；
- status 不返回任何凭据派生信息；
- delete 幂等。

### 4.2 Credential Resolver

- keyring 优先；
- 只有配置显式声明环境变量名称时才允许环境变量后备；
- 每次 Provider 调用重新解析，支持运行时更新；
- 模型与 Embedding 使用同一解析契约；
- 无认证本地 Provider 保持兼容。

### 4.3 Provider 接入

- Application Service 向模型和 Embedding Adapter 注入 resolver；
- Provider Adapter 不直接持久化凭据；
- 配置声明凭据来源但解析失败时，在发出 HTTP 请求前失败；
- 错误不包含 key 值。

### 4.4 分发依赖

`pyproject.toml` 新增：

```toml
dependencies = ["keyring>=25.7,<26"]
```

选择 25.7 系列是因为项目支持 Python 3.9+，而 PyPI 当前 25.7 元数据显示其要求 Python 3.9+。Linux 是否存在可用 Secret Service/KWallet backend 仍取决于目标系统；代码不会用不安全明文 backend 静默降级。

## 5. 回归中发现的问题

第一次完整回归有 1 项失败：已有无认证 localhost Provider 被 resolver 误判为必须配置凭据。

修复后规则：

- 配置存在 `credential_env`：凭据是必需的；
- 配置没有 `credential_env`：凭据可选；
- 可选 Provider 的 keyring 中存在凭据：使用该凭据；
- 可选 Provider 没有凭据：不发送 Authorization header。

新增测试 `test_resolver_keeps_unauthenticated_local_provider_optional` 防止回归。

## 6. 最终验证

凭据与 Provider 相关专项测试：

```text
Ran 31 tests in 0.050s
OK
```

完整验证：

```powershell
python scripts/verify.py
```

结果：

```text
Ran 165 tests in 11.512s
OK
```

退出码：0。

## 7. 安全测试覆盖

- 隐藏输入可注入测试；
- stdout/stderr 不含标记 secret；
- keyring 优先于环境变量；
- 环境变量仅在显式命名时使用；
- Provider 在每次调用时解析最新 key；
- 模型和 Embedding 均接入；
- 未知 Provider 不读取输入；
- 更新、状态、删除和重复删除；
- backend 不可用和覆盖失败；
- 无认证 localhost Provider 兼容。

## 8. 尚待外部验证

- 在真实 Windows Credential Locker、macOS Keychain 和 Linux Secret Service 上的人工验收；
- 正常联网安装 `keyring` 依赖；
- 干净机器验证；
- 容器/云平台 secret 注入；
- commit、PR 和代码评审。

因此，T5 的代码与离线验收完成，但课程最终 AC-06 仍需要 T13 的真实环境证据。
