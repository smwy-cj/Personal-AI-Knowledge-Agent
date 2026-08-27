"""Citation-ready keyword retrieval with FTS5 and deterministic fallback."""

import json
import math
import re
import sqlite3
from typing import Dict, List, Sequence, Tuple

from .knowledge import KeywordSearchQuery, KnowledgeSearchResult
from .knowledge_repository import SQLiteKnowledgeRepository


TERM_RE = re.compile(r"[^\W_]+(?:[-/][^\W_]+)*", re.UNICODE)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
CJK_SEQUENCE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
LATIN_TERM_RE = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)*")

# These are question scaffolding rather than useful retrieval anchors.  The
# list intentionally stays small: domain words such as "定义", "区别" and
# "作用" remain searchable.
CJK_STOP_BIGRAMS = {
    "为何",
    "为什",
    "什么",
    "么说",
    "怎样",
    "怎么",
    "如何",
    "哪些",
    "哪个",
    "哪篇",
    "哪里",
    "是否",
    "能否",
    "请问",
    "帮我",
    "给我",
    "找到",
    "查找",
    "打开",
    "讲解",
    "说明",
    "介绍",
    "一下",
    "目前",
    "分别",
    "以及",
    "及其",
    "其中",
    "中的",
    "有关",
    "关于",
    "对于",
}

CJK_MIN_TERM_COVERAGE = 0.18
CJK_METADATA_INTENT_TERMS = {"标签", "索引"}
MAX_CJK_CHUNKS_PER_DOCUMENT = 2


def query_terms(text: str) -> List[str]:
    terms: List[str] = []
    seen = set()
    for match in TERM_RE.findall(text.casefold()):
        if match not in seen:
            terms.append(match)
            seen.add(match)
    if not terms:
        raise ValueError("search text contains no searchable terms")
    return terms


def fts5_expression(terms: Sequence[str]) -> str:
    return " AND ".join('"%s"' % term.replace('"', '""') for term in terms)


def _cjk_query_terms(text: str) -> Tuple[List[str], List[str]]:
    """Return searchable terms and mandatory Latin anchors for a CJK query.

    SQLite's default ``unicode61`` tokenizer treats a continuous Chinese
    clause as one token.  Overlapping bigrams provide a dependency-free,
    deterministic lexical fallback while Latin identifiers such as
    ``Q-learning`` remain exact anchors.
    """

    normalized = text.casefold()
    latin_terms = _deduplicate(LATIN_TERM_RE.findall(normalized))
    cjk_terms: List[str] = []
    for sequence in CJK_SEQUENCE_RE.findall(normalized):
        if len(sequence) == 1:
            continue
        for index in range(len(sequence) - 1):
            term = sequence[index : index + 2]
            if term not in CJK_STOP_BIGRAMS:
                cjk_terms.append(term)
    terms = latin_terms + _deduplicate(cjk_terms)
    if not terms:
        # A one-character CJK query is uncommon, but retaining the original
        # parser keeps the public error behavior and makes it searchable.
        terms = query_terms(text)
    return terms, latin_terms


def _deduplicate(values: Sequence[str]) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            output.append(value)
            seen.add(value)
    return output


class KeywordSearchEngine:
    def __init__(
        self, repository: SQLiteKnowledgeRepository, prefer_fts5: bool = True
    ) -> None:
        self.repository = repository
        self.prefer_fts5 = prefer_fts5

    def search(self, query: KeywordSearchQuery) -> List[KnowledgeSearchResult]:
        tags = [tag.strip().lstrip("#") for tag in query.tags if tag.strip()]
        if CJK_RE.search(query.text):
            terms, latin_terms = _cjk_query_terms(query.text)
            rows = self.repository.keyword_candidates_fallback(
                query.vault_id, query.path_prefix, tags
            )
            return self._from_cjk_fallback(rows, terms, latin_terms, query.limit)

        terms = query_terms(query.text)
        if self.prefer_fts5 and self.repository.fts5_available:
            try:
                rows = self.repository.keyword_candidates_fts(
                    fts5_expression(terms),
                    query.vault_id,
                    query.path_prefix,
                    tags,
                    query.limit,
                )
                if rows:
                    return self._from_fts(rows, terms)
            except sqlite3.OperationalError:
                pass
        rows = self.repository.keyword_candidates_fallback(
            query.vault_id, query.path_prefix, tags
        )
        return self._from_fallback(rows, terms, query.limit)

    @staticmethod
    def _from_fts(rows: Sequence[sqlite3.Row], terms: Sequence[str]) -> List[KnowledgeSearchResult]:
        results: List[KnowledgeSearchResult] = []
        for index, row in enumerate(rows):
            results.append(_result_from_row(row, 1.0 / (index + 1), "fts5", terms))
        return results

    @staticmethod
    def _from_fallback(
        rows: Sequence[sqlite3.Row], terms: Sequence[str], limit: int
    ) -> List[KnowledgeSearchResult]:
        scored = []
        for row in rows:
            title = row["title"].casefold()
            heading = (row["heading"] or "").casefold()
            content = row["content"].casefold()
            metadata = _row_metadata(row)
            if not all(
                term in "%s\n%s\n%s\n%s" % (title, heading, content, metadata)
                for term in terms
            ):
                continue
            raw_score = sum(
                title.count(term) * 4
                + heading.count(term) * 3
                + content.count(term)
                + metadata.count(term) * 2
                for term in terms
            )
            scored.append((raw_score, row))
        scored.sort(key=lambda item: (-item[0], item[1]["relative_path"], item[1]["ordinal"]))
        if not scored:
            return []
        maximum = scored[0][0]
        return [
            _result_from_row(row, raw_score / maximum, "deterministic", terms)
            for raw_score, row in scored[:limit]
        ]

    @staticmethod
    def _from_cjk_fallback(
        rows: Sequence[sqlite3.Row],
        terms: Sequence[str],
        latin_terms: Sequence[str],
        limit: int,
    ) -> List[KnowledgeSearchResult]:
        searchable_rows = [
            (
                row,
                row["title"].casefold(),
                (row["heading"] or "").casefold(),
                row["content"].casefold(),
                _row_metadata(row),
            )
            for row in rows
        ]
        document_frequency: Dict[str, int] = {
            term: sum(
                term in "%s\n%s\n%s\n%s" % (title, heading, content, metadata)
                for _, title, heading, content, metadata in searchable_rows
            )
            for term in terms
        }
        row_count = len(searchable_rows)
        term_weights = {
            term: math.log((row_count + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }
        latin_set = set(latin_terms)
        cjk_terms = [term for term in terms if term not in latin_set]
        minimum_cjk_matches = min(2, len(cjk_terms))
        latin_terms_are_sufficient = len(latin_terms) >= 2 or bool(
            CJK_METADATA_INTENT_TERMS.intersection(cjk_terms)
        )

        scored = []
        for row, title, heading, content, metadata in searchable_rows:
            searchable = "%s\n%s\n%s\n%s" % (title, heading, content, metadata)
            matched = [term for term in terms if term in searchable]
            matched_set = set(matched)
            if any(term not in matched_set for term in latin_terms):
                continue
            matched_cjk = sum(term in matched_set for term in cjk_terms)
            if cjk_terms and not latin_terms_are_sufficient:
                required_matches = 1 if latin_terms else minimum_cjk_matches
                if matched_cjk < required_matches:
                    continue
                if not latin_terms and matched_cjk / len(cjk_terms) < CJK_MIN_TERM_COVERAGE:
                    continue
            if not matched:
                continue

            raw_score = 0.0
            for term in matched:
                field_score = (
                    (6 if term in title else 0)
                    + (4 if term in heading else 0)
                    + min(content.count(term), 2)
                    + (3 if term in metadata else 0)
                )
                raw_score += term_weights[term] * field_score
            scored.append((raw_score, row))

        scored.sort(
            key=lambda item: (
                -item[0],
                item[1]["relative_path"],
                item[1]["ordinal"],
            )
        )
        if not scored:
            return []
        maximum = scored[0][0]
        diversified = []
        document_counts: Dict[str, int] = {}
        for raw_score, row in scored:
            document_id = row["document_id"]
            if document_counts.get(document_id, 0) >= MAX_CJK_CHUNKS_PER_DOCUMENT:
                continue
            diversified.append((raw_score, row))
            document_counts[document_id] = document_counts.get(document_id, 0) + 1
            if len(diversified) >= limit:
                break
        return [
            _result_from_row(row, raw_score / maximum, "deterministic", terms)
            for raw_score, row in diversified
        ]


def _result_from_row(
    row: sqlite3.Row, score: float, match_method: str, terms: Sequence[str]
) -> KnowledgeSearchResult:
    searchable = "%s\n%s\n%s\n%s" % (
        row["title"],
        row["heading"] or "",
        row["content"],
        _row_metadata(row),
    )
    matched = [term for term in terms if term in searchable.casefold()]
    return KnowledgeSearchResult(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        vault_id=row["vault_id"],
        relative_path=row["relative_path"],
        title=row["title"],
        heading=row["heading"],
        heading_path=json.loads(row["heading_path_json"]),
        content=row["content"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        score=score,
        match_method=match_method,
        matched_terms=matched,
    )


def _row_metadata(row: sqlite3.Row) -> str:
    keys = set(row.keys())
    values = [str(row["relative_path"])] if "relative_path" in keys else []
    for key in ("metadata_text", "tags_text", "links_text"):
        if key in keys and row[key]:
            values.append(str(row[key]))
    return "\n".join(values).casefold()
