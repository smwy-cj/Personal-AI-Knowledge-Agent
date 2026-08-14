import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.memory_repository import SQLiteMemoryRepository
from personal_ai_agent.memory_workflow import register_memory_workflows
from personal_ai_agent.models import AgentTaskState, Artifact, MemoryCandidate, PlanStep, TaskStatus
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry
from personal_ai_agent.repository import SQLiteTaskRepository


def state_with_summary(statement="Memory requires approval."):
    state = AgentTaskState.create("thread-1", "memory governance")
    state.artifacts = [
        Artifact(
            "research_evidence_pack",
            {
                "schema": "research_evidence_pack_v1",
                "citations": [{"citation_id": 1, "chunk_id": "chunk-1"}],
            },
        ),
        Artifact(
            "research_summary",
            {
                "schema": "research_summary_v1",
                "sections": [
                    {
                        "heading": "Policy",
                        "paragraphs": [{"text": statement, "citations": [1]}],
                    }
                ],
            },
        ),
    ]
    return state


class MemoryGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.memory_repository = SQLiteMemoryRepository(root / "memory.sqlite3")
        self.task_repository = SQLiteTaskRepository(root / "tasks.sqlite3")
        registry = WorkflowRegistry()
        register_memory_workflows(registry, self.memory_repository)
        self.runtime = Orchestrator(registry, checkpoint_store=self.task_repository)
        self.plan = [
            PlanStep("propose", "memory", "memory.propose"),
            PlanStep("persist", "memory", "memory.persist", depends_on=("propose",)),
        ]

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_pauses_then_approved_candidate_is_persisted(self):
        state = self.runtime.run(state_with_summary(), self.plan)
        self.assertEqual(TaskStatus.WAITING_USER, state.status)
        self.assertTrue(state.awaiting_user_approval)
        self.assertEqual("PENDING", state.plan[1].status.value)
        self.assertEqual([], self.memory_repository.list_all())
        candidate_id = state.memory_candidates[0].candidate_id
        restored = self.task_repository.load(state.task_id)

        result = self.runtime.resolve_memory_approval(restored, approved_ids=[candidate_id])

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual("PERSISTED", result.memory_candidates[0].governance_status)
        self.assertEqual(1, len(self.memory_repository.list_all()))
        reasons = [item.reason for item in self.task_repository.list_checkpoints(state.task_id)]
        self.assertIn("waiting_for_memory_approval", reasons)
        self.assertIn("memory_approval_resolved", reasons)

    def test_rejection_completes_without_writing_memory(self):
        state = self.runtime.run(state_with_summary(), self.plan)
        candidate_id = state.memory_candidates[0].candidate_id
        result = self.runtime.resolve_memory_approval(state, rejected_ids=[candidate_id])

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual("REJECTED", result.memory_candidates[0].governance_status)
        self.assertEqual([], self.memory_repository.list_all())

    def test_requires_decision_for_every_pending_candidate(self):
        state = self.runtime.run(state_with_summary(), self.plan)
        with self.assertRaises(ValueError):
            self.runtime.resolve_memory_approval(state)
        self.assertEqual(TaskStatus.WAITING_USER, state.status)

    def test_sensitive_candidate_is_rejected_without_pause_or_write(self):
        state = self.runtime.run(
            state_with_summary("api_key = sk-abcdefghijklmnop"), self.plan
        )
        self.assertEqual(TaskStatus.COMPLETED, state.status)
        self.assertEqual("sensitive_content", state.memory_candidates[0].decision_reason)
        self.assertEqual([], self.memory_repository.list_all())

    def test_duplicate_is_rejected_and_conflict_is_flagged(self):
        first = self.runtime.run(state_with_summary(), self.plan)
        self.runtime.resolve_memory_approval(
            first, approved_ids=[first.memory_candidates[0].candidate_id]
        )

        duplicate = self.runtime.run(state_with_summary(), self.plan)
        self.assertEqual(TaskStatus.COMPLETED, duplicate.status)
        self.assertEqual("duplicate", duplicate.memory_candidates[0].decision_reason)

        conflict = self.runtime.run(
            state_with_summary("Memory requires explicit human confirmation."), self.plan
        )
        self.assertEqual(TaskStatus.WAITING_USER, conflict.status)
        self.assertEqual("conflict_requires_approval", conflict.memory_candidates[0].decision_reason)
        self.assertEqual(1, len(conflict.memory_candidates[0].conflict_ids))


if __name__ == "__main__":
    unittest.main()
