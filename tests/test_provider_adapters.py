import json
import os
import unittest
from unittest.mock import patch

from personal_ai_agent.config import EmbeddingProviderConfig, ModelProviderConfig
from personal_ai_agent.model_gateway import ModelRequest
from personal_ai_agent.provider_adapters import (
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleModelProvider,
    ProviderConfigurationError,
    ProviderPayloadTooLarge,
    _post_json,
)
from personal_ai_agent.model_gateway import RetryableModelError
from email.message import Message
from urllib.error import HTTPError


class FakeHttpResponse:
    def __init__(self, document):
        self.payload = json.dumps(document).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        return False

    def read(self):
        return self.payload


class ProviderAdapterTests(unittest.TestCase):
    def test_model_adapter_reads_credential_at_call_time(self):
        config = ModelProviderConfig(
            "model-test",
            "https://example.test/v1",
            "model-v1",
            "MODEL_TEST_CREDENTIAL",
            frozenset({"structured_output"}),
            8192,
            "medium",
            "personal",
        )
        provider = OpenAICompatibleModelProvider(config)
        captured = {}

        def fake_urlopen(request, timeout):
            captured["authorization"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeHttpResponse(
                {
                    "model": "model-v1",
                    "choices": [
                        {"message": {"content": json.dumps({"value": "ok"})}}
                    ],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3},
                }
            )

        with patch.dict(os.environ, {"MODEL_TEST_CREDENTIAL": "private-value"}), patch(
            "personal_ai_agent.provider_adapters.urlopen", fake_urlopen
        ):
            response = provider.generate(ModelRequest("test", "v1", {"input": "hi"}))

        self.assertEqual(response.data, {"value": "ok"})
        self.assertEqual(response.input_tokens + response.output_tokens, 10)
        self.assertEqual(captured["authorization"], "Bearer private-value")
        self.assertEqual(captured["timeout"], 30.0)
        self.assertEqual(captured["body"]["response_format"], {"type": "json_object"})

    def test_missing_credential_reports_only_the_environment_name(self):
        config = ModelProviderConfig(
            "model-test",
            "https://example.test/v1",
            "model-v1",
            "MODEL_MISSING_CREDENTIAL",
            frozenset({"structured_output"}),
            8192,
            "medium",
            "personal",
        )
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(
            ProviderConfigurationError
        ) as raised:
            OpenAICompatibleModelProvider(config).generate(
                ModelRequest("test", "v1", {})
            )
        self.assertIn("MODEL_MISSING_CREDENTIAL", str(raised.exception))

    def test_embedding_adapter_preserves_provider_order(self):
        config = EmbeddingProviderConfig(
            "embed-test", "http://127.0.0.1:9000/v1", "embed-v1", 2, None
        )

        def fake_urlopen(request, timeout):
            return FakeHttpResponse(
                {
                    "data": [
                        {"index": 1, "embedding": [0.0, 1.0]},
                        {"index": 0, "embedding": [1.0, 0.0]},
                    ]
                }
            )

        with patch("personal_ai_agent.provider_adapters.urlopen", fake_urlopen):
            vectors = OpenAICompatibleEmbeddingProvider(config).embed(["a", "b"])
        self.assertEqual(vectors, [[1.0, 0.0], [0.0, 1.0]])

    def test_embedding_payload_is_recursively_split_without_reordering(self):
        config = EmbeddingProviderConfig(
            "embed-test", "http://127.0.0.1:9000/v1", "embed-v1", 2, None
        )
        batch_sizes = []

        def fake_post(url, payload, credential_env, timeout_seconds):
            texts = payload["input"]
            batch_sizes.append(len(texts))
            if len(texts) > 2:
                raise ProviderPayloadTooLarge("too large")
            return {
                "data": [
                    {"index": index, "embedding": [float(text), 1.0]}
                    for index, text in enumerate(texts)
                ]
            }

        with patch("personal_ai_agent.provider_adapters._post_json", fake_post):
            vectors = OpenAICompatibleEmbeddingProvider(config).embed(
                ["1", "2", "3", "4", "5"]
            )

        self.assertEqual(batch_sizes, [5, 2, 3, 1, 2])
        self.assertEqual([vector[0] for vector in vectors], [1, 2, 3, 4, 5])

    def test_single_embedding_payload_too_large_terminates(self):
        config = EmbeddingProviderConfig(
            "embed-test", "http://127.0.0.1:9000/v1", "embed-v1", 2, None
        )
        with patch(
            "personal_ai_agent.provider_adapters._post_json",
            side_effect=ProviderPayloadTooLarge("too large"),
        ), self.assertRaisesRegex(ProviderPayloadTooLarge, "one embedding input"):
            OpenAICompatibleEmbeddingProvider(config).embed(["oversized"])

    def test_retry_after_is_parsed_without_reading_error_body(self):
        headers = Message()
        headers["Retry-After"] = "7"

        def rate_limited(request, timeout):
            raise HTTPError(request.full_url, 429, "limited", headers, None)

        with patch(
            "personal_ai_agent.provider_adapters.urlopen", rate_limited
        ), self.assertRaises(RetryableModelError) as raised:
            _post_json("https://example.test/v1", {}, None, 1.0)

        self.assertEqual(raised.exception.retry_after_seconds, 7.0)


if __name__ == "__main__":
    unittest.main()
