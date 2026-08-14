import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.hybrid_search import HybridSearchEngine
from personal_ai_agent.knowledge import HybridSearchQuery, KeywordSearchQuery
from personal_ai_agent.knowledge_repository import SQLiteKnowledgeRepository
from personal_ai_agent.obsidian import ObsidianVaultIngester
from personal_ai_agent.search import KeywordSearchEngine
from personal_ai_agent.vector import InvalidEmbedding, SQLiteVectorIndex


class DeterministicEmbeddingProvider:
    provider_id = "deterministic-test-v1"
    dimension = 4

    def __init__(self):
        self.embedded_text_count = 0

    def embed(self, texts):
        self.embedded_text_count += len(texts)
        vectors = []
        for text in texts:
            lowered = text.casefold()
            vectors.append(
                [
                    float(lowered.count("agent") + lowered.count("智能体")),
                    float(lowered.count("memory") + lowered.count("记忆")),
                    float(lowered.count("retrieval") + lowered.count("检索")),
                    1.0,
                ]
            )
        return vectors


class VectorAndHybridSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.vault = root / "vault"
        self.vault.mkdir()
        (self.vault / "memory.md").write_text(
            "---\ntags: [agent]\n---\n# Long-term Memory\nAgent stores durable memory.\n",
            encoding="utf-8",
        )
        (self.vault / "retrieval.md").write_text(
            "# Search\nHybrid retrieval combines semantic search and keywords.\n",
            encoding="utf-8",
        )
        (self.vault / "misc.md").write_text(
            "# Cooking\nA recipe for noodles.\n", encoding="utf-8"
        )
        self.repository = SQLiteKnowledgeRepository(root / "knowledge.sqlite3")
        self.ingester = ObsidianVaultIngester(self.vault, self.repository)
        self.ingester.sync()
        self.provider = DeterministicEmbeddingProvider()
        self.vector_index = SQLiteVectorIndex(self.repository, self.provider, batch_size=2)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_vector_sync_is_incremental_and_search_is_citation_ready(self):
        first = self.vector_index.sync()
        count_after_first = self.provider.embedded_text_count
        second = self.vector_index.sync()
        results = self.vector_index.search(KeywordSearchQuery("agent memory"))

        self.assertEqual(3, first.embedded)
        self.assertEqual(0, second.embedded)
        self.assertEqual(3, second.unchanged)
        self.assertEqual(count_after_first + 1, self.provider.embedded_text_count)
        self.assertEqual("memory.md", results[0].relative_path)
        self.assertEqual("vector", results[0].match_method)
        self.assertGreaterEqual(results[0].start_line, 1)

    def test_changed_chunk_is_reembedded_and_deleted_chunk_disappears(self):
        self.vector_index.sync()
        note = self.vault / "memory.md"
        note.write_text("# Changed\nOnly retrieval remains.\n", encoding="utf-8")
        self.ingester.sync()
        changed = self.vector_index.sync()
        self.assertEqual(1, changed.embedded)

        note.unlink()
        self.ingester.sync()
        deleted = self.vector_index.sync()
        self.assertEqual([], [item for item in self.vector_index.search(KeywordSearchQuery("memory")) if item.relative_path == "memory.md"])
        self.assertGreaterEqual(deleted.deleted, 0)

    def test_vector_filter_and_hybrid_rrf(self):
        self.vector_index.sync()
        vector_results = self.vector_index.search(
            KeywordSearchQuery("agent memory", tags=["agent"])
        )
        hybrid = HybridSearchEngine(
            KeywordSearchEngine(self.repository), self.vector_index
        ).search(HybridSearchQuery("agent memory", limit=2))

        self.assertTrue(all(item.relative_path == "memory.md" for item in vector_results))
        self.assertEqual("memory.md", hybrid[0].relative_path)
        self.assertEqual("hybrid", hybrid[0].match_method)
        self.assertEqual(1.0, hybrid[0].score)

    def test_rejects_invalid_provider_vectors(self):
        class BadProvider(DeterministicEmbeddingProvider):
            provider_id = "bad-v1"

            def embed(self, texts):
                return [[1.0] for _ in texts]

        index = SQLiteVectorIndex(self.repository, BadProvider())
        with self.assertRaises(InvalidEmbedding):
            index.sync()

    def test_dimension_change_invalidates_cache_even_with_same_provider_id(self):
        self.vector_index.sync()

        class ChangedDimensionProvider(DeterministicEmbeddingProvider):
            dimension = 5

            def embed(self, texts):
                self.embedded_text_count += len(texts)
                return [[1.0, 1.0, 1.0, 1.0, 1.0] for _ in texts]

        changed_provider = ChangedDimensionProvider()
        changed_index = SQLiteVectorIndex(self.repository, changed_provider)
        result = changed_index.sync()

        self.assertEqual(3, result.embedded)
        self.assertEqual(0, result.unchanged)


if __name__ == "__main__":
    unittest.main()
