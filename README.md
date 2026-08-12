# Personal-AI-Knowledge-Agent

基于 Obsidian 与 RAG 的个人智能知识管理系统。项目正按“状态图 + Workflow + 可治理记忆”的路线，从架构设计进入工程实现。

## 当前进度

Iteration 0 已建立最小 Agent Runtime：结构化 Task State、计划依赖校验、显式状态机、Workflow Registry、预算控制、有限重试与基础 Trace。

Iteration 1 已加入版本化 JSON 序列化、SQLite 任务快照、追加式 Checkpoint 历史，以及 `RUNNING` / `VERIFYING` 任务恢复。恢复采用 at-least-once 语义，有副作用的 Workflow 必须保证幂等。

Iteration 2 已加入 Obsidian Markdown 增量摄取：文件指纹、Frontmatter、标题层级、Wiki Link、标签、引用行号，以及 SQLite 文档与 Chunk 元数据索引。

## 摄取 Obsidian Vault

```python
from personal_ai_agent import ObsidianVaultIngester, SQLiteKnowledgeRepository

repository = SQLiteKnowledgeRepository("data/knowledge.sqlite3")
result = ObsidianVaultIngester("D:/Notes/MyVault", repository).sync()
print(result)
```

同步会忽略 `.obsidian` 目录，并报告新增、更新、未变化、删除和失败文件数量。当前要求 Markdown 使用 UTF-8 或 UTF-8 BOM 编码。

## 关键词检索

```python
from personal_ai_agent import KeywordSearchEngine, KeywordSearchQuery

engine = KeywordSearchEngine(repository)
results = engine.search(
    KeywordSearchQuery(
        "agent memory",
        path_prefix="Projects/",
        tags=["agent"],
        limit=10,
    )
)
```

结果粒度是 Chunk：同一文档可能返回多个标题块。每项结果都包含 Vault、相对路径、标题层级、正文、1-based 起止行号、归一化分数、命中方式和匹配词。运行环境支持 FTS5 时默认使用全文索引，否则自动使用确定性回退。

## 向量与混合检索

项目通过 `EmbeddingProvider` 协议接入任意本地或云端嵌入模型。适配器必须提供稳定的 `provider_id`、向量维度和批量 `embed()`；`provider_id` 应包含模型名与配置版本，避免复用不兼容的缓存。

```python
from personal_ai_agent import (
    HybridSearchEngine,
    HybridSearchQuery,
    KeywordSearchEngine,
    SQLiteVectorIndex,
)

vector_index = SQLiteVectorIndex(repository, embedding_provider)
vector_index.sync()  # 只计算新增、变化或模型版本不兼容的 Chunk

hybrid = HybridSearchEngine(
    KeywordSearchEngine(repository),
    vector_index,
)
results = hybrid.search(HybridSearchQuery("长期记忆治理", limit=10))
```

当前 SQLite 向量索引使用精确余弦扫描，适合个人本地 MVP；混合检索使用加权 Reciprocal Rank Fusion，不直接混合 BM25 与余弦的原始分数。大规模知识库后续可替换 ANN 后端，而无需修改上层检索契约。

## Research Workflow

`ResearchWorkflow` 是首个接入 Orchestrator 的领域工作流。当前职责是可靠地准备研究证据，不假装已经完成模型综合：

```python
from personal_ai_agent import (
    AgentTaskState,
    CitationIntegrityVerifier,
    Orchestrator,
    PlanStep,
    WorkflowRegistry,
    register_research_workflow,
)

registry = WorkflowRegistry()
register_research_workflow(registry, hybrid)
runtime = Orchestrator(
    registry,
    verifier=CitationIntegrityVerifier(repository),
)

state = runtime.run(
    AgentTaskState.create("thread-1", "总结长期记忆治理方案"),
    [PlanStep("retrieve", "research", "research.retrieve")],
)
```

输出包含 `research_evidence_pack_v1`、Markdown 研究上下文、Task Evidence 和 retrieved context。Verifier 会回查当前数据库，验证 Chunk、文档、Vault、路径、行号、内容哈希及证据包引用；来源更新或展示层引用被篡改都会导致任务验证失败。

## Model Gateway 与研究摘要

`ModelGateway` 通过 `ModelProvider` 协议接入模型，Provider 声明能力并负责在请求指定的超时内返回。Gateway 统一执行能力选择、结构校验、有限重试和调用 Trace；只有 Provider 明确抛出的 `RetryableModelError` 会重试，Gateway 终态错误不会再被 Orchestrator 二次重试。

`research.summarize` 只接收已有的 `research_evidence_pack_v1`，模型输出必须符合 `research_summary_v1`：每个非空段落都提供一个或多个有效引用编号。最终 Markdown 由确定性渲染器生成 `[n]` 标记，模型不能自行拼接引用字符串。

Task Trace 会记录：

```text
provider_id / model_id
task_type / prompt_version
input_tokens / output_tokens
latency_ms / attempt_count
```

当前网关本身不使用后台线程强行中断 Provider；Provider 适配器必须使用其 HTTP/SDK 原生 timeout，才能可靠释放连接和计算资源。

## Model Capability Registry

生产配置应使用 `ModelProfile` 显式注册每个 Provider：

```python
from personal_ai_agent import (
    CostLevel,
    ModelCapabilityRegistry,
    ModelGateway,
    ModelProfile,
    PrivacyLevel,
)

registry = ModelCapabilityRegistry([
    ModelProfile(
        provider=local_provider,
        capabilities=frozenset({"structured_output", "chinese", "reasoning"}),
        max_context_tokens=32_000,
        cost_level=CostLevel.LOW,
        max_privacy_level=PrivacyLevel.SENSITIVE,
        priority=10,
    ),
    ModelProfile(
        provider=cloud_provider,
        capabilities=frozenset({"structured_output", "long_context"}),
        max_context_tokens=128_000,
        cost_level=CostLevel.MEDIUM,
        max_privacy_level=PrivacyLevel.PERSONAL,
        priority=20,
    ),
])
gateway = ModelGateway(registry=registry, max_retries=1)
```

路由先排除能力、上下文、成本或隐私不合规的 Provider，再按成本、优先级和注册顺序稳定排序。只有可重试故障才会进入下一 Provider；显式指定 `provider_id` 时禁止跨 Provider fallback。未提供 Profile 的旧式 Provider 默认最多处理 `PERSONAL` 数据，不会被隐式授权处理 `SENSITIVE` 数据。

Task Budget 同时限制：

```text
max_tool_calls
max_model_calls
max_tokens
max_step_retries
max_replans
```

## Memory Governance 与人工确认

`memory.propose` 从已验证的 `research_summary_v1` 段落生成语义记忆候选，并将引用编号映射回真实 Chunk。治理管道执行：

```text
来源检查
→ 敏感信息检查
→ 内容规范化与哈希
→ 完全重复检测
→ 同类型/同主题冲突检测
→ WAITING_USER
→ 显式批准或拒绝
→ memory.persist
```

任务进入 `WAITING_USER` 后，下游持久化步骤保持 `PENDING`，任务和候选可以从 SQLite Checkpoint 恢复。审批必须覆盖每个待决候选；批准与拒绝均记录在候选状态和 Checkpoint 中。

当前 `memory.persist` 仅写入独立的 SQLite Memory Store。它不会直接修改 Obsidian Vault；后续 Vault Writer 必须另外实现目录白名单、安全文件名、原子写入和用户确认，不能绕过这一审批边界。

## 受控 Obsidian Writer

`ControlledObsidianWriter` 只把已经进入 Memory Store 的记忆写入配置的 Vault 托管目录：

```python
from personal_ai_agent import (
    ControlledObsidianWriter,
    ObsidianWritebackWorkflow,
)

writer = ControlledObsidianWriter(
    vault_root="D:/Notes/MyVault",
    managed_directory="Agent/Memory",
    memory_repository=memory_repository,
)
workflow = ObsidianWritebackWorkflow(writer, ingester)
```

写回规则：

- 托管目录必须是 Vault 内的安全相对路径，禁止 `..`、绝对路径和 `.obsidian`；
- 文件名固定为 `<memory_id>.md`，不使用模型生成标题作为路径；
- 同目录临时文件写入、刷新后使用原子替换；
- Frontmatter 保存 Memory ID、类型、规范化哈希、置信度和 Chunk 来源；
- SQLite 保存 Vault、相对路径、内容 SHA-256 和写入时间收据；
- 相同内容重复调用返回 `unchanged`；
- 原子替换成功但收据尚未保存时，可凭完整所有权标记安全补登记；
- 用户修改或删除托管文件均视为 drift，拒绝覆盖或自动重建；
- 写入完成后运行 Vault 增量摄取，并返回 `obsidian_writeback_receipt_v1`。

## Application Service 与 CLI

`ApplicationService` 统一装配 Task、Knowledge、Memory 三个 SQLite Store，以及 Vault Ingester、关键词检索和受控 Writer。CLI 使用无密钥 JSON 配置；相对路径以配置文件所在目录为基准，运行数据目录必须与 Vault 完全分离。

先复制 `agent.config.example.json` 为被 `.gitignore` 排除的 `agent.config.json`，然后修改 Vault 路径：

```powershell
$env:PYTHONPATH = "src"
python -m personal_ai_agent --config agent.config.json config-validate
python -m personal_ai_agent --config agent.config.json sync
python -m personal_ai_agent --config agent.config.json search "memory governance" --limit 5
```

运维与人工确认命令：

```text
task-show <task_id>                 查看持久化任务快照
task-list <thread_id>               查看会话中的任务
task-cancel <task_id>               持久化请求取消任务
task-events <task_id>               查看脱敏结构化运行事件
events-prune [--older-than-days N]  预览事件保留策略；增加 --apply 才实际清理
memory-pending <task_id>            查看待决记忆候选
memory-resolve <task_id> --approve <candidate_id> [--reject <candidate_id>]
memory-list                         查看已持久化语义记忆
```

成功结果输出稳定 JSON；配置、参数或资源错误输出到 stderr 并返回退出码 `2`。配置文件拒绝 token、password、secret、API key 等字段。模型凭据应由未来的 Provider Adapter 从进程环境或专用密钥服务读取，不能进入项目配置。

Provider 在配置中只声明 ID、端点、模型、能力和凭据环境变量名称，密钥值不进入配置、数据库或公开配置摘要。携带凭据的端点强制使用 HTTPS；无凭据 HTTP 仅允许连接本机回环地址。当前适配器支持 OpenAI-compatible 的 `/chat/completions` 和 `/embeddings` JSON 协议，不依赖供应商 SDK。

```powershell
$env:PERSONAL_AGENT_MODEL_KEY = "由本机密钥管理方式注入"
$env:PERSONAL_AGENT_EMBEDDING_KEY = "由本机密钥管理方式注入"
python -m personal_ai_agent --config agent.config.json vector-sync --provider primary-embedding
python -m personal_ai_agent --config agent.config.json hybrid-search "memory governance" --provider primary-embedding
python -m personal_ai_agent --config agent.config.json research-run "总结记忆治理方案" --thread-id cli-1 --model-provider primary-model --embedding-provider primary-embedding
```

`research-run` 执行检索、结构化摘要和记忆候选治理；存在可接受候选时，任务持久化并停在 `WAITING_USER`，随后使用 `memory-pending` 和 `memory-resolve` 逐项决策。省略 `--embedding-provider` 时研究检索使用关键词引擎，不会暗中调用向量服务。多个向量 Provider 并存时，`vector-sync` 与 `hybrid-search` 必须显式选择 Provider。

Provider 可靠性边界：

- 模型的可重试故障使用有上限的指数退避，服务端合法 `Retry-After` 优先但仍受本地上限约束；
- 退避发生在下一次真实调用前，因此不会突破 `max_model_calls`；
- 取消令牌可在调用前和重试等待期立即终止，已经发出的同步 HTTP 请求由原生 timeout 收敛；
- Embedding 请求遇到 HTTP `413` 时按原顺序递归二分，单条输入仍超限则明确失败；
- HTTP 错误正文不会进入异常、Trace 或任务快照，避免意外记录供应商返回的敏感内容。

每个 Provider 可配置跨进程共享限流：

```json
{
  "requests_per_minute": 60,
  "max_rate_limit_wait_seconds": 30
}
```

模型 Provider 还可声明公开价格元数据：

```json
{
  "input_cost_per_million_tokens_usd": 2.5,
  "output_cost_per_million_tokens_usd": 10
}
```

价格按每百万 Token 的美元单价配置。系统只对成功响应中供应商实际返回的输入/输出 Token 计价，以整数微美元写入脱敏事件；失败调用若没有 Usage 数据则无法估算，因此聚合金额是可审计估算值，不是供应商账单。

限流器通过独立 SQLite 数据库原子预约调用时隙，同一数据目录下的多个 CLI/进程共享配额。它采用平滑间隔：每分钟 60 次表示约每秒一个调用，而不是允许一分钟开始时同时突发 60 次。预计等待超过本地硬上限时调用直接失败；等待模型请求时可响应任务取消。Embedding 的每个真实 HTTP 子批次分别消耗一个时隙。

执行控制面现已提供 SQLite 租约、后台心跳和持久化取消请求。同一任务只有一个活跃 owner 可以执行或恢复；租约过期后其他进程才能接管，旧 owner 在每次 Checkpoint 前会重新验证所有权。`task-cancel` 对闲置或等待确认的任务立即落盘为 `CANCELLED`；对正在执行的任务登记取消请求，由运行者在步骤边界、Provider 调用前或重试等待期确认并写入最终状态。

取消仍采用协作语义：已经发出的同步 HTTP 请求不能安全强杀，而是依靠原生 timeout 收敛；取消请求会在请求返回后的下一个运行边界生效。

项目总体能力与路线状态见 [项目状态总览](docs/PROJECT_STATUS.md)。

## Observability 与 Retrieval Evaluation

运行事件存放在独立的 `observability.sqlite3`，使用事件类型与字段双白名单。事件可记录状态、执行器、步骤耗时、错误类型、Provider/模型 ID、Prompt 版本、Token 和重试延迟，但不接受用户问题、Prompt 正文、请求 Payload、证据/回答正文或凭据。`task-events` 因此适合排查生命周期和成本，不是完整内容审计日志。

事件写入采用 best-effort：SQLite/I/O 故障不会改变任务业务状态；非法字段或敏感字段仍会被验证层拒绝，以便开发阶段及时发现观测契约违规。

检索评测数据集使用 `retrieval_eval_v1`：

```json
{
  "schema": "retrieval_eval_v1",
  "name": "my-baseline-v1",
  "cases": [
    {
      "case_id": "memory-governance-1",
      "query": "memory governance approval",
      "expected_paths": ["Architecture.md"]
    }
  ]
}
```

运行基线：

```powershell
python -m personal_ai_agent --config agent.config.json eval-retrieval evaluations/retrieval.example.json --limit 10
python -m personal_ai_agent --config agent.config.json eval-retrieval evaluations/retrieval.example.json --engine hybrid --provider primary-embedding --limit 10
python -m personal_ai_agent --config agent.config.json eval-retrieval evaluations/retrieval.example.json --minimum recall_at_k=0.9 --maximum p95_latency_ms=250
python -m personal_ai_agent --config evaluations/evaluation-agent.config.example.json sync
python -m personal_ai_agent --config evaluations/evaluation-agent.config.example.json eval-retrieval evaluations/retrieval.example.json --baseline evaluations/baselines/retrieval.keyword.example.json
```

报告输出 `Recall@K`、`Hit Rate@K`、`MRR@K`、P50/P95 查询延迟及逐 Case 的命中计数和倒数排名。报告不回显查询和检索正文；数据集本身仍包含查询，应该只提交经过审查、无敏感信息的固定评测语料。

运行聚合：

```powershell
python -m personal_ai_agent --config agent.config.json observability-summary --limit 1000 --minimum task_success_rate=0.95 --maximum model_p95_latency_ms=30000 --maximum estimated_cost_usd=1
python -m personal_ai_agent --config agent.config.json events-prune --older-than-days 90
python -m personal_ai_agent --config agent.config.json events-prune --older-than-days 90 --apply
```

聚合报告包含最近 N 条脱敏事件窗口内的任务终态分布、成功率、步骤成功/失败数、模型完成/重试数、输入/输出 Token、估算美元成本以及步骤和模型 P50/P95 延迟。它是运行健康视图，不是全历史账单。

`observability_retention_days` 默认是 `90`。`events-prune` 默认只返回截止时间和匹配数量，不删除数据；只有显式提供 `--apply` 才执行事务性清理，并保留一条仅含保留天数和删除数量的 `events_pruned` 审计事件。

### Research 与 Memory 离线评测

Research Summary 数据集使用 `research_summary_eval_v1`，为每个摘要段落提供人工标注的期望引用 ID 集合；Memory 数据集使用 `memory_governance_eval_v1`，标注期望治理状态、原因和是否需要人工审批，并可声明用于测试重复/冲突的既有记忆。示例见 `evaluations/`。

```powershell
python -m personal_ai_agent --config agent.config.json eval-research evaluations/research_summary.example.json --minimum structure_valid_rate=1 --minimum citation_f1=0.9
python -m personal_ai_agent --config agent.config.json eval-memory evaluations/memory_governance.example.json --minimum decision_accuracy=1
```

准确率和成功率使用重复的 `--minimum metric=value` 下限门禁；检索延迟及观测窗口中的步骤/模型延迟、估算成本使用重复的 `--maximum metric=value` 上限门禁。门禁输出包含实际指标、阈值和失败指标名称：

- 达标返回退出码 `0`；
- 评测正常但未达标返回 `3`，stdout 仍包含完整 JSON 报告；
- 数据集、参数或执行错误返回 `2`，错误写入 stderr。

Research 报告衡量结构有效率、段落引用覆盖率、引用集合精确匹配率及引用 Precision/Recall/F1。它衡量人工引用标签一致性，不自动证明摘要文本被证据蕴含或事实为真。Memory 报告衡量规则治理的状态、原因、审批和整体决策准确率，不等同于真实用户接受率。报告只保留 Case ID 与指标，不输出被评测正文。

`eval-retrieval` 的上限指标白名单是 `p50_latency_ms` / `p95_latency_ms`。`observability-summary` 支持 `task_success_rate` 下限，以及步骤/模型 P50/P95 延迟、`estimated_cost_microusd` / `estimated_cost_usd` 上限。错误方向、未知指标、负数、NaN 或 Infinity 会作为配置错误返回退出码 `2`，不会被静默忽略。

### 版本化质量基线

`--baseline` 接收 `quality_baseline_v1` JSON 策略。检索策略绑定数据集名称、检索引擎、K 值和 Embedding Provider；观测策略绑定最近事件窗口大小。作用域不一致时命令拒绝执行，防止把同一组阈值误用到不同评测条件。命令行 `--minimum` / `--maximum` 会覆盖基线中的同名指标，最终报告记录策略名称、作用域和生效阈值，但不记录本地策略文件路径。

仓库提供三篇无个人信息的固定知识笔记、三条检索查询和一个关键词基线。`scripts/verify.py` 会在临时目录从零同步这些笔记并执行基线评测，因此本地与 CI 都能验证数据集、配置、摄取、检索和门禁的完整链路。示例阈值只用于固定小语料的工程回归，不代表真实个人 Vault 或云端 Provider 的生产目标。

### 候选基线与历史对比

检索评测和观测汇总报告现在都包含完整的 `evaluation_scope`，用于证明两次结果是在相同数据集、引擎、K、Provider 或事件窗口下产生。报告可保存后交给两个不依赖 Agent 配置的离线命令：

```powershell
python -m personal_ai_agent baseline-candidate reports/retrieval-current.json --name retrieval-candidate-v2
python -m personal_ai_agent baseline-candidate reports/operations-current.json --name operations-candidate-v2 --minimum-retention 0.99 --maximum-headroom 1.1
python -m personal_ai_agent baseline-compare reports/retrieval-reference.json reports/retrieval-current.json
```

`baseline-candidate` 默认把越高越好的实际指标乘以 `0.98`，把越低越好的延迟/成本指标乘以 `1.20`。输出固定为 `quality_baseline_candidate_v1` 和 `pending_review`，同时记录生成参数、观察值与规范化报告 SHA-256；它不会覆盖现有基线，也不能未经人工审查直接作为 `--baseline` 使用。审查者需要确认数据代表性、零值或小样本造成的过严阈值，并从 `proposed_policy` 提取正式策略。

`baseline-compare` 只接受 Schema 和评测作用域完全一致的报告。它逐指标输出参考值、当前值、绝对/相对变化及 `improved`、`degraded`、`unchanged` 判断；存在任一退化时仍输出完整比较报告，但返回退出码 `3`，可直接用于 CI。候选和比较结果不复制逐 Case 内容、本地报告路径或用户正文，只保存报告指纹。

完整路线见 [实施计划](docs/IMPLEMENTATION_PLAN.md)。

## 本地验证

项目当前只依赖 Python 3.9+ 标准库：

```powershell
python scripts/verify.py
```

该入口统一执行全部单元/集成测试、源码编译检查、CLI 冒烟检查、脱敏固定语料的端到端检索基线、候选基线生成与无退化历史比较。GitHub Actions 会在 Python 3.9、3.11、3.13 以及 Windows/Linux 环境中重复执行，并额外验证安装后的 `personal-ai-agent` 命令。
