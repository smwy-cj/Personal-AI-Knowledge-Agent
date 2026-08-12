import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from personal_ai_agent.application import ApplicationService
from personal_ai_agent.cli import main
from personal_ai_agent.memory_workflow import register_memory_workflows
from personal_ai_agent.models import AgentTaskState, Artifact, PlanStep, TaskStatus
from personal_ai_agent.obsidian_writer import register_obsidian_writeback_workflow
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry
from personal_ai_agent.research_summary import render_research_summary
from personal_ai_agent.research_workflow import ResearchWorkflow


class ApplicationCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / "Architecture.md").write_text(
            "# Agent Architecture\n\nCheckpoint enables durable recovery.\n",
            encoding="utf-8",
        )
        self.config_path = self.root / "agent.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "vault_path": "vault",
                    "data_directory": "runtime",
                    "managed_memory_directory": "Agent/Memory",
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["--config", str(self.config_path), *arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def configure_providers(self):
        self.config_path.write_text(
            json.dumps(
                {
                    "vault_path": "vault",
                    "data_directory": "runtime",
                    "managed_memory_directory": "Agent/Memory",
                    "model_providers": [
                        {
                            "provider_id": "model-local",
                            "base_url": "http://127.0.0.1:9000/v1",
                            "model": "model-v1",
                            "capabilities": ["structured_output", "chinese"],
                            "max_context_tokens": 32768,
                            "max_privacy_level": "personal",
                            "requests_per_minute": 60000,
                            "max_rate_limit_wait_seconds": 1,
                        }
                    ],
                    "embedding_providers": [
                        {
                            "provider_id": "embed-local",
                            "base_url": "http://127.0.0.1:9000/v1",
                            "model": "embed-v1",
                            "dimension": 4,
                            "requests_per_minute": 60000,
                            "max_rate_limit_wait_seconds": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_config_sync_and_search_form_a_real_command_chain(self):
        code, output, errors = self.invoke("config-validate")
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        validation = json.loads(output)
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["config"]["vault_path"], str(self.vault.resolve()))

        code, output, errors = self.invoke("sync")
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        self.assertEqual(json.loads(output)["added"], 1)

        code, output, errors = self.invoke("search", "durable recovery")
        self.assertEqual(code, 0)
        self.assertEqual(errors, "")
        results = json.loads(output)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["relative_path"], "Architecture.md")
        self.assertGreaterEqual(results[0]["start_line"], 1)
        self.assertIn(results[0]["match_method"], {"fts5", "keyword_fallback"})

    def test_task_show_and_list_read_the_same_durable_store(self):
        service = ApplicationService.from_file(str(self.config_path))
        state = AgentTaskState.create("thread-cli", "Inspect architecture")
        service.task_repository.save(state, "test")

        code, output, _ = self.invoke("task-show", state.task_id)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["state"]["task_id"], state.task_id)

        code, output, _ = self.invoke("task-list", "thread-cli")
        self.assertEqual(code, 0)
        self.assertEqual(
            [item["state"]["task_id"] for item in json.loads(output)],
            [state.task_id],
        )

    def test_task_cancel_is_immediate_when_task_is_idle(self):
        service = ApplicationService.from_file(str(self.config_path))
        state = AgentTaskState.create("thread-cancel", "cancel me")
        service.task_repository.save(state, "created")

        code, output, errors = self.invoke("task-cancel", state.task_id)

        self.assertEqual((code, errors), (0, ""))
        result = json.loads(output)
        self.assertTrue(result["immediate"])
        self.assertEqual(
            service.task_repository.load(state.task_id).status, TaskStatus.CANCELLED
        )

        code, output, errors = self.invoke("observability-summary")
        self.assertEqual((code, errors), (0, ""))
        summary = json.loads(output)
        self.assertEqual(summary["schema"], "observability_summary_v1")
        self.assertEqual(summary["terminal_task_count"], 1)
        self.assertEqual(summary["task_status_counts"], {"CANCELLED": 1})

    def test_task_cancel_only_requests_when_an_executor_owns_the_lease(self):
        service = ApplicationService.from_file(str(self.config_path))
        state = AgentTaskState.create("thread-cancel", "running")
        state.status = TaskStatus.RUNNING
        service.task_repository.save(state, "running")
        self.assertTrue(
            service.execution_control.acquire(state.task_id, "active-owner", 30)
        )

        code, output, errors = self.invoke("task-cancel", state.task_id)

        self.assertEqual((code, errors), (0, ""))
        result = json.loads(output)
        self.assertFalse(result["immediate"])
        self.assertEqual(result["active_owner"], "active-owner")
        self.assertTrue(
            service.execution_control.cancellation_requested(state.task_id)
        )
        self.assertEqual(
            service.task_repository.load(state.task_id).status, TaskStatus.RUNNING
        )

    def test_events_prune_defaults_to_preview_and_requires_apply(self):
        service = ApplicationService.from_file(str(self.config_path))
        event_id = service.event_store.record("task_started", "old-task")
        with service.event_store._connect() as connection:
            connection.execute(
                "UPDATE observation_events SET created_at = ? WHERE event_id = ?",
                ("2000-01-01T00:00:00+00:00", event_id),
            )

        code, output, errors = self.invoke("events-prune", "--older-than-days", "30")
        preview = json.loads(output)

        self.assertEqual((code, errors), (0, ""))
        self.assertFalse(preview["applied"])
        self.assertEqual(preview["matched_count"], 1)
        self.assertEqual(len(service.event_store.list_events()), 1)

        code, output, errors = self.invoke(
            "events-prune", "--older-than-days", "30", "--apply"
        )
        applied = json.loads(output)

        self.assertEqual((code, errors), (0, ""))
        self.assertTrue(applied["applied"])
        self.assertEqual(applied["deleted_count"], 1)
        self.assertEqual(service.event_store.list_events()[0].event_type, "events_pruned")

    def test_invalid_config_returns_machine_readable_safe_error(self):
        secret = "never-print-this-value"
        self.config_path.write_text(
            json.dumps(
                {
                    "vault_path": "vault",
                    "data_directory": "runtime",
                    "access_token": secret,
                }
            ),
            encoding="utf-8",
        )

        code, output, errors = self.invoke("config-validate")

        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        error = json.loads(errors)
        self.assertEqual(error["error"], "ConfigurationError")
        self.assertNotIn(secret, errors)

    def test_cli_approval_resumes_persistence_writeback_and_reindex(self):
        service = ApplicationService.from_file(str(self.config_path))
        service.sync_vault()
        state = AgentTaskState.create("thread-approval", "durable recovery")
        retrieved = ResearchWorkflow(service.keyword_search)(
            state, PlanStep("retrieve", "research", "research.retrieve")
        )
        state.artifacts.extend(retrieved.artifacts)
        state.evidence.extend(retrieved.evidence)
        state.retrieved_context.extend(retrieved.retrieved_context)
        summary = {
            "schema": "research_summary_v1",
            "evidence_schema": "research_evidence_pack_v1",
            "title": "Recovery",
            "sections": [
                {
                    "heading": "Policy",
                    "paragraphs": [
                        {"text": "Checkpoint enables durable recovery.", "citations": [1]}
                    ],
                }
            ],
        }
        summary["markdown"] = render_research_summary(summary)
        state.artifacts.append(Artifact("research_summary", summary))
        state.final_answer = summary["markdown"]
        registry = WorkflowRegistry()
        register_memory_workflows(registry, service.memory_repository)
        register_obsidian_writeback_workflow(registry, service.writer, service.ingester)
        waiting = Orchestrator(
            registry, checkpoint_store=service.task_repository
        ).run(
            state,
            [
                PlanStep("propose", "memory", "memory.propose"),
                PlanStep("persist", "memory", "memory.persist", depends_on=("propose",)),
                PlanStep(
                    "writeback",
                    "memory",
                    "obsidian.writeback",
                    depends_on=("persist",),
                ),
            ],
        )
        self.assertEqual(waiting.status, TaskStatus.WAITING_USER)
        candidate_id = waiting.memory_candidates[0].candidate_id

        code, output, errors = self.invoke("memory-pending", waiting.task_id)
        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(json.loads(output)[0]["candidate_id"], candidate_id)

        code, output, errors = self.invoke(
            "memory-resolve", waiting.task_id, "--approve", candidate_id
        )
        self.assertEqual((code, errors), (0, ""))
        resolved = json.loads(output)["state"]
        self.assertEqual(resolved["status"], "COMPLETED")
        self.assertEqual(
            resolved["memory_candidates"][0]["governance_status"], "VAULT_WRITTEN"
        )
        self.assertTrue((self.vault / "Agent" / "Memory" / (candidate_id + ".md")).is_file())

        code, output, _ = self.invoke("search", "Checkpoint durable recovery")
        self.assertEqual(code, 0)
        paths = [item["relative_path"] for item in json.loads(output)]
        self.assertIn("Agent/Memory/%s.md" % candidate_id, paths)

    def test_cli_vector_sync_hybrid_search_and_research_run(self):
        self.configure_providers()
        self.assertEqual(self.invoke("sync")[0], 0)

        class FakeResponse:
            def __init__(self, document):
                self.payload = json.dumps(document).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *arguments):
                return False

            def read(self):
                return self.payload

        def fake_urlopen(request, timeout):
            payload = json.loads(request.data.decode("utf-8"))
            if request.full_url.endswith("/embeddings"):
                return FakeResponse(
                    {
                        "data": [
                            {"index": index, "embedding": [1.0, 0.0, 0.0, 1.0]}
                            for index, _ in enumerate(payload["input"])
                        ]
                    }
                )
            return FakeResponse(
                {
                    "model": "model-v1",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "title": "Recovery",
                                        "sections": [
                                            {
                                                "heading": "Policy",
                                                "paragraphs": [
                                                    {
                                                        "text": "Checkpoint enables durable recovery.",
                                                        "citations": [1],
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 8},
                }
            )

        with patch("personal_ai_agent.provider_adapters.urlopen", fake_urlopen):
            code, output, errors = self.invoke("vector-sync")
            self.assertEqual((code, errors), (0, ""))
            self.assertEqual(json.loads(output)["embedded"], 1)

            code, output, errors = self.invoke(
                "hybrid-search", "durable recovery", "--provider", "embed-local"
            )
            self.assertEqual((code, errors), (0, ""))
            self.assertEqual(json.loads(output)[0]["relative_path"], "Architecture.md")

            code, output, errors = self.invoke(
                "research-run",
                "durable recovery",
                "--thread-id",
                "thread-provider",
                "--model-provider",
                "model-local",
            )
            self.assertEqual((code, errors), (0, ""))
            state = json.loads(output)["state"]
            self.assertEqual(state["status"], "WAITING_USER")
            self.assertEqual(state["model_calls"][0]["provider_id"], "model-local")
            self.assertEqual(state["thread_id"], "thread-provider")

            code, output, errors = self.invoke("task-events", state["task_id"])
            self.assertEqual((code, errors), (0, ""))
            events = json.loads(output)
            event_types = [item["event_type"] for item in events]
            self.assertIn("model_attempt", event_types)
            self.assertIn("model_completed", event_types)
            self.assertIn("task_waiting_user", event_types)
            self.assertNotIn("durable recovery", output)

    def test_cli_retrieval_evaluation_produces_private_baseline_report(self):
        self.assertEqual(self.invoke("sync")[0], 0)
        dataset = self.root / "retrieval-eval.json"
        dataset.write_text(
            json.dumps(
                {
                    "schema": "retrieval_eval_v1",
                    "name": "cli-baseline",
                    "cases": [
                        {
                            "case_id": "architecture-recovery",
                            "query": "durable recovery",
                            "expected_paths": ["Architecture.md"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        code, output, errors = self.invoke(
            "eval-retrieval", str(dataset), "--limit", "3"
        )

        self.assertEqual((code, errors), (0, ""))
        report = json.loads(output)
        self.assertEqual(report["schema"], "retrieval_eval_report_v1")
        self.assertEqual(report["recall_at_k"], 1.0)
        self.assertEqual(report["hit_rate_at_k"], 1.0)
        self.assertEqual(report["mrr_at_k"], 1.0)
        self.assertNotIn("durable recovery", output)
        service = ApplicationService.from_file(str(self.config_path))
        events = service.event_store.list_events("evaluation_completed")
        self.assertEqual(events[0].attributes["dataset_name"], "cli-baseline")

        code, output, errors = self.invoke(
            "eval-retrieval",
            str(dataset),
            "--minimum",
            "recall_at_k=1.0",
            "--minimum",
            "mrr_at_k=1.0",
        )
        self.assertEqual((code, errors), (0, ""))
        self.assertTrue(json.loads(output)["gate_passed"])

    def test_cli_research_and_memory_quality_gates_use_distinct_exit_code(self):
        research = self.root / "research-eval.json"
        research.write_text(
            json.dumps(
                {
                    "schema": "research_summary_eval_v1",
                    "name": "cli-research-baseline",
                    "cases": [
                        {
                            "case_id": "summary-case",
                            "citation_count": 2,
                            "summary": {
                                "title": "Result",
                                "sections": [
                                    {
                                        "heading": "Findings",
                                        "paragraphs": [
                                            {
                                                "text": "Private evaluated statement.",
                                                "citations": [1],
                                            }
                                        ],
                                    }
                                ],
                            },
                            "expected_paragraph_citations": [[1, 2]],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        memory = self.root / "memory-eval.json"
        memory.write_text(
            json.dumps(
                {
                    "schema": "memory_governance_eval_v1",
                    "name": "cli-memory-baseline",
                    "cases": [
                        {
                            "case_id": "memory-case",
                            "subject": "policy",
                            "statement": "Private governed memory.",
                            "source_ids": ["chunk-1"],
                            "existing_memories": [],
                            "expected_status": "PENDING",
                            "expected_reason": None,
                            "expected_requires_approval": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        code, output, errors = self.invoke(
            "eval-research", str(research), "--minimum", "citation_recall=1.0"
        )
        self.assertEqual((code, errors), (3, ""))
        research_report = json.loads(output)
        self.assertFalse(research_report["gate_passed"])
        self.assertEqual(research_report["failed_gates"], ["citation_recall"])
        self.assertNotIn("Private evaluated statement", output)

        code, output, errors = self.invoke(
            "eval-memory", str(memory), "--minimum", "decision_accuracy=1.0"
        )
        self.assertEqual((code, errors), (0, ""))
        memory_report = json.loads(output)
        self.assertTrue(memory_report["gate_passed"])
        self.assertNotIn("Private governed memory", output)


if __name__ == "__main__":
    unittest.main()
