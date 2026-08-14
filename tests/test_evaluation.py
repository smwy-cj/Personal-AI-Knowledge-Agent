import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.evaluation import (
    RetrievalEvaluationDataset,
    evaluate_retrieval,
)
from personal_ai_agent.knowledge import KnowledgeSearchResult


def result(path):
    return KnowledgeSearchResult(
        chunk_id=path,
        document_id=path,
        vault_id="vault",
        relative_path=path,
        title=path,
        heading=None,
        heading_path=[],
        content="not included in report",
        start_line=1,
        end_line=1,
        score=1.0,
        match_method="test",
    )


class RetrievalEvaluationTests(unittest.TestCase):
    def test_metrics_are_deterministic_and_report_omits_queries(self):
        dataset = RetrievalEvaluationDataset(
            "baseline",
            [
                self.case("c1", "private query one", ["a.md", "b.md"]),
                self.case("c2", "private query two", ["z.md"]),
            ],
        )

        report = evaluate_retrieval(
            dataset,
            lambda query, limit: (
                [result("x.md"), result("b.md")] if query.endswith("one") else []
            ),
            "keyword",
            2,
        )

        self.assertEqual(report.recall_at_k, 0.25)
        self.assertEqual(report.hit_rate_at_k, 0.5)
        self.assertEqual(report.mrr_at_k, 0.25)
        serialized = json.dumps(report.as_dict())
        self.assertNotIn("private query", serialized)
        self.assertNotIn("not included in report", serialized)

    def test_dataset_loader_enforces_schema_and_unique_case_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "eval.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": "retrieval_eval_v1",
                        "name": "test",
                        "cases": [
                            {
                                "case_id": "same",
                                "query": "one",
                                "expected_paths": ["a.md"],
                            },
                            {
                                "case_id": "same",
                                "query": "two",
                                "expected_paths": ["b.md"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                RetrievalEvaluationDataset.load(path)

    @staticmethod
    def case(case_id, query, expected_paths):
        from personal_ai_agent.evaluation import RetrievalEvaluationCase

        return RetrievalEvaluationCase(case_id, query, expected_paths)


if __name__ == "__main__":
    unittest.main()
