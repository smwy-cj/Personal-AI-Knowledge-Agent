"""Privacy-minimized structured events for runtime observability."""

import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union

from .models import utc_now


EVENT_TYPES = {
    "task_started",
    "task_resumed",
    "task_waiting_user",
    "task_completed",
    "task_failed",
    "task_cancelled",
    "step_started",
    "step_completed",
    "step_failed",
    "verification_started",
    "model_attempt",
    "model_retry",
    "model_completed",
    "evaluation_completed",
    "events_pruned",
}

ALLOWED_ATTRIBUTE_KEYS = {
    "status",
    "executor",
    "kind",
    "attempt",
    "duration_ms",
    "artifact_count",
    "evidence_count",
    "memory_candidate_count",
    "error_type",
    "provider_id",
    "model_id",
    "task_type",
    "prompt_version",
    "input_tokens",
    "output_tokens",
    "model_call_count",
    "retry_delay_ms",
    "final_status",
    "tool_calls",
    "token_usage",
    "retry_count",
    "case_count",
    "limit",
    "recall_at_k",
    "hit_rate_at_k",
    "mrr_at_k",
    "p50_latency_ms",
    "p95_latency_ms",
    "engine",
    "dataset_name",
    "evaluation_type",
    "gate_passed",
    "structure_valid_rate",
    "paragraph_coverage_rate",
    "exact_citation_set_rate",
    "citation_precision",
    "citation_recall",
    "citation_f1",
    "status_accuracy",
    "reason_accuracy",
    "approval_accuracy",
    "decision_accuracy",
    "estimated_cost_microusd",
    "retention_days",
    "deleted_count",
}

FORBIDDEN_KEY_PARTS = {
    "prompt", "payload", "content", "query", "answer", "evidence", "secret",
    "token_value", "password", "credential", "api_key",
}


class ObservationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ObservationEvent:
    event_id: int
    event_type: str
    task_id: Optional[str]
    step_id: Optional[str]
    attributes: Dict[str, Any]
    created_at: str


class SQLiteEventStore:
    def __init__(self, database_path: Union[str, Path]) -> None:
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS observation_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    step_id TEXT,
                    attributes_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_observation_task_event
                    ON observation_events(task_id, event_id);
                CREATE INDEX IF NOT EXISTS idx_observation_type_event
                    ON observation_events(event_type, event_id);
                CREATE INDEX IF NOT EXISTS idx_observation_created_at
                    ON observation_events(created_at);
                CREATE INDEX IF NOT EXISTS idx_observation_type_created_at
                    ON observation_events(event_type, created_at, event_id);
                """
            )

    def record(
        self,
        event_type: str,
        task_id: Optional[str] = None,
        step_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> int:
        if event_type not in EVENT_TYPES:
            raise ObservationValidationError("unsupported observation event type")
        if task_id is not None and not task_id.strip():
            raise ObservationValidationError("task_id must be non-empty when supplied")
        if step_id is not None and not step_id.strip():
            raise ObservationValidationError("step_id must be non-empty when supplied")
        safe = _validate_attributes(attributes or {})
        created_at = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO observation_events(
                    event_type, task_id, step_id, attributes_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    task_id,
                    step_id,
                    json.dumps(safe, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
            return int(cursor.lastrowid)

    def list_task_events(self, task_id: str, limit: int = 200) -> List[ObservationEvent]:
        if not task_id.strip() or limit <= 0 or limit > 1000:
            raise ValueError("task_id and event limit are invalid")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM observation_events
                WHERE task_id = ? ORDER BY event_id LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [_event(row) for row in rows]

    def list_events(
        self, event_type: Optional[str] = None, limit: int = 200
    ) -> List[ObservationEvent]:
        if limit <= 0 or limit > 1000:
            raise ValueError("event limit must be between 1 and 1000")
        if event_type is not None and event_type not in EVENT_TYPES:
            raise ObservationValidationError("unsupported observation event type")
        with self._connect() as connection:
            if event_type is None:
                rows = connection.execute(
                    "SELECT * FROM observation_events ORDER BY event_id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM observation_events
                    WHERE event_type = ? ORDER BY event_id DESC LIMIT ?
                    """,
                    (event_type, limit),
                ).fetchall()
        return [_event(row) for row in rows]

    def aggregate(self, limit: int = 1000) -> Dict[str, Any]:
        events = self.list_events(limit=limit)
        terminal = [
            item
            for item in events
            if item.event_type in {"task_completed", "task_failed", "task_cancelled"}
        ]
        statuses: Dict[str, int] = {}
        for item in terminal:
            status = str(item.attributes.get("final_status", "UNKNOWN"))
            statuses[status] = statuses.get(status, 0) + 1
        completed = statuses.get("COMPLETED", 0)
        step_durations = [
            int(item.attributes["duration_ms"])
            for item in events
            if item.event_type == "step_completed" and "duration_ms" in item.attributes
        ]
        model_durations = [
            int(item.attributes["duration_ms"])
            for item in events
            if item.event_type == "model_completed" and "duration_ms" in item.attributes
        ]
        model_events = [item for item in events if item.event_type == "model_completed"]
        estimated_cost_microusd = sum(
            int(item.attributes.get("estimated_cost_microusd", 0))
            for item in model_events
        )
        return {
            "schema": "observability_summary_v1",
            "event_count": len(events),
            "terminal_task_count": len(terminal),
            "task_status_counts": statuses,
            "task_success_rate": completed / len(terminal) if terminal else 0.0,
            "step_completed_count": sum(
                item.event_type == "step_completed" for item in events
            ),
            "step_failed_count": sum(item.event_type == "step_failed" for item in events),
            "model_completed_count": len(model_events),
            "model_retry_count": sum(item.event_type == "model_retry" for item in events),
            "input_tokens": sum(int(item.attributes.get("input_tokens", 0)) for item in model_events),
            "output_tokens": sum(int(item.attributes.get("output_tokens", 0)) for item in model_events),
            "estimated_cost_microusd": estimated_cost_microusd,
            "estimated_cost_usd": estimated_cost_microusd / 1_000_000,
            "step_p50_latency_ms": _percentile(step_durations, 0.50),
            "step_p95_latency_ms": _percentile(step_durations, 0.95),
            "model_p50_latency_ms": _percentile(model_durations, 0.50),
            "model_p95_latency_ms": _percentile(model_durations, 0.95),
        }

    def cost_report(
        self,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        task_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        include_calls: bool = False,
    ) -> Dict[str, Any]:
        normalized_from = normalize_utc_bound(from_time, "from")
        normalized_to = normalize_utc_bound(to_time, "to")
        if normalized_from is not None and normalized_to is not None:
            if normalized_from >= normalized_to:
                raise ValueError("cost report from time must be before to time")
        task_id = _optional_filter(task_id, "task_id")
        provider_id = _optional_filter(provider_id, "provider_id")
        if not isinstance(include_calls, bool):
            raise ValueError("include_calls must be a boolean")

        clauses = ["event_type = ?"]
        parameters: List[object] = ["model_completed"]
        if normalized_from is not None:
            clauses.append("created_at >= ?")
            parameters.append(normalized_from)
        if normalized_to is not None:
            clauses.append("created_at < ?")
            parameters.append(normalized_to)
        if task_id is not None:
            clauses.append("task_id = ?")
            parameters.append(task_id)
        statement = (
            "SELECT * FROM observation_events WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at, event_id"
        )
        with self._connect() as connection:
            events = [_event(row) for row in connection.execute(statement, parameters)]

        calls = []
        for event in events:
            call = _cost_call(event)
            if provider_id is not None and call["provider_id"] != provider_id:
                continue
            calls.append(call)

        by_task: Dict[Optional[str], Dict[str, Any]] = {}
        by_provider: Dict[Optional[str], Dict[str, Any]] = {}
        for call in calls:
            _add_cost(by_task, call["task_id"], "task_id", call)
            _add_cost(by_provider, call["provider_id"], "provider_id", call)
        totals = _cost_totals(calls)
        output: Dict[str, Any] = {
            "schema": "cost_report_v1",
            "generated_at": utc_now(),
            "filters": {
                "from": normalized_from,
                "to": normalized_to,
                "task_id": task_id,
                "provider_id": provider_id,
            },
            "window_semantics": "from_inclusive_to_exclusive",
            "totals": {
                **totals,
                "task_count": len({call["task_id"] for call in calls if call["task_id"]}),
                "provider_count": len(
                    {call["provider_id"] for call in calls if call["provider_id"]}
                ),
            },
            "by_task": _sorted_cost_groups(by_task, "task_id"),
            "by_provider": _sorted_cost_groups(by_provider, "provider_id"),
            "audit_calls_included": include_calls,
        }
        if include_calls:
            output["calls"] = calls
        return output

    def prune(self, retention_days: int, apply: bool = False) -> Dict[str, Any]:
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days <= 0:
            raise ValueError("retention_days must be a positive integer")
        cutoff_at = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).isoformat()
        with self._connect() as connection:
            matched_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM observation_events WHERE created_at < ?",
                    (cutoff_at,),
                ).fetchone()[0]
            )
            deleted_count = 0
            if apply:
                cursor = connection.execute(
                    "DELETE FROM observation_events WHERE created_at < ?",
                    (cutoff_at,),
                )
                deleted_count = int(cursor.rowcount)
                attributes = {
                    "retention_days": retention_days,
                    "deleted_count": deleted_count,
                }
                connection.execute(
                    """
                    INSERT INTO observation_events(
                        event_type, task_id, step_id, attributes_json, created_at
                    ) VALUES (?, NULL, NULL, ?, ?)
                    """,
                    (
                        "events_pruned",
                        json.dumps(attributes, sort_keys=True),
                        utc_now(),
                    ),
                )
        return {
            "schema": "observability_retention_v1",
            "applied": apply,
            "retention_days": retention_days,
            "cutoff_at": cutoff_at,
            "matched_count": matched_count,
            "deleted_count": deleted_count,
        }


def record_event_safely(
    store: Optional[SQLiteEventStore],
    event_type: str,
    task_id: Optional[str] = None,
    step_id: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    if store is None:
        return False
    try:
        store.record(event_type, task_id, step_id, attributes)
        return True
    except (OSError, sqlite3.Error):
        return False

def _validate_attributes(attributes: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(attributes, dict):
        raise ObservationValidationError("observation attributes must be an object")
    safe: Dict[str, Any] = {}
    for key, value in attributes.items():
        if key not in ALLOWED_ATTRIBUTE_KEYS:
            raise ObservationValidationError("observation attribute is not allowed: %s" % key)
        if isinstance(value, bool) or value is None or isinstance(value, (str, int, float)):
            safe[key] = value
        else:
            raise ObservationValidationError(
                "observation attributes must contain scalar values"
            )
    return safe


def _event(row: sqlite3.Row) -> ObservationEvent:
    return ObservationEvent(
        event_id=row["event_id"],
        event_type=row["event_type"],
        task_id=row["task_id"],
        step_id=row["step_id"],
        attributes=json.loads(row["attributes_json"]),
        created_at=row["created_at"],
    )


def _percentile(values: List[int], quantile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def normalize_utc_bound(value: Optional[str], name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("cost report %s time must be a non-empty ISO-8601 value" % name)
    raw = value.strip()
    if raw.endswith("Z") or raw.endswith("z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("cost report %s time must be valid ISO-8601" % name) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("cost report %s time must include a timezone" % name)
    return parsed.astimezone(timezone.utc).isoformat()


def _optional_filter(value: Optional[str], name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 128:
        raise ValueError("cost report %s filter is invalid" % name)
    return value.strip()


def _cost_call(event: ObservationEvent) -> Dict[str, Any]:
    attributes = event.attributes
    has_cost = "estimated_cost_microusd" in attributes
    cost = _non_negative_integer(attributes.get("estimated_cost_microusd", 0), "cost")
    return {
        "event_id": event.event_id,
        "created_at": event.created_at,
        "task_id": event.task_id,
        "step_id": event.step_id,
        "provider_id": _optional_text(attributes.get("provider_id")),
        "model_id": _optional_text(attributes.get("model_id")),
        "task_type": _optional_text(attributes.get("task_type")),
        "prompt_version": _optional_text(attributes.get("prompt_version")),
        "input_tokens": _non_negative_integer(attributes.get("input_tokens", 0), "input tokens"),
        "output_tokens": _non_negative_integer(attributes.get("output_tokens", 0), "output tokens"),
        "duration_ms": _non_negative_integer(attributes.get("duration_ms", 0), "duration"),
        "has_cost_estimate": has_cost,
        "estimated_cost_microusd": cost,
        "estimated_cost_usd": cost / 1_000_000,
    }


def _non_negative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("model cost event has invalid %s" % name)
    return value


def _optional_text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _cost_totals(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    cost = sum(int(call["estimated_cost_microusd"]) for call in calls)
    estimated = sum(bool(call["has_cost_estimate"]) for call in calls)
    return {
        "model_call_count": len(calls),
        "calls_with_cost_estimate": estimated,
        "calls_without_cost_estimate": len(calls) - estimated,
        "input_tokens": sum(int(call["input_tokens"]) for call in calls),
        "output_tokens": sum(int(call["output_tokens"]) for call in calls),
        "duration_ms": sum(int(call["duration_ms"]) for call in calls),
        "estimated_cost_microusd": cost,
        "estimated_cost_usd": cost / 1_000_000,
    }


def _add_cost(
    groups: Dict[Optional[str], Dict[str, Any]],
    key: Optional[str],
    key_name: str,
    call: Dict[str, Any],
) -> None:
    group = groups.setdefault(key, {key_name: key, "_calls": []})
    group["_calls"].append(call)


def _sorted_cost_groups(
    groups: Dict[Optional[str], Dict[str, Any]], key_name: str
) -> List[Dict[str, Any]]:
    output = []
    for key in sorted(groups, key=lambda value: (value is None, value or "")):
        group = groups[key]
        output.append({key_name: key, **_cost_totals(group["_calls"])})
    return output
