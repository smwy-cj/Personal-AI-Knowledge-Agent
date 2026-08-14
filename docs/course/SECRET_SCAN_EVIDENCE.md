# 密钥与敏感凭据扫描证据

扫描日期：2026-08-14（Asia/Shanghai）

## 结论

对当前工作区与现有 Git 历史执行高置信度凭据扫描，最终结果为 0 个发现：

```text
secret scan: 0 finding(s) across working-tree, git-history
```

当前历史共 10 个提交。扫描同时覆盖未提交的新文件，因此本轮新增的课程交付材料也在范围内。

## 扫描器与规则

使用仓库内无第三方依赖的 `scripts/scan_secrets.py`。它检查：

- OpenAI、GitHub、GitLab 常见令牌格式；
- AWS Access Key 标识；
- 私钥头；
- URL 中的明文用户名和密码。

输出只包含规则、文件、行号和 12 位 SHA-256 指纹，不输出匹配到的秘密值。自动测试覆盖了命中、占位符忽略和结果脱敏行为。

## 执行方式

```powershell
python scripts/scan_secrets.py --working-tree --git-history
```

此外：

- `.gitlab-ci.yml` 在单元测试前执行工作区扫描；
- `Dockerfile.verify` 在干净 Linux 镜像中先扫描再验收；
- `.gitignore` 排除 `.env`、`.env.*` 与扫描报告，同时保留无秘密的 `.env.example`；
- 运行时凭据通过操作系统密钥环或显式环境变量解析，不写入项目配置。

## 处理记录与限制

扫描规则开发时，测试样例中的模拟私钥头和带凭据 URL 曾被正确识别。测试数据改为运行时拼接后，扫描能够区分“扫描器测试材料”与静态泄漏，而测试仍会验证真实规则。

本工具面向高置信度已知格式，并非熵分析或完整取证工具。最终提交前仍应在远程 CI 再执行一次；若课程环境提供 Gitleaks 等独立工具，可将其作为第二道扫描，但不能代替当前工作区和历史的人工复核。

