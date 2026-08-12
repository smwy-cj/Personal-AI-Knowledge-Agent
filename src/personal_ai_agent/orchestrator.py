"""A minimal deterministic orchestrator for workflow execution."""

import time
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Set

from .cancellation import CancellationToken, OperationCancelled, check_cancelled
from .models import AgentTaskState, ErrorRecord, PlanStep, StepResult, StepStatus, TaskStatus
from .observability import record_event_safely
from .state_machine import transition


Workflow = Callable[[AgentTaskState, PlanStep], StepResult]
Verifier = Callable[[AgentTaskState], bool]


class CheckpointStore(Protocol):
    def save(self, state: AgentTaskState, reason: str) -> int:
        ...


class BudgetExceeded(RuntimeError):
    pass


class WorkflowNotFound(KeyError):
    pass


class WorkflowRegistry:
    def __init__(self) -> None:
        self._workflows: Dict[str, Workflow] = {}

    def register(self, name: str, workflow: Workflow) -> None:
        if not name or name in self._workflows:
            raise ValueError("workflow name must be non-empty and unique")
        self._workflows[name] = workflow

    def get(self, name: str) -> Workflow:
        try:
            return self._workflows[name]
        except KeyError as exc:
            raise WorkflowNotFound("unknown workflow executor: %s" % name) from exc


class InvalidPlan(ValueError):
    pass


def validate_plan(steps: Iterable[PlanStep]) -> List[PlanStep]:
    plan = deepcopy(list(steps))
    step_ids = [step.step_id for step in plan]
    if not plan:
        raise InvalidPlan("plan must contain at least one step")
    if len(step_ids) != len(set(step_ids)):
        raise InvalidPlan("step ids must be unique")

    known = set(step_ids)
    for step in plan:
        missing = set(step.depends_on) - known
        if missing:
            raise InvalidPlan("step %s has unknown dependencies: %s" % (step.step_id, sorted(missing)))
        if step.step_id in step.depends_on:
            raise InvalidPlan("step %s cannot depend on itself" % step.step_id)

    resolved: Set[str] = set()
    remaining = list(plan)
    while remaining:
        ready = [step for step in remaining if set(step.depends_on) <= resolved]
        if not ready:
            raise InvalidPlan("plan contains a dependency cycle")
        for step in ready:
            resolved.add(step.step_id)
            remaining.remove(step)
    return plan


class Orchestrator:
    def __init__(
        self,
        registry: WorkflowRegistry,
        verifier: Optional[Verifier] = None,
        checkpoint_store: Optional[CheckpointStore] = None,
        cancellation_token: Optional[CancellationToken] = None,
        execution_guard: Optional[Callable[[], None]] = None,
        event_store: Optional[Any] = None,
    ) -> None:
        self.registry = registry
        self.verifier = verifier or (lambda state: True)
        self.checkpoint_store = checkpoint_store
        self.cancellation_token = cancellation_token
        self.execution_guard = execution_guard
        self.event_store = event_store

    def run(
        self, state: AgentTaskState, steps: Optional[Iterable[PlanStep]] = None
    ) -> AgentTaskState:
        if state.status != TaskStatus.CREATED:
            return self.resume(state)
        if steps is None:
            raise ValueError("new tasks require plan steps")
        self._observe("task_started", state, attributes={"status": state.status.value})
        transition(state, TaskStatus.PLANNING, "task accepted for planning")
        self._checkpoint(state, "planning_started")
        try:
            state.plan = validate_plan(steps)
        except Exception as exc:
            self._record_error(state, None, exc)
            transition(state, TaskStatus.FAILED, "plan validation failed")
            self._checkpoint(state, "plan_validation_failed")
            self._observe_final("task_failed", state)
            return state

        transition(state, TaskStatus.RUNNING, "plan validated")
        self._checkpoint(state, "plan_validated")
        return self._execute(state)

    def resume(self, state: AgentTaskState) -> AgentTaskState:
        self._observe("task_resumed", state, attributes={"status": state.status.value})
        if state.status == TaskStatus.VERIFYING:
            self._checkpoint(state, "verification_resumed")
            return self._verify(state)
        if state.status != TaskStatus.RUNNING:
            raise ValueError("only RUNNING or VERIFYING tasks can be resumed")
        state.plan = validate_plan(state.plan)
        for step in state.plan:
            if step.status == StepStatus.RUNNING:
                step.status = StepStatus.PENDING
        state.current_step_id = None
        self._checkpoint(state, "execution_resumed")
        return self._execute(state)

    def _execute(self, state: AgentTaskState) -> AgentTaskState:
        completed: Set[str] = {
            step.step_id for step in state.plan if step.status == StepStatus.COMPLETED
        }

        while len(completed) < len(state.plan):
            if self._cancel_if_requested(state):
                return state
            ready = [
                step
                for step in state.plan
                if step.status == StepStatus.PENDING and set(step.depends_on) <= completed
            ]
            if not ready:
                transition(state, TaskStatus.FAILED, "no executable step remains")
                self._checkpoint(state, "execution_blocked")
                self._observe_final("task_failed", state)
                return state

            for step in ready:
                if not self._run_step(state, step):
                    if state.status == TaskStatus.CANCELLED:
                        return state
                    transition(state, TaskStatus.FAILED, "step execution failed")
                    self._checkpoint(state, "step_failed:%s" % step.step_id)
                    self._observe_final("task_failed", state)
                    return state
                completed.add(step.step_id)
                if state.status == TaskStatus.WAITING_USER:
                    return state

        state.current_step_id = None
        transition(state, TaskStatus.VERIFYING, "all plan steps completed")
        self._checkpoint(state, "verification_started")
        return self._verify(state)

    def _verify(self, state: AgentTaskState) -> AgentTaskState:
        if self._cancel_if_requested(state):
            return state
        self._observe(
            "verification_started", state, attributes={"status": state.status.value}
        )
        try:
            verified = self.verifier(state)
        except Exception as exc:
            self._record_error(state, None, exc)
            verified = False

        if verified:
            transition(state, TaskStatus.COMPLETED, "verification passed")
            self._checkpoint(state, "task_completed")
            self._observe_final("task_completed", state)
        else:
            transition(state, TaskStatus.FAILED, "verification failed")
            self._checkpoint(state, "verification_failed")
            self._observe_final("task_failed", state)
        return state

    def _run_step(self, state: AgentTaskState, step: PlanStep) -> bool:
        retries_allowed = state.budget.max_step_retries
        while step.attempt_count <= retries_allowed:
            if self._cancel_if_requested(state):
                return False
            if state.tool_calls >= state.budget.max_tool_calls:
                self._record_error(state, step.step_id, BudgetExceeded("tool call budget exhausted"))
                step.status = StepStatus.FAILED
                return False

            step.status = StepStatus.RUNNING
            step.attempt_count += 1
            state.current_step_id = step.step_id
            state.tool_calls += 1
            started = time.monotonic()
            self._observe(
                "step_started",
                state,
                step.step_id,
                {
                    "executor": step.executor,
                    "kind": step.kind,
                    "attempt": step.attempt_count,
                },
            )
            self._checkpoint(state, "step_started:%s" % step.step_id)
            try:
                result = self.registry.get(step.executor)(state, step)
                if result.token_usage < 0:
                    raise ValueError("token usage cannot be negative")
                if state.token_usage + result.token_usage > state.budget.max_tokens:
                    raise BudgetExceeded("token budget exhausted")
                state.token_usage += result.token_usage
                state.artifacts.extend(result.artifacts)
                state.evidence.extend(result.evidence)
                state.memory_candidates.extend(result.memory_candidates)
                state.retrieved_context.extend(result.retrieved_context)
                state.model_calls.extend(result.model_calls)
                state.model_call_count += result.model_call_count
                if result.final_answer is not None:
                    state.final_answer = result.final_answer
                step.status = StepStatus.COMPLETED
                if result.pause_for_approval:
                    state.awaiting_user_approval = True
                    transition(
                        state,
                        TaskStatus.WAITING_USER,
                        "memory candidates require user approval",
                    )
                    self._checkpoint(state, "waiting_for_memory_approval")
                    self._observe_step_completed(state, step, result, started)
                    self._observe(
                        "task_waiting_user",
                        state,
                        step.step_id,
                        {
                            "status": state.status.value,
                            "memory_candidate_count": len(result.memory_candidates),
                        },
                    )
                    return True
                self._checkpoint(state, "step_completed:%s" % step.step_id)
                self._observe_step_completed(state, step, result, started)
                return True
            except Exception as exc:
                if isinstance(exc, OperationCancelled):
                    step.status = StepStatus.PENDING
                    self._cancel(state, str(exc))
                    return False
                self._record_error(state, step.step_id, exc)
                self._observe(
                    "step_failed",
                    state,
                    step.step_id,
                    {
                        "executor": step.executor,
                        "kind": step.kind,
                        "attempt": step.attempt_count,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "error_type": type(exc).__name__,
                    },
                )
                self._checkpoint(state, "step_error:%s" % step.step_id)
                if isinstance(exc, (BudgetExceeded, WorkflowNotFound, ValueError)):
                    step.status = StepStatus.FAILED
                    return False
                if step.attempt_count <= retries_allowed:
                    state.retry_count += 1
                    step.status = StepStatus.PENDING
                    continue
                step.status = StepStatus.FAILED
                return False
        return False

    def _cancel_if_requested(self, state: AgentTaskState) -> bool:
        try:
            if self.execution_guard is not None:
                self.execution_guard()
            check_cancelled(self.cancellation_token)
            return False
        except OperationCancelled as exc:
            self._cancel(state, str(exc))
            return True

    def _cancel(self, state: AgentTaskState, reason: str) -> None:
        if state.status in {
            TaskStatus.CREATED,
            TaskStatus.PLANNING,
            TaskStatus.RUNNING,
            TaskStatus.WAITING_USER,
            TaskStatus.VERIFYING,
            TaskStatus.WRITING_MEMORY,
        }:
            transition(state, TaskStatus.CANCELLED, reason or "cancellation requested")
            self._checkpoint(state, "task_cancelled")
            self._observe_final("task_cancelled", state)

    def resolve_memory_approval(
        self,
        state: AgentTaskState,
        approved_ids: Iterable[str] = (),
        rejected_ids: Iterable[str] = (),
    ) -> AgentTaskState:
        if state.status != TaskStatus.WAITING_USER or not state.awaiting_user_approval:
            raise ValueError("task is not waiting for memory approval")
        approved = set(approved_ids)
        rejected = set(rejected_ids)
        if approved & rejected:
            raise ValueError("a memory candidate cannot be both approved and rejected")
        candidates = {
            item.candidate_id: item
            for item in state.memory_candidates
            if item.governance_status == "PENDING" and item.requires_approval
        }
        supplied = approved | rejected
        unknown = supplied - set(candidates)
        if unknown:
            raise ValueError("unknown pending memory candidate ids: %s" % sorted(unknown))
        if supplied != set(candidates):
            raise ValueError("every pending memory candidate requires an explicit decision")
        for candidate_id in approved:
            candidates[candidate_id].governance_status = "APPROVED"
            candidates[candidate_id].decision_reason = "approved_by_user"
        for candidate_id in rejected:
            candidates[candidate_id].governance_status = "REJECTED"
            candidates[candidate_id].decision_reason = "rejected_by_user"
        state.awaiting_user_approval = False
        transition(state, TaskStatus.RUNNING, "memory approval resolved")
        self._checkpoint(state, "memory_approval_resolved")
        return self._execute(state)

    def _checkpoint(self, state: AgentTaskState, reason: str) -> None:
        if self.execution_guard is not None:
            self.execution_guard()
        if self.checkpoint_store is not None:
            self.checkpoint_store.save(state, reason)

    @staticmethod
    def _record_error(state: AgentTaskState, step_id: Optional[str], exc: Exception) -> None:
        state.errors.append(
            ErrorRecord(step_id=step_id, error_type=type(exc).__name__, message=str(exc))
        )

    def _observe(
        self,
        event_type: str,
        state: AgentTaskState,
        step_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.event_store is not None:
            record_event_safely(
                self.event_store,
                event_type,
                task_id=state.task_id,
                step_id=step_id,
                attributes=attributes or {},
            )

    def _observe_final(self, event_type: str, state: AgentTaskState) -> None:
        self._observe(
            event_type,
            state,
            attributes={
                "final_status": state.status.value,
                "tool_calls": state.tool_calls,
                "model_call_count": state.model_call_count,
                "token_usage": state.token_usage,
                "retry_count": state.retry_count,
            },
        )

    def _observe_step_completed(
        self,
        state: AgentTaskState,
        step: PlanStep,
        result: StepResult,
        started: float,
    ) -> None:
        self._observe(
            "step_completed",
            state,
            step.step_id,
            {
                "executor": step.executor,
                "kind": step.kind,
                "attempt": step.attempt_count,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "artifact_count": len(result.artifacts),
                "evidence_count": len(result.evidence),
                "memory_candidate_count": len(result.memory_candidates),
            },
        )
