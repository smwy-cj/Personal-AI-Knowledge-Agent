# T4 凭据存储抽象实施证据

## 1. 任务信息

- 日期：2026-08-13
- 对应计划：T4
- 对应规格：`SPEC.md`、`SPEC_v2.md`
- 状态：实现与本地验证完成，尚未提交 commit 或创建 PR

## 2. 新增文件

- `src/personal_ai_agent/credentials.py`
- `tests/test_credentials.py`

本任务没有修改既有业务文件，也没有访问真实操作系统密钥环。

## 3. 红灯证据

新增测试后，使用正确源码路径运行：

```powershell
$env:PYTHONPATH='src'
python -m unittest tests.test_credentials -v
```

失败原因：

```text
ModuleNotFoundError: No module named 'personal_ai_agent.credentials'
```

这证明失败来自待实现的凭据模块，而非断言错误。

备注：第一次直接运行测试时先因源码目录未加入模块路径而失败；随后按项目源码布局重新执行，才得到上述有效红灯。该环境问题不冒充功能测试失败。

## 4. 最小实现

新增能力：

- `CredentialStore` 协议；
- 不含明文的 `CredentialStatus`；
- `InMemoryCredentialStore`，供确定性离线测试使用；
- `KeyringCredentialStore`，通过注入 backend 测试；
- 延迟加载系统 `keyring` 的 `from_system()`；
- 固定 service name `personal-ai-knowledge-agent`；
- 固定 username `provider:<provider_id>`；
- backend 不可用时明确失败；
- 幂等删除；
- 更新失败不主动删除旧值；
- Provider ID 与空凭据校验；
- 安全错误文本不拼接凭据。

## 5. 绿灯证据

凭据专项测试：

```text
Ran 7 tests in 0.001s
OK
```

覆盖：

1. 保存、状态、覆盖和删除；
2. 状态对象不泄漏凭据；
3. 非法 Provider ID 和空凭据拒绝；
4. Unicode 凭据原样保存；
5. 稳定 keyring 命名空间；
6. backend 不可用；
7. 覆盖失败保留旧值并隐藏新值；
8. 重复删除返回 false。

完整回归：

```powershell
python scripts/verify.py
```

结果：

```text
Ran 156 tests in 11.985s
OK
```

验证脚本退出码为 0。原有 149 项测试和新增 7 项测试全部通过。

## 6. 安全边界

- 测试使用 fake backend，没有读取或写入开发者真实密钥环。
- 代码不提供明文文件后端。
- `CredentialStatus` 不包含掩码、长度、前后缀或明文。
- 系统 `keyring` 依赖尚未加入正式分发配置；`from_system()` 在依赖缺失时安全失败。
- 环境变量后备和 Provider 接入属于 T5，本任务没有改变现有 Provider 行为。

## 7. 尚未完成

- CLI 隐藏录入、状态和删除命令；
- keyring 优先、环境变量后备的 Credential Resolver；
- Provider Adapter 接入；
- 正式依赖安装和干净机器验证；
- commit、PR 与两阶段评审。

因此，本证据只证明 T4 存储抽象完成，不代表 SPEC AC-06 已整体完成。
