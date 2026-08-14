"""Versioned JSON serialization for durable task checkpoints."""

import json
from dataclasses import asdict
from typing import Any, Dict

from .models import (
    AgentTaskState,
    Artifact,
    ErrorRecord,
    Evidence,
    MemoryCandidate,
    ModelCallRecord,
    PlanStep,
    StateTransition,
    StepStatus,
    TaskBudget,
    TaskStatus,
)


SCHEMA_VERSION = 1


class UnsupportedSchemaVersion(ValueError):
    pass


def task_state_to_dict(state: AgentTaskState) -> Dict[str, Any]:
    payload = asdict(state)
    payload["status"] = state.status.value
    for index, step in enumerate(state.plan):
        payload["plan"][index]["status"] = step.status.value
        payload["plan"][index]["depends_on"] = list(step.depends_on)
    for index, item in enumerate(state.transitions):
        payload["transitions"][index]["from_status"] = item.from_status.value
        payload["transitions"][index]["to_status"] = item.to_status.value
    return {"schema_version": SCHEMA_VERSION, "state": payload}


def task_state_to_json(state: AgentTaskState) -> str:
    return json.dumps(
        task_state_to_dict(state),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def task_state_from_dict(document: Dict[str, Any]) -> AgentTaskState:
    version = document.get("schema_version")
    if version != SCHEMA_VERSION:
        raise UnsupportedSchemaVersion(
            "unsupported task state schema version: %r" % version
        )

    data = document["state"]
    return AgentTaskState(
        task_id=data["task_id"],
        thread_id=data["thread_id"],
        user_goal=data["user_goal"],
        user_constraints=data.get("user_constraints", {}),
        status=TaskStatus(data["status"]),
        plan=[
            PlanStep(
                step_id=item["step_id"],
                kind=item["kind"],
                executor=item["executor"],
                inputs=item.get("inputs", {}),
                depends_on=tuple(item.get("depends_on", [])),
                status=StepStatus(item.get("status", StepStatus.PENDING.value)),
                attempt_count=item.get("attempt_count", 0),
            )
            for item in data.get("plan", [])
        ],
        current_step_id=data.get("current_step_id"),
        retrieved_context=data.get("retrieved_context", []),
        artifacts=[Artifact(**item) for item in data.get("artifacts", [])],
        evidence=[Evidence(**item) for item in data.get("evidence", [])],
        tool_calls=data.get("tool_calls", 0),
        model_calls=[ModelCallRecord(**item) for item in data.get("model_calls", [])],
        model_call_count=data.get("model_call_count", 0),
        errors=[ErrorRecord(**item) for item in data.get("errors", [])],
        memory_candidates=[
            MemoryCandidate(**item) for item in data.get("memory_candidates", [])
        ],
        budget=TaskBudget(**data.get("budget", {})),
        token_usage=data.get("token_usage", 0),
        retry_count=data.get("retry_count", 0),
        replan_count=data.get("replan_count", 0),
        awaiting_user_approval=data.get("awaiting_user_approval", False),
        final_answer=data.get("final_answer"),
        transitions=[
            StateTransition(
                from_status=TaskStatus(item["from_status"]),
                to_status=TaskStatus(item["to_status"]),
                reason=item["reason"],
                occurred_at=item["occurred_at"],
            )
            for item in data.get("transitions", [])
        ],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def task_state_from_json(payload: str) -> AgentTaskState:
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError("task state document must be a JSON object")
    return task_state_from_dict(document)
