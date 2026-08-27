# 本地中文 Embedding 操作指南

本项目可以通过 `scripts/local_embedding_server.py` 在本机启动一个最小 OpenAI-compatible `/v1/embeddings` 服务。默认使用 `BAAI/bge-small-zh-v1.5`：FastEmbed 官方模型表标注其为 512 维中文模型，ONNX 文件约 90MB。首次启动会下载模型，之后推理和知识正文均只在本机处理。

参考：[FastEmbed 官方说明](https://github.com/qdrant/fastembed)、[官方支持模型表](https://qdrant.github.io/fastembed/examples/Supported_Models/)。

## 1. 建立隔离运行时

在项目根目录执行：

```powershell
py -3.12 -m venv evaluations/private/embedding-runtime
evaluations/private/embedding-runtime/Scripts/python.exe `
  -m pip install -r requirements-local-embedding.txt
```

运行时、模型缓存、真实配置和向量数据库都位于 `evaluations/private/`，该目录已被 Git 忽略。

## 2. 启动本地服务

```powershell
evaluations/private/embedding-runtime/Scripts/python.exe `
  scripts/local_embedding_server.py `
  --host 127.0.0.1 `
  --port 11435 `
  --model BAAI/bge-small-zh-v1.5 `
  --cache-dir evaluations/private/embedding-models `
  --threads 4
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:11435/health
```

服务默认拒绝非回环地址；不要为了方便加入 `--allow-remote`。端点没有身份认证，设计用途仅限同一台机器上的应用进程。请求正文不会写入服务日志。

## 3. 配置 Provider

在本地配置的 `embedding_providers` 中加入：

```json
{
  "provider_id": "fastembed-bge-small-zh-local",
  "base_url": "http://127.0.0.1:11435/v1",
  "model": "BAAI/bge-small-zh-v1.5",
  "dimension": 512,
  "minimum_query_score": 0.82,
  "batch_size": 16,
  "requests_per_minute": 60000,
  "max_rate_limit_wait_seconds": 1,
  "max_concurrent_requests": 1
}
```

`minimum_query_score` 是归一化余弦分数的查询级拒答门槛：只有最佳邻居达到门槛，才返回该查询的向量候选。`0.82` 来自当前真实 Vault 的 tuning 集，只适用于该模型与当前数据分布；更换模型或知识库后必须重新校准，不能照搬为通用默认值。

## 4. 同步与查询

另开一个 PowerShell：

```powershell
$env:PYTHONPATH = "src"

python -m personal_ai_agent `
  --config evaluations/private/jay.config.json `
  vector-sync `
  --provider fastembed-bge-small-zh-local

python -m personal_ai_agent `
  --config evaluations/private/jay.config.json `
  hybrid-search "Context 和 Memory 有什么区别？" `
  --provider fastembed-bge-small-zh-local `
  --limit 10
```

`vector-sync` 是增量操作：Provider ID、Chunk 文本哈希和维度未变化时不会重复生成向量。

## 5. 当前选择

当前真实独立 test 表明：keyword 与 hybrid 的 Recall@10 都是 92.31%；hybrid 的 Chunk Recall 更高（83.33% 对 75%），但 P95 更慢（110ms 对 16ms），MRR 也略低。因此：

- 默认快速搜索继续使用 keyword；
- 需要语义补充或更精确 Chunk 时显式使用 hybrid；
- 不把纯 vector 作为默认入口；
- 任何阈值或模型调整先在新的 tuning 版本上完成，再一次性运行独立 test。

停止服务时，在服务终端按 `Ctrl+C`。
