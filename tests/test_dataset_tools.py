import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.prepare_retrieval_dataset import main, split_cases


class RetrievalDatasetToolTests(unittest.TestCase):
    def test_split_is_deterministic_valid_and_does_not_echo_queries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "private.json"
            cases = [
                {
                    "case_id": f"case-{index}",
                    "query": f"private query {index}",
                    "language": "en",
                    "query_type": "factual",
                    "expects_answer": True,
                    "expected_paths": [f"note-{index}.md"],
                    "expected_chunks": [],
                }
                for index in range(5)
            ]
            source.write_text(
                json.dumps(
                    {
                        "schema": "retrieval_dataset_v2",
                        "name": "private-local-eval",
                        "cases": cases,
                    }
                ),
                encoding="utf-8",
            )
            tuning = root / "tuning.json"
            test = root / "test.json"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(
                    [
                        str(source),
                        "--tuning-output",
                        str(tuning),
                        "--test-output",
                        str(test),
                        "--test-ratio",
                        "0.4",
                    ]
                )

            self.assertEqual(code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["tuning_case_count"], 3)
            self.assertEqual(summary["test_case_count"], 2)
            self.assertNotIn("private query", stdout.getvalue())
            tuning_document = json.loads(tuning.read_text(encoding="utf-8"))
            test_document = json.loads(test.read_text(encoding="utf-8"))
            split_ids = {
                item["case_id"]
                for item in tuning_document["cases"] + test_document["cases"]
            }
            self.assertEqual(split_ids, {item["case_id"] for item in cases})
            self.assertTrue(
                {item["case_id"] for item in tuning_document["cases"]}.isdisjoint(
                    {item["case_id"] for item in test_document["cases"]}
                )
            )
            with self.assertRaises(SystemExit):
                main(
                    [
                        str(source),
                        "--tuning-output",
                        str(tuning),
                        "--test-output",
                        str(test),
                    ]
                )

    def test_split_refuses_v1_overwrite_and_invalid_ratio(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "v1.json"
            source.write_text(
                json.dumps(
                    {
                        "schema": "retrieval_eval_v1",
                        "name": "legacy",
                        "cases": [
                            {
                                "case_id": "one",
                                "query": "private",
                                "expected_paths": ["a.md"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            arguments = [
                str(source),
                "--tuning-output",
                str(root / "tuning.json"),
                "--test-output",
                str(root / "test.json"),
            ]
            with self.assertRaises(SystemExit):
                main(arguments)
            with self.assertRaises(SystemExit):
                main(arguments + ["--test-ratio", "1"])

    def test_split_stratifies_query_types_when_each_has_two_cases(self):
        query_types = [
            "factual",
            "conceptual",
            "navigational",
            "tag",
            "link",
            "synonym",
            "no_answer",
        ]
        cases = [
            {"case_id": f"{query_type}-{index}", "query_type": query_type}
            for query_type in query_types
            for index in range(2)
        ]

        tuning, test = split_cases("stratified", cases, 0.5)

        self.assertEqual(len(tuning), 7)
        self.assertEqual(len(test), 7)
        self.assertEqual({item["query_type"] for item in tuning}, set(query_types))
        self.assertEqual({item["query_type"] for item in test}, set(query_types))


if __name__ == "__main__":
    unittest.main()
