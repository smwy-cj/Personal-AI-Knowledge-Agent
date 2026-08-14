import json
import unittest

from personal_ai_agent.web import ApplicationServiceWebAdapter, create_app


class FakeWebApplicationPort:
    def __init__(self):
        self.health_calls = 0
        self.fail_health = False

    def health(self):
        self.health_calls += 1
        if self.fail_health:
            raise RuntimeError("private-path C:/Users/example/vault private-prompt")
        return {
            "status": "ok",
            "config_loaded": True,
            "storage_ready": True,
            "demo_mode": True,
        }

    def knowledge_status(self):
        return {"vault_id": "demo-vault", "fts5_available": True}


class WebFoundationTests(unittest.TestCase):
    def setUp(self):
        self.port = FakeWebApplicationPort()
        self.app = create_app(
            application_port=self.port,
            test_config={"TESTING": True, "DEMO_MODE": True},
        )
        self.client = self.app.test_client()

    def test_health_is_json_and_uses_only_the_injected_port(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json()["status"], "ok")
        self.assertEqual(self.port.health_calls, 1)

    def test_home_explains_value_and_demo_boundary(self):
        response = self.client.get("/")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Personal AI Knowledge Agent", page)
        self.assertIn("可追溯", page)
        self.assertIn("演示模式", page)
        self.assertIn("demo-vault", page)

    def test_factory_keeps_port_per_application_instance(self):
        other_port = FakeWebApplicationPort()
        other = create_app(
            application_port=other_port,
            test_config={"TESTING": True, "DEMO_MODE": False},
        )

        self.assertIs(
            self.app.extensions["personal_ai_agent_port"], self.port
        )
        self.assertIs(other.extensions["personal_ai_agent_port"], other_port)

    def test_unknown_route_returns_safe_404(self):
        response = self.client.get("/missing")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 404)
        self.assertIn("页面不存在", page)
        self.assertNotIn("C:/", page)
        self.assertNotIn("Traceback", page)

    def test_unhandled_error_returns_only_correlation_id(self):
        self.port.fail_health = True
        response = self.client.get("/health")
        payload = response.get_json()

        self.assertEqual(response.status_code, 500)
        self.assertEqual(payload["error"], "internal_error")
        self.assertRegex(payload["correlation_id"], r"^[0-9a-f]{32}$")
        serialized = json.dumps(payload)
        self.assertNotIn("private-path", serialized)
        self.assertNotIn("private-prompt", serialized)
        self.assertNotIn("Traceback", serialized)

    def test_production_adapter_health_only_uses_public_validation(self):
        class FakeApplicationService:
            def __init__(self):
                self.calls = []

            def validate(self):
                self.calls.append("validate")
                return {
                    "valid": True,
                    "fts5_available": True,
                    "vault_id": "vault-id",
                    "config": {
                        "model_provider_ids": [],
                        "embedding_provider_ids": [],
                    },
                }

        service = FakeApplicationService()
        adapter = ApplicationServiceWebAdapter(service, demo_mode=True)

        health = adapter.health()

        self.assertEqual(service.calls, ["validate"])
        self.assertEqual(
            health,
            {
                "status": "ok",
                "config_loaded": True,
                "storage_ready": True,
                "demo_mode": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
