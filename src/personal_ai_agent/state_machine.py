"""Deterministic task lifecycle rules."""

from typing import Dict, FrozenSet

from .models import AgentTaskState, StateTransition, TaskStatus, utc_now


class InvalidStateTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: Dict[TaskStatus, FrozenSet[TaskStatus]] = {
    TaskStatus.CREATED: frozenset({TaskStatus.PLANNING, TaskStatus.CANCELLED}),
    TaskStatus.PLANNING: frozenset(
        {TaskStatus.RUNNING, TaskStatus.WAITING_USER, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.VERIFYING,
            TaskStatus.WAITING_USER,
            TaskStatus.PARTIAL_SUCCESS,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_USER: frozenset(
        {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.VERIFYING: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.WRITING_MEMORY,
            TaskStatus.COMPLETED,
            TaskStatus.PARTIAL_SUCCESS,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WRITING_MEMORY: frozenset(
        {
            TaskStatus.COMPLETED,
            TaskStatus.PARTIAL_SUCCESS,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.PARTIAL_SUCCESS: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def transition(state: AgentTaskState, target: TaskStatus, reason: str) -> None:
    if target not in ALLOWED_TRANSITIONS[state.status]:
        raise InvalidStateTransition("cannot transition from %s to %s" % (state.status, target))
    previous = state.status
    state.status = target
    state.updated_at = utc_now()
    state.transitions.append(
        StateTransition(from_status=previous, to_status=target, reason=reason)
    )
