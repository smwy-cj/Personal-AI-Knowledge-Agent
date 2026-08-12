"""Citation-ready keyword retrieval with FTS5 and deterministic fallback."""

import json
import re
import sqlite3
from typing import List, Sequence

from .knowledge import KeywordSearchQuery, KnowledgeSearchResult
from .knowledge_repository import SQLiteKnowledgeRepository


TERM_RE = re.compile(r"[^\W_]+(?:[-/][^\W_]+)*", re.UNICODE)


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


class KeywordSearchEngine:
    def __init__(
        self, repository: SQLiteKnowledgeRepository, prefer_fts5: bool = True
    ) -> None:
        self.repository = repository
        self.prefer_fts5 = prefer_fts5

    def search(self, query: KeywordSearchQuery) -> List[KnowledgeSearchResult]:
        terms = query_terms(query.text)
        tags = [tag.strip().lstrip("#") for tag in query.tags if tag.strip()]
        if self.prefer_fts5 and self.repository.fts5_available:
            try:
                rows = self.repository.keyword_candidates_fts(
                    fts5_expression(terms),
                    query.vault_id,
                    query.path_prefix,
                    tags,
                    query.limit,
                )
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
            if not all(term in "%s\n%s\n%s" % (title, heading, content) for term in terms):
                continue
            raw_score = sum(
                title.count(term) * 4 + heading.count(term) * 3 + content.count(term)
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


def _result_from_row(
    row: sqlite3.Row, score: float, match_method: str, terms: Sequence[str]
) -> KnowledgeSearchResult:
    searchable = "%s\n%s\n%s" % (row["title"], row["heading"] or "", row["content"])
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
