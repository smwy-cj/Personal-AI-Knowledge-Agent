import unittest

from personal_ai_agent.web import create_app

from tests.test_web_research import ResearchPort, task_document


class MemoryPort(ResearchPort):
    def __init__(self):
        super().__init__()
        self.resolve_calls = []

    def pending_memory_candidates(self, task_id):
        if task_id != "task-demo-1":
            raise KeyError(task_id)
        if self.task["state"]["status"] != "WAITING_USER":
            return []
        return [
            {
                "candidate_id": "memory-1",
                "memory_type": "semantic",
                "content": "Checkpoint requires review <script>alert('x')</script>",
                "confidence": 0.93,
                "decision_reason": "new_fact",
                "conflict_ids": [],
            },
            {
                "candidate_id": "memory-2",
                "memory_type": "semantic",
                "content": "Recovery is durable.",
                "confidence": 0.88,
                "decision_reason": "conflict_requires_approval",
                "conflict_ids": ["existing-1"],
            },
        ]

    def resolve_memory(self, task_id, approved_ids, rejected_ids):
        self.resolve_calls.append((task_id, list(approved_ids), list(rejected_ids)))
        self.task = task_document("COMPLETED")
        self.task["state"]["memory_candidates"] = [
            {"candidate_id": "memory-1", "governance_status": "VAULT_WRITTEN"},
            {"candidate_id": "memory-2", "governance_status": "REJECTED"},
        ]
        return self.task


class WebMemoryTests(unittest.TestCase):
    def setUp(self):
        self.port = MemoryPort()
        self.app = create_app(
            application_port=self.port,
            test_config={
                "TESTING": True,
                "DEMO_MODE": True,
                "CSRF_ENABLED": False,
            },
        )
        self.client = self.app.test_client()

    def test_review_page_lists_all_candidates_and_escapes_content(self):
        response = self.client.get("/tasks/task-demo-1/memory")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("memory-1", page)
        self.assertIn("memory-2", page)
        self.assertIn("冲突", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert", page)

    def test_every_candidate_requires_an_explicit_valid_decision(self):
        missing = self.client.post(
            "/tasks/task-demo-1/memory",
            data={"decision_memory-1": "approve"},
        )
        invalid = self.client.post(
            "/tasks/task-demo-1/memory",
            data={
                "decision_memory-1": "approve",
                "decision_memory-2": "later",
            },
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(self.port.resolve_calls, [])

    def test_complete_decisions_resolve_once_and_redirect(self):
        response = self.client.post(
            "/tasks/task-demo-1/memory",
            data={
                "decision_memory-1": "approve",
                "decision_memory-2": "reject",
            },
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            self.port.resolve_calls,
            [("task-demo-1", ["memory-1"], ["memory-2"])],
        )
        detail = self.client.get(response.headers["Location"]).get_data(as_text=True)
        self.assertIn("COMPLETED", detail)
        self.assertIn("VAULT_WRITTEN", detail)
        self.assertIn("REJECTED", detail)

    def test_repeated_submission_after_completion_does_not_resolve_again(self):
        payload = {
            "decision_memory-1": "approve",
            "decision_memory-2": "reject",
        }
        first = self.client.post("/tasks/task-demo-1/memory", data=payload)
        second = self.client.post("/tasks/task-demo-1/memory", data=payload)
        self.assertEqual(first.status_code, 303)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(len(self.port.resolve_calls), 1)


if __name__ == "__main__":
    unittest.main()
