import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from personal_ai_agent.cli import main
from personal_ai_agent.credentials import InMemoryCredentialStore


class CredentialCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "vault").mkdir()
        self.config = self.root / "agent.json"
        self.config.write_text(
            json.dumps(
                {
                    "vault_path": "vault",
                    "data_directory": "runtime",
                    "model_providers": [
                        {
                            "provider_id": "model-main",
                            "base_url": "https://example.test/v1",
                            "model": "model-v1",
                            "credential_env": "MODEL_MAIN_KEY",
                            "capabilities": ["structured_output"],
                            "max_context_tokens": 8192,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.store = InMemoryCredentialStore()

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *arguments, secret_reader=None, environ=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(
                ["--config", str(self.config), *arguments],
                credential_store=self.store,
                secret_reader=secret_reader,
                environ={} if environ is None else environ,
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def test_set_uses_secret_reader_and_status_never_returns_value(self):
        marker = "private-cli-value"
        prompts = []

        code, output, errors = self.invoke(
            "credential-set",
            "model-main",
            secret_reader=lambda prompt: prompts.append(prompt) or marker,
        )

        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(self.store.get("model-main"), marker)
        self.assertEqual(len(prompts), 1)
        self.assertNotIn(marker, output)

        code, output, errors = self.invoke("credential-status", "model-main")
        self.assertEqual((code, errors), (0, ""))
        status = json.loads(output)
        self.assertEqual(status["source"], "keyring")
        self.assertTrue(status["configured"])
        self.assertNotIn(marker, output)

    def test_set_overwrites_and_delete_is_idempotent(self):
        self.invoke("credential-set", "model-main", secret_reader=lambda _: "first")
        self.invoke("credential-set", "model-main", secret_reader=lambda _: "second")
        self.assertEqual(self.store.get("model-main"), "second")

        code, output, _ = self.invoke("credential-delete", "model-main")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output)["deleted"])
        code, output, _ = self.invoke("credential-delete", "model-main")
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output)["deleted"])

    def test_status_uses_explicit_environment_fallback_without_value(self):
        marker = "environment-private-value"
        code, output, errors = self.invoke(
            "credential-status", "model-main", environ={"MODEL_MAIN_KEY": marker}
        )

        self.assertEqual((code, errors), (0, ""))
        status = json.loads(output)
        self.assertTrue(status["configured"])
        self.assertEqual(status["source"], "environment")
        self.assertNotIn(marker, output)

    def test_unknown_provider_fails_without_reading_secret(self):
        reads = []
        code, output, errors = self.invoke(
            "credential-set",
            "unknown",
            secret_reader=lambda prompt: reads.append(prompt) or "private-value",
        )
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertEqual(reads, [])
        self.assertNotIn("private-value", errors)


if __name__ == "__main__":
    unittest.main()
