import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from personal_ai_agent.application import ApplicationService
from personal_ai_agent.web import ApplicationServiceWebAdapter, create_app


def task_document(status="WAITING_USER"):
    return {
        "schema_version": 1,
        "state": {
            "task_id": "task-demo-1",
            "thread_id": "web-demo",
            "user_goal": "How does checkpoint recovery work?",
            "status": status,
            "plan": [
                {"step_id": "retrieve", "status": "COMPLETED"},
                {"step_id": "summarize", "status": "COMPLETED"},
                {"step_id": "persist", "status": "PENDING"},
            ],
            "artifacts": [
                {
                    "artifact_type": "research_summary",
                    "content": {
                        "title": "Recovery <script>alert('x')</script>",
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
                    },
                }
            ],
            "evidence": [
                {
                    "source_id": "1",
                    "relative_path": "Architecture.md",
                    "start_line": 3,
                    "end_line": 4,
                }
            ],
            "errors": [],
            "memory_candidates": [{"candidate_id": "memory-1"}],
            "awaiting_user_approval": status == "WAITING_USER",
            "final_answer": None,
            "tool_calls": 3,
            "model_call_count": 1,
            "token_usage": 28,
        },
    }


class ResearchPort:
    def __init__(self):
        self.run_calls = []
        self.cancel_calls = []
        self.task = task_document()

    def health(self):
        return {"status": "ok"}

    def knowledge_status(self):
        return {"vault_id": "demo-vault", "fts5_available": True}

    def run_research(self, *args, **kwargs):
        self.run_calls.append((args, kwargs))
        return self.task

    def show_task(self, task_id):
        if task_id != "task-demo-1":
            raise KeyError(task_id)
        return self.task

    def cancel_task(self, task_id):
        self.cancel_calls.append(task_id)
        self.task = task_document("CANCELLED")
        return {"task_id": task_id, "status": "CANCELLED"}


class WebResearchTests(unittest.TestCase):
    def setUp(self):
        self.port = ResearchPort()
        self.app = create_app(
            application_port=self.port,
            test_config={
                "TESTING": True,
                "DEMO_MODE": True,
                "CSRF_ENABLED": False,
            },
        )
        self.client = self.app.test_client()

    def test_research_form_does_not_start_task_on_get(self):
        response = self.client.get("/research")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("创建研究任务", page)
        self.assertEqual(self.port.run_calls, [])

    def test_blank_goal_is_rejected_before_port_call(self):
        response = self.client.post("/research", data={"goal": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("请输入研究目标", response.get_data(as_text=True))
        self.assertEqual(self.port.run_calls, [])

    def test_submit_starts_task_and_redirects_to_detail(self):
        response = self.client.post(
            "/research",
            data={"goal": "recovery", "thread_id": "web-demo", "limit": "6"},
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/tasks/task-demo-1")
        args, kwargs = self.port.run_calls[0]
        self.assertEqual(args[:2], ("recovery", "web-demo"))
        self.assertEqual(kwargs["limit"], 6)

    def test_task_page_shows_status_summary_citations_and_escapes_html(self):
        response = self.client.get("/tasks/task-demo-1")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("WAITING_USER", page)
        self.assertIn("Checkpoint enables durable recovery", page)
        self.assertIn("Architecture.md", page)
        self.assertIn("第 3–4 行", page)
        self.assertIn("审查记忆候选", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert", page)

    def test_cancel_is_post_only_and_redirects(self):
        self.assertEqual(self.client.get("/tasks/task-demo-1/cancel").status_code, 405)
        response = self.client.post("/tasks/task-demo-1/cancel")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.port.cancel_calls, ["task-demo-1"])
        detail = self.client.get(response.headers["Location"]).get_data(as_text=True)
        self.assertIn("CANCELLED", detail)

    def test_missing_task_maps_to_safe_404(self):
        response = self.client.get("/tasks/missing")
        self.assertEqual(response.status_code, 404)
        self.assertIn("任务不存在", response.get_data(as_text=True))
        self.assertNotIn("KeyError", response.get_data(as_text=True))

    def test_real_research_pause_approval_and_writeback_web_loop(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            vault.mkdir()
            (vault / "Architecture.md").write_text(
                "# Architecture\n\nCheckpoint enables durable recovery.\n",
                encoding="utf-8",
            )
            config_path = root / "agent.json"
            config_path.write_text(
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
                    }
                ),
                encoding="utf-8",
            )
            service = ApplicationService.from_file(str(config_path))
            service.sync_vault()
            app = create_app(
                application_port=ApplicationServiceWebAdapter(service, True),
                test_config={
                    "TESTING": True,
                    "DEMO_MODE": True,
                    "CSRF_ENABLED": False,
                },
            )

            class FakeResponse:
                headers = None

                def __enter__(self):
                    return self

                def __exit__(self, *arguments):
                    return False

                def read(self):
                    return json.dumps(
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
                    ).encode("utf-8")

            with patch(
                "personal_ai_agent.provider_adapters.urlopen",
                lambda request, timeout: FakeResponse(),
            ):
                response = app.test_client().post(
                    "/research",
                    data={
                        "goal": "durable recovery",
                        "thread_id": "web-real",
                        "model_provider": "model-local",
                        "limit": "6",
                    },
                )

            self.assertEqual(response.status_code, 303)
            task_id = response.headers["Location"].rsplit("/", 1)[-1]
            candidates = service.pending_memory_candidates(task_id)
            self.assertEqual(len(candidates), 1)
            candidate_id = candidates[0]["candidate_id"]

            approval = app.test_client().post(
                "/tasks/%s/memory" % task_id,
                data={"decision_%s" % candidate_id: "approve"},
            )

            self.assertEqual(approval.status_code, 303)
            state = service.show_task(task_id)["state"]
            self.assertEqual(state["status"], "COMPLETED")
            self.assertEqual(
                state["memory_candidates"][0]["governance_status"], "VAULT_WRITTEN"
            )
            self.assertTrue(
                (vault / "Agent" / "Memory" / (candidate_id + ".md")).is_file()
            )

    def test_default_demo_mode_completes_research_without_network_or_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            vault.mkdir()
            (vault / "Demo.md").write_text(
                "# Demo\n\nCheckpoint recovery uses durable state.\n",
                encoding="utf-8",
            )
            config_path = root / "agent.json"
            config_path.write_text(
                json.dumps(
                    {
                        "vault_path": "vault",
                        "data_directory": "runtime",
                        "managed_memory_directory": "Agent/Memory",
                    }
                ),
                encoding="utf-8",
            )
            ApplicationService.from_file(str(config_path)).sync_vault()
            with patch.dict(
                "os.environ",
                {
                    "PERSONAL_AGENT_DEMO_MODE": "1",
                    "PERSONAL_AGENT_DEMO_DATA_ROOT": str(root),
                },
                clear=False,
            ):
                app = create_app(
                    config_path=str(config_path),
                    test_config={"TESTING": True, "CSRF_ENABLED": False},
                )

            with patch(
                "personal_ai_agent.provider_adapters.urlopen",
                side_effect=AssertionError("demo mode must not use the network"),
            ):
                response = app.test_client().post(
                    "/research",
                    data={
                        "goal": "checkpoint recovery",
                        "thread_id": "web-offline-demo",
                        "limit": "6",
                    },
                )

            self.assertEqual(response.status_code, 303)
            detail = app.test_client().get(response.headers["Location"])
            page = detail.get_data(as_text=True)
            self.assertEqual(detail.status_code, 200)
            self.assertIn("WAITING_USER", page)
            self.assertIn("Checkpoint recovery uses durable state", page)
            self.assertIn("Demo.md", page)


if __name__ == "__main__":
    unittest.main()
