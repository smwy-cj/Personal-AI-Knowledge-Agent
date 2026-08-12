import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.knowledge_repository import SQLiteKnowledgeRepository
from personal_ai_agent.obsidian import ObsidianVaultIngester, parse_obsidian_markdown


class MarkdownParserTests(unittest.TestCase):
    def test_extracts_properties_structure_links_tags_and_lines(self):
        markdown = """---
title: Agent Memory
tags: [agent, memory]
aliases:
  - 长期记忆
---
前言 #overview

# 设计
参见 [[RAG#检索|RAG 系统]]。

## 写入策略
需要审核 #governance

```markdown
# 不是标题
[[Fake Link]] #fake
```
"""
        document = parse_obsidian_markdown(
            "vault-1", "Projects/memory.md", markdown, "hash", len(markdown), 1
        )

        self.assertEqual("Agent Memory", document.title)
        self.assertEqual(["agent", "governance", "memory", "overview"], document.tags)
        self.assertEqual(["RAG"], document.wiki_links)
        self.assertEqual([None, "设计", "写入策略"], [item.heading for item in document.chunks])
        self.assertEqual(["设计", "写入策略"], document.chunks[-1].heading_path)
        self.assertEqual(7, document.chunks[0].start_line)
        self.assertNotIn("Fake Link", document.wiki_links)


class IncrementalIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        self.vault = root / "vault"
        self.vault.mkdir()
        self.repository = SQLiteKnowledgeRepository(root / "knowledge.sqlite3")
        self.ingester = ObsidianVaultIngester(self.vault, self.repository)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_tracks_add_unchanged_update_and_delete(self):
        note = self.vault / "note.md"
        note.write_text("# Note\nFirst #tag\n", encoding="utf-8")
        ignored = self.vault / ".obsidian"
        ignored.mkdir()
        (ignored / "internal.md").write_text("ignored", encoding="utf-8")

        first = self.ingester.sync()
        second = self.ingester.sync()
        note.write_text("# Note\nUpdated [[Other]]\n", encoding="utf-8")
        third = self.ingester.sync()
        stored_id = next(iter(self.repository.document_hashes(self.ingester.vault_id)))
        note.unlink()
        fourth = self.ingester.sync()

        self.assertEqual((1, 0, 0, 0, 0), tuple(first.__dict__.values()))
        self.assertEqual(1, second.unchanged)
        self.assertEqual(1, third.updated)
        self.assertEqual("note.md", stored_id)
        self.assertEqual(1, fourth.deleted)
        self.assertEqual({}, self.repository.document_hashes(self.ingester.vault_id))

    def test_persists_citation_ready_chunks(self):
        note = self.vault / "research.md"
        note.write_text("# Research\nEvidence\n## Result\nFinding\n", encoding="utf-8")

        self.ingester.sync()
        document = self.repository.get_document_by_path(
            self.ingester.vault_id, "research.md"
        )

        self.assertIsNotNone(document)
        self.assertEqual([1, 3], [chunk.start_line for chunk in document.chunks])
        self.assertEqual([2, 4], [chunk.end_line for chunk in document.chunks])


if __name__ == "__main__":
    unittest.main()
