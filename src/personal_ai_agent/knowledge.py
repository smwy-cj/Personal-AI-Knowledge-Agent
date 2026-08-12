"""Contracts for Obsidian documents and their citation-ready chunks."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    ordinal: int
    heading: Optional[str]
    heading_path: List[str]
    content: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    vault_id: str
    relative_path: str
    title: str
    content_hash: str
    size_bytes: int
    modified_at_ns: int
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    wiki_links: List[str] = field(default_factory=list)
    chunks: List[KnowledgeChunk] = field(default_factory=list)


@dataclass(frozen=True)
class SyncResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    failed: int = 0


@dataclass(frozen=True)
class KnowledgeSearchResult:
    chunk_id: str
    document_id: str
    vault_id: str
    relative_path: str
    title: str
    heading: Optional[str]
    heading_path: List[str]
    content: str
    start_line: int
    end_line: int
    score: float
    match_method: str
    matched_terms: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class KeywordSearchQuery:
    text: str
    vault_id: Optional[str] = None
    path_prefix: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    limit: int = 10

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("search text must be non-empty")
        if self.limit <= 0 or self.limit > 100:
            raise ValueError("search limit must be between 1 and 100")


@dataclass(frozen=True)
class VectorSyncResult:
    embedded: int = 0
    unchanged: int = 0
    deleted: int = 0


@dataclass(frozen=True)
class HybridSearchQuery:
    text: str
    vault_id: Optional[str] = None
    path_prefix: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    limit: int = 10
    keyword_weight: float = 1.0
    vector_weight: float = 1.0
    rrf_k: int = 60

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("search text must be non-empty")
        if self.limit <= 0 or self.limit > 100:
            raise ValueError("search limit must be between 1 and 100")
        if self.keyword_weight < 0 or self.vector_weight < 0:
            raise ValueError("search weights must be non-negative")
        if self.keyword_weight == 0 and self.vector_weight == 0:
            raise ValueError("at least one search weight must be positive")
        if self.rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
