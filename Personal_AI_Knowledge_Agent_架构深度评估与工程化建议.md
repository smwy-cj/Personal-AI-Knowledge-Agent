# Personal AI Knowledge Agent 架构深度评估与工程化建议

## 一、总体结论

这份设计的**方向是正确的，核心概念也基本完整**，适合作为《Personal AI Knowledge Agent》的**架构愿景文档或立项说明**；但从智能体应用工程角度看，它暂时还不能直接作为开发团队的技术设计书。

综合评价如下：

| 维度 | 评分 | 评价 |
|---|---:|---|
| 产品定位 | 8.5/10 | 目标明确，个人知识库与研究助手结合合理 |
| 概念完整性 | 8/10 | Planner、Memory、Tools、Reflection、Multi-Agent 均已覆盖 |
| 架构解耦 | 7/10 | LLM Gateway 和专业 Agent 的拆分方向正确 |
| 工程可实现性 | 5/10 | 缺少状态、接口、数据结构和运行机制 |
| 可靠性设计 | 3.5/10 | 没有失败恢复、幂等、超时、终止条件 |
| 知识治理 | 4.5/10 | 有记忆写入，但缺少来源、冲突和审核机制 |
| 安全性 | 3/10 | 工具权限、代码执行、提示词注入均未涉及 |
| 可观测与评测 | 2.5/10 | 没有 Trace、成本统计、质量指标和测试集 |
| 综合评价 | **6.2/10** | 是不错的第一版蓝图，但距离生产架构还有明显距离 |

一句话概括：

> 当前架构解决了“系统应该有哪些模块”，但还没有解决“这些模块如何可靠地运行”。

当前设计提出了 Supervisor、Research/Learning/Coding Agent、三层 Memory、LLM Gateway、Reflection 和 Obsidian 知识闭环，整体方向一致，结构也比较清楚。

---

## 二、现有设计最值得保留的部分

### 1. 没有把系统简单等同于 RAG

当前设计已经意识到，个人智能研究助手不能只是：

```text
问题 → 检索 → 回答
```

而应该形成：

```text
理解目标 → 规划 → 检索 → 执行 → 验证 → 记忆更新
```

这是正确的产品判断。

普通 RAG 主要解决“找到相关内容”，而智能体系统还必须处理：

- 当前任务进行到哪一步；
- 下一步应该做什么；
- 哪些步骤必须调用工具；
- 工具失败后如何处理；
- 哪些结果值得写入长期记忆；
- 什么时候应该向用户确认。

这也是该项目从“Obsidian 聊天插件”升级为“Personal AI Knowledge Agent”的关键。

### 2. LLM Gateway 是重要且正确的抽象

当前设计提出 Agent 不直接绑定 DeepSeek、GLM 或本地模型，而是经过统一的 LLM Gateway。

这一点应该保留，而且需要进一步强化。

Gateway 不应只负责“切换模型”，还应该负责：

- 模型能力注册；
- 任务模型选择；
- JSON Schema 校验；
- 超时和重试；
- Fallback；
- Token 和成本控制；
- 敏感数据路由；
- Prompt 版本管理；
- 响应缓存；
- 推理模式选择。

### 3. Obsidian 闭环符合个人知识管理场景

设计中的 Knowledge Growth Loop 是整个方案最有产品价值的部分：

```text
学习
→ 记录
→ 检索
→ 分析
→ 生成新知识
→ 回写知识库
```

这使系统不只是“使用知识库”，而是在帮助用户维护和发展知识库。

但需要注意：

> 自动回写不能直接等同于自动积累知识。

如果没有质量控制，系统最终可能把以下内容写入 Obsidian：

- 重复总结；
- 模型幻觉；
- 互相冲突的结论；
- 缺乏来源的信息；
- 临时任务信息；
- 过度推测的用户画像。

因此闭环必须加入“记忆治理”，而不是直接：

```text
模型生成结果 → 写入 Obsidian
```

---

## 三、最核心的架构问题：现在是“角色架构”，不是“运行架构”

现有设计主要以角色为中心：

```text
Supervisor
├── Research Agent
├── Learning Agent
└── Coding Agent
```

但生产系统更重要的是任务状态和执行过程：

```text
任务创建
→ 状态初始化
→ 路由
→ 规划
→ 执行
→ 工具调用
→ 结果验证
→ 失败恢复
→ 人工确认
→ 写入记忆
→ 结束
```

目前设计没有定义：

- Task 是什么数据结构；
- Plan 如何保存；
- Agent 之间传递什么；
- 子任务如何标记完成；
- 工具调用结果放在哪里；
- 失败后从哪里恢复；
- Supervisor 如何判断任务已经结束；
- Reflection 最多执行几次；
- 多 Agent 是否可以并行；
- 用户中途修改目标后如何重新规划。

因此，建议把架构中心从：

> Supervisor 调用多个 Agent

调整为：

> **有状态的任务编排器管理多个工作流和能力组件。**

---

## 四、不要过早多智能体化

当前设计默认 Research、Learning、Coding 都是独立 Agent。这个设计在概念图上清晰，但工程上可能造成过度复杂。

并不是所有复杂任务都需要多智能体。很多任务通过单个 Agent 配合合适的工具和上下文即可完成。多智能体更适合以下场景：

- 工具数量过多；
- 领域上下文差异明显；
- 需要并行执行；
- 需要独立上下文；
- 不同模块由不同团队维护；
- 某个子任务本身就需要多轮自治决策。

建议采用三层能力结构。

### 1. Workflow

确定性较高的任务使用固定工作流。

例如：

```text
论文总结工作流
PDF解析
→ 章节识别
→ 分段总结
→ 创新点提取
→ 实验结果提取
→ 引用校验
→ 报告生成
```

这些步骤不需要每一次都由 Agent 临时决定。

### 2. Skill

将可复用能力封装为 Skill：

- 论文摘要；
- 知识点抽取；
- 笔记关联；
- 代码解释；
- 测试生成；
- 学习计划生成；
- Obsidian 笔记格式化。

Skill 通常是 Prompt、工具和输出 Schema 的组合，不一定是完整 Agent。

### 3. Agent

只有在以下情况下才升级为独立 Agent：

- 需要自主进行多步决策；
- 拥有独立的工具集；
- 需要独立上下文；
- 需要多轮执行和重新规划；
- 可以明确限定输入和输出；
- 可以独立评测成功率。

因此第一版不建议直接实现三个完全自治的 Agent。

更稳妥的结构是：

```text
Orchestrator Agent
├── Research Workflow
├── Learning Workflow
├── Coding Workflow
└── Shared Skills
```

等某个 Workflow 足够复杂后，再将其提升为 Sub-Agent。

---

## 五、Planner 需要从“文字拆解”升级为“可执行计划”

当前 Planner 的描述是：

```text
理解目标
→ 拆解任务
→ 生成执行步骤
→ 调度 Agent
```

这在概念上没有问题，但缺少执行约束。

### 1. Planner 至少要输出结构化计划

例如：

```json
{
  "task_id": "task_20260730_001",
  "goal": "总结最近一个月 AI Agent 学习情况",
  "constraints": {
    "time_range": "2026-07-01/2026-07-30",
    "language": "zh-CN",
    "max_length": 3000
  },
  "steps": [
    {
      "step_id": "s1",
      "type": "retrieve",
      "executor": "knowledge_search",
      "input": {
        "sources": ["daily_notes"],
        "query": "AI Agent"
      },
      "depends_on": [],
      "status": "pending"
    },
    {
      "step_id": "s2",
      "type": "analyze",
      "executor": "learning_summary",
      "depends_on": ["s1"],
      "status": "pending"
    }
  ],
  "budget": {
    "max_tool_calls": 10,
    "max_replans": 2,
    "max_tokens": 30000
  }
}
```

### 2. Planner 还需要明确五个机制

#### 计划粒度

不能拆得太粗，也不能把每一次检索都作为独立计划步骤。

#### Replan 触发条件

例如：

- 搜索结果为空；
- 工具失败；
- 用户修改目标；
- 验证结果不合格；
- 预算不足；
- 关键来源缺失。

#### 终止条件

必须明确：

```text
成功完成
部分完成
等待用户
工具失败
预算耗尽
主动取消
```

#### 重试预算

Reflection 和 ReAct 如果没有限制，很容易形成：

```text
生成 → 认为不好 → 重写 → 再认为不好 → 无限循环
```

建议设置：

```text
max_step_retry = 2
max_replan = 2
max_reflection = 1
max_total_tool_calls = N
```

#### 确定性步骤与智能步骤分离

例如：

- 文件是否存在：代码判断；
- JSON 是否有效：Schema 校验；
- 引用是否齐全：规则判断；
- 下一步研究方向：LLM 判断。

不要让 LLM 承担所有判断。

---

## 六、Memory 设计需要重构

当前设计将 Memory 分成：

- Short-term Memory；
- Long-term Memory；
- User Profile Memory。

这个划分容易理解，但对于工程实现过于粗糙。

建议调整为五类存储。

### 1. Task State：任务状态

保存当前任务执行情况：

- 当前步骤；
- 已完成步骤；
- 工具结果；
- 中间产物；
- 错误；
- 预算；
- 等待确认状态。

它不应该被放进聊天记录，也不应该写入 Obsidian。

### 2. Conversation Memory：对话记忆

保存当前 Thread 的：

- 用户问题；
- 必要上下文；
- 已确认约束；
- 当前对话摘要。

长对话不能无条件把所有历史内容持续放入上下文，否则会产生注意力分散、延迟和成本问题。

### 3. Episodic Memory：经历记忆

记录系统过去完成过什么：

```text
2026-07-30：
为用户完成了 Agent 架构评审；
用户更倾向于先搭建单 Orchestrator 架构；
输出了 P0/P1/P2 实施计划。
```

它用于帮助系统理解历史任务，而不是作为权威知识。

### 4. Semantic Memory：语义事实

保存相对稳定的事实：

```text
项目 EduFlow 使用某技术栈
用户正在研究 AgentCom
某篇论文的核心创新点
某个项目采用特定目录结构
```

必须具有：

- source；
- created_at；
- updated_at；
- confidence；
- valid_from；
- valid_until；
- tags；
- conflict_status。

### 5. User Preference Memory：用户偏好

只保存长期有用的偏好：

- 更偏好中文回答；
- 喜欢系统化解释；
- 默认输出简洁；
- 重点关注 AI Agent 和软件工程。

用户画像不应该是模型自由生成的一大段描述，而应该是可修改、可删除、可追溯的结构化数据。

---

## 七、必须增加 Memory Write Policy

当前设计的逻辑是：

```text
任务完成
→ 判断是否值得保存
→ 写入 Memory
```

问题是“是否值得保存”本身没有标准。

建议设计以下写入管道：

```text
生成候选记忆
       ↓
记忆类型分类
       ↓
敏感信息检查
       ↓
来源和证据检查
       ↓
重复检测
       ↓
冲突检测
       ↓
置信度评估
       ↓
自动写入 / 用户确认 / 拒绝写入
       ↓
写入 Obsidian
       ↓
增量索引
```

### 自动写入范围

可以自动写入：

- 任务日志；
- 临时工作摘要；
- 带明确来源的论文元数据；
- 用户明确要求保存的内容。

### 建议确认后写入

- 用户画像修改；
- 对某个项目的关键技术结论；
- 系统推断出的用户偏好；
- 覆盖已有知识的结论；
- 无法验证的信息；
- 自动生成的“我的理解”。

### 不应长期写入

- 一次性的格式要求；
- 工具错误；
- 模型内部推测；
- 没有来源的事实；
- 重复的对话内容；
- 密钥、Token、隐私数据。

---

## 八、Obsidian 应是知识源与人机界面，不是系统数据库

建议明确以下边界。

### Obsidian 保存

- 用户原创笔记；
- 论文总结；
- 项目文档；
- 学习记录；
- 可读的知识条目；
- 经确认的 Agent 产物。

### 数据库存储

- Task State；
- Agent 执行记录；
- Tool Call 日志；
- Embedding；
- Chunk；
- 索引元数据；
- 权限；
- Prompt 版本；
- 用户设置；
- 评测结果。

不要把所有状态都保存成 Markdown。

否则会出现：

- 大量机器生成文件污染 Vault；
- Git 频繁冲突；
- 任务中间状态难以查询；
- 并发写入困难；
- 数据结构迁移困难；
- 删除和更新不一致。

推荐采用：

```text
Obsidian Vault：用户可读的知识源
PostgreSQL/SQLite：系统状态和元数据
Vector Store：语义索引
Object Storage/File System：原始文档和中间产物
```

个人本地 MVP 可以先使用：

```text
SQLite + 本地文件 + 向量扩展
```

等规模扩大后再拆分。

---

## 九、RAG 层目前过于简化

当前设计基本是：

```text
Obsidian
→ Embedding
→ Vector Database
→ Retriever
```

这只能构成最基础的语义检索。

建议升级为完整的知识摄取和检索管道。

### 摄取管道

```text
Vault 文件变化
→ 文件解析
→ Frontmatter 提取
→ Markdown 结构解析
→ 标题层级切分
→ 链接与标签提取
→ 内容去重
→ Embedding
→ 索引更新
```

### 检索管道

```text
用户问题
→ 查询理解
→ 时间和项目过滤
→ 关键词检索
→ 向量检索
→ 结果融合
→ Rerank
→ 邻接笔记扩展
→ 上下文压缩
→ 返回证据
```

### 每个检索结果应保存

```json
{
  "document_id": "doc_xxx",
  "path": "Projects/EduFlow/architecture.md",
  "heading": "Memory Design",
  "chunk_id": "chunk_xxx",
  "content": "...",
  "updated_at": "...",
  "score": 0.87,
  "source_type": "obsidian",
  "line_range": [120, 153]
}
```

否则 Agent 无法稳定引用来源，也无法判断知识是否已经过期。

---

## 十、多 Agent 通信不能只是自然语言消息

当前 Agent 通信类似：

```text
Supervisor:
完成论文分析

Learning Agent:
生成学习计划
```

这种自然语言通信适合演示，但不适合可靠执行。

应该为每个 Agent 定义输入输出契约。

### Agent 输入

```json
{
  "task_id": "task_xxx",
  "goal": "分析论文",
  "context_refs": ["doc_1", "doc_2"],
  "constraints": {
    "language": "zh-CN",
    "must_include_citations": true
  },
  "allowed_tools": [
    "pdf_reader",
    "knowledge_search"
  ],
  "expected_output_schema": "paper_analysis_v1",
  "budget": {
    "max_tool_calls": 6,
    "max_tokens": 16000
  }
}
```

### Agent 输出

```json
{
  "status": "completed",
  "artifact": {
    "type": "paper_analysis",
    "content": "..."
  },
  "evidence": [
    {
      "source_id": "doc_1",
      "location": "section_4.2"
    }
  ],
  "confidence": 0.82,
  "memory_candidates": [],
  "errors": []
}
```

---

## 十一、Supervisor 不应成为万能大脑

当前架构把几乎所有职责都放给 Supervisor：

- 理解问题；
- 规划任务；
- 选择 Agent；
- 调度 Agent；
- 整合结果；
- 管理 Memory；
- 执行 Reflection。

这会导致 Supervisor：

- Prompt 过长；
- 路由不稳定；
- 难以单独测试；
- 成为性能瓶颈；
- 出错后影响所有任务；
- 无法确定究竟是哪一个环节失败。

建议拆成以下组件：

```text
Intent Router
负责识别任务类型

Policy Engine
负责权限、敏感操作和预算判断

Planner
负责生成或修改计划

Orchestrator
负责按照状态图推进执行

Context Builder
负责选择上下文和记忆

Worker / Sub-Agent
负责完成具体任务

Verifier
负责验证结果

Memory Manager
负责生成和处理记忆候选
```

Supervisor 可以保留为产品层面的称呼，但内部不要只实现成一个巨大 Prompt。

---

## 十二、Reflection 机制目前存在明显风险

当前设计将 Reflection 设计为：

```text
生成结果
→ 检查质量
→ 发现问题
→ 重新执行
```

方向合理，但“让模型评价自己”不等于真正验证。

建议将 Reflection 拆为三类。

### 1. 规则验证

由代码完成：

- 输出是否符合 JSON Schema；
- 是否缺少必要章节；
- 是否引用不存在的文件；
- 链接是否有效；
- 代码是否能够执行；
- 测试是否通过。

### 2. 证据验证

检查：

- 每个关键结论是否有来源；
- 引用是否真的支持结论；
- 是否混入知识库外的信息；
- 是否遗漏反面证据；
- 来源是否过期。

### 3. 模型评审

只有难以规则化的问题交给 Reviewer：

- 结构是否清楚；
- 论证是否充分；
- 是否符合用户需求；
- 是否存在明显遗漏。

推荐执行顺序：

```text
规则校验
→ 工具验证
→ 证据校验
→ 模型评审
→ 有限次数修订
```

而不是直接让原模型重新阅读自己的回答。

---

## 十三、工具系统必须设置确定性执行层

当前设计列出了：

- Knowledge Search；
- Paper Search；
- GitHub Search；
- File Reader；
- Code Executor；
- Report Generator。

但缺少工具治理。

### 每个工具都需要定义

- 工具名称；
- 参数 JSON Schema；
- 返回 Schema；
- 权限等级；
- 是否需要用户确认；
- 超时时间；
- 重试策略；
- 是否幂等；
- 是否可能产生副作用；
- 日志脱敏规则。

例如：

| 工具 | 风险等级 | 是否确认 |
|---|---:|---|
| 搜索知识库 | 低 | 否 |
| 读取本地文件 | 中 | 按目录授权 |
| 写入 Obsidian | 中 | 可配置 |
| 执行代码 | 高 | 沙箱运行 |
| 删除文件 | 高 | 必须确认 |
| Git push | 高 | 必须确认 |
| 发送邮件 | 高 | 必须确认 |

### Code Executor 必须隔离

Coding Agent 不应直接在宿主机任意执行代码。

至少应包含：

- 临时工作目录；
- CPU 和内存限制；
- 执行超时；
- 网络默认关闭；
- 环境变量隔离；
- 文件路径白名单；
- 输出长度限制；
- 子进程清理；
- 危险命令拦截。

---

## 十四、LLM Gateway 应升级为 Model Capability Registry

不建议硬编码：

```text
Research Agent → GLM
Coding Agent → DeepSeek
```

因为“Agent 类型”不等于“固定模型类型”。

同一个 Research Agent 中可能包含：

- 大规模文档总结；
- 快速分类；
- 结构化抽取；
- 复杂推理；
- 翻译；
- 格式修正。

这些步骤适合不同模型。

建议使用能力注册表：

```yaml
models:
  deepseek_reasoner:
    capabilities:
      - reasoning
      - tool_calling
      - structured_output
    privacy: cloud
    cost_level: medium

  glm_general:
    capabilities:
      - long_context
      - chinese
      - tool_calling
      - structured_output
    privacy: cloud
    cost_level: medium

  local_embedding:
    capabilities:
      - embedding
    privacy: local
    cost_level: low
```

路由依据应包括：

```text
任务能力要求
+ 数据敏感等级
+ 上下文长度
+ 延迟要求
+ 成本预算
+ 当前模型可用性
```

---

## 十五、缺失的关键模块：Observability 与 Evaluation

这是当前设计中最严重的缺失之一。

没有可观测性，就无法回答：

- Planner 为什么这样拆任务；
- Supervisor 为什么选择 Coding Agent；
- 检索了哪些笔记；
- 哪个工具最耗时；
- 哪个步骤消耗 Token 最多；
- 为什么发生重新规划；
- 为什么写入了某条记忆；
- 最终答案是否真正引用了正确来源。

### 每一次任务至少记录

```text
task_id
user_id
thread_id
workflow_version
prompt_version
model
input_tokens
output_tokens
retrieved_documents
tool_calls
tool_latency
state_transitions
retry_count
errors
final_status
user_feedback
```

### 评测体系建议分四层

#### 1. 单元测试

测试：

- Retriever；
- Chunker；
- Router；
- Memory 冲突检测；
- Tool 参数校验。

#### 2. Workflow 测试

准备固定任务：

- 总结一周学习；
- 分析指定论文；
- 定位代码错误；
- 根据已有笔记生成复习题。

#### 3. Agent 行为评测

指标：

- 任务完成率；
- 工具选择正确率；
- 无效工具调用次数；
- 平均执行步数；
- 重新规划次数；
- 引用准确率；
- 记忆写入正确率。

#### 4. 产品评测

指标：

- 用户接受率；
- 人工修改率；
- 平均响应时间；
- 单任务成本；
- 知识库重复率；
- 错误写入率；
- 用户撤销记忆比例。

---

## 十六、建议的目标架构

```text
┌──────────────────────────────────────────┐
│                 Client                   │
│ Chat UI / Obsidian Plugin / CLI / Web UI │
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│            Application API Layer         │
│ Auth / Session / Task API / Streaming    │
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│              Agent Runtime               │
│                                          │
│ Intent Router                            │
│ Policy Engine                            │
│ Task Orchestrator / State Graph          │
│ Planner                                  │
│ Context Builder                          │
│ Workflow Registry                        │
│ Verifier                                 │
│ Memory Manager                           │
└──────────────┬───────────────┬───────────┘
               ↓               ↓
┌──────────────────────┐  ┌──────────────────────┐
│ Capability Workers   │  │ Execution Plane      │
│                      │  │                      │
│ Research Workflow    │  │ Tool Registry        │
│ Learning Workflow    │  │ MCP Client           │
│ Coding Workflow      │  │ Deterministic Runner │
│ Optional Sub-Agents  │  │ Sandbox              │
└──────────────┬───────┘  │ Job Queue            │
               │          └──────────┬───────────┘
               ↓                     ↓
┌──────────────────────────────────────────┐
│              Knowledge Plane             │
│                                          │
│ Ingestion Pipeline                       │
│ Document Store                           │
│ Metadata Store                           │
│ Vector + Keyword Index                   │
│ Reranker                                 │
│ Memory Store                             │
│ Obsidian Writer                          │
└────────────────────┬─────────────────────┘
                     ↓
┌──────────────────────────────────────────┐
│              Model Gateway               │
│ DeepSeek / GLM / Local LLM / Embedding   │
│ Routing / Retry / Cache / Cost / Schema  │
└──────────────────────────────────────────┘

横向基础设施：
Observability / Evaluation / Security / Configuration
```

---

## 十七、建议的核心 Task State

这是后续实现时最先应该确定的数据结构之一。

```python
class AgentTaskState:
    task_id: str
    thread_id: str
    user_goal: str

    user_constraints: dict
    status: str

    plan: list
    current_step_id: str | None

    retrieved_context: list
    artifacts: list
    evidence: list

    tool_calls: list
    errors: list

    memory_candidates: list

    token_budget: int
    tool_call_budget: int
    retry_count: int
    replan_count: int

    awaiting_user_approval: bool
    final_answer: str | None
```

状态值建议统一定义：

```text
CREATED
PLANNING
RUNNING
WAITING_USER
VERIFYING
WRITING_MEMORY
COMPLETED
PARTIAL_SUCCESS
FAILED
CANCELLED
```

---

## 十八、推荐的实施顺序

### P0：先完成可用闭环

第一阶段不要上完整多 Agent。

实现：

1. Obsidian 增量索引；
2. 基础混合检索；
3. 单一 Orchestrator；
4. Research Workflow；
5. 结构化 Task State；
6. 检索证据和引用；
7. 用户确认后写回 Obsidian；
8. 基础日志和成本统计。

目标闭环：

```text
读取知识库
→ 分析任务
→ 检索
→ 生成带引用结果
→ 用户确认
→ 写回知识库
```

### P1：增强可靠性

加入：

- Planner；
- Checkpoint；
- 失败恢复；
- Verifier；
- Memory Candidate；
- 用户偏好存储；
- Model Router；
- Coding Sandbox；
- Prompt 和 Workflow 版本管理。

### P2：引入真正的多 Agent

仅在评测证明单 Agent 存在瓶颈后加入：

- Research Sub-Agent；
- Coding Sub-Agent；
- Reviewer Agent；
- 并行子任务；
- Agent 间结构化消息；
- MCP 工具生态。

### P3：主动型智能助手

最后再实现：

- 定期扫描知识缺口；
- 主动提出学习计划；
- 项目进展跟踪；
- 自动生成复习任务；
- 长期研究主题追踪；
- 知识冲突检测；
- 个性化模型路由。

“Autonomous Learning” 应最后实现，因为主动读取、搜索和写入会显著增加成本、噪声和安全风险。

---

## 十九、需要立刻修改原设计文档的内容

### 必须新增

1. **任务状态模型**
2. **Agent 输入输出协议**
3. **Workflow 与 Agent 的边界**
4. **Planner 计划 Schema**
5. **失败恢复与终止条件**
6. **Memory Write Policy**
7. **知识来源与引用机制**
8. **工具权限和人工确认**
9. **代码执行沙箱**
10. **Observability 与 Trace**
11. **Evaluation 指标体系**
12. **Prompt Injection 防护**
13. **模型路由规则**
14. **数据库与 Obsidian 的职责边界**
15. **MVP 实施路线**

### 建议修改

将：

```text
Supervisor Agent
→ Research / Learning / Coding Agent
```

修改为：

```text
Task Orchestrator
→ Workflow Registry
→ Specialized Worker / Optional Sub-Agent
```

将：

```text
Agent直接判断是否写入Memory
```

修改为：

```text
Memory Candidate
→ Policy
→ Deduplication
→ Conflict Check
→ Approval
→ Persistence
```

将：

```text
Reflection重新执行
```

修改为：

```text
Rule Validation
→ Evidence Validation
→ Reviewer
→ Bounded Retry
```

---

## 二十、最终评价

这份架构没有根本性的方向错误。相反，它已经抓住了 Personal AI Knowledge Agent 最重要的几个概念：

- 任务规划；
- 长期记忆；
- 工具调用；
- 多领域能力；
- 模型解耦；
- 知识增长闭环。

它现在最大的风险不是“设计得太简单”，而是：

> **在基础执行机制尚未建立时，过早把系统描述成一个完整的多智能体自治系统。**

真正可靠的个人研究助手，不是 Agent 数量越多越好，而是：

```text
状态清楚
边界明确
工具可控
结果可验证
记忆可治理
失败可恢复
行为可追踪
成本可衡量
```

因此，建议将下一版定位为：

> **以状态图为核心、以工作流为基础、以 Agent 为可选自治单元、以 Obsidian 为人类可读知识源、以 Memory Governance 为知识闭环保障的个人智能研究系统。**

按照这个方向修改后，这套架构才会从“概念全面的智能体方案”，转变为“可以逐步编码、测试和演进的工程架构”。
