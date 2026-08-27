# Retrieval Evaluation v2 指南

`retrieval_dataset_v2` 用于在不把私人查询或知识正文写入报告的前提下，评测多语言检索、查询类型、Chunk 定位和无答案误召回。

## Case Schema

每个 Case 必须包含：

| 字段 | 说明 |
|---|---|
| `case_id` | 不含用户信息的稳定标识符 |
| `query` | 仅保存在本地数据集中的查询；不会进入评测报告 |
| `language` | BCP 47 风格语言标识，例如 `zh-CN`、`en` |
| `query_type` | `factual`、`conceptual`、`navigational`、`tag`、`link`、`synonym` 或 `no_answer` |
| `expects_answer` | 是否期望知识库中存在答案 |
| `expected_paths` | 期望命中的 Vault 相对路径；无答案 Case 必须为空 |
| `expected_chunks` | 可选的 `{path, heading}` 列表；无答案 Case 必须为空 |

`query_type=no_answer` 必须与 `expects_answer=false` 同时使用。其他查询类型必须有至少一个期望路径。

## 报告与指标

v2 输出 `retrieval_eval_report_v2`，保留 Recall@K、Hit Rate@K、MRR@K 和 P50/P95，同时增加：

- `chunk_recall_at_k`：带 Chunk 标签的 Case 中，命中的期望路径和标题组合比例；
- `no_answer_false_positive_rate`：无答案 Case 中仍返回结果的比例；
- `answer_case_count`、`no_answer_case_count`、`chunk_case_count`：解释指标分母。

逐 Case 报告只包含 Case ID、语言、查询类型、计数、是否误召回、倒数排名和延迟。它不包含查询、路径、标题、Chunk ID 或检索正文。

## 中文关键词检索策略

SQLite FTS5 的默认 `unicode61` tokenizer 不会把连续中文自然问句自动切成词。当前关键词引擎因此采用两条明确路径：

- 不含中文的查询继续使用 FTS5 严格 AND 检索；FTS5 无结果时才进入确定性兼容回退；
- 含中文的查询提取去重的 CJK 双字片段，过滤少量通用问句片段，并以标题、Heading、正文和文档元数据的字段权重确定性排序；
- 查询中的英文标识符（例如 `Agent Harness`、`Q-learning`）保留为精确锚点，避免仅凭“模型”“算法”等通用中文词误召回；
- 标签、Wiki Link、Frontmatter 和相对路径参与元数据匹配，使标签、链接和导航查询不依赖正文偶然重复；
- 每篇文档最多占用前列中的两个 Chunk，避免单篇长笔记挤出其他相关来源；
- 纯中文查询必须满足最少命中数和覆盖率；这项保护用于控制无答案问题的误召回。

这是一条无外部中文分词依赖、结果可复现的本地基线。若未来引入分词器或 Embedding，必须在独立测试集上同时比较召回、Chunk Recall、无答案误召回和延迟，不能只看正例召回。

## 本地运行

```powershell
personal-ai-agent --config agent.local.config.json sync
personal-ai-agent --config agent.local.config.json eval-retrieval evaluations/retrieval.v2.example.json
```

`--engine` 支持 `keyword`、`vector` 和 `hybrid`。后两者需要先执行 `vector-sync`，并通过 `--provider` 指定 Embedding Provider：

```powershell
personal-ai-agent --config agent.local.config.json vector-sync --provider embed-local
personal-ai-agent --config agent.local.config.json eval-retrieval `
  evaluations/private/retrieval.test.json `
  --engine vector `
  --provider embed-local
```

可选门禁示例：

```powershell
personal-ai-agent --config agent.local.config.json eval-retrieval `
  evaluations/retrieval.v2.example.json `
  --minimum recall_at_k=0.8 `
  --minimum chunk_recall_at_k=0.7 `
  --maximum no_answer_false_positive_rate=0.1 `
  --maximum p95_latency_ms=500
```

## 私人数据集制作规则

1. 先复制 v2 样例到 Git 忽略的本地路径，不直接修改并提交真实查询；
2. Case ID 使用随机或主题类别标识，不使用姓名、项目代号或笔记标题；
3. 对查询中的姓名、账号、地址、公司内部术语和秘密进行替换；
4. 期望路径若含私人信息，也只保存在本地数据集；报告不会复制这些路径；
5. 先保留一部分 Case 作为独立测试集，避免用同一批查询同时调参与验收；
6. 运行秘密扫描不能证明查询已充分匿名化，提交前仍需人工审查。

仓库样例位于 `evaluations/retrieval.v2.example.json`，只使用固定脱敏 Fixture。

完成至少两个 Case 后，可以确定性划分调参与独立测试集：

```powershell
python scripts/prepare_retrieval_dataset.py `
  evaluations/private/retrieval.all.json `
  --tuning-output evaluations/private/retrieval.tuning.json `
  --test-output evaluations/private/retrieval.test.json `
  --test-ratio 0.2
```

划分先按 `query_type` 分层，再依据数据集名称和 Case ID 的 SHA-256 排序；只要某类型至少有两个 Case，就尽量保证 tuning 和 test 两边都有样本。同一输入会得到相同结果，查询内容不参与划分，也不会输出到终端。目标文件默认拒绝覆盖；确认需要替换时显式传入 `--force`。`evaluations/private/` 已被 Git 忽略。

调参期间只能重复运行 tuning 集；阈值、停用片段、字段权重和文档多样性规则冻结后，test 集只运行一次并记录结果。若 test 结果不理想，应先记录失败，再创建下一版数据划分，不能继续针对同一 test 集调参。

## 本地真实 Keyword 基线（2026-08-28）

真实 Vault 数据集只保存在 `evaluations/private/`，以下报告不包含查询、笔记路径或正文：

| 数据集 / 引擎 | Case | 可回答 / 无答案 | Recall@10 | MRR@10 | Chunk Recall@10 | 无答案误召回 | P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| tuning / keyword | 66 | 59 / 7 | 100% | 96.15% | 92.59% | 0% | 15 ms |
| tuning / vector | 66 | 59 / 7 | 62.71% | 59.56% | 62.96% | 0% | 125 ms |
| tuning / hybrid | 66 | 59 / 7 | 100% | 94.77% | 98.15% | 0% | 110 ms |
| 独立 test / keyword | 16 | 13 / 3 | 92.31% | 81.41% | 75.00% | 0% | 16 ms |
| 独立 test / vector | 16 | 13 / 3 | 69.23% | 53.46% | 58.33% | 0% | 250 ms |
| 独立 test / hybrid | 16 | 13 / 3 | 92.31% | 76.92% | 83.33% | 0% | 110 ms |

keyword、vector 与 hybrid 的 test 均在各自参数冻结后只运行一次。Hybrid 采用 BGE 中文 512 维模型、模型特定查询门槛 `0.82` 和 RRF 1:1；13 条可回答查询命中 12 条，唯一漏检按匿名 Case ID 留在本地报告中，未用于继续调参。这组数字是当前机器、当前 Vault 与当前模型的本地基线，不代表其他知识库或硬件上的通用 SLA。
