import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from personal_ai_agent.cancellation import CancellationToken
from personal_ai_agent.execution_control import (
    SQLiteExecutionControl,
    TaskLeaseConflict,
    TaskLeaseLost,
)
from personal_ai_agent.models import AgentTaskState, PlanStep, StepResult, TaskStatus
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry
from personal_ai_agent.repository import SQLiteTaskRepository


class ExecutionControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "tasks.sqlite3"
        self.control = SQLiteExecutionControl(self.database)

    def tearDown(self):
        self.temporary.cleanup()

    def test_only_one_live_owner_can_hold_a_task(self):
        self.assertTrue(self.control.acquire("task-1", "owner-a", 30))
        self.assertFalse(self.control.acquire("task-1", "owner-b", 30))
        self.control.release("task-1", "owner-a")
        self.assertTrue(self.control.acquire("task-1", "owner-b", 30))

    def test_expired_lease_can_be_taken_over(self):
        self.assertTrue(self.control.acquire("task-1", "owner-a", 30))
        with self.control._connect() as connection:
            connection.execute(
                "UPDATE task_execution_control SET lease_until = ? WHERE task_id = ?",
                ("2000-01-01T00:00:00+00:00", "task-1"),
            )
        self.assertTrue(self.control.acquire("task-1", "owner-b", 30))
        with self.assertRaises(TaskLeaseLost):
            self.control.heartbeat("task-1", "owner-a", 30)

    def test_context_lease_conflict_is_explicit(self):
        with self.control.lease("task-1", "owner-a", 3, 1):
            with self.assertRaises(TaskLeaseConflict):
                with self.control.lease("task-1", "owner-b", 3, 1):
                    pass

    def test_persisted_cancel_reaches_orchestrator_step_boundary(self):
        repository = SQLiteTaskRepository(self.database)
        state = AgentTaskState.create("thread", "cancel")
        self.control.request_cancel(state.task_id)
        token = CancellationToken(
            lambda: self.control.cancellation_requested(state.task_id)
        )
        calls = []
        registry = WorkflowRegistry()
        registry.register("work", lambda current, step: calls.append(step.step_id) or StepResult())

        result = Orchestrator(
            registry,
            checkpoint_store=repository,
            cancellation_token=token,
        ).run(state, [PlanStep("s1", "work", "work")])

        self.assertEqual(result.status, TaskStatus.CANCELLED)
        self.assertEqual(calls, [])
        self.assertEqual(repository.load(state.task_id).status, TaskStatus.CANCELLED)

    def test_lost_lease_prevents_stale_checkpoint_write(self):
        repository = SQLiteTaskRepository(self.database)
        state = AgentTaskState.create("thread", "lease takeover")
        registry = WorkflowRegistry()
        registry.register("work", lambda current, step: StepResult())
        self.assertTrue(self.control.acquire(state.task_id, "old-owner", 30))

        def lose_lease():
            with self.control._connect() as connection:
                connection.execute(
                    "UPDATE task_execution_control SET owner_id = ? WHERE task_id = ?",
                    ("new-owner", state.task_id),
                )
            self.control.heartbeat(state.task_id, "old-owner", 30)

        with self.assertRaises(TaskLeaseLost):
            Orchestrator(
                registry,
                checkpoint_store=repository,
                execution_guard=lose_lease,
            ).run(state, [PlanStep("s1", "work", "work")])

        with self.assertRaises(KeyError):
            repository.load(state.task_id)


if __name__ == "__main__":
    unittest.main()
