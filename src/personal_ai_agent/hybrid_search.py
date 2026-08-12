"""Rank-based fusion of lexical and semantic retrieval."""

from dataclasses import replace
from typing import Dict, List, Tuple

from .knowledge import (
    HybridSearchQuery,
    KeywordSearchQuery,
    KnowledgeSearchResult,
)
from .search import KeywordSearchEngine
from .vector import SQLiteVectorIndex


class HybridSearchEngine:
    def __init__(
        self,
        keyword_engine: KeywordSearchEngine,
        vector_index: SQLiteVectorIndex,
        candidate_multiplier: int = 3,
    ) -> None:
        if candidate_multiplier <= 0:
            raise ValueError("candidate_multiplier must be positive")
        self.keyword_engine = keyword_engine
        self.vector_index = vector_index
        self.candidate_multiplier = candidate_multiplier

    def search(self, query: HybridSearchQuery) -> List[KnowledgeSearchResult]:
        candidate_limit = min(100, query.limit * self.candidate_multiplier)
        base_query = KeywordSearchQuery(
            text=query.text,
            vault_id=query.vault_id,
            path_prefix=query.path_prefix,
            tags=query.tags,
            limit=candidate_limit,
        )
        keyword_results = (
            self.keyword_engine.search(base_query) if query.keyword_weight > 0 else []
        )
        vector_results = (
            self.vector_index.search(base_query) if query.vector_weight > 0 else []
        )
        return reciprocal_rank_fusion(
            keyword_results,
            vector_results,
            query.limit,
            query.rrf_k,
            query.keyword_weight,
            query.vector_weight,
        )


def reciprocal_rank_fusion(
    keyword_results: List[KnowledgeSearchResult],
    vector_results: List[KnowledgeSearchResult],
    limit: int,
    k: int = 60,
    keyword_weight: float = 1.0,
    vector_weight: float = 1.0,
) -> List[KnowledgeSearchResult]:
    scores: Dict[str, float] = {}
    exemplars: Dict[str, KnowledgeSearchResult] = {}
    sources: Dict[str, set] = {}
    for results, weight, source in (
        (keyword_results, keyword_weight, "keyword"),
        (vector_results, vector_weight, "vector"),
    ):
        for rank, result in enumerate(results, start=1):
            scores[result.chunk_id] = scores.get(result.chunk_id, 0.0) + weight / (k + rank)
            exemplars.setdefault(result.chunk_id, result)
            sources.setdefault(result.chunk_id, set()).add(source)

    ranked = sorted(
        scores,
        key=lambda chunk_id: (
            -scores[chunk_id],
            exemplars[chunk_id].relative_path,
            exemplars[chunk_id].start_line,
        ),
    )[:limit]
    if not ranked:
        return []
    maximum = scores[ranked[0]]
    keyword_by_id = {item.chunk_id: item for item in keyword_results}
    output = []
    for chunk_id in ranked:
        exemplar = exemplars[chunk_id]
        method = "hybrid" if len(sources[chunk_id]) == 2 else next(iter(sources[chunk_id]))
        matched_terms = keyword_by_id.get(chunk_id, exemplar).matched_terms
        output.append(
            replace(
                exemplar,
                score=scores[chunk_id] / maximum,
                match_method=method,
                matched_terms=matched_terms,
            )
        )
    return output
