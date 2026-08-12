"""Reviewable baseline candidates and privacy-minimized report comparisons."""

import hashlib
import json
import math
from typing import Any, Dict, Tuple, Union
from pathlib import Path

from .quality_baseline import (
    QUALITY_BASELINE_SCHEMA,
    QualityBaselinePolicy,
    validate_quality_baseline_scope,
)
from .quality_evaluation import (
    OBSERVABILITY_LEGACY_MAXIMUM_METRICS,
    OBSERVABILITY_MINIMUM_METRICS,
    OBSERVABILITY_QUOTA_MAXIMUM_METRICS,
    RETRIEVAL_MAXIMUM_METRICS,
    RETRIEVAL_MINIMUM_METRICS,
)


QUALITY_BASELINE_CANDIDATE_SCHEMA = "quality_baseline_candidate_v1"
QUALITY_REPORT_COMPARISON_SCHEMA = "quality_report_comparison_v1"


def generate_quality_baseline_candidate(
    report_path: Union[str, Path],
    name: str,
    minimum_retention: float = 0.98,
    maximum_headroom: float = 1.20,
) -> Dict[str, object]:
    """Generate a pending policy proposal without copying report content or paths."""
    if (
        isinstance(minimum_retention, bool)
        or not isinstance(minimum_retention, (int, float))
        or not math.isfinite(float(minimum_retention))
        or not 0 <= minimum_retention <= 1
    ):
        raise ValueError("minimum retention must be between 0 and 1")
    if (
        isinstance(maximum_headroom, bool)
        or not isinstance(maximum_headroom, (int, float))
        or not math.isfinite(float(maximum_headroom))
        or maximum_headroom < 1
    ):
        raise ValueError("maximum headroom must be at least 1")

    report = _load_report(report_path)
    scope, minimum_metrics, maximum_metrics = _report_profile(report)
    observations = _metric_values(report, minimum_metrics, maximum_metrics)
    minimums = {
        metric: _rounded(observations[metric] * float(minimum_retention))
        for metric in sorted(minimum_metrics)
    }
    maximums = {
        metric: _rounded(observations[metric] * float(maximum_headroom))
        for metric in sorted(maximum_metrics)
    }
    proposed_policy = {
        "schema": QUALITY_BASELINE_SCHEMA,
        "name": name,
        "scope": scope,
        "minimums": minimums,
        "maximums": maximums,
    }
    validated = QualityBaselinePolicy.from_document(proposed_policy)
    return {
        "schema": QUALITY_BASELINE_CANDIDATE_SCHEMA,
        "status": "pending_review",
        "source_report": {
            "schema": report["schema"],
            "sha256": _report_digest(report),
        },
        "generation_parameters": {
            "minimum_retention": float(minimum_retention),
            "maximum_headroom": float(maximum_headroom),
        },
        "observed_metrics": {
            metric: observations[metric] for metric in sorted(observations)
        },
        "proposed_policy": {
            "schema": QUALITY_BASELINE_SCHEMA,
            "name": validated.name,
            "scope": validated.scope,
            "minimums": validated.minimums,
            "maximums": validated.maximums,
        },
    }


def compare_quality_reports(
    reference_path: Union[str, Path], current_path: Union[str, Path]
) -> Dict[str, object]:
    """Compare equivalent reports using each metric's declared direction."""
    reference = _load_report(reference_path)
    current = _load_report(current_path)
    reference_scope, minimum_metrics, maximum_metrics = _report_profile(reference)
    current_scope, current_minimums, current_maximums = _report_profile(current)
    if reference["schema"] != current["schema"] or reference_scope != current_scope:
        raise ValueError("quality reports must have the same schema and evaluation scope")
    if minimum_metrics != current_minimums or maximum_metrics != current_maximums:
        raise ValueError("quality reports must have the same metric sets")

    reference_values = _metric_values(reference, minimum_metrics, maximum_metrics)
    current_values = _metric_values(current, minimum_metrics, maximum_metrics)
    metrics: Dict[str, object] = {}
    counts = {"improved": 0, "degraded": 0, "unchanged": 0}
    for metric in sorted(minimum_metrics | maximum_metrics):
        direction = "minimum" if metric in minimum_metrics else "maximum"
        before = reference_values[metric]
        after = current_values[metric]
        change = after - before
        if change == 0:
            outcome = "unchanged"
        elif (direction == "minimum" and change > 0) or (
            direction == "maximum" and change < 0
        ):
            outcome = "improved"
        else:
            outcome = "degraded"
        counts[outcome] += 1
        metrics[metric] = {
            "direction": direction,
            "reference": before,
            "current": after,
            "absolute_change": _rounded(change),
            "relative_change": (
                None if before == 0 else _rounded(change / abs(before))
            ),
            "outcome": outcome,
        }
    return {
        "schema": QUALITY_REPORT_COMPARISON_SCHEMA,
        "evaluation_scope": reference_scope,
        "reference_report": {
            "schema": reference["schema"],
            "sha256": _report_digest(reference),
        },
        "current_report": {
            "schema": current["schema"],
            "sha256": _report_digest(current),
        },
        "summary": {
            **counts,
            "regression_detected": counts["degraded"] > 0,
        },
        "metrics": metrics,
    }


def _load_report(path: Union[str, Path]) -> Dict[str, Any]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("quality report must be valid UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("quality report root must be an object")
    return document


def _report_profile(
    report: Dict[str, Any]
) -> Tuple[Dict[str, object], frozenset, frozenset]:
    schema = report.get("schema")
    scope = validate_quality_baseline_scope(report.get("evaluation_scope"))
    if schema == "retrieval_eval_report_v1":
        if scope["evaluation_type"] != "retrieval" or any(
            report.get(name) != scope[name]
            for name in ("dataset_name", "engine", "limit")
        ):
            raise ValueError("retrieval report scope does not match its metadata")
        return scope, RETRIEVAL_MINIMUM_METRICS, RETRIEVAL_MAXIMUM_METRICS
    if schema == "observability_summary_v1":
        if scope["evaluation_type"] != "observability":
            raise ValueError("observability report scope is invalid")
        quota_metrics = frozenset(
            metric
            for metric in OBSERVABILITY_QUOTA_MAXIMUM_METRICS
            if metric in report
        )
        if quota_metrics and quota_metrics != OBSERVABILITY_QUOTA_MAXIMUM_METRICS:
            raise ValueError("observability report quota metrics must be complete")
        return (
            scope,
            OBSERVABILITY_MINIMUM_METRICS,
            OBSERVABILITY_LEGACY_MAXIMUM_METRICS | quota_metrics,
        )
    raise ValueError("unsupported quality report schema")


def _metric_values(
    report: Dict[str, Any], minimum_metrics: frozenset, maximum_metrics: frozenset
) -> Dict[str, float]:
    output = {}
    for metric in minimum_metrics | maximum_metrics:
        value = report.get(metric)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise ValueError("quality report metric is missing or invalid: %s" % metric)
        if metric in minimum_metrics and not 0 <= value <= 1:
            raise ValueError("quality report minimum metrics must be between 0 and 1")
        if metric in maximum_metrics and value < 0:
            raise ValueError("quality report maximum metrics must be non-negative")
        output[metric] = float(value)
    return output


def _report_digest(report: Dict[str, Any]) -> str:
    encoded = json.dumps(
        report, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _rounded(value: float) -> float:
    return round(float(value), 6)
