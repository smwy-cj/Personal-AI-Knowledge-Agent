import json
import os
import unittest
from unittest.mock import patch

from personal_ai_agent.config import EmbeddingProviderConfig, ModelProviderConfig
from personal_ai_agent.credentials import CredentialResolver, InMemoryCredentialStore
from personal_ai_agent.model_gateway import ModelRequest
from personal_ai_agent.provider_adapters import (
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleModelProvider,
)


class FakeHttpResponse:
    def __init__(self):
        self.headers = None

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def read(self):
        return json.dumps(
            {
                "model": "model-v1",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }
        ).encode("utf-8")


class CredentialResolutionTests(unittest.TestCase):
    def test_keyring_precedes_explicit_environment_fallback(self):
        store = InMemoryCredentialStore()
        store.set("model-main", "keyring-private-value")
        resolver = CredentialResolver(store, {"MODEL_MAIN_KEY": "env-private-value"})

        self.assertEqual(
            resolver.resolve("model-main", "MODEL_MAIN_KEY"),
            "keyring-private-value",
        )
        self.assertEqual(resolver.status("model-main", "MODEL_MAIN_KEY").source, "keyring")

    def test_environment_is_used_only_when_explicitly_named(self):
        resolver = CredentialResolver(
            InMemoryCredentialStore(), {"MODEL_MAIN_KEY": "env-private-value"}
        )
        self.assertEqual(
            resolver.resolve("model-main", "MODEL_MAIN_KEY"), "env-private-value"
        )
        self.assertIsNone(resolver.resolve("model-main", None))
        self.assertEqual(resolver.status("model-main", None).source, "none")

    def test_model_provider_uses_resolver_at_call_time(self):
        config = ModelProviderConfig(
            "model-main",
            "https://example.test/v1",
            "model-v1",
            "MODEL_MAIN_KEY",
            frozenset({"structured_output"}),
            8192,
            "medium",
            "personal",
        )
        values = {"credential": "first-private-value"}
        captured = []

        def resolve(provider_id, environment_name):
            self.assertEqual((provider_id, environment_name), ("model-main", "MODEL_MAIN_KEY"))
            return values["credential"]

        def fake_urlopen(request, timeout):
            captured.append(request.headers["Authorization"])
            return FakeHttpResponse()

        provider = OpenAICompatibleModelProvider(config, credential_resolver=resolve)
        with patch("personal_ai_agent.provider_adapters.urlopen", fake_urlopen), patch.dict(
            os.environ, {"MODEL_MAIN_KEY": "wrong-environment-value"}
        ):
            provider.generate(ModelRequest("test", "v1", {}))
            values["credential"] = "second-private-value"
            provider.generate(ModelRequest("test", "v1", {}))

        self.assertEqual(
            captured,
            ["Bearer first-private-value", "Bearer second-private-value"],
        )

    def test_embedding_provider_uses_same_resolver_contract(self):
        config = EmbeddingProviderConfig(
            "embed-main",
            "https://example.test/v1",
            "embed-v1",
            2,
            "EMBED_MAIN_KEY",
        )
        resolved = []

        def resolve(provider_id, environment_name):
            resolved.append((provider_id, environment_name))
            return "embedding-private-value"

        def fake_post(url, payload, credential_reference, timeout_seconds):
            self.assertEqual(credential_reference(), "embedding-private-value")
            return {"data": [{"index": 0, "embedding": [1.0, 0.0]}]}

        with patch("personal_ai_agent.provider_adapters._post_json", fake_post):
            vectors = OpenAICompatibleEmbeddingProvider(
                config, credential_resolver=resolve
            ).embed(["text"])

        self.assertEqual(vectors, [[1.0, 0.0]])
        self.assertEqual(resolved, [("embed-main", "EMBED_MAIN_KEY")])

    def test_resolver_keeps_unauthenticated_local_provider_optional(self):
        config = EmbeddingProviderConfig(
            "embed-local", "http://127.0.0.1:9000/v1", "embed-v1", 2, None
        )

        def fake_post(url, payload, credential_reference, timeout_seconds):
            self.assertIsNone(credential_reference())
            self.assertFalse(credential_reference.required)
            return {"data": [{"index": 0, "embedding": [1.0, 0.0]}]}

        with patch("personal_ai_agent.provider_adapters._post_json", fake_post):
            vectors = OpenAICompatibleEmbeddingProvider(
                config,
                credential_resolver=lambda provider_id, environment_name: None,
            ).embed(["text"])
        self.assertEqual(vectors, [[1.0, 0.0]])


if __name__ == "__main__":
    unittest.main()
