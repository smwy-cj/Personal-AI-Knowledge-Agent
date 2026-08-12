"""JSON-oriented command-line interface for the local application service."""

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence

from .application import ApplicationService
from .config import ApplicationConfig, ConfigurationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="personal-ai-agent")
    parser.add_argument("--config", default="agent.config.json", help="Path to secret-free JSON config")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("config-validate", help="Validate paths and initialize local databases")
    subcommands.add_parser("sync", help="Incrementally ingest the configured Obsidian Vault")

    search = subcommands.add_parser("search", help="Run citation-ready keyword search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--path-prefix")
    search.add_argument("--tag", action="append", default=[])

    vector_sync = subcommands.add_parser("vector-sync", help="Sync one configured embedding index")
    vector_sync.add_argument("--provider")
    hybrid = subcommands.add_parser("hybrid-search", help="Fuse keyword and vector retrieval")
    hybrid.add_argument("query")
    hybrid.add_argument("--provider")
    hybrid.add_argument("--limit", type=int, default=10)
    hybrid.add_argument("--path-prefix")
    hybrid.add_argument("--tag", action="append", default=[])
    hybrid.add_argument("--keyword-weight", type=float, default=1.0)
    hybrid.add_argument("--vector-weight", type=float, default=1.0)

    research = subcommands.add_parser("research-run", help="Run research and pause for memory approval")
    research.add_argument("goal")
    research.add_argument("--thread-id", default="cli")
    research.add_argument("--model-provider")
    research.add_argument("--embedding-provider")
    research.add_argument("--limit", type=int, default=8)
    research.add_argument("--language", default="zh-CN")

    task = subcommands.add_parser("task-show", help="Show a durable task snapshot")
    task.add_argument("task_id")
    cancel = subcommands.add_parser("task-cancel", help="Request durable task cancellation")
    cancel.add_argument("task_id")
    events = subcommands.add_parser("task-events", help="Show privacy-minimized task events")
    events.add_argument("task_id")
    events.add_argument("--limit", type=int, default=200)
    thread = subcommands.add_parser("task-list", help="List tasks in a thread")
    thread.add_argument("thread_id")
    thread.add_argument("--limit", type=int, default=50)

    pending = subcommands.add_parser("memory-pending", help="List pending candidates for a task")
    pending.add_argument("task_id")
    decision = subcommands.add_parser("memory-resolve", help="Approve/reject all pending candidates")
    decision.add_argument("task_id")
    decision.add_argument("--approve", action="append", default=[])
    decision.add_argument("--reject", action="append", default=[])
    subcommands.add_parser("memory-list", help="List persisted semantic memories")
    evaluation = subcommands.add_parser("eval-retrieval", help="Run a versioned retrieval evaluation dataset")
    evaluation.add_argument("dataset")
    evaluation.add_argument("--engine", choices=("keyword", "hybrid"), default="keyword")
    evaluation.add_argument("--provider")
    evaluation.add_argument("--limit", type=int, default=10)
    evaluation.add_argument("--minimum", action="append", default=[])
    research_evaluation = subcommands.add_parser("eval-research", help="Evaluate summary structure and citation labels")
    research_evaluation.add_argument("dataset")
    research_evaluation.add_argument("--minimum", action="append", default=[])
    memory_evaluation = subcommands.add_parser("eval-memory", help="Evaluate memory governance decisions")
    memory_evaluation.add_argument("dataset")
    memory_evaluation.add_argument("--minimum", action="append", default=[])
    summary = subcommands.add_parser("observability-summary", help="Aggregate privacy-minimized runtime events")
    summary.add_argument("--limit", type=int, default=1000)
    prune = subcommands.add_parser(
        "events-prune", help="Preview or explicitly apply observability retention"
    )
    prune.add_argument("--older-than-days", type=int)
    prune.add_argument("--apply", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        service = ApplicationService.from_file(arguments.config)
        if arguments.command == "config-validate":
            result = service.validate()
        elif arguments.command == "sync":
            result = service.sync_vault()
        elif arguments.command == "search":
            result = service.search(
                arguments.query,
                arguments.limit,
                arguments.path_prefix,
                arguments.tag,
            )
        elif arguments.command == "vector-sync":
            result = service.vector_sync(arguments.provider)
        elif arguments.command == "hybrid-search":
            result = service.hybrid_search(
                arguments.query,
                arguments.provider,
                arguments.limit,
                arguments.path_prefix,
                arguments.tag,
                arguments.keyword_weight,
                arguments.vector_weight,
            )
        elif arguments.command == "research-run":
            result = service.run_research(
                arguments.goal,
                arguments.thread_id,
                arguments.model_provider,
                arguments.embedding_provider,
                arguments.limit,
                arguments.language,
            )
        elif arguments.command == "task-show":
            result = service.show_task(arguments.task_id)
        elif arguments.command == "task-cancel":
            result = service.cancel_task(arguments.task_id)
        elif arguments.command == "task-events":
            result = service.task_events(arguments.task_id, arguments.limit)
        elif arguments.command == "task-list":
            result = service.list_thread_tasks(arguments.thread_id, arguments.limit)
        elif arguments.command == "memory-pending":
            result = service.pending_memory_candidates(arguments.task_id)
        elif arguments.command == "memory-resolve":
            result = service.resolve_memory(
                arguments.task_id, arguments.approve, arguments.reject
            )
        elif arguments.command == "memory-list":
            result = service.list_memories()
        elif arguments.command == "eval-retrieval":
            result = service.evaluate_retrieval(
                arguments.dataset,
                arguments.engine,
                arguments.provider,
                arguments.limit,
                _minimums(arguments.minimum),
            )
        elif arguments.command == "eval-research":
            result = service.evaluate_research_summaries(
                arguments.dataset, _minimums(arguments.minimum)
            )
        elif arguments.command == "eval-memory":
            result = service.evaluate_memory_governance(
                arguments.dataset, _minimums(arguments.minimum)
            )
        elif arguments.command == "observability-summary":
            result = service.observability_summary(arguments.limit)
        elif arguments.command == "events-prune":
            result = service.prune_observability_events(
                arguments.older_than_days, arguments.apply
            )
        else:
            parser.error("unknown command")
            return 2
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2, sort_keys=True))
        return 3 if isinstance(result, dict) and result.get("gate_passed") is False else 0
    except (ConfigurationError, ValueError, KeyError, OSError) as exc:
        print(
            json.dumps(
                {"error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _minimums(values: Sequence[str]) -> dict:
    output = {}
    for value in values:
        if "=" not in value:
            raise ValueError("quality minimums must use metric=value")
        name, raw = value.split("=", 1)
        name = name.strip()
        if not name or name in output:
            raise ValueError("quality minimum metric names must be non-empty and unique")
        try:
            threshold = float(raw)
        except ValueError as exc:
            raise ValueError("quality minimum values must be numbers") from exc
        if not 0 <= threshold <= 1:
            raise ValueError("quality minimum values must be between 0 and 1")
        output[name] = threshold
    return output


if __name__ == "__main__":
    raise SystemExit(main())
