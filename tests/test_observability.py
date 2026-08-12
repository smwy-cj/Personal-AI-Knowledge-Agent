import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from personal_ai_agent.models import AgentTaskState, PlanStep, StepResult, TaskStatus
from personal_ai_agent.observability import (
    ObservationValidationError,
    SQLiteEventStore,
    record_event_safely,
)
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = SQLiteEventStore(Path(self.temporary.name) / "events.sqlite3")

    def tearDown(self):
        self.temporary.cleanup()

    def test_safe_recording_swallows_attribute_validation_failures(self):
        recorded = record_event_safely(
            self.store,
            "provider_quota_waited",
            attributes={"request_body": "must-not-be-recorded"},
        )

        self.assertFalse(recorded)
        self.assertEqual(self.store.list_events(), [])

    def test_rejects_raw_or_unknown_sensitive_attributes(self):
        for key in ("prompt", "query", "content", "api_key", "unexpected"):
            with self.subTest(key=key), self.assertRaises(
                ObservationValidationError
            ):
                self.store.record("step_started", attributes={key: "private"})
        self.assertEqual(self.store.list_events(), [])

    def test_orchestrator_records_metadata_without_goal_or_result_content(self):
        registry = WorkflowRegistry()
        registry.register("work", lambda state, step: StepResult(token_usage=3))
        state = AgentTaskState.create("thread-private", "private user question")

        result = Orchestrator(registry, event_store=self.store).run(
            state, [PlanStep("s1", "research", "work")]
        )

        self.assertEqual(result.status, TaskStatus.COMPLETED)
        events = self.store.list_task_events(state.task_id)
        self.assertEqual(
            [item.event_type for item in events],
            [
                "task_started",
                "step_started",
                "step_completed",
                "verification_started",
                "task_completed",
            ],
        )
        serialized = repr(events)
        self.assertNotIn("private user question", serialized)
        self.assertNotIn("thread-private", serialized)
        self.assertEqual(events[-1].attributes["token_usage"], 3)

    def test_failed_task_has_step_and_task_terminal_events(self):
        registry = WorkflowRegistry()
        registry.register("work", lambda state, step: (_ for _ in ()).throw(ValueError("bad private value")))
        state = AgentTaskState.create("thread", "private goal")

        result = Orchestrator(registry, event_store=self.store).run(
            state, [PlanStep("s1", "research", "work")]
        )

        self.assertEqual(result.status, TaskStatus.FAILED)
        events = self.store.list_task_events(state.task_id)
        self.assertEqual(events[-2].event_type, "step_failed")
        self.assertEqual(events[-1].event_type, "task_failed")
        self.assertEqual(events[-2].attributes["error_type"], "ValueError")
        self.assertNotIn("bad private value", repr(events))

    def test_event_storage_io_failure_does_not_change_task_outcome(self):
        class BrokenStore:
            def record(self, *arguments, **keywords):
                raise OSError("disk unavailable")

        registry = WorkflowRegistry()
        registry.register("work", lambda state, step: StepResult())

        result = Orchestrator(registry, event_store=BrokenStore()).run(
            AgentTaskState.create("thread", "goal"),
            [PlanStep("s1", "work", "work")],
        )

        self.assertEqual(result.status, TaskStatus.COMPLETED)

    def test_aggregate_reports_terminal_counts_tokens_retries_and_latency(self):
        self.store.record(
            "task_completed",
            "task-1",
            attributes={
                "final_status": "COMPLETED",
                "tool_calls": 2,
                "model_call_count": 1,
                "token_usage": 15,
                "retry_count": 0,
            },
        )
        self.store.record(
            "task_failed",
            "task-2",
            attributes={
                "final_status": "FAILED",
                "tool_calls": 1,
                "model_call_count": 1,
                "token_usage": 8,
                "retry_count": 1,
            },
        )
        for duration in (10, 20, 100):
            self.store.record(
                "step_completed",
                "task-1",
                attributes={
                    "executor": "work",
                    "kind": "test",
                    "attempt": 1,
                    "duration_ms": duration,
                    "artifact_count": 0,
                    "evidence_count": 0,
                    "memory_candidate_count": 0,
                },
            )
        self.store.record(
            "model_completed",
            "task-1",
            attributes={
                "provider_id": "provider",
                "model_id": "model",
                "task_type": "summary",
                "prompt_version": "v1",
                "input_tokens": 12,
                "output_tokens": 3,
                "duration_ms": 40,
                "model_call_count": 1,
                "estimated_cost_microusd": 54,
            },
        )
        self.store.record(
            "model_retry",
            "task-2",
            attributes={
                "provider_id": "provider",
                "task_type": "summary",
                "prompt_version": "v1",
                "attempt": 1,
                "retry_delay_ms": 250,
                "error_type": "RetryableModelError",
            },
        )
        for wait in (20, 80):
            self.store.record(
                "provider_quota_waited",
                attributes={
                    "provider_id": "provider",
                    "quota_kind": "capacity",
                    "wait_ms": wait,
                },
            )
        self.store.record(
            "provider_cooldown_updated",
            attributes={"provider_id": "provider", "cooldown_ms": 1500},
        )
        self.store.record(
            "provider_tokens_reconciled",
            attributes={
                "provider_id": "provider",
                "estimated_tokens": 20,
                "actual_tokens": 12,
                "token_delta": -8,
                "applied_token_adjustment": -8,
            },
        )

        summary = self.store.aggregate()

        self.assertEqual(summary["terminal_task_count"], 2)
        self.assertEqual(summary["task_status_counts"], {"FAILED": 1, "COMPLETED": 1})
        self.assertEqual(summary["task_success_rate"], 0.5)
        self.assertEqual(summary["input_tokens"], 12)
        self.assertEqual(summary["output_tokens"], 3)
        self.assertEqual(summary["model_retry_count"], 1)
        self.assertEqual(summary["estimated_cost_microusd"], 54)
        self.assertEqual(summary["estimated_cost_usd"], 0.000054)
        self.assertEqual(summary["step_p50_latency_ms"], 20)
        self.assertEqual(summary["step_p95_latency_ms"], 100)
        self.assertEqual(summary["provider_quota_wait_count"], 2)
        self.assertEqual(summary["provider_quota_wait_ms"], 100)
        self.assertEqual(summary["provider_quota_p50_wait_ms"], 20)
        self.assertEqual(summary["provider_quota_p95_wait_ms"], 80)
        self.assertEqual(summary["provider_cooldown_count"], 1)
        self.assertEqual(summary["provider_cooldown_max_ms"], 1500)
        self.assertEqual(summary["provider_token_reconciliation_count"], 1)
        self.assertEqual(summary["provider_estimated_tokens"], 20)
        self.assertEqual(summary["provider_actual_tokens"], 12)
        self.assertEqual(summary["provider_token_estimate_delta"], -8)
        self.assertEqual(summary["provider_token_estimate_absolute_error"], 8)
        self.assertEqual(summary["provider_applied_token_adjustment"], -8)

    def test_retention_is_preview_only_until_explicitly_applied(self):
        old_id = self.store.record("task_started", "old-task")
        recent_id = self.store.record("task_started", "recent-task")
        old_time = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE observation_events SET created_at = ? WHERE event_id = ?",
                (old_time, old_id),
            )

        preview = self.store.prune(30)

        self.assertFalse(preview["applied"])
        self.assertEqual(preview["matched_count"], 1)
        self.assertEqual(preview["deleted_count"], 0)
        self.assertEqual(len(self.store.list_events()), 2)

        applied = self.store.prune(30, apply=True)

        self.assertTrue(applied["applied"])
        self.assertEqual(applied["matched_count"], 1)
        self.assertEqual(applied["deleted_count"], 1)
        events = self.store.list_events()
        self.assertEqual({item.event_id for item in events if item.task_id}, {recent_id})
        self.assertEqual(events[0].event_type, "events_pruned")
        self.assertEqual(events[0].attributes["deleted_count"], 1)

    def test_cost_report_filters_time_task_and_provider_and_groups_totals(self):
        first = self.store.record(
            "model_completed",
            "task-a",
            "summary",
            {
                "provider_id": "provider-a",
                "model_id": "model-a",
                "task_type": "summary",
                "prompt_version": "v1",
                "input_tokens": 100,
                "output_tokens": 20,
                "duration_ms": 50,
                "model_call_count": 1,
                "estimated_cost_microusd": 120,
            },
        )
        second = self.store.record(
            "model_completed",
            "task-b",
            "summary",
            {
                "provider_id": "provider-b",
                "model_id": "model-b",
                "task_type": "summary",
                "prompt_version": "v2",
                "input_tokens": 200,
                "output_tokens": 40,
                "duration_ms": 80,
                "model_call_count": 1,
                "estimated_cost_microusd": 240,
            },
        )
        with self.store._connect() as connection:
            connection.execute(
                "UPDATE observation_events SET created_at = ? WHERE event_id = ?",
                ("2026-08-10T00:00:00+00:00", first),
            )
            connection.execute(
                "UPDATE observation_events SET created_at = ? WHERE event_id = ?",
                ("2026-08-11T00:00:00+00:00", second),
            )

        report = self.store.cost_report(
            "2026-08-10T08:00:00+08:00",
            "2026-08-11T08:00:00+08:00",
            include_calls=True,
        )

        self.assertEqual(report["schema"], "cost_report_v1")
        self.assertEqual(report["window_semantics"], "from_inclusive_to_exclusive")
        self.assertEqual(report["totals"]["model_call_count"], 1)
        self.assertEqual(report["totals"]["estimated_cost_microusd"], 120)
        self.assertEqual(report["totals"]["task_count"], 1)
        self.assertEqual(report["totals"]["provider_count"], 1)
        self.assertEqual(report["by_task"][0]["task_id"], "task-a")
        self.assertEqual(report["by_provider"][0]["provider_id"], "provider-a")
        self.assertEqual(report["calls"][0]["event_id"], first)
        self.assertNotIn("attributes", report["calls"][0])

        filtered = self.store.cost_report(task_id="task-b", provider_id="provider-b")
        self.assertEqual(filtered["totals"]["estimated_cost_microusd"], 240)
        self.assertFalse(filtered["audit_calls_included"])
        self.assertNotIn("calls", filtered)

    def test_cost_report_tracks_missing_estimates_and_rejects_invalid_windows(self):
        self.store.record(
            "model_completed",
            "legacy-task",
            attributes={
                "provider_id": "legacy-provider",
                "model_id": "legacy-model",
                "task_type": "summary",
                "prompt_version": "v1",
                "input_tokens": 10,
                "output_tokens": 2,
                "duration_ms": 30,
                "model_call_count": 1,
            },
        )

        report = self.store.cost_report()

        self.assertEqual(report["totals"]["calls_with_cost_estimate"], 0)
        self.assertEqual(report["totals"]["calls_without_cost_estimate"], 1)
        self.assertEqual(report["totals"]["estimated_cost_microusd"], 0)
        with self.assertRaises(ValueError):
            self.store.cost_report(from_time="2026-08-10T00:00:00")
        with self.assertRaises(ValueError):
            self.store.cost_report(
                from_time="2026-08-11T00:00:00Z",
                to_time="2026-08-10T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
