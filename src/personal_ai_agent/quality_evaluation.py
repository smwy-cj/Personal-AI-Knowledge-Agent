"""Offline research and memory evaluation with configurable quality gates."""

import hashlib
import json
import math
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .memory_repository import SQLiteMemoryRepository
from .memory_workflow import govern_memory_candidate
from .models import MemoryCandidate
from .research_summary import validate_research_summary


RETRIEVAL_MINIMUM_METRICS = frozenset(
    {"recall_at_k", "hit_rate_at_k", "mrr_at_k"}
)
RETRIEVAL_MAXIMUM_METRICS = frozenset(
    {"p50_latency_ms", "p95_latency_ms"}
)
OBSERVABILITY_MINIMUM_METRICS = frozenset({"task_success_rate"})
OBSERVABILITY_LEGACY_MAXIMUM_METRICS = frozenset(
    {
        "estimated_cost_microusd",
        "estimated_cost_usd",
        "step_p50_latency_ms",
        "step_p95_latency_ms",
        "model_p50_latency_ms",
        "model_p95_latency_ms",
    }
)
OBSERVABILITY_QUOTA_MAXIMUM_METRICS = frozenset(
    {
        "provider_quota_p95_wait_ms",
        "provider_cooldown_count",
        "provider_token_estimate_absolute_error",
    }
)
OBSERVABILITY_MAXIMUM_METRICS = (
    OBSERVABILITY_LEGACY_MAXIMUM_METRICS | OBSERVABILITY_QUOTA_MAXIMUM_METRICS
)


@dataclass(frozen=True)
class ResearchSummaryEvaluationCase:
    case_id: str
    citation_count: int
    summary: Dict[str, Any]
    expected_paragraph_citations: List[List[int]]


@dataclass(frozen=True)
class ResearchSummaryEvaluationDataset:
    name: str
    cases: List[ResearchSummaryEvaluationCase]

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ResearchSummaryEvaluationDataset":
        document = _load_document(path, "research_summary_eval_v1")
        cases = []
        seen = set()
        for item in _cases(document):
            required = {
                "case_id", "citation_count", "summary", "expected_paragraph_citations"
            }
            if not isinstance(item, dict) or set(item) != required:
                raise ValueError("research evaluation cases have an invalid shape")
            case_id = item["case_id"]
            citation_count = item["citation_count"]
            summary = item["summary"]
            expected = item["expected_paragraph_citations"]
            if (
                not _unique_identifier(case_id, seen)
                or isinstance(citation_count, bool)
                or not isinstance(citation_count, int)
                or citation_count <= 0
                or not isinstance(summary, dict)
                or not _citation_sets(expected, citation_count)
            ):
                raise ValueError("research evaluation case values are invalid")
            cases.append(
                ResearchSummaryEvaluationCase(
                    case_id.strip(), citation_count, summary, expected
                )
            )
        return cls(document["name"].strip(), cases)


@dataclass(frozen=True)
class ResearchSummaryCaseResult:
    case_id: str
    structure_valid: bool
    paragraph_count: int
    expected_paragraph_count: int
    covered_paragraph_count: int
    exact_citation_paragraph_count: int
    citation_true_positive: int
    citation_predicted_count: int
    citation_expected_count: int


@dataclass(frozen=True)
class ResearchSummaryEvaluationReport:
    schema: str
    dataset_name: str
    case_count: int
    structure_valid_rate: float
    paragraph_coverage_rate: float
    exact_citation_set_rate: float
    citation_precision: float
    citation_recall: float
    citation_f1: float
    gate_passed: bool
    failed_gates: List[str]
    cases: List[ResearchSummaryCaseResult]

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ExistingMemoryFixture:
    subject: str
    statement: str
    source_ids: List[str]


@dataclass(frozen=True)
class MemoryGovernanceEvaluationCase:
    case_id: str
    subject: str
    statement: str
    source_ids: List[str]
    existing_memories: List[ExistingMemoryFixture]
    expected_status: str
    expected_reason: Optional[str]
    expected_requires_approval: bool


@dataclass(frozen=True)
class MemoryGovernanceEvaluationDataset:
    name: str
    cases: List[MemoryGovernanceEvaluationCase]

    @classmethod
    def load(cls, path: Union[str, Path]) -> "MemoryGovernanceEvaluationDataset":
        document = _load_document(path, "memory_governance_eval_v1")
        cases = []
        seen = set()
        for item in _cases(document):
            required = {
                "case_id", "subject", "statement", "source_ids", "existing_memories",
                "expected_status", "expected_reason", "expected_requires_approval",
            }
            if not isinstance(item, dict) or set(item) != required:
                raise ValueError("memory evaluation cases have an invalid shape")
            fixtures = item["existing_memories"]
            if not isinstance(fixtures, list):
                raise ValueError("existing_memories must be a list")
            existing = [_memory_fixture(fixture) for fixture in fixtures]
            if (
                not _unique_identifier(item["case_id"], seen)
                or not _non_empty(item["subject"])
                or not _non_empty(item["statement"])
                or not _string_list(item["source_ids"])
                or item["expected_status"] not in {"PENDING", "REJECTED"}
                or not (
                    item["expected_reason"] is None
                    or _safe_identifier(item["expected_reason"])
                )
                or not isinstance(item["expected_requires_approval"], bool)
            ):
                raise ValueError("memory evaluation case values are invalid")
            cases.append(
                MemoryGovernanceEvaluationCase(
                    item["case_id"].strip(),
                    item["subject"].strip(),
                    item["statement"].strip(),
                    list(item["source_ids"]),
                    existing,
                    item["expected_status"],
                    item["expected_reason"],
                    item["expected_requires_approval"],
                )
            )
        return cls(document["name"].strip(), cases)


@dataclass(frozen=True)
class MemoryGovernanceCaseResult:
    case_id: str
    status_correct: bool
    reason_correct: bool
    approval_correct: bool
    decision_correct: bool


@dataclass(frozen=True)
class MemoryGovernanceEvaluationReport:
    schema: str
    dataset_name: str
    case_count: int
    status_accuracy: float
    reason_accuracy: float
    approval_accuracy: float
    decision_accuracy: float
    gate_passed: bool
    failed_gates: List[str]
    cases: List[MemoryGovernanceCaseResult]

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


def evaluate_research_summaries(
    dataset: ResearchSummaryEvaluationDataset,
    minimums: Optional[Dict[str, float]] = None,
) -> ResearchSummaryEvaluationReport:
    results = []
    valid_count = covered = exact = true_positive = predicted = expected_total = 0
    paragraph_total = expected_paragraph_total = 0
    for case in dataset.cases:
        actual = _paragraph_citations(case.summary)
        structure_valid = True
        try:
            validate_research_summary(case.summary, case.citation_count)
        except (KeyError, TypeError, ValueError):
            structure_valid = False
        if structure_valid:
            valid_count += 1
        paragraph_total += len(actual)
        expected_paragraph_total += len(case.expected_paragraph_citations)
        paired = min(len(actual), len(case.expected_paragraph_citations))
        for index in range(paired):
            actual_set = set(actual[index])
            expected_set = set(case.expected_paragraph_citations[index])
            if actual_set:
                covered += 1
            if actual_set == expected_set:
                exact += 1
            true_positive += len(actual_set & expected_set)
            predicted += len(actual_set)
            expected_total += len(expected_set)
        for citations in actual[paired:]:
            predicted += len(set(citations))
        for citations in case.expected_paragraph_citations[paired:]:
            expected_total += len(set(citations))
        results.append(
            ResearchSummaryCaseResult(
                case.case_id,
                structure_valid,
                len(actual),
                len(case.expected_paragraph_citations),
                sum(bool(citations) for citations in actual),
                sum(
                    set(actual[index]) == set(case.expected_paragraph_citations[index])
                    for index in range(paired)
                ),
                sum(
                    len(set(actual[index]) & set(case.expected_paragraph_citations[index]))
                    for index in range(paired)
                ),
                sum(len(set(citations)) for citations in actual),
                sum(len(set(citations)) for citations in case.expected_paragraph_citations),
            )
        )
    precision = true_positive / predicted if predicted else 0.0
    recall = true_positive / expected_total if expected_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    metrics = {
        "structure_valid_rate": valid_count / len(results),
        "paragraph_coverage_rate": covered / expected_paragraph_total if expected_paragraph_total else 0.0,
        "exact_citation_set_rate": exact / expected_paragraph_total if expected_paragraph_total else 0.0,
        "citation_precision": precision,
        "citation_recall": recall,
        "citation_f1": f1,
    }
    failed = _failed_gates(metrics, minimums or {})
    return ResearchSummaryEvaluationReport(
        "research_summary_eval_report_v1",
        dataset.name,
        len(results),
        metrics["structure_valid_rate"],
        metrics["paragraph_coverage_rate"],
        metrics["exact_citation_set_rate"],
        precision,
        recall,
        f1,
        not failed,
        failed,
        results,
    )


def evaluate_memory_governance(
    dataset: MemoryGovernanceEvaluationDataset,
    minimums: Optional[Dict[str, float]] = None,
) -> MemoryGovernanceEvaluationReport:
    results = []
    with tempfile.TemporaryDirectory() as temporary:
        for case in dataset.cases:
            repository = SQLiteMemoryRepository(Path(temporary) / (case.case_id + ".sqlite3"))
            for index, fixture in enumerate(case.existing_memories):
                seeded = govern_memory_candidate(
                    repository, fixture.subject, fixture.statement, fixture.source_ids
                )
                seeded.candidate_id = _fixture_memory_id(case.case_id, index)
                seeded.governance_status = "APPROVED"
                repository.save_approved(seeded)
            candidate = govern_memory_candidate(
                repository, case.subject, case.statement, case.source_ids
            )
            status_correct = candidate.governance_status == case.expected_status
            reason_correct = candidate.decision_reason == case.expected_reason
            approval_correct = candidate.requires_approval == case.expected_requires_approval
            results.append(
                MemoryGovernanceCaseResult(
                    case.case_id,
                    status_correct,
                    reason_correct,
                    approval_correct,
                    status_correct and reason_correct and approval_correct,
                )
            )
    metrics = {
        "status_accuracy": _boolean_rate(results, "status_correct"),
        "reason_accuracy": _boolean_rate(results, "reason_correct"),
        "approval_accuracy": _boolean_rate(results, "approval_correct"),
        "decision_accuracy": _boolean_rate(results, "decision_correct"),
    }
    failed = _failed_gates(metrics, minimums or {})
    return MemoryGovernanceEvaluationReport(
        "memory_governance_eval_report_v1",
        dataset.name,
        len(results),
        metrics["status_accuracy"],
        metrics["reason_accuracy"],
        metrics["approval_accuracy"],
        metrics["decision_accuracy"],
        not failed,
        failed,
        results,
    )


def apply_retrieval_gates(
    report: Dict[str, object],
    minimums: Dict[str, float],
    maximums: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    return apply_metric_gates(
        report,
        minimums,
        maximums or {},
        RETRIEVAL_MINIMUM_METRICS,
        RETRIEVAL_MAXIMUM_METRICS,
    )


def apply_observability_gates(
    report: Dict[str, object],
    minimums: Dict[str, float],
    maximums: Dict[str, float],
) -> Dict[str, object]:
    return apply_metric_gates(
        report,
        minimums,
        maximums,
        OBSERVABILITY_MINIMUM_METRICS,
        OBSERVABILITY_MAXIMUM_METRICS,
    )


def apply_metric_gates(
    report: Dict[str, object],
    minimums: Dict[str, float],
    maximums: Dict[str, float],
    allowed_minimums: frozenset,
    allowed_maximums: frozenset,
) -> Dict[str, object]:
    output = dict(report)
    _validate_gate_names(minimums, allowed_minimums, "minimum")
    _validate_gate_names(maximums, allowed_maximums, "maximum")
    failed = _failed_gates(output, minimums)
    failed.extend(_failed_maximum_gates(output, maximums))
    output["gate_passed"] = not failed
    output["failed_gates"] = failed
    output["gate_thresholds"] = {
        "minimums": dict(minimums),
        "maximums": dict(maximums),
    }
    return output


def _failed_gates(metrics: Dict[str, object], minimums: Dict[str, float]) -> List[str]:
    failed = []
    for name, threshold in minimums.items():
        if name not in metrics:
            raise ValueError("unknown quality gate metric: %s" % name)
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or not 0 <= threshold <= 1
        ):
            raise ValueError("quality gate thresholds must be between 0 and 1")
        if float(metrics[name]) < float(threshold):
            failed.append(name)
    return failed


def _failed_maximum_gates(
    metrics: Dict[str, object], maximums: Dict[str, float]
) -> List[str]:
    failed = []
    for name, threshold in maximums.items():
        if name not in metrics:
            raise ValueError("unknown quality gate metric: %s" % name)
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or threshold < 0
        ):
            raise ValueError("quality maximum thresholds must be finite and non-negative")
        if float(metrics[name]) > float(threshold):
            failed.append(name)
    return failed


def _validate_gate_names(
    thresholds: Dict[str, float], allowed: frozenset, direction: str
) -> None:
    for name in thresholds:
        if name not in allowed:
            raise ValueError("unsupported %s gate metric: %s" % (direction, name))


def _load_document(path: Union[str, Path], schema: str) -> Dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("evaluation dataset must be valid UTF-8 JSON") from exc
    if not isinstance(document, dict) or document.get("schema") != schema:
        raise ValueError("unsupported evaluation dataset schema")
    if set(document) != {"schema", "name", "cases"} or not _safe_identifier(document.get("name")):
        raise ValueError("evaluation dataset root is invalid")
    return document


def _cases(document: Dict[str, Any]) -> List[Any]:
    cases = document["cases"]
    if not isinstance(cases, list) or not cases:
        raise ValueError("evaluation dataset cases are required")
    return cases


def _paragraph_citations(summary: Dict[str, Any]) -> List[List[int]]:
    output = []
    sections = summary.get("sections", [])
    if not isinstance(sections, list):
        return output
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("paragraphs"), list):
            continue
        for paragraph in section["paragraphs"]:
            citations = paragraph.get("citations", []) if isinstance(paragraph, dict) else []
            output.append(list(citations) if isinstance(citations, list) else [])
    return output


def _citation_sets(value: Any, maximum: int) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(items, list)
            and bool(items)
            and len(items) == len(set(items))
            and all(isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= maximum for item in items)
            for items in value
        )
    )


def _memory_fixture(value: Any) -> ExistingMemoryFixture:
    if not isinstance(value, dict) or set(value) != {"subject", "statement", "source_ids"}:
        raise ValueError("existing memory fixtures have an invalid shape")
    if not _non_empty(value["subject"]) or not _non_empty(value["statement"]) or not _string_list(value["source_ids"]):
        raise ValueError("existing memory fixture values are invalid")
    return ExistingMemoryFixture(value["subject"].strip(), value["statement"].strip(), list(value["source_ids"]))


def _fixture_memory_id(case_id: str, index: int) -> str:
    return "memory_" + hashlib.md5((case_id + str(index)).encode("utf-8")).hexdigest()


def _boolean_rate(items: Sequence[Any], field: str) -> float:
    return sum(bool(getattr(item, field)) for item in items) / len(items) if items else 0.0


def _unique_identifier(value: Any, seen: set) -> bool:
    if not _safe_identifier(value) or value in seen:
        return False
    seen.add(value)
    return True


def _safe_identifier(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= 128 and all(
        character.isalnum() or character in "._-" for character in value.strip()
    )


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and bool(item.strip()) for item in value)
