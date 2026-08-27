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

    def test_chinese_natural_question_uses_deterministic_bigrams(self):
        results = KeywordSearchEngine(self.repository).search(
            KeywordSearchQuery("如何设计混合检索并保留引用证据？")
        )

        self.assertEqual(1, len(results))
        self.assertEqual("中文.md", results[0].relative_path)
        self.assertEqual("deterministic", results[0].match_method)
        self.assertIn("混合", results[0].matched_terms)
        self.assertIn("引用", results[0].matched_terms)

    def test_chinese_fallback_rejects_unrelated_question(self):
        results = KeywordSearchEngine(self.repository).search(
            KeywordSearchQuery("量子纠错编码怎样处理退相干？")
        )

        self.assertEqual([], results)

    def test_latin_identifier_is_mandatory_in_mixed_language_query(self):
        results = KeywordSearchEngine(self.repository).search(
            KeywordSearchQuery("Q-learning 如何设计混合检索？")
        )

        self.assertEqual([], results)

    def test_mixed_query_still_requires_a_chinese_anchor_for_one_identifier(self):
        results = KeywordSearchEngine(self.repository).search(
            KeywordSearchQuery("Agent 量子纠错机制是什么？")
        )

        self.assertEqual([], results)

    def test_chinese_tag_question_searches_document_metadata(self):
        results = KeywordSearchEngine(self.repository).search(
            KeywordSearchQuery("哪些笔记带有 active 标签？")
        )

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual("Projects/memory.md", results[0].relative_path)
        self.assertIn("active", results[0].matched_terms)

    def test_chinese_results_limit_repeated_chunks_per_document(self):
        (self.vault / "verbose.md").write_text(
            "# 中文检索\n## 一\n中文检索证据证据。\n"
            "## 二\n中文检索证据证据。\n## 三\n中文检索证据证据。\n",
            encoding="utf-8",
        )
        (self.vault / "concise.md").write_text(
            "# 证据设计\n中文检索需要证据。\n", encoding="utf-8"
        )
        self.ingester.sync()

        results = KeywordSearchEngine(self.repository).search(
            KeywordSearchQuery("中文检索证据如何设计？", limit=3)
        )

        self.assertEqual(3, len(results))
        paths = [item.relative_path for item in results]
        self.assertLessEqual(paths.count("verbose.md"), 2)
        self.assertIn("verbose.md", paths)
        self.assertIn("concise.md", paths)

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
