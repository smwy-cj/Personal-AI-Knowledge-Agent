# Personal AI Knowledge Agent 的 Agent 架构设计

## 如何加入 Planner、Memory、多Agent协作，让它真正像一个智能研究助手

------------------------------------------------------------------------

# 一、项目定位

Personal AI Knowledge Agent 的目标：

> 构建一个基于个人知识库的智能研究助手，使其能够理解用户知识背景、主动规划任务、调用工具、持续记忆，并协助完成学习、研究和项目开发。

区别于普通 RAG：

普通 RAG：

    用户问题
      ↓
    检索知识
      ↓
    LLM回答

智能研究助手：

    用户目标
      ↓
    Agent理解任务
      ↓
    Planner任务规划
      ↓
    Memory获取历史信息
      ↓
    Multi-Agent协作
      ↓
    工具调用
      ↓
    生成结果
      ↓
    更新长期记忆

------------------------------------------------------------------------

# 二、整体Agent架构

                     User

                      ↓

              Supervisor Agent

                      ↓

           ---------------------

           |         |         |

     Research   Learning   Coding
     Agent      Agent      Agent

           |         |         |

           ---------------------

                      ↓

                LLM Gateway

                      ↓

          DeepSeek / GLM / Local LLM

                      ↓

                 RAG System

                      ↓

            Obsidian Knowledge Base

------------------------------------------------------------------------

# 三、Agent核心模块

一个完整Agent包含：

    Agent

    ├── Planner
    ├── Memory
    ├── Tools
    ├── Reasoning
    ├── Action
    └── Reflection

------------------------------------------------------------------------

# 四、Planner设计

## 1. Planner作用

Planner负责：

-   理解用户目标
-   拆解复杂任务
-   生成执行步骤
-   调度不同Agent

例如：

用户：

> 总结我最近一个月AI Agent方向学习情况

Planner：

    Task:

    生成学习总结


    Step1:
    查询Daily Notes

    Step2:
    查询Agent相关知识

    Step3:
    查询项目记录

    Step4:
    分析学习路线

    Step5:
    生成总结报告

------------------------------------------------------------------------

## 2. Planner实现方式

### ReAct模式

    Thought

    ↓

    Action

    ↓

    Observation

    ↓

    Thought

    ↓

    Answer

------------------------------------------------------------------------

### Planning模式

    Goal

    ↓

    Task Decomposition

    ↓

    Sub Tasks

    ↓

    Execution

    ↓

    Evaluation

------------------------------------------------------------------------

# 五、Memory系统设计

Memory决定Agent是否具有长期智能。

设计三层Memory：

------------------------------------------------------------------------

# 1. Short-term Memory

短期记忆：

保存当前对话上下文。

例如：

    用户：
    介绍MCP


    Agent:
    已经讨论过Agent Tool Calling

实现：

-   Conversation Buffer
-   Context Window

------------------------------------------------------------------------

# 2. Long-term Memory

长期知识。

来源：

    Obsidian Vault

    ↓

    Embedding

    ↓

    Vector Database

    ↓

    Retriever

保存：

-   技术知识
-   论文
-   项目经验
-   学习笔记

------------------------------------------------------------------------

# 3. User Profile Memory

用户画像。

例如：

    用户：

    专业:
    软件工程

    关注方向:
    AI Agent
    LLM
    软件工程


    学习习惯:
    喜欢系统化解释

    项目:
    EduFlow
    SimAI

------------------------------------------------------------------------

# 六、Memory更新机制

Agent不能只读取Memory，还需要更新。

流程：

    新任务

    ↓

    Agent执行

    ↓

    总结经验

    ↓

    判断是否值得保存

    ↓

    写入Memory

例如：

完成论文阅读：

生成：

    Paper Summary

    创新点:
    ...

    我的理解:
    ...

    关联:
    [[Agent]]
    [[RAG]]

自动进入Obsidian。

------------------------------------------------------------------------

# 七、多Agent协作设计

采用Supervisor模式：

                  Supervisor Agent


                         |

     ---------------------------------

     |              |                 |

    Research     Learning          Coding
    Agent        Agent             Agent

------------------------------------------------------------------------

# 八、Research Agent

职责：

-   阅读论文
-   提炼创新点
-   生成汇报材料

工具：

    Paper Reader

    PDF Parser

    Knowledge Search

    PPT Generator

适合模型：

GLM系列：

原因：

-   长文本理解
-   推理能力

------------------------------------------------------------------------

# 九、Learning Agent

职责：

-   每日学习总结
-   知识复习
-   查漏补缺

输入：

    Daily Notes

    Course Notes

    Knowledge Graph

输出：

    今日学习总结

    知识关联

    待学习内容

    复习问题

------------------------------------------------------------------------

# 十、Coding Agent

职责：

-   项目代码分析
-   Debug
-   架构设计

工具：

    GitHub Reader

    Code Analyzer

    Terminal

    Documentation Search

适合：

DeepSeek-Coder等代码模型。

------------------------------------------------------------------------

# 十一、Agent之间通信

采用消息机制：

    Supervisor

    ↓

    Research Agent:

    完成论文分析


    ↓

    Learning Agent:

    生成学习计划


    ↓

    Coding Agent:

    评估工程实现

    ↓

    Supervisor:

    整合结果

------------------------------------------------------------------------

# 十二、LLM Gateway设计

Agent不直接调用模型。

    Agent

    ↓

    LLM Interface

    ↓

    Model Router

    ↓

    ----------------

    DeepSeek

    GLM

    Local Model

    ----------------

优势：

-   模型可替换
-   成本控制
-   不同任务选择不同模型

------------------------------------------------------------------------

# 十三、工具系统设计

Agent拥有Tools：

    Tools

    ├── Knowledge Search

    ├── Paper Search

    ├── GitHub Search

    ├── File Reader

    ├── Code Executor

    └── Report Generator

------------------------------------------------------------------------

# 十四、Reflection机制

高级Agent需要自我评价。

流程：

    生成结果

    ↓

    检查质量

    ↓

    发现问题

    ↓

    重新执行

例如：

论文总结：

第一次：

    缺少实验分析

Reflection：

    重新读取Experiment章节

    补充结果

------------------------------------------------------------------------

# 十五、最终智能研究助手流程

完整流程：

    User

    ↓

    Supervisor Agent

    ↓

    Planner拆解任务

    ↓

    Memory读取历史信息

    ↓

    调用多个Agent

    ↓

    调用Tools

    ↓

    RAG获取知识

    ↓

    LLM生成结果

    ↓

    Reflection优化

    ↓

    保存新知识

    ↓

    返回用户

------------------------------------------------------------------------

# 十六、与Personal Knowledge Base结合

最终形成闭环：

    学习

    ↓

    记录Obsidian

    ↓

    Embedding

    ↓

    RAG

    ↓

    Agent理解

    ↓

    辅助研究

    ↓

    生成新知识

    ↓

    再次进入Obsidian

形成：

    Knowledge Growth Loop

------------------------------------------------------------------------

# 十七、未来扩展方向

## MCP支持

让Agent连接：

-   GitHub
-   浏览器
-   数据库
-   云服务

## Multi-Agent Evolution

加入：

-   Debate Agent
-   Reviewer Agent
-   Planner Agent

## Autonomous Learning

实现：

    发现知识空缺

    ↓

    主动学习

    ↓

    补充知识库

    ↓

    更新用户模型

------------------------------------------------------------------------

# 十八、项目价值

该系统融合：

-   RAG
-   Agent
-   Memory
-   Multi-Agent
-   MCP
-   Knowledge Management

最终目标：

> 构建一个能够陪伴个人长期学习、研究和创造的AI智能伙伴。
