"""Versioned, scope-bound quality baseline policies."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from .quality_evaluation import (
    OBSERVABILITY_MAXIMUM_METRICS,
    OBSERVABILITY_MINIMUM_METRICS,
    RETRIEVAL_MAXIMUM_METRICS,
    RETRIEVAL_MINIMUM_METRICS,
)


QUALITY_BASELINE_SCHEMA = "quality_baseline_v1"


@dataclass(frozen=True)
class QualityBaselinePolicy:
    name: str
    scope: Dict[str, object]
    minimums: Dict[str, float]
    maximums: Dict[str, float]

    @classmethod
    def load(cls, path: Union[str, Path]) -> "QualityBaselinePolicy":
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("quality baseline must be valid UTF-8 JSON") from exc
        if not isinstance(document, dict) or document.get("schema") != QUALITY_BASELINE_SCHEMA:
            raise ValueError("unsupported quality baseline schema")
        if set(document) != {"schema", "name", "scope", "minimums", "maximums"}:
            raise ValueError("quality baseline root has an invalid shape")
        name = document["name"]
        if not _safe_identifier(name):
            raise ValueError("quality baseline name must be a safe identifier")
        scope = _validated_scope(document["scope"])
        minimums = _thresholds(document["minimums"], "minimum")
        maximums = _thresholds(document["maximums"], "maximum")
        allowed_minimums, allowed_maximums = _allowed_metrics(scope["evaluation_type"])
        _validate_metric_names(minimums, allowed_minimums, "minimum")
        _validate_metric_names(maximums, allowed_maximums, "maximum")
        return cls(name.strip(), scope, minimums, maximums)

    def require_scope(self, expected: Dict[str, object]) -> None:
        if self.scope != expected:
            raise ValueError("quality baseline scope does not match the current evaluation")

    def merged_thresholds(
        self,
        minimum_overrides: Dict[str, float],
        maximum_overrides: Dict[str, float],
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        minimums = dict(self.minimums)
        minimums.update(minimum_overrides)
        maximums = dict(self.maximums)
        maximums.update(maximum_overrides)
        return minimums, maximums

    def metadata(self) -> Dict[str, object]:
        return {
            "schema": QUALITY_BASELINE_SCHEMA,
            "name": self.name,
            "scope": dict(self.scope),
        }


def retrieval_baseline_scope(
    dataset_name: str,
    engine: str,
    limit: int,
    provider_id: Optional[str],
) -> Dict[str, object]:
    return {
        "evaluation_type": "retrieval",
        "dataset_name": dataset_name,
        "engine": engine,
        "limit": limit,
        "provider_id": provider_id,
    }


def observability_baseline_scope(event_limit: int) -> Dict[str, object]:
    return {"evaluation_type": "observability", "event_limit": event_limit}


def resolve_quality_baseline(
    path: Optional[str],
    expected_scope: Dict[str, object],
    minimums: Dict[str, float],
    maximums: Dict[str, float],
) -> Tuple[Dict[str, float], Dict[str, float], Optional[Dict[str, object]]]:
    if path is None:
        return dict(minimums), dict(maximums), None
    policy = QualityBaselinePolicy.load(path)
    policy.require_scope(expected_scope)
    resolved_minimums, resolved_maximums = policy.merged_thresholds(
        minimums, maximums
    )
    return resolved_minimums, resolved_maximums, policy.metadata()


def _validated_scope(value: Any) -> Dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("quality baseline scope must be an object")
    evaluation_type = value.get("evaluation_type")
    if evaluation_type == "retrieval":
        required = {
            "evaluation_type",
            "dataset_name",
            "engine",
            "limit",
            "provider_id",
        }
        if set(value) != required:
            raise ValueError("retrieval baseline scope has an invalid shape")
        dataset_name = value["dataset_name"]
        engine = value["engine"]
        limit = value["limit"]
        provider_id = value["provider_id"]
        if not _safe_identifier(dataset_name):
            raise ValueError("retrieval baseline dataset_name is invalid")
        if engine not in {"keyword", "hybrid"}:
            raise ValueError("retrieval baseline engine must be keyword or hybrid")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("retrieval baseline limit must be between 1 and 100")
        if engine == "keyword" and provider_id is not None:
            raise ValueError("keyword retrieval baseline must not declare a provider_id")
        if engine == "hybrid" and not _safe_identifier(provider_id):
            raise ValueError("hybrid retrieval baseline requires a provider_id")
        return retrieval_baseline_scope(
            dataset_name.strip(), engine, limit, provider_id
        )
    if evaluation_type == "observability":
        if set(value) != {"evaluation_type", "event_limit"}:
            raise ValueError("observability baseline scope has an invalid shape")
        event_limit = value["event_limit"]
        if (
            isinstance(event_limit, bool)
            or not isinstance(event_limit, int)
            or not 1 <= event_limit <= 1000
        ):
            raise ValueError("observability baseline event_limit must be between 1 and 1000")
        return observability_baseline_scope(event_limit)
    raise ValueError("quality baseline evaluation_type is unsupported")


def _thresholds(value: Any, direction: str) -> Dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("quality baseline %ss must be an object" % direction)
    output: Dict[str, float] = {}
    for name, threshold in value.items():
        if not _safe_identifier(name):
            raise ValueError("quality baseline metric names must be safe identifiers")
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
        ):
            raise ValueError("quality baseline thresholds must be finite numbers")
        if direction == "minimum" and not 0 <= threshold <= 1:
            raise ValueError("quality baseline minimums must be between 0 and 1")
        if direction == "maximum" and threshold < 0:
            raise ValueError("quality baseline maximums must be non-negative")
        output[name.strip()] = float(threshold)
    return output


def _allowed_metrics(evaluation_type: object) -> Tuple[frozenset, frozenset]:
    if evaluation_type == "retrieval":
        return RETRIEVAL_MINIMUM_METRICS, RETRIEVAL_MAXIMUM_METRICS
    if evaluation_type == "observability":
        return OBSERVABILITY_MINIMUM_METRICS, OBSERVABILITY_MAXIMUM_METRICS
    raise ValueError("quality baseline evaluation_type is unsupported")


def _validate_metric_names(
    thresholds: Dict[str, float], allowed: frozenset, direction: str
) -> None:
    for name in thresholds:
        if name not in allowed:
            raise ValueError("unsupported %s baseline metric: %s" % (direction, name))


def _safe_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value.strip()) <= 128
        and all(character.isalnum() or character in "._-" for character in value.strip())
    )
