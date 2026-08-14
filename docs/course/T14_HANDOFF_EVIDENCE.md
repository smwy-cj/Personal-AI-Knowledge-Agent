# T14 助教交付入口验证证据

日期：2026-08-14（Asia/Shanghai）

## 本阶段产物

- `README_COURSE.md`：课程入口与运行、安全、分发、验收导航；
- `docs/course/ARCHITECTURE.md`：最终组件、数据流、数据模型、信任边界和部署架构；
- `REFLECTION_GUIDE.md`：学生本人反思的题纲、事实素材和自查规则；
- `AGENT_LOG_v11.md`：本阶段过程记录；
- `docs/course/DELIVERY_REMAINING_FILES_v3.md`：剩余 4 个核心文件盘点。

## TDD 证据

新增 3 项文档交付契约。首次执行时，三个目标文件均不存在，因此结果为 3 项失败；创建文档后，聚焦测试 3/3 通过。

完整一键验收最终结果：

```text
Ran 228 tests in 21.048s
OK
```

更新验证镜像后，独立 Linux 环境最终结果：

```text
secret scan: 0 finding(s) across working-tree
Ran 228 tests in 17.068s
OK
```

最终验证镜像 manifest list 摘要：

```text
sha256:62ec7bc0094911a43b3687f770a2cb766a6864c961fb919b25adbecb50cc46eb
```

工作区及 10 个已有 Git 提交的秘密扫描仍为 0 个发现；新文档 UTF-8 解码未出现替换字符，`git diff --check` 无空白错误。

## 未宣称完成的事项

本阶段没有创建 `REFLECTION.md`，也没有宣称存在公网 URL、公开 registry、远程 pipeline pass、commit/PR/MR 或人工评审。这些事项仍需真实外部行为和学生本人输入。

