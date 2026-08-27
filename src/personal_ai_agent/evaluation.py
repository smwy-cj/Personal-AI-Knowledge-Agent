"""Versioned retrieval evaluation datasets and deterministic metrics."""

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from .knowledge import KnowledgeSearchResult


RETRIEVAL_DATASET_V1 = "retrieval_eval_v1"
RETRIEVAL_DATASET_V2 = "retrieval_dataset_v2"
RETRIEVAL_QUERY_TYPES = frozenset(
    {"factual", "conceptual", "navigational", "tag", "link", "synonym", "no_answer"}
)


@dataclass(frozen=True)
class ExpectedRetrievalChunk:
    path: str
    heading: Optional[str]


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    case_id: str
    query: str
    expected_paths: List[str]
    language: str = "und"
    query_type: str = "conceptual"
    expects_answer: bool = True
    expected_chunks: List[ExpectedRetrievalChunk] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalEvaluationDataset:
    name: str
    cases: List[RetrievalEvaluationCase]
    schema: str = RETRIEVAL_DATASET_V1

    @classmethod
    def load(cls, path: Union[str, Path]) -> "RetrievalEvaluationDataset":
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("evaluation dataset must be valid UTF-8 JSON") from exc
        if not isinstance(document, dict) or document.get("schema") not in {
            RETRIEVAL_DATASET_V1,
            RETRIEVAL_DATASET_V2,
        }:
            raise ValueError("unsupported retrieval evaluation dataset schema")
        schema = document["schema"]
        name = document.get("name")
        items = document.get("cases")
        if not _safe_identifier(name) or not isinstance(items, list) or not items:
            raise ValueError("evaluation dataset name and cases are required")
        cases = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("evaluation cases have an invalid shape")
            if schema == RETRIEVAL_DATASET_V1:
                if set(item) != {"case_id", "query", "expected_paths"}:
                    raise ValueError("evaluation cases have an invalid shape")
                language = "und"
                query_type = "conceptual"
                expects_answer = True
                expected_chunks = []
            else:
                required = {
                    "case_id",
                    "query",
                    "language",
                    "query_type",
                    "expects_answer",
                    "expected_paths",
                    "expected_chunks",
                }
                if set(item) != required:
                    raise ValueError("evaluation cases have an invalid shape")
                language = item["language"]
                query_type = item["query_type"]
                expects_answer = item["expects_answer"]
                expected_chunks = _expected_chunks(item["expected_chunks"])
            case_id = item["case_id"]
            query = item["query"]
            expected = item["expected_paths"]
            if (
                not _safe_identifier(case_id)
                or case_id in seen
                or not isinstance(query, str)
                or not query.strip()
                or not isinstance(expected, list)
                or any(not isinstance(path, str) or not path.strip() for path in expected)
                or not _language(language)
                or query_type not in RETRIEVAL_QUERY_TYPES
                or not isinstance(expects_answer, bool)
                or (expects_answer and not expected)
                or (not expects_answer and (expected or expected_chunks))
                or (query_type == "no_answer") != (not expects_answer)
                or any(chunk.path not in expected for chunk in expected_chunks)
            ):
                raise ValueError("evaluation case values are invalid")
            seen.add(case_id)
            cases.append(
                RetrievalEvaluationCase(
                    case_id.strip(),
                    query.strip(),
                    list(dict.fromkeys(path.strip() for path in expected)),
                    language.strip(),
                    query_type,
                    expects_answer,
                    expected_chunks,
                )
            )
        return cls(name.strip(), cases, schema)


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id: str
    language: str
    query_type: str
    expects_answer: bool
    expected_count: int
    retrieved_count: int
    matched_count: int
    expected_chunk_count: int
    matched_chunk_count: int
    false_positive: bool
    reciprocal_rank: float
    latency_ms: int


@dataclass(frozen=True)
class RetrievalEvaluationReport:
    schema: str
    dataset_name: str
    engine: str
    limit: int
    case_count: int
    answer_case_count: int
    no_answer_case_count: int
    recall_at_k: float
    hit_rate_at_k: float
    mrr_at_k: float
    chunk_case_count: int
    chunk_recall_at_k: float
    no_answer_false_positive_rate: float
    p50_latency_ms: int
    p95_latency_ms: int
    cases: List[RetrievalCaseResult]

    def as_dict(self) -> Dict[str, object]:
        document = asdict(self)
        if self.schema == "retrieval_eval_report_v1":
            for name in (
                "answer_case_count",
                "no_answer_case_count",
                "chunk_case_count",
                "chunk_recall_at_k",
                "no_answer_false_positive_rate",
            ):
                document.pop(name)
            for case in document["cases"]:
                for name in (
                    "language",
                    "query_type",
                    "expects_answer",
                    "expected_chunk_count",
                    "matched_chunk_count",
                    "false_positive",
                ):
                    case.pop(name)
        return document


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
    chunk_recalls = []
    no_answer_false_positives = []
    for case in dataset.cases:
        started = time.monotonic()
        results = list(search(case.query, limit))
        latency_ms = max(0, int((time.monotonic() - started) * 1000))
        retrieved_paths = [item.relative_path for item in results]
        expected = set(case.expected_paths)
        matched = expected & set(retrieved_paths)
        expected_chunks = {(item.path, item.heading) for item in case.expected_chunks}
        retrieved_chunks = {(item.relative_path, item.heading) for item in results}
        matched_chunks = expected_chunks & retrieved_chunks
        first_rank = next(
            (index for index, path in enumerate(retrieved_paths, start=1) if path in expected),
            None,
        )
        reciprocal_rank = 1.0 / first_rank if first_rank is not None else 0.0
        if case.expects_answer:
            recalls.append(len(matched) / len(expected))
            hits.append(1.0 if matched else 0.0)
            reciprocal_ranks.append(reciprocal_rank)
        else:
            no_answer_false_positives.append(1.0 if results else 0.0)
        if expected_chunks:
            chunk_recalls.append(len(matched_chunks) / len(expected_chunks))
        latencies.append(latency_ms)
        case_results.append(
            RetrievalCaseResult(
                case.case_id,
                case.language,
                case.query_type,
                case.expects_answer,
                len(expected),
                len(retrieved_paths),
                len(matched),
                len(expected_chunks),
                len(matched_chunks),
                not case.expects_answer and bool(results),
                reciprocal_rank,
                latency_ms,
            )
        )
    return RetrievalEvaluationReport(
        schema=(
            "retrieval_eval_report_v2"
            if dataset.schema == RETRIEVAL_DATASET_V2
            else "retrieval_eval_report_v1"
        ),
        dataset_name=dataset.name,
        engine=engine,
        limit=limit,
        case_count=len(case_results),
        answer_case_count=len(recalls),
        no_answer_case_count=len(no_answer_false_positives),
        recall_at_k=_mean(recalls),
        hit_rate_at_k=_mean(hits),
        mrr_at_k=_mean(reciprocal_ranks),
        chunk_case_count=len(chunk_recalls),
        chunk_recall_at_k=_mean(chunk_recalls),
        no_answer_false_positive_rate=_mean(no_answer_false_positives),
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


def _language(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 < len(value.strip()) <= 35
        and all(character.isalnum() or character == "-" for character in value.strip())
    )


def _expected_chunks(value: object) -> List[ExpectedRetrievalChunk]:
    if not isinstance(value, list):
        raise ValueError("expected_chunks must be a list")
    chunks = []
    seen: set = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"path", "heading"}:
            raise ValueError("expected_chunks have an invalid shape")
        path = item["path"]
        heading = item["heading"]
        if (
            not isinstance(path, str)
            or not path.strip()
            or (heading is not None and (not isinstance(heading, str) or not heading.strip()))
        ):
            raise ValueError("expected_chunks have invalid values")
        key: Tuple[str, Optional[str]] = (
            path.strip(),
            heading.strip() if isinstance(heading, str) else None,
        )
        if key not in seen:
            seen.add(key)
            chunks.append(ExpectedRetrievalChunk(*key))
    return chunks
