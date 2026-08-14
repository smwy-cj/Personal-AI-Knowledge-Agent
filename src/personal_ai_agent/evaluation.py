"""Versioned retrieval evaluation datasets and deterministic metrics."""

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Union

from .knowledge import KnowledgeSearchResult


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    case_id: str
    query: str
    expected_paths: List[str]


@dataclass(frozen=True)
class RetrievalEvaluationDataset:
    name: str
    cases: List[RetrievalEvaluationCase]

    @classmethod
    def load(cls, path: Union[str, Path]) -> "RetrievalEvaluationDataset":
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("evaluation dataset must be valid UTF-8 JSON") from exc
        if not isinstance(document, dict) or document.get("schema") != "retrieval_eval_v1":
            raise ValueError("unsupported retrieval evaluation dataset schema")
        name = document.get("name")
        items = document.get("cases")
        if not _safe_identifier(name) or not isinstance(items, list) or not items:
            raise ValueError("evaluation dataset name and cases are required")
        cases = []
        seen = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != {"case_id", "query", "expected_paths"}:
                raise ValueError("evaluation cases have an invalid shape")
            case_id = item["case_id"]
            query = item["query"]
            expected = item["expected_paths"]
            if (
                not _safe_identifier(case_id)
                or case_id in seen
                or not isinstance(query, str)
                or not query.strip()
                or not isinstance(expected, list)
                or not expected
                or any(not isinstance(path, str) or not path.strip() for path in expected)
            ):
                raise ValueError("evaluation case values are invalid")
            seen.add(case_id)
            cases.append(
                RetrievalEvaluationCase(
                    case_id.strip(), query.strip(), list(dict.fromkeys(expected))
                )
            )
        return cls(name.strip(), cases)


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    expected_count: int
    retrieved_count: int
    matched_count: int
    reciprocal_rank: float
    latency_ms: int


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    schema: str
    dataset_name: str
    engine: str
    limit: int
    case_count: int
    recall_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float
    p50_latency_ms: int
    p95_latency_ms: int
    cases: List[RetrievalCaseResult]

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def evaluate_retrieval(
    dataset: RetrievalEvaluationDataset,
    search: Callable[[str, int], Sequence[KnowledgeSearchResult]],
    engine: str,
    limit: int,
) -> RetrievalEvaluationReport:
    if limit <= 0 or limit > 100:
        raise ValueError("evaluation limit must be between 1 and 100")
    case_results = []
    recalls = []
    hits = []
    reciprocal_ranks = []
    latencies = []
    for case in dataset.cases:
        started = time.monotonic()
        results = list(search(case.query, limit))
        latency_ms = max(0, int((time.monotonic() - started) * 1000))
        retrieved_paths = [item.relative_path for item in results]
        expected = set(case.expected_paths)
        matched = expected & set(retrieved_paths)
        first_rank = next(
            (index for index, path in enumerate(retrieved_paths, start=1) if path in expected),
            None,
        )
        reciprocal_rank = 1.0 / first_rank if first_rank is not None else 0.0
        recalls.append(len(matched) / len(expected))
        hits.append(1.0 if matched else 0.0)
        reciprocal_ranks.append(reciprocal_rank)
        latencies.append(latency_ms)
        case_results.append(
            RetrievalCaseResult(
                case.case_id,
                len(expected),
                len(retrieved_paths),
                len(matched),
                reciprocal_rank,
                latency_ms,
            )
        )
    return RetrievalEvaluationReport(
        schema="retrieval_eval_report_v1",
        dataset_name=dataset.name,
        engine=engine,
        limit=limit,
        case_count=len(case_results),
        recall_at_k=_mean(recalls),
        hit_rate_at_k=_mean(hits),
        mrr_at_k=_mean(reciprocal_ranks),
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        cases=case_results,
    )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: Sequence[int], quantile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[rank]


def _safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.strip()) <= 128
        and all(character.isalnum() or character in "._-" for character in value.strip())
    )
