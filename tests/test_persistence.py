import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from personal_ai_agent.models import (
    AgentTaskState,
    Artifact,
    Evidence,
    MemoryCandidate,
    ModelCallRecord,
    PlanStep,
    StepResult,
    StepStatus,
    TaskStatus,
)
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry
from personal_ai_agent.repository import SQLiteTaskRepository, TaskNotFound
from personal_ai_agent.serialization import task_state_from_json, task_state_to_json


class SerializationTests(unittest.TestCase):
    def test_round_trip_preserves_nested_contracts(self):
        state = AgentTaskState.create("thread-1", "研究 Agent", {"language": "zh-CN"})
        state.plan = [PlanStep("s1", "retrieve", "search", depends_on=("s0",))]
        state.artifacts = [Artifact("summary", {"text": "结论"})]
        state.evidence = [Evidence("doc-1", "line:10", "证据")]
        state.memory_candidates = [MemoryCandidate("semantic", "事实", ["doc-1"], 0.9)]
        state.model_calls = [
            ModelCallRecord("provider", "model", "summary", "prompt-v1", 10, 5, 12, 1)
        ]

        restored = task_state_from_json(task_state_to_json(state))

        self.assertEqual(state, restored)
        self.assertIsInstance(restored.status, TaskStatus)
        self.assertIsInstance(restored.plan[0].status, StepStatus)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.repository = SQLiteTaskRepository(
            Path(self.temp_directory.name) / "runtime.sqlite3"
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_saves_latest_state_and_checkpoint_history(self):
        state = AgentTaskState.create("thread-1", "persist me")
        first_id = self.repository.save(state, "created")
        state.final_answer = "done"
        second_id = self.repository.save(state, "updated")

        restored = self.repository.load(state.task_id)
        checkpoints = self.repository.list_checkpoints(state.task_id)

        self.assertEqual("done", restored.final_answer)
        self.assertEqual([first_id, second_id], [item.checkpoint_id for item in checkpoints])
        self.assertEqual(["created", "updated"], [item.reason for item in checkpoints])
        self.assertEqual([state.task_id], [item.task_id for item in self.repository.list_by_thread("thread-1")])

    def test_missing_task_raises(self):
        with self.assertRaises(TaskNotFound):
            self.repository.load("missing")

    def test_orchestrator_checkpoints_and_resume_skips_completed_step(self):
        calls = []
        registry = WorkflowRegistry()

        def worker(state, step):
            calls.append(step.step_id)
            return StepResult(artifacts=[Artifact("result", step.step_id)])

        registry.register("worker", worker)
        state = AgentTaskState.create("thread-1", "resume")
        state.status = TaskStatus.RUNNING
        state.plan = [
            PlanStep("s1", "work", "worker", status=StepStatus.COMPLETED),
            PlanStep("s2", "work", "worker", depends_on=("s1",), status=StepStatus.RUNNING),
        ]
        self.repository.save(state, "simulated_process_crash")

        restored = self.repository.load(state.task_id)
        result = Orchestrator(
            registry, checkpoint_store=self.repository
        ).resume(restored)

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(["s2"], calls)
        self.assertEqual(StepStatus.COMPLETED, result.plan[1].status)
        reasons = [item.reason for item in self.repository.list_checkpoints(state.task_id)]
        self.assertIn("execution_resumed", reasons)
        self.assertIn("task_completed", reasons)

    def test_resume_continues_interrupted_verification(self):
        state = AgentTaskState.create("thread-1", "resume verification")
        state.status = TaskStatus.VERIFYING
        state.plan = [
            PlanStep("s1", "work", "unused", status=StepStatus.COMPLETED)
        ]
        self.repository.save(state, "simulated_verifier_crash")

        result = Orchestrator(
            WorkflowRegistry(),
            verifier=lambda current: bool(current.plan),
            checkpoint_store=self.repository,
        ).resume(self.repository.load(state.task_id))

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        reasons = [item.reason for item in self.repository.list_checkpoints(state.task_id)]
        self.assertIn("verification_resumed", reasons)

    def test_save_updates_timestamp_inside_snapshot(self):
        state = AgentTaskState.create("thread-1", "timestamp")
        previous = state.updated_at

        self.repository.save(state, "created")
        restored = self.repository.load(state.task_id)

        self.assertGreaterEqual(
            datetime.fromisoformat(restored.updated_at), datetime.fromisoformat(previous)
        )
        self.assertEqual(state.updated_at, restored.updated_at)


if __name__ == "__main__":
    unittest.main()
