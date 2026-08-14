## 变更目标

<!-- 用 2–4 句话说明本 PR 解决的课程或产品问题。 -->

## 规格与计划

- 对应 SPEC/PLAN：
- Agent/任务来源：
- 学生人工决策与修改：
- 已知流程偏离：

## 变更范围

- [ ] 实现与配置
- [ ] 自动测试
- [ ] 凭据与隐私边界
- [ ] 分发/部署
- [ ] 课程文档与证据

## 阶段一：规格合规评审

- 评审人：
- 评审 commit：
- 结论：
- 发现与处理：

## 阶段二：代码质量评审

- 评审人：
- 评审 commit：
- 结论：
- 发现与处理：

## 验证

```text
python scripts/scan_secrets.py --working-tree --git-history
python scripts/verify.py
docker build -f Dockerfile.verify -t personal-ai-knowledge-agent:verification .
```

- [ ] 聚焦测试通过
- [ ] 完整本地验收通过
- [ ] 干净 Linux 验收通过
- [ ] 工作区和 Git 历史秘密扫描无发现
- [ ] 远程 pipeline 对本 PR 最新 commit 通过
- [ ] 公网部署（如适用）已复验

## 安全与隐私

- [ ] 不包含真实 API key、`.env`、个人 Vault、SQLite 或用户数据
- [ ] 错误、日志和截图不暴露秘密或私人正文
- [ ] 公开演示保持 demo mode 和 fake Provider
- [ ] 新增外部依赖及其许可证已经核验

## 未完成项

<!-- 明确写出尚未完成、需要外部账号或学生本人处理的事项，不要留空。 -->

