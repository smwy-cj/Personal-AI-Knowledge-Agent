"""Structured contracts shared by the agent runtime.

The module intentionally has no model-provider or storage dependencies. These
types are the stable boundary between planners, workflows and persistence.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    VERIFYING = "VERIFYING"
    WRITING_MEMORY = "WRITING_MEMORY"
    COMPLETED = "COMPLETED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class TaskBudget:
    max_tool_calls: int = 10
    max_model_calls: int = 4
    max_tokens: int = 30_000
    max_replans: int = 2
    max_step_retries: int = 2

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value < 0:
                raise ValueError("%s must be non-negative" % name)


@dataclass
class PlanStep:
    step_id: str
    kind: str
    executor: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    depends_on: Sequence[str] = field(default_factory=tuple)
    status: StepStatus = StepStatus.PENDING
    attempt_count: int = 0


@dataclass
class Evidence:
    source_id: str
    location: str
    content: Optional[str] = None
    chunk_id: Optional[str] = None
    vault_id: Optional[str] = None
    relative_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    content_hash: Optional[str] = None


@dataclass
class Artifact:
    artifact_type: str
    content: Any


@dataclass
class MemoryCandidate:
    memory_type: str
    content: Any
    source_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    requires_approval: bool = True
    candidate_id: str = field(default_factory=lambda: "memory_%s" % uuid4().hex)
    subject: Optional[str] = None
    normalized_hash: Optional[str] = None
    governance_status: str = "PENDING"
    conflict_ids: List[str] = field(default_factory=list)
    decision_reason: Optional[str] = None


@dataclass
class ModelCallRecord:
    provider_id: str
    model_id: str
    task_type: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    attempt_count: int
    attempted_provider_ids: List[str] = field(default_factory=list)


@dataclass
class StepResult:
    artifacts: List[Artifact] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    memory_candidates: List[MemoryCandidate] = field(default_factory=list)
    retrieved_context: List[Dict[str, Any]] = field(default_factory=list)
    model_calls: List[ModelCallRecord] = field(default_factory=list)
    model_call_count: int = 0
    final_answer: Optional[str] = None
    pause_for_approval: bool = False
    token_usage: int = 0


@dataclass
class ErrorRecord:
    step_id: Optional[str]
    error_type: str
    message: str
    occurred_at: str = field(default_factory=utc_now)


@dataclass
class StateTransition:
    from_status: TaskStatus
    to_status: TaskStatus
    reason: str
    occurred_at: str = field(default_factory=utc_now)


@dataclass
class AgentTaskState:
    task_id: str
    thread_id: str
    user_goal: str
    user_constraints: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.CREATED
    plan: List[PlanStep] = field(default_factory=list)
    current_step_id: Optional[str] = None
    retrieved_context: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Artifact] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    tool_calls: int = 0
    model_calls: List[ModelCallRecord] = field(default_factory=list)
    model_call_count: int = 0
    errors: List[ErrorRecord] = field(default_factory=list)
    memory_candidates: List[MemoryCandidate] = field(default_factory=list)
    budget: TaskBudget = field(default_factory=TaskBudget)
    token_usage: int = 0
    retry_count: int = 0
    replan_count: int = 0
    awaiting_user_approval: bool = False
    final_answer: Optional[str] = None
    transitions: List[StateTransition] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        thread_id: str,
        user_goal: str,
        user_constraints: Optional[Dict[str, Any]] = None,
        budget: Optional[TaskBudget] = None,
    ) -> "AgentTaskState":
        return cls(
            task_id="task_%s" % uuid4().hex,
            thread_id=thread_id,
            user_goal=user_goal,
            user_constraints=user_constraints or {},
            budget=budget or TaskBudget(),
        )
