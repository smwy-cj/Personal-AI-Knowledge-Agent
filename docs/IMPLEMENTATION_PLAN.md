# Personal AI Knowledge Agent 实施计划

## 目标共识

项目不是一个简单的“提问 → RAG → 回答”应用，而是一个围绕个人知识库运行、能规划和执行研究任务、保留证据、治理长期记忆，并可逐步扩展专业工作流的智能研究系统。

首要工程原则：

- 以有状态的任务编排器为运行核心；
- 先建设 Workflow，再按评测结果决定是否升级为 Sub-Agent；
- Obsidian 保存人类可读知识，运行状态与索引元数据由数据库保存；
- 确定性校验优先于模型自我反思；
- 所有重试、重规划、工具调用和写入行为都必须有预算与 Trace；
- 长期记忆先生成候选，再经过来源、去重、冲突与确认策略。

## 迭代路线

### P0：最小可信闭环

1. 任务状态、计划步骤、预算和状态迁移契约；
2. 单 Orchestrator 与 Workflow Registry；
3. SQLite 状态持久化与恢复（已完成首版）；
4. Obsidian Markdown 增量摄取（已完成首版）；
5. 关键词 + 向量的混合检索接口；
6. Research Workflow，输出可定位的证据与引用；
7. Memory Candidate 与确认后写回；
8. 结构化日志、延迟与 Token/工具成本统计。

验收闭环：读取知识库 → 检索 → 生成带引用结果 → 用户确认 → 写回知识库。

### P1：可靠性增强

加入结构化 Planner、Checkpoint、恢复、Verifier、模型能力路由、Prompt/Workflow 版本和代码沙箱。

### P2：按需多智能体

仅在评测证明单工作流存在上下文、并发或工具隔离瓶颈后，引入 Research、Coding、Reviewer 子智能体及结构化消息协议。

### P3：主动学习

在权限、成本和记忆质量指标稳定后，再实现知识缺口扫描、学习计划、项目跟踪与知识冲突检测。

## 当前进度（Iteration 0—2）

当前已完成 P0 的运行时地基与第一版持久化：

- `AgentTaskState`、`PlanStep`、`TaskBudget` 等稳定数据契约；
- 显式状态迁移表与非法迁移保护；
- 计划依赖和环检测；
- Workflow 注册与确定性调度；
- 工具调用/Token 预算、有限步骤重试；
- 状态迁移、错误、产物、证据和记忆候选的记录；
- 不依赖外部服务的单元测试。
- 版本化 Task State JSON 序列化；
- SQLite 最新快照与追加式 Checkpoint 历史；
- `RUNNING` / `VERIFYING` 阶段的进程中断恢复。
- Vault 路径约束、SHA-256 文件指纹和新增/修改/未变化/删除检测；
- Obsidian Frontmatter、标题层级、Wiki Link 与标签解析；
- 按标题生成带稳定 ID 和 1-based 行号的引用分块；
- SQLite 文档、Chunk、标签和链接元数据索引。

恢复采用 at-least-once 语义：中断时处于 `RUNNING` 的步骤会重置为 `PENDING`，因此未来有副作用的 Workflow 必须使用 `task_id + step_id` 作为幂等键。Checkpoint 写入失败会中止执行，避免系统继续运行却失去审计和恢复能力。

当前解析器支持 Obsidian 常见的扁平 Frontmatter 属性和列表；复杂嵌套 YAML 暂不做推测性解析。代码围栏内的伪标题、标签和 Wiki Link 不进入结构化元数据。

Iteration 3 已完成可引用的关键词检索：SQLite FTS5、无 FTS5 时的确定性回退、Vault/路径/标签过滤，以及统一的 Chunk 级检索结果契约。

Iteration 4 已完成 Embedding Provider 协议、模型版本化 SQLite 向量缓存、精确余弦检索和加权 Reciprocal Rank Fusion。Embedding 与 Vault 摄取显式分离，避免扫描笔记时产生不可见的模型调用和成本。

Iteration 5 已完成第一个 Research Workflow：混合检索被包装为 Orchestrator 的确定性步骤，输出 `research_evidence_pack_v1`、Markdown 研究上下文和结构化 Evidence。Citation Integrity Verifier 会回查当前知识索引，校验 Chunk、文件、Vault、行号、正文、内容哈希和证据包引用一致性。

本阶段明确不把检索片段拼接冒充研究结论。下一增量应实现 Model Gateway 的最小契约与一个可注入的结构化生成步骤，让模型基于已验证 Evidence 生成带 `[n]` 引用的研究摘要；随后由规则 Verifier 检查每个引用编号存在且所有关键段落均有来源。

Iteration 6 已完成最小 Model Gateway、能力匹配、Provider 原生超时契约、有限重试、结构化输出验证和模型调用 Trace。`research.summarize` 基于 Evidence Pack 生成 `research_summary_v1`，所有段落必须包含合法引用，最终 Markdown 由代码确定性渲染。

Iteration 7 已完成 Model Capability Registry 与约束路由：能力、隐私级别、上下文规模、成本等级和优先级共同决定候选顺序；可重试故障支持受控 fallback，显式 Provider 不会被静默替换。Task Budget 新增 `max_model_calls`，fallback 与重试的每次真实 Provider 调用都会计入预算和 Trace。

真实 DeepSeek/GLM/OpenAI 适配器仍应在配置层按需接入，不把密钥或供应商 SDK 渗透进 Workflow。下一增量应实现 Memory Candidate 管道与人工确认状态：从已验证研究摘要生成候选知识，执行类型分类、来源检查、去重和冲突检测，并在用户批准前停留于 `WAITING_USER`，禁止直接写回 Obsidian。

Iteration 8 已完成 Memory Candidate Governance：摘要段落生成带 Chunk 来源的语义候选，敏感内容、缺少来源和完全重复自动拒绝，同主题差异标记冲突；待决候选使任务暂停于 `WAITING_USER`。用户必须逐项批准或拒绝，随后任务从 Checkpoint 恢复，仅将批准项写入独立 SQLite Memory Store。

本阶段仍不直接写回 Obsidian。下一增量应实现受控 Obsidian Writer：固定目标目录、路径穿越防护、安全文件名、原子写入、内容哈希幂等、写入收据和增量重新索引；只有 `PERSISTED` 且策略允许的记忆才能成为写回候选。

Iteration 9 已完成受控 Obsidian Writer：写入限定在 Vault 的托管目录，使用稳定 Memory ID 文件名和同目录原子替换；SQLite 收据记录路径与内容哈希，实现幂等、崩溃后补登记和用户修改/删除漂移检测。`obsidian.writeback` 只处理 `PERSISTED` 记忆，写后触发增量摄取并返回结构化收据。

至此 P0 的核心闭环已经具备工程实现：摄取 → 混合检索 → Research Evidence → 结构化模型摘要 → 引用验证 → Memory Governance → 人工确认 → Memory Store → 受控 Vault 写回 → 重新索引。下一增量应整理 Application Service/CLI，把这些组件装配为一个可运行命令，并补真实配置加载、数据库路径与 Vault 路径校验，但不内置任何供应商密钥。

Iteration 10 已完成 Application Service 与本地 CLI：使用无密钥 JSON 配置统一装配三个 SQLite Store、Vault Ingester、关键词检索和受控 Writer；路径相对配置文件解析，Vault 必须存在，运行数据目录不得位于 Vault 内或包含 Vault，托管目录禁止绝对路径、`..` 和 `.obsidian`。CLI 提供配置校验、增量同步、可引用检索、任务读取、待决记忆查询、逐项审批恢复和记忆列表，并以稳定 JSON 及明确退出码对接后续 UI/插件。

本轮没有把真实模型或向量供应商硬编码进 CLI。下一增量应定义 Provider Adapter 配置协议与凭据解析边界：公开配置只引用 Provider ID，凭据只从环境变量或密钥服务读取；在此基础上再增加 `research-run`、`vector-sync` 和混合检索命令，并补进程级超时、速率限制与端到端评测。

Iteration 11 已完成 Provider Adapter 与完整 CLI 研究入口：公开配置声明 OpenAI-compatible 端点、模型、能力、上下文、成本、隐私级别和 `credential_env`，凭据值仅在请求发起时从环境读取。远程明文 HTTP、URL 内嵌凭据和配置内密钥字段会被拒绝；HTTP/协议错误不会回显响应正文。`vector-sync` 显式维护指定 Provider 的版本化向量缓存，`hybrid-search` 执行加权 RRF，`research-run` 串联检索、模型摘要、引用验证、Memory Governance、Checkpoint 与后续受控写回。

下一增量应集中于生产可靠性：为不同 Provider 增加协议能力探测、指数退避与 `Retry-After`、批量嵌入自适应拆分、进程级取消和速率限制；同时建立固定评测语料，衡量检索命中、引用完整率、摘要忠实度、记忆候选接受率、延迟与真实成本。供应商特有差异应留在 Adapter 内，不能渗透 Workflow。

Iteration 12 已完成第一组生产可靠性原语：`RetryableModelError` 可携带服务端等待提示，Model Gateway 在重试与 Provider fallback 前执行可注入、指数增长且有上限的退避；`Retry-After` 支持秒数和 HTTP 日期，非法值安全忽略。`CancellationToken` 在调用前与退避等待期提供协作取消，不创建无法回收的后台线程。Embedding Adapter 对 HTTP `413` 自动按顺序二分批次，单条超限终止，避免无限拆分；错误正文仍不进入持久化状态。

跨进程取消仍需任务租约、持久化取消请求和执行者心跳，不能用单纯修改 Task Snapshot 冒充。下一增量应实现这套执行控制面，并加入共享 Provider 速率限制；随后建立离线评测数据集和基线报告，将检索 Recall@K、引用完整率、摘要忠实度、候选接受率、P50/P95 延迟、调用次数和 Token 成本纳入迭代门禁。

Iteration 13 已完成 SQLite 执行控制面：任务租约通过原子事务竞争，同一任务只允许一个活跃 owner；后台心跳续租，过期租约可被安全接管，旧 owner 在 Checkpoint 前重新验证所有权，防止陈旧执行覆盖新状态。取消请求独立持久化，`task-cancel` 对闲置任务立即终结，对活跃任务只登记请求；运行者在步骤边界、模型调用前和退避等待期协作取消并写入 `CANCELLED` Checkpoint。

当前 P0 可信知识闭环已经完成，P1 可靠性建设已覆盖主要运行时基础，但共享 Provider 限流、显式 Planner、Prompt/Workflow 注册表、用户偏好存储、Coding Sandbox 和正式 Evaluation Harness 仍待实现。详细对照与下一阶段门禁见 `docs/PROJECT_STATUS.md`。

Iteration 14 已完成第一版 Observability 与 Retrieval Evaluation：独立 SQLite Event Store 使用事件类型和属性双白名单，记录任务/步骤/验证/模型/重试/取消终态，但拒绝用户查询、Prompt/Payload、证据正文、答案正文和凭据。`task-events` 提供单任务脱敏轨迹。版本化 `retrieval_eval_v1` 数据集与 `eval-retrieval` CLI 可重复评测关键词或混合检索，输出 Recall@K、Hit Rate@K、MRR@K 和 P50/P95 延迟；报告逐 Case 不包含查询或检索正文。

当前 Evaluation 只覆盖检索质量，尚不能衡量摘要忠实度、引用蕴含关系、记忆候选接受率和真实产品效果。下一增量应先加入共享 Provider 限流和观测聚合，再扩展 Research/Memory 离线评测与基线门禁；动态 Planner 仍应等待这些数据证明规划是主要瓶颈。

Iteration 15 已完成跨进程 Provider 限流与观测聚合：模型和 Embedding Provider 在共享 SQLite 中原子预约平滑调用时隙，多个进程不会各自突破配额；配置控制每分钟请求数和最大允许等待，超限直接失败，模型等待可协作取消，Embedding 的自适应子批次逐次计入。`observability-summary` 基于最近事件窗口汇总任务终态、成功率、步骤/模型调用、重试、Token 与 P50/P95 延迟，不读取或暴露原始用户内容。

下一增量应扩展 Evaluation 到 Research Summary 与 Memory Governance，并引入可配置质量门禁；之后补 Provider 价格表与货币成本聚合。Planner 和 P2 多 Agent 继续等待评测证据，而不是凭架构想象提前引入。

Iteration 16 已完成 Research Summary 与 Memory Governance 离线评测及统一质量门禁：Research 使用人工段落—引用集合标签，输出结构有效率、引用覆盖、精确集合匹配与 Citation Precision/Recall/F1；Memory 使用独立临时 Store 逐 Case 验证状态、原因、审批和整体决策准确率，覆盖自动拒绝、待审批、重复与冲突。所有 Evaluation CLI 支持 `--minimum metric=value`，达标返回 `0`，质量未达标返回 `3`，配置/执行错误返回 `2`；报告和观测均不输出评测正文。

这些指标仍不能自动证明自然语言蕴含，也不能替代真实用户反馈。下一增量应增加 Provider 价格表、货币成本聚合和事件保留策略，再决定是否建设结构化 Planner；P2 多 Agent 仍没有评测证据支持启动。

Iteration 17 已完成 Provider 价格表、货币成本聚合与事件保留策略：模型配置可声明输入/输出每百万 Token 的美元单价，Model Gateway 根据成功响应的实际 Usage 计算整数微美元成本并写入脱敏事件，`observability-summary` 同时输出微美元整数和美元展示值。`observability_retention_days` 提供默认保留期，`events-prune` 默认仅预览，只有显式 `--apply` 才在同一事务中清理过期事件并写入 `events_pruned` 审计事件。

成本结果是基于静态配置价和供应商 Usage 的估算，不能覆盖未返回 Usage 的失败调用，也不能代替供应商账单。下一增量应把延迟与货币成本基线接入可配置回归门禁，并扩展 Provider 限流到 Token/并发配额；结构化 Planner 仍应等待评测证明规划质量是主要瓶颈。

Iteration 18 已完成第一版交付基线：新增跨平台一键验收入口，统一运行 103 项测试、源码编译和 CLI 冒烟检查；GitHub Actions 在 Python 3.9/3.11/3.13 与 Linux/Windows 环境安装项目并重复验收，同时验证安装后的命令入口。包元数据和忽略规则已补齐，不再依赖手工设置 `PYTHONPATH` 才能确认项目可用。跨版本验收还暴露了 Windows 新版 Python 下 SQLite 文件句柄延迟释放的问题，现已将七类 SQLite Store 统一改为事务结束时显式关闭连接，不改变现有数据库 Schema。

本轮不改变业务逻辑。下一增量应扩充真实、脱敏的固定评测语料，并将延迟和成本阈值纳入自动化回归门禁；在数据规模增长前不提前引入 Planner 或多 Agent。

Iteration 19 已完成方向化性能与成本门禁：准确率、引用质量、记忆决策和任务成功率继续使用 `--minimum`；检索 P50/P95 延迟、观测窗口步骤/模型 P50/P95 延迟和估算美元成本使用 `--maximum`。报告显式保存阈值和失败指标，质量回归返回 `3`，非法阈值或错误指标方向返回 `2`。门禁只消费现有脱敏报告，不扩大观测数据边界。

当前实现提供回归机制，但没有硬编码未经真实数据校准的默认阈值。下一增量应扩充脱敏固定语料并形成版本化基线策略，随后建设按任务、Provider 和时间范围的成本报告；Planner 与多 Agent 继续等待质量数据证明其必要性。

Iteration 20 已完成版本化基线策略与第一组脱敏固定语料：`quality_baseline_v1` 将阈值绑定到数据集、检索引擎、K、Embedding Provider 或观测事件窗口，CLI 支持显式阈值覆盖但拒绝作用域错配。报告只记录策略名称和作用域，不写入本地策略路径。三篇固定 Markdown 与三条查询覆盖 Runtime、Research、Memory；一键验收会从空数据库同步语料并执行关键词检索基线。

这一基线证明工程链路可重复，不代表真实用户数据的效果或统一生产阈值。下一增量应增加候选基线生成/比较工作流，并在人工审查后逐步扩展真实、脱敏的检索、蕴含与记忆接受数据。

Iteration 21 已完成待审基线候选与历史对比闭环：检索和观测报告显式携带评测作用域；`baseline-candidate` 使用可见的质量保留率和性能/成本余量生成 `pending_review` 候选，保留观察指标和规范化报告 SHA-256，但不复制逐 Case 内容或本地路径，也不自动覆盖正式策略。`baseline-compare` 只比较相同 Schema 与作用域的报告，按指标方向判断改善、退化和持平；任一退化返回 `3`，参数/报告错误返回 `2`。

一键验收现在会实际生成固定检索报告、候选策略并完成无退化自比较。下一增量应优先建设按任务、Provider 和时间范围的成本报告及可审计导出；同时继续扩充经人工审查的脱敏语料。Planner 和多 Agent 仍需等待真实评测证明当前结构化计划成为主要瓶颈。
