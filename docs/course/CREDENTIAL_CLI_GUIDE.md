# Provider 凭据安全管理指南

## 1. 安全模型

本项目使用操作系统密钥环保存本地 Provider 凭据：

- Windows：Windows Credential Locker；
- macOS：Keychain；
- Linux 桌面：Secret Service 或系统支持的安全 backend。

项目通过 Python `keyring` 访问操作系统 backend。配置文件只保存 Provider ID 和可选环境变量名称，不保存 key 值。

固定密钥环命名：

```text
service:  personal-ai-knowledge-agent
username: provider:<provider_id>
```

## 2. 保存或更新

```powershell
personal-ai-agent --config agent.config.json credential-set primary-model
```

命令通过隐藏输入读取凭据，不提供接受明文 key 的命令行参数。重复执行会更新同一 Provider 的凭据。

Provider 必须已经存在于配置的 `model_providers` 或 `embedding_providers` 中。未知 Provider 会在读取 secret 前失败。

## 3. 查看状态

```powershell
personal-ai-agent --config agent.config.json credential-status primary-model
```

输出示例：

```json
{
  "backend_available": true,
  "configured": true,
  "provider_id": "primary-model",
  "source": "keyring"
}
```

输出不会包含明文、掩码值、长度、前缀或后缀。

`source` 可能是：

- `keyring`：操作系统密钥环中存在凭据；
- `environment`：密钥环没有凭据，使用配置显式声明的环境变量；
- `none`：没有可用凭据。

## 4. 删除

```powershell
personal-ai-agent --config agent.config.json credential-delete primary-model
```

第一次成功删除返回 `deleted: true`；再次删除返回 `deleted: false`，不把“不存在”视为异常。

删除 keyring 凭据后，如果 Provider 配置显式声明了 `credential_env` 且目标环境存在该变量，Provider 会使用环境变量后备。

## 5. 解析优先级

每次真实 Provider 调用时重新解析：

1. 操作系统密钥环；
2. 配置 `credential_env` 指定的环境变量；
3. 无凭据。

当配置显式声明 `credential_env` 时，无可用凭据会导致请求前安全失败。未声明 `credential_env` 的本地无认证 Provider 可以继续工作；如果其 Provider ID 在 keyring 中存在凭据，则仍会自动添加认证头。

## 6. 容器和云端

无桌面密钥环的 Docker/云端环境使用平台 secret 注入配置中显式声明的环境变量。项目不会静默创建明文 keyring backend，也不会自动写入 `.env`。

`.env` 只能作为用户明确选择的本地兼容方案，存在明文文件、备份和进程环境可见风险。课程公开演示模式不开放凭据录入，并使用 fake Provider。

## 7. 安全限制

- 系统 backend 不可用时，`credential-set` 明确失败；
- 不支持通过命令行参数传入明文 key；
- 不记录 key 到事件、日志或错误；
- 测试只使用内存 store 和 fake backend；
- 当前不提供跨设备凭据同步；
- 操作系统账户被攻破时，密钥环安全性取决于操作系统自身保护。
