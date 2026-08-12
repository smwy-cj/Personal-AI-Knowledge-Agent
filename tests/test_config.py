import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.config import ApplicationConfig, ConfigurationError


class ApplicationConfigTests(unittest.TestCase):
    def test_load_resolves_relative_paths_and_exposes_no_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault").mkdir()
            path = root / "agent.json"
            path.write_text(
                json.dumps(
                    {
                        "vault_path": "vault",
                        "data_directory": "runtime",
                        "managed_memory_directory": "AI/Memory",
                    }
                ),
                encoding="utf-8",
            )

            config = ApplicationConfig.load(path)

            self.assertEqual(config.vault_path, (root / "vault").resolve())
            self.assertEqual(config.data_directory, (root / "runtime").resolve())
            self.assertEqual(config.managed_memory_directory, "AI/Memory")
            self.assertEqual(set(config.as_public_dict()), {
                "vault_path",
                "data_directory",
                "managed_memory_directory",
                "model_provider_ids",
                "embedding_provider_ids",
                "observability_retention_days",
            })
            self.assertEqual(config.observability_retention_days, 90)

    def test_loads_provider_metadata_but_never_resolves_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault").mkdir()
            path = root / "agent.json"
            path.write_text(
                json.dumps(
                    {
                        "vault_path": "vault",
                        "data_directory": "runtime",
                        "model_providers": [
                            {
                                "provider_id": "model-local",
                                "base_url": "https://example.test/v1",
                                "model": "model-v1",
                                "credential_env": "MODEL_CREDENTIAL",
                                "capabilities": ["structured_output"],
                                "max_context_tokens": 8192,
                                "input_cost_per_million_tokens_usd": 2.5,
                                "output_cost_per_million_tokens_usd": 10,
                            }
                        ],
                        "embedding_providers": [
                            {
                                "provider_id": "embedding-local",
                                "base_url": "http://127.0.0.1:9000/v1",
                                "model": "embed-v1",
                                "dimension": 4,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            config = ApplicationConfig.load(path)
            public = config.as_public_dict()

            self.assertEqual(public["model_provider_ids"], ["model-local"])
            self.assertEqual(public["embedding_provider_ids"], ["embedding-local"])
            self.assertNotIn("MODEL_CREDENTIAL", json.dumps(public))
            self.assertEqual(
                config.model_providers[0].input_cost_per_million_tokens_usd, 2.5
            )
            self.assertEqual(
                config.model_providers[0].output_cost_per_million_tokens_usd, 10.0
            )

    def test_rejects_invalid_prices_and_retention(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault").mkdir()
            path = root / "agent.json"
            documents = [
                {
                    "vault_path": "vault",
                    "data_directory": "runtime",
                    "observability_retention_days": 0,
                },
                {
                    "vault_path": "vault",
                    "data_directory": "runtime",
                    "model_providers": [
                        {
                            "provider_id": "model",
                            "base_url": "http://127.0.0.1:9000/v1",
                            "model": "model-v1",
                            "max_context_tokens": 8192,
                            "input_cost_per_million_tokens_usd": -1,
                        }
                    ],
                },
            ]
            for document in documents:
                with self.subTest(document=document):
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(ConfigurationError):
                        ApplicationConfig.load(path)

    def test_rejects_credential_over_plain_remote_http(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault").mkdir()
            path = root / "agent.json"
            path.write_text(
                json.dumps(
                    {
                        "vault_path": "vault",
                        "data_directory": "runtime",
                        "model_providers": [
                            {
                                "provider_id": "unsafe",
                                "base_url": "http://example.test/v1",
                                "model": "model-v1",
                                "credential_env": "MODEL_CREDENTIAL",
                                "max_context_tokens": 8192,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                ApplicationConfig.load(path)

    def test_rejects_invalid_provider_rate_limits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault").mkdir()
            path = root / "agent.json"
            for requests, wait in ((0, 1), (1, -1)):
                with self.subTest(requests=requests, wait=wait):
                    path.write_text(
                        json.dumps(
                            {
                                "vault_path": "vault",
                                "data_directory": "runtime",
                                "embedding_providers": [
                                    {
                                        "provider_id": "embed",
                                        "base_url": "http://127.0.0.1:9000/v1",
                                        "model": "embed-v1",
                                        "dimension": 4,
                                        "requests_per_minute": requests,
                                        "max_rate_limit_wait_seconds": wait,
                                    }
                                ],
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ConfigurationError):
                        ApplicationConfig.load(path)

    def test_rejects_secret_fields_without_echoing_the_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault").mkdir()
            secret = "must-not-appear-in-errors"
            path = root / "agent.json"
            path.write_text(
                json.dumps(
                    {
                        "vault_path": "vault",
                        "data_directory": "runtime",
                        "api_key": secret,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError) as raised:
                ApplicationConfig.load(path)

            self.assertNotIn(secret, str(raised.exception))

    def test_rejects_runtime_data_inside_vault(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault").mkdir()
            path = root / "agent.json"
            path.write_text(
                json.dumps(
                    {
                        "vault_path": "vault",
                        "data_directory": "vault/.agent-data",
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "must be separate"):
                ApplicationConfig.load(path)

    def test_rejects_unsafe_managed_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "vault").mkdir()
            for managed in ("../escape", "/absolute", ".obsidian/agent"):
                with self.subTest(managed=managed):
                    path = root / "agent.json"
                    path.write_text(
                        json.dumps(
                            {
                                "vault_path": "vault",
                                "data_directory": "runtime",
                                "managed_memory_directory": managed,
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaises(ConfigurationError):
                        ApplicationConfig.load(path)


if __name__ == "__main__":
    unittest.main()
