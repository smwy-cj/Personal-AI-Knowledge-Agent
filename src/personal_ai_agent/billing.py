"""Strict provider billing statements and local estimate reconciliation."""

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .observability import SQLiteEventStore, normalize_utc_bound
from .models import utc_now


PROVIDER_BILLING_STATEMENT_SCHEMA = "provider_billing_statement_v1"
COST_RECONCILIATION_REPORT_SCHEMA = "cost_reconciliation_report_v1"


@dataclass(frozen=True)
class ProviderBillingLine:
    model_id: str
    input_tokens: int
    output_tokens: int
    billed_cost_microusd: int


@dataclass(frozen=True)
class ProviderBillingStatement:
    statement_id: str
    provider_id: str
    period_from: str
    period_to: str
    total_billed_cost_microusd: int
    models: List[ProviderBillingLine]
    sha256: str

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ProviderBillingStatement":
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("provider billing statement must be valid UTF-8 JSON") from exc
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document: Any) -> "ProviderBillingStatement":
        root_keys = {
            "schema",
            "statement_id",
            "provider_id",
            "currency",
            "period",
            "total_billed_cost_microusd",
            "models",
        }
        if not isinstance(document, dict) or document.get("schema") != PROVIDER_BILLING_STATEMENT_SCHEMA:
            raise ValueError("unsupported provider billing statement schema")
        if set(document) != root_keys:
            raise ValueError("provider billing statement root has an invalid shape")
        statement_id = _identifier(document["statement_id"], "statement_id")
        provider_id = _identifier(document["provider_id"], "provider_id")
        if document["currency"] != "USD":
            raise ValueError("provider billing statement currency must be USD")
        period = document["period"]
        if not isinstance(period, dict) or set(period) != {"from", "to"}:
            raise ValueError("provider billing statement period has an invalid shape")
        period_from = normalize_utc_bound(period["from"], "statement from")
        period_to = normalize_utc_bound(period["to"], "statement to")
        if period_from is None or period_to is None or period_from >= period_to:
            raise ValueError("provider billing statement period must be increasing")
        total = _non_negative_integer(
            document["total_billed_cost_microusd"], "total billed cost"
        )
        raw_models = document["models"]
        if not isinstance(raw_models, list):
            raise ValueError("provider billing statement models must be a list")
        models = []
        seen = set()
        for item in raw_models:
            if not isinstance(item, dict) or set(item) != {
                "model_id",
                "input_tokens",
                "output_tokens",
                "billed_cost_microusd",
            }:
                raise ValueError("provider billing model line has an invalid shape")
            model_id = _model_identifier(item["model_id"])
            if model_id in seen:
                raise ValueError("provider billing model_id values must be unique")
            seen.add(model_id)
            models.append(
                ProviderBillingLine(
                    model_id,
                    _non_negative_integer(item["input_tokens"], "input tokens"),
                    _non_negative_integer(item["output_tokens"], "output tokens"),
                    _non_negative_integer(
                        item["billed_cost_microusd"], "billed cost"
                    ),
                )
            )
        if sum(item.billed_cost_microusd for item in models) != total:
            raise ValueError("provider billing statement total must equal model line costs")
        models.sort(key=lambda item: item.model_id)
        canonical_document = {
            "schema": PROVIDER_BILLING_STATEMENT_SCHEMA,
            "statement_id": statement_id,
            "provider_id": provider_id,
            "currency": "USD",
            "period": {"from": period_from, "to": period_to},
            "total_billed_cost_microusd": total,
            "models": [
                {
                    "model_id": item.model_id,
                    "input_tokens": item.input_tokens,
                    "output_tokens": item.output_tokens,
                    "billed_cost_microusd": item.billed_cost_microusd,
                }
                for item in models
            ],
        }
        canonical = json.dumps(
            canonical_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            statement_id,
            provider_id,
            period_from,
            period_to,
            total,
            models,
            hashlib.sha256(canonical).hexdigest(),
        )

    def metadata(self) -> Dict[str, object]:
        return {
            "schema": PROVIDER_BILLING_STATEMENT_SCHEMA,
            "statement_id": self.statement_id,
            "provider_id": self.provider_id,
            "currency": "USD",
            "period": {"from": self.period_from, "to": self.period_to},
            "sha256": self.sha256,
        }


def reconcile_provider_billing(
    store: SQLiteEventStore,
    statement_path: Union[str, Path],
    absolute_tolerance_microusd: int = 100,
    relative_tolerance: float = 0.05,
) -> Dict[str, object]:
    statement = ProviderBillingStatement.load(statement_path)
    absolute_tolerance = _non_negative_integer(
        absolute_tolerance_microusd, "absolute tolerance"
    )
    if (
        isinstance(relative_tolerance, bool)
        or not isinstance(relative_tolerance, (int, float))
        or not math.isfinite(float(relative_tolerance))
        or not 0 <= relative_tolerance <= 1
    ):
        raise ValueError("billing relative tolerance must be between 0 and 1")

    local = store.cost_report(
        statement.period_from,
        statement.period_to,
        provider_id=statement.provider_id,
        include_calls=True,
    )
    calls = local["calls"]
    local_models: Dict[Optional[str], Dict[str, int]] = {}
    for call in calls:
        model_id = call["model_id"]
        aggregate = local_models.setdefault(
            model_id,
            {
                "model_call_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_microusd": 0,
                "calls_without_cost_estimate": 0,
            },
        )
        aggregate["model_call_count"] += 1
        aggregate["input_tokens"] += int(call["input_tokens"])
        aggregate["output_tokens"] += int(call["output_tokens"])
        aggregate["estimated_cost_microusd"] += int(
            call["estimated_cost_microusd"]
        )
        aggregate["calls_without_cost_estimate"] += int(
            not call["has_cost_estimate"]
        )
    billed_models = {line.model_id: line for line in statement.models}
    model_ids = sorted(
        set(billed_models) | set(local_models),
        key=lambda value: (value is None, value or ""),
    )
    by_model = []
    model_failure_count = 0
    for model_id in model_ids:
        billed = billed_models.get(model_id)
        estimated = local_models.get(model_id)
        billed_cost = billed.billed_cost_microusd if billed is not None else 0
        estimated_cost = (
            estimated["estimated_cost_microusd"] if estimated is not None else 0
        )
        tolerance = _effective_tolerance(
            billed_cost, absolute_tolerance, float(relative_tolerance)
        )
        difference = estimated_cost - billed_cost
        presence = _presence(billed is not None, estimated is not None, model_id)
        cost_within_tolerance = abs(difference) <= tolerance
        complete_estimates = (
            estimated is None or estimated["calls_without_cost_estimate"] == 0
        )
        passed = (
            presence == "matched" and cost_within_tolerance and complete_estimates
        )
        if not passed:
            model_failure_count += 1
        by_model.append(
            {
                "model_id": model_id,
                "presence": presence,
                "local": {
                    **(
                        estimated
                        if estimated is not None
                        else {
                            "model_call_count": 0,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "estimated_cost_microusd": 0,
                            "calls_without_cost_estimate": 0,
                        }
                    ),
                    "estimated_cost_usd": estimated_cost / 1_000_000,
                },
                "statement": {
                    "input_tokens": billed.input_tokens if billed is not None else 0,
                    "output_tokens": billed.output_tokens if billed is not None else 0,
                    "billed_cost_microusd": billed_cost,
                    "billed_cost_usd": billed_cost / 1_000_000,
                },
                "difference_microusd": difference,
                "absolute_difference_microusd": abs(difference),
                "input_token_difference": (
                    (estimated["input_tokens"] if estimated is not None else 0)
                    - (billed.input_tokens if billed is not None else 0)
                ),
                "output_token_difference": (
                    (estimated["output_tokens"] if estimated is not None else 0)
                    - (billed.output_tokens if billed is not None else 0)
                ),
                "effective_tolerance_microusd": tolerance,
                "cost_within_tolerance": cost_within_tolerance,
                "reconciliation_passed": passed,
            }
        )

    local_total = int(local["totals"]["estimated_cost_microusd"])
    billed_total = statement.total_billed_cost_microusd
    total_difference = local_total - billed_total
    total_tolerance = _effective_tolerance(
        billed_total, absolute_tolerance, float(relative_tolerance)
    )
    missing_estimates = int(local["totals"]["calls_without_cost_estimate"])
    total_within_tolerance = abs(total_difference) <= total_tolerance
    passed = total_within_tolerance and model_failure_count == 0 and missing_estimates == 0
    return {
        "schema": COST_RECONCILIATION_REPORT_SCHEMA,
        "generated_at": utc_now(),
        "statement": statement.metadata(),
        "tolerances": {
            "absolute_microusd": absolute_tolerance,
            "relative": float(relative_tolerance),
            "rule": "max_absolute_or_statement_relative",
        },
        "summary": {
            "local_model_call_count": int(local["totals"]["model_call_count"]),
            "calls_without_cost_estimate": missing_estimates,
            "estimated_cost_microusd": local_total,
            "estimated_cost_usd": local_total / 1_000_000,
            "billed_cost_microusd": billed_total,
            "billed_cost_usd": billed_total / 1_000_000,
            "difference_microusd": total_difference,
            "absolute_difference_microusd": abs(total_difference),
            "effective_tolerance_microusd": total_tolerance,
            "total_within_tolerance": total_within_tolerance,
            "model_failure_count": model_failure_count,
            "reconciliation_passed": passed,
        },
        "by_model": by_model,
        "reconciliation_passed": passed,
    }


def _effective_tolerance(billed: int, absolute: int, relative: float) -> int:
    return max(absolute, int(round(billed * relative)))


def _presence(has_statement: bool, has_local: bool, model_id: Optional[str]) -> str:
    if model_id is None:
        return "local_unattributed"
    if has_statement and has_local:
        return "matched"
    if has_statement:
        return "missing_local_model"
    return "missing_statement_model"


def _identifier(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 128
        or any(not (character.isalnum() or character in "._-") for character in value.strip())
    ):
        raise ValueError("provider billing %s is invalid" % name)
    return value.strip()


def _model_identifier(value: Any) -> str:
    allowed = "._-/:@"
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 256
        or any(
            not (character.isalnum() or character in allowed)
            for character in value.strip()
        )
    ):
        raise ValueError("provider billing model_id is invalid")
    return value.strip()


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("provider billing %s must be a non-negative integer" % name)
    return value
