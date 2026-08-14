import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.application import ApplicationService
from personal_ai_agent.knowledge import KnowledgeSearchResult
from personal_ai_agent.web import ApplicationServiceWebAdapter, create_app


class SearchPort:
    def __init__(self):
        self.search_calls = []
        self.results = []

    def health(self):
        return {
            "status": "ok",
            "config_loaded": True,
            "storage_ready": True,
            "demo_mode": True,
        }

    def knowledge_status(self):
        return {"vault_id": "demo-vault", "fts5_available": True}

    def search(self, text, limit=10, path_prefix=None, tags=None):
        self.search_calls.append((text, limit, path_prefix, tags))
        return self.results


class WebSearchTests(unittest.TestCase):
    def setUp(self):
        self.port = SearchPort()
        self.app = create_app(
            application_port=self.port,
            test_config={"TESTING": True, "DEMO_MODE": True},
        )
        self.client = self.app.test_client()

    def test_initial_page_shows_form_without_running_search(self):
        response = self.client.get("/search")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("搜索个人知识库", page)
        self.assertIn('name="q"', page)
        self.assertEqual(self.port.search_calls, [])

    def test_blank_and_excessive_queries_show_safe_validation_error(self):
        blank = self.client.get("/search?q=%20%20")
        excessive = self.client.get("/search?q=" + "a" * 501)

        self.assertEqual(blank.status_code, 400)
        self.assertIn("请输入搜索内容", blank.get_data(as_text=True))
        self.assertEqual(excessive.status_code, 400)
        self.assertIn("不能超过 500", excessive.get_data(as_text=True))
        self.assertEqual(self.port.search_calls, [])

    def test_filters_and_limit_are_passed_to_application_port(self):
        response = self.client.get(
            "/search?q=agent&limit=7&path_prefix=Research&tag=ai&tag=course"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.port.search_calls,
            [("agent", 7, "Research", ["ai", "course"])],
        )

    def test_invalid_limit_is_rejected_before_port_call(self):
        for limit in ("invalid", "0", "51"):
            with self.subTest(limit=limit):
                response = self.client.get("/search?q=agent&limit=" + limit)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.port.search_calls, [])

    def test_results_show_citation_location_and_escape_note_html(self):
        self.port.results = [
            KnowledgeSearchResult(
                chunk_id="chunk-1",
                document_id="doc-1",
                vault_id="demo-vault",
                relative_path="Research/Agent.md",
                title="Agent <script>alert('title')</script>",
                heading="Safety",
                heading_path=["Agent", "Safety"],
                content="Evidence <script>alert('content')</script>",
                start_line=12,
                end_line=18,
                score=0.91,
                match_method="fts5",
                matched_terms=["agent"],
            )
        ]

        response = self.client.get("/search?q=agent")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Research/Agent.md", page)
        self.assertIn("第 12–18 行", page)
        self.assertIn("fts5", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert", page)

    def test_empty_result_is_explained_without_provider_requirement(self):
        response = self.client.get("/search?q=missing")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("没有找到匹配结果", page)
        self.assertEqual(self.port.search_calls[0][0], "missing")

    def test_real_vault_sync_and_keyword_search_work_without_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            vault.mkdir()
            (vault / "Architecture.md").write_text(
                "# Architecture\n\nCheckpoint enables durable recovery.\n",
                encoding="utf-8",
            )
            config_path = root / "agent.json"
            config_path.write_text(
                json.dumps(
                    {
                        "vault_path": "vault",
                        "data_directory": "runtime",
                    }
                ),
                encoding="utf-8",
            )
            service = ApplicationService.from_file(str(config_path))
            service.sync_vault()
            app = create_app(
                application_port=ApplicationServiceWebAdapter(service, True),
                test_config={"TESTING": True, "DEMO_MODE": True},
            )

            response = app.test_client().get("/search?q=durable+recovery")
            page = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("Architecture.md", page)
            self.assertIn("Checkpoint enables durable recovery", page)


if __name__ == "__main__":
    unittest.main()
