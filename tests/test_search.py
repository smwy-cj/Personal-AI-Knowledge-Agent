import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.knowledge import KeywordSearchQuery
from personal_ai_agent.knowledge_repository import SQLiteKnowledgeRepository
from personal_ai_agent.obsidian import ObsidianVaultIngester
from personal_ai_agent.search import KeywordSearchEngine


class KeywordSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.vault = root / "vault"
        (self.vault / "Projects").mkdir(parents=True)
        (self.vault / "Archive").mkdir()
        (self.vault / "Projects" / "memory.md").write_text(
            "---\ntags: [agent, active]\n---\n# Agent Memory\n"
            "Task state supports durable agent memory.\n## Policy\nMemory write needs evidence.\n",
            encoding="utf-8",
        )
        (self.vault / "Archive" / "old.md").write_text(
            "---\ntags: [agent, archived]\n---\n# Old Agent\nAgent memory draft.\n",
            encoding="utf-8",
        )
        (self.vault / "中文.md").write_text(
            "# 检索设计\n混合检索需要保留引用证据。\n", encoding="utf-8"
        )
        self.repository = SQLiteKnowledgeRepository(root / "knowledge.sqlite3")
        self.ingester = ObsidianVaultIngester(self.vault, self.repository)
        self.ingester.sync()

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_fts5_returns_citation_ready_result(self):
        results = KeywordSearchEngine(self.repository).search(
            KeywordSearchQuery("agent memory", limit=5)
        )

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual("fts5", results[0].match_method)
        self.assertEqual("Projects/memory.md", results[0].relative_path)
        self.assertGreaterEqual(results[0].start_line, 1)
        self.assertGreaterEqual(results[0].end_line, results[0].start_line)
        self.assertEqual(["agent", "memory"], results[0].matched_terms)

    def test_filters_by_path_and_all_tags(self):
        results = KeywordSearchEngine(self.repository).search(
            KeywordSearchQuery(
                "agent", path_prefix="Projects/", tags=["#agent", "active"]
            )
        )
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(all(item.relative_path == "Projects/memory.md" for item in results))
        self.assertEqual(len(results), len({item.chunk_id for item in results}))

    def test_deterministic_fallback_supports_chinese_and_stable_order(self):
        engine = KeywordSearchEngine(self.repository, prefer_fts5=False)
        results = engine.search(KeywordSearchQuery("混合检索 引用"))

        self.assertEqual(1, len(results))
        self.assertEqual("deterministic", results[0].match_method)
        self.assertEqual("中文.md", results[0].relative_path)
        self.assertEqual(1.0, results[0].score)

    def test_index_removes_deleted_and_replaces_updated_content(self):
        note = self.vault / "Projects" / "memory.md"
        note.write_text("# Replacement\nCompletely new topic.\n", encoding="utf-8")
        self.ingester.sync()
        engine = KeywordSearchEngine(self.repository)
        self.assertEqual([], engine.search(KeywordSearchQuery("durable")))

        note.unlink()
        self.ingester.sync()
        self.assertEqual([], engine.search(KeywordSearchQuery("Replacement")))

    def test_rejects_empty_or_excessive_query(self):
        with self.assertRaises(ValueError):
            KeywordSearchQuery("   ")
        with self.assertRaises(ValueError):
            KeywordSearchQuery("agent", limit=101)


if __name__ == "__main__":
    unittest.main()
