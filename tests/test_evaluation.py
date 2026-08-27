import json
import tempfile
import unittest
from pathlib import Path

from personal_ai_agent.evaluation import (
    ExpectedRetrievalChunk,
    RetrievalEvaluationDataset,
    evaluate_retrieval,
)
from personal_ai_agent.knowledge import KnowledgeSearchResult


def result(path, heading=None):
    return KnowledgeSearchResult(
        chunk_id=path,
        document_id=path,
        vault_id="vault",
        relative_path=path,
        title=path,
        heading=heading,
        heading_path=[heading] if heading else [],
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
        self.assertNotIn("no_answer_false_positive_rate", serialized)
        self.assertNotIn("query_type", serialized)

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

    def test_v2_supports_metadata_chunks_and_no_answer_metrics(self):
        dataset = RetrievalEvaluationDataset(
            "v2-baseline",
            [
                self.case(
                    "answer",
                    "private bilingual query",
                    ["a.md"],
                    language="zh-CN",
                    query_type="factual",
                    expected_chunks=[ExpectedRetrievalChunk("a.md", "Target")],
                ),
                self.case(
                    "no-answer",
                    "private absent query",
                    [],
                    language="en",
                    query_type="no_answer",
                    expects_answer=False,
                ),
            ],
            "retrieval_dataset_v2",
        )

        answer = result("a.md", "Target")
        report = evaluate_retrieval(
            dataset,
            lambda query, limit: [answer] if "bilingual" in query else [result("x.md")],
            "keyword",
            3,
        )

        self.assertEqual(report.schema, "retrieval_eval_report_v2")
        self.assertEqual(report.answer_case_count, 1)
        self.assertEqual(report.no_answer_case_count, 1)
        self.assertEqual(report.chunk_recall_at_k, 1.0)
        self.assertEqual(report.no_answer_false_positive_rate, 1.0)
        serialized = json.dumps(report.as_dict())
        self.assertNotIn("private", serialized)
        self.assertNotIn("a.md", serialized)
        self.assertNotIn("Target", serialized)

    def test_v2_loader_rejects_inconsistent_no_answer_cases(self):
        document = {
            "schema": "retrieval_dataset_v2",
            "name": "invalid-v2",
            "cases": [
                {
                    "case_id": "bad",
                    "query": "must remain private",
                    "language": "en",
                    "query_type": "no_answer",
                    "expects_answer": False,
                    "expected_paths": ["should-not-exist.md"],
                    "expected_chunks": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "eval-v2.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ValueError):
                RetrievalEvaluationDataset.load(path)

    @staticmethod
    def case(
        case_id,
        query,
        expected_paths,
        language="und",
        query_type="conceptual",
        expects_answer=True,
        expected_chunks=None,
    ):
        from personal_ai_agent.evaluation import RetrievalEvaluationCase

        return RetrievalEvaluationCase(
            case_id,
            query,
            expected_paths,
            language,
            query_type,
            expects_answer,
            expected_chunks or [],
        )


if __name__ == "__main__":
    unittest.main()
