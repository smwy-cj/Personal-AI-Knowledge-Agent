import json
import re
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.web import create_app

from tests.test_web_research import ResearchPort, task_document


def csrf_token(client, path="/research"):
    page = client.get(path).get_data(as_text=True)
    match = re.search(r'name="_csrf_token" value="([^"]+)"', page)
    if match is None:
        raise AssertionError("page contains no CSRF token")
    return match.group(1)


class ErrorPort(ResearchPort):
    def run_research(self, *args, **kwargs):
        raise RuntimeError(
            "provider body secret-marker prompt=C:\\Users\\student\\private.txt"
        )


class TaskErrorPort(ResearchPort):
    def __init__(self):
        super().__init__()
        self.task = task_document("FAILED")
        self.task["state"]["errors"] = [
            {
                "error_type": "ProviderProtocolError",
                "message": "secret-marker C:\\Users\\student\\vault",
            }
        ]


class WebSecurityTests(unittest.TestCase):
    def make_app(self, port=None, **config):
        values = {
            "TESTING": True,
            "SECRET_KEY": "test-only-secret-key",
            "DEMO_MODE": True,
        }
        values.update(config)
        return create_app(application_port=port or ResearchPort(), test_config=values)

    def test_csrf_is_required_and_valid_token_allows_state_change(self):
        port = ResearchPort()
        client = self.make_app(port).test_client()

        missing = client.post(
            "/research",
            data={"goal": "recovery", "thread_id": "web", "limit": "6"},
        )
        valid = client.post(
            "/research",
            data={
                "_csrf_token": csrf_token(client),
                "goal": "recovery",
                "thread_id": "web",
                "limit": "6",
            },
        )

        self.assertEqual(missing.status_code, 400)
        self.assertIn("请求验证失败", missing.get_data(as_text=True))
        self.assertEqual(valid.status_code, 303)
        self.assertEqual(len(port.run_calls), 1)

    def test_csrf_covers_cancel_and_memory_resolution(self):
        port = ResearchPort()
        port.pending_memory_candidates = lambda task_id: [
            {
                "candidate_id": "memory-1",
                "memory_type": "semantic",
                "content": "safe",
                "confidence": 0.9,
                "decision_reason": "new_fact",
                "conflict_ids": [],
            }
        ]
        port.resolve_calls = []
        port.resolve_memory = lambda *args: port.resolve_calls.append(args)
        client = self.make_app(port).test_client()

        self.assertEqual(client.post("/tasks/task-demo-1/cancel").status_code, 400)
        token = csrf_token(client, "/tasks/task-demo-1/memory")
        approved = client.post(
            "/tasks/task-demo-1/memory",
            data={"_csrf_token": token, "decision_memory-1": "approve"},
        )
        self.assertEqual(approved.status_code, 303)
        self.assertEqual(len(port.resolve_calls), 1)

    def test_security_headers_are_present_and_hsts_requires_https(self):
        client = self.make_app().test_client()
        http = client.get("/")
        https = client.get("/", base_url="https://localhost")

        for response in (http, https):
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertIn("Permissions-Policy", response.headers)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn("Strict-Transport-Security", http.headers)
        self.assertIn("max-age=31536000", https.headers["Strict-Transport-Security"])

    def test_csrf_session_cookie_uses_secure_attributes_on_https(self):
        client = self.make_app(SESSION_COOKIE_SECURE=True).test_client()
        response = client.get("/research", base_url="https://localhost")
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_explicit_https_deployment_emits_hsts_behind_tls_terminator(self):
        response = self.make_app(SESSION_COOKIE_SECURE=True).test_client().get("/")
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])

    def test_oversized_body_is_rejected_before_business_call(self):
        port = ResearchPort()
        client = self.make_app(port, MAX_CONTENT_LENGTH=256).test_client()
        response = client.post(
            "/research",
            data={"_csrf_token": "x", "goal": "a" * 1000},
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("请求内容过大", response.get_data(as_text=True))
        self.assertEqual(port.run_calls, [])

    def test_internal_and_task_errors_hide_sensitive_details(self):
        internal = self.make_app(ErrorPort()).test_client()
        token = csrf_token(internal)
        response = internal.post(
            "/research",
            data={
                "_csrf_token": token,
                "goal": "recovery",
                "thread_id": "web",
                "limit": "6",
            },
        )
        task = self.make_app(TaskErrorPort()).test_client().get("/tasks/task-demo-1")
        combined = response.get_data(as_text=True) + task.get_data(as_text=True)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret-marker", combined)
        self.assertNotIn("C:\\Users", combined)
        self.assertNotIn("prompt=", combined)
        self.assertIn("ProviderProtocolError", combined)

    def test_demo_mode_rejects_vault_outside_explicit_demo_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            approved = root / "approved"
            outside_vault = root / "outside-vault"
            runtime = approved / "runtime"
            approved.mkdir()
            outside_vault.mkdir()
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "vault_path": str(outside_vault),
                        "data_directory": str(runtime),
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "demo data root"):
                create_app(
                    config_path=str(config),
                    test_config={
                        "TESTING": True,
                        "DEMO_MODE": True,
                        "DEMO_DATA_ROOT": str(approved),
                    },
                )

    def test_forms_have_accessible_navigation_labels_and_errors(self):
        client = self.make_app().test_client()
        research = client.get("/research").get_data(as_text=True)
        invalid = client.post(
            "/research",
            data={"_csrf_token": csrf_token(client), "goal": "", "limit": "8"},
        ).get_data(as_text=True)
        self.assertIn('class="skip-link"', research)
        self.assertIn('id="main-content"', research)
        self.assertIn('for="goal"', research)
        self.assertIn('aria-describedby="form-error"', invalid)
        self.assertIn('id="form-error"', invalid)
        self.assertIn('role="alert"', invalid)


if __name__ == "__main__":
    unittest.main()
