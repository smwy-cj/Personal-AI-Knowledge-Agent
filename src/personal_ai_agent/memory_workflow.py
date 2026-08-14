"""Memory candidate governance, approval boundary and persistence workflow."""

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from .memory_repository import SQLiteMemoryRepository
from .models import AgentTaskState, Artifact, MemoryCandidate, PlanStep, StepResult


SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_ -]?key|secret|token|password)\s*[:=]\s*\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]


class MemoryCandidateWorkflow:
    def __init__(self, repository: SQLiteMemoryRepository) -> None:
        self.repository = repository

    def __call__(self, state: AgentTaskState, step: PlanStep) -> StepResult:
        summary = _latest_artifact(state, "research_summary")
        evidence_pack = _latest_artifact(state, "research_evidence_pack")
        if summary is None or evidence_pack is None:
            raise ValueError("memory candidates require verified research artifacts")
        citation_to_chunk = {
            item["citation_id"]: item["chunk_id"]
            for item in evidence_pack.get("citations", [])
        }
        candidates: List[MemoryCandidate] = []
        for section in summary.get("sections", []):
            subject = _normalize_text(section.get("heading", ""))
            for paragraph in section.get("paragraphs", []):
                statement = str(paragraph.get("text", "")).strip()
                citations = paragraph.get("citations", [])
                source_ids = [citation_to_chunk[item] for item in citations if item in citation_to_chunk]
                candidate = govern_memory_candidate(
                    self.repository,
                    subject,
                    statement,
                    source_ids,
                )
                candidates.append(candidate)
        if not candidates:
            raise ValueError("research summary produced no memory candidates")
        pending = [item for item in candidates if item.governance_status == "PENDING"]
        audit = {
            "schema": "memory_candidates_v1",
            "candidate_count": len(candidates),
            "pending_count": len(pending),
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "subject": item.subject,
                    "content": item.content,
                    "source_ids": item.source_ids,
                    "status": item.governance_status,
                    "conflict_ids": item.conflict_ids,
                    "decision_reason": item.decision_reason,
                }
                for item in candidates
            ],
        }
        return StepResult(
            artifacts=[Artifact("memory_candidate_audit", audit)],
            memory_candidates=candidates,
            pause_for_approval=bool(pending),
        )


class MemoryPersistenceWorkflow:
    def __init__(self, repository: SQLiteMemoryRepository) -> None:
        self.repository = repository

    def __call__(self, state: AgentTaskState, step: PlanStep) -> StepResult:
        pending = [
            item for item in state.memory_candidates if item.governance_status == "PENDING"
        ]
        if pending:
            raise ValueError("memory persistence cannot run before all decisions are resolved")
        persisted = []
        for candidate in state.memory_candidates:
            if candidate.governance_status != "APPROVED":
                continue
            existing = self.repository.find_by_hash(candidate.normalized_hash or "")
            if existing is not None:
                candidate.governance_status = "REJECTED"
                candidate.decision_reason = "duplicate_detected_at_persistence"
                continue
            record = self.repository.save_approved(candidate)
            candidate.governance_status = "PERSISTED"
            persisted.append(record.memory_id)
        return StepResult(
            artifacts=[
                Artifact(
                    "memory_persistence_receipt",
                    {"schema": "memory_persistence_receipt_v1", "memory_ids": persisted},
                )
            ]
        )


def register_memory_workflows(
    registry: Any, repository: SQLiteMemoryRepository
) -> None:
    registry.register("memory.propose", MemoryCandidateWorkflow(repository))
    registry.register("memory.persist", MemoryPersistenceWorkflow(repository))


def govern_memory_candidate(
    repository: SQLiteMemoryRepository,
    subject: str,
    statement: str,
    source_ids: List[str],
) -> MemoryCandidate:
    normalized_statement = _normalize_text(statement)
    normalized_hash = hashlib.sha256(
        json.dumps(
            {"type": "semantic", "subject": subject, "statement": normalized_statement},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    candidate = MemoryCandidate(
        memory_type="semantic",
        content={"statement": statement},
        source_ids=source_ids,
        confidence=1.0 if source_ids else 0.0,
        requires_approval=True,
        subject=subject,
        normalized_hash=normalized_hash,
    )
    if not subject or not normalized_statement:
        candidate.governance_status = "REJECTED"
        candidate.decision_reason = "empty_content"
    elif not source_ids:
        candidate.governance_status = "REJECTED"
        candidate.decision_reason = "missing_source"
    elif any(pattern.search(statement) for pattern in SECRET_PATTERNS):
        candidate.governance_status = "REJECTED"
        candidate.decision_reason = "sensitive_content"
    else:
        duplicate = repository.find_by_hash(normalized_hash)
        if duplicate is not None:
            candidate.governance_status = "REJECTED"
            candidate.decision_reason = "duplicate"
            candidate.conflict_ids = [duplicate.memory_id]
        else:
            conflicts = repository.find_by_subject("semantic", subject)
            candidate.conflict_ids = [item.memory_id for item in conflicts]
            if conflicts:
                candidate.decision_reason = "conflict_requires_approval"
    if candidate.governance_status == "REJECTED":
        candidate.requires_approval = False
    return candidate


def _normalize_text(value: Any) -> str:
    return " ".join(str(value).casefold().split())


def _latest_artifact(state: AgentTaskState, artifact_type: str) -> Optional[Dict[str, Any]]:
    for artifact in reversed(state.artifacts):
        if artifact.artifact_type == artifact_type and isinstance(artifact.content, dict):
            return artifact.content
    return None
