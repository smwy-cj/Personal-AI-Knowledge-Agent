"""Validate and deterministically split a private retrieval_dataset_v2 file."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from personal_ai_agent.evaluation import (  # noqa: E402
    RETRIEVAL_DATASET_V2,
    RetrievalEvaluationDataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and split a private retrieval_dataset_v2 file"
    )
    parser.add_argument("dataset")
    parser.add_argument("--tuning-output", required=True)
    parser.add_argument("--test-output", required=True)
    parser.add_argument("--test-ratio", type=float, default=0.2)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    source = Path(arguments.dataset).resolve()
    tuning_output = Path(arguments.tuning_output).resolve()
    test_output = Path(arguments.test_output).resolve()
    if len({source, tuning_output, test_output}) != 3:
        raise SystemExit("input, tuning output, and test output must be distinct files")
    if not 0 < arguments.test_ratio < 1:
        raise SystemExit("test ratio must be between 0 and 1")
    if not arguments.force and (tuning_output.exists() or test_output.exists()):
        raise SystemExit("output already exists; use --force to replace it")

    dataset = RetrievalEvaluationDataset.load(source)
    if dataset.schema != RETRIEVAL_DATASET_V2:
        raise SystemExit("dataset splitting requires retrieval_dataset_v2")
    document = json.loads(source.read_text(encoding="utf-8-sig"))
    cases = document["cases"]
    if len(cases) < 2:
        raise SystemExit("dataset splitting requires at least two cases")

    tuning_cases, test_cases = split_cases(
        dataset.name, cases, arguments.test_ratio
    )
    _write_dataset(
        tuning_output, _split_name(dataset.name, "-tuning"), tuning_cases, arguments.force
    )
    _write_dataset(
        test_output, _split_name(dataset.name, "-test"), test_cases, arguments.force
    )
    json.dump(
        {
            "schema": "retrieval_dataset_split_summary_v1",
            "source_dataset_name": dataset.name,
            "tuning_case_count": len(tuning_cases),
            "test_case_count": len(test_cases),
        },
        sys.stdout,
        ensure_ascii=False,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


def split_cases(
    dataset_name: str, cases: List[Dict[str, object]], test_ratio: float
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    test_count = max(1, min(len(cases) - 1, round(len(cases) * test_ratio)))
    groups: Dict[str, List[Dict[str, object]]] = {}
    for item in cases:
        groups.setdefault(str(item["query_type"]), []).append(item)
    for items in groups.values():
        items.sort(key=lambda item: _case_digest(dataset_name, item))

    eligible = sorted(
        (items for items in groups.values() if len(items) >= 2),
        key=lambda items: _case_digest(dataset_name, items[0]),
    )
    test_ids = {
        items[0]["case_id"]
        for items in eligible[: min(test_count, len(eligible))]
    }
    ranked_remaining = sorted(
        (item for item in cases if item["case_id"] not in test_ids),
        key=lambda item: _case_digest(dataset_name, item),
    )
    for item in ranked_remaining:
        if len(test_ids) >= test_count:
            break
        group = groups[str(item["query_type"])]
        selected_in_group = sum(member["case_id"] in test_ids for member in group)
        if selected_in_group < len(group) - 1:
            test_ids.add(item["case_id"])
    if len(test_ids) < test_count:
        for item in ranked_remaining:
            if len(test_ids) >= test_count:
                break
            test_ids.add(item["case_id"])
    tuning = [item for item in cases if item["case_id"] not in test_ids]
    test = [item for item in cases if item["case_id"] in test_ids]
    return tuning, test


def _case_digest(dataset_name: str, item: Dict[str, object]) -> bytes:
    return hashlib.sha256(
        (dataset_name + "\0" + str(item["case_id"])).encode("utf-8")
    ).digest()


def _write_dataset(
    path: Path, name: str, cases: List[Dict[str, object]], force: bool
) -> None:
    if path.exists() and not force:
        raise SystemExit("output already exists; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": RETRIEVAL_DATASET_V2,
        "name": name,
        "cases": cases,
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _split_name(name: str, suffix: str) -> str:
    return name[: 128 - len(suffix)] + suffix


if __name__ == "__main__":
    raise SystemExit(main())
