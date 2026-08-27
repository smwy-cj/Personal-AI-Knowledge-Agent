import json
import math
import unittest

from scripts.local_embedding_server import (
    EmbeddingRequestError,
    EmbeddingService,
    MAX_INPUTS,
    _normalize_inputs,
)


class FakeEmbeddingModel:
    def embed(self, texts):
        for index, _ in enumerate(texts):
            yield [float(index + 1), 0.5, -0.25]


class LocalEmbeddingServerTests(unittest.TestCase):
    def setUp(self):
        self.service = EmbeddingService(FakeEmbeddingModel(), "local-model", 3)

    def test_openai_compatible_response_preserves_order_and_dimension(self):
        response = self.service.create_embeddings(
            {"model": "local-model", "input": ["第一条", "second"]}
        )

        self.assertEqual("list", response["object"])
        self.assertEqual("local-model", response["model"])
        self.assertEqual([0, 1], [item["index"] for item in response["data"]])
        self.assertTrue(
            all(len(item["embedding"]) == 3 for item in response["data"])
        )

    def test_validation_rejects_wrong_model_empty_and_excess_inputs(self):
        invalid_documents = [
            {"model": "wrong", "input": ["safe"]},
            {"model": "local-model", "input": []},
            {"model": "local-model", "input": ["safe", ""]},
            {"model": "local-model", "input": ["safe"] * (MAX_INPUTS + 1)},
        ]
        for document in invalid_documents:
            with self.subTest(document=document), self.assertRaises(
                EmbeddingRequestError
            ):
                self.service.create_embeddings(document)

    def test_errors_and_response_do_not_copy_input_text(self):
        marker = "private-query-marker"
        response = self.service.create_embeddings(
            {"model": "local-model", "input": marker}
        )

        self.assertNotIn(marker, json.dumps(response))
        with self.assertRaises(EmbeddingRequestError) as raised:
            _normalize_inputs([marker, ""])
        self.assertNotIn(marker, str(raised.exception))

    def test_invalid_vector_is_rejected(self):
        class InvalidModel:
            def embed(self, texts):
                return [[math.nan, 0.0, 0.0] for _ in texts]

        service = EmbeddingService(InvalidModel(), "local-model", 3)
        with self.assertRaises(RuntimeError):
            service.create_embeddings({"model": "local-model", "input": "safe"})


if __name__ == "__main__":
    unittest.main()
