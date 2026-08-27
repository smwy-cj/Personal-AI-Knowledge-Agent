"""SQLite metadata and chunk index for local knowledge documents."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Union

from .knowledge import KnowledgeChunk, KnowledgeDocument
from .models import utc_now


class SQLiteKnowledgeRepository:
    def __init__(self, database_path: Union[str, Path]) -> None:
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.fts5_available = self._initialize_fts5()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT PRIMARY KEY,
                    vault_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    modified_at_ns INTEGER NOT NULL,
                    frontmatter_json TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    UNIQUE(vault_id, relative_path)
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_documents_vault
                    ON knowledge_documents(vault_id, relative_path);

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    heading TEXT,
                    heading_path_json TEXT NOT NULL,
                    content TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
                    UNIQUE(document_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document
                    ON knowledge_chunks(document_id, ordinal);

                CREATE TABLE IF NOT EXISTS knowledge_tags (
                    document_id TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
                    PRIMARY KEY(document_id, tag)
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_tags_tag ON knowledge_tags(tag);

                CREATE TABLE IF NOT EXISTS knowledge_links (
                    document_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    FOREIGN KEY(document_id) REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
                    PRIMARY KEY(document_id, target)
                );
                CREATE INDEX IF NOT EXISTS idx_knowledge_links_target ON knowledge_links(target);
                """
            )

    def _initialize_fts5(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        document_id UNINDEXED,
                        title,
                        heading,
                        content,
                        tokenize = 'unicode61 remove_diacritics 2'
                    )
                    """
                )
                indexed_count = connection.execute(
                    "SELECT count(*) AS count FROM knowledge_chunks_fts"
                ).fetchone()["count"]
                chunk_count = connection.execute(
                    "SELECT count(*) AS count FROM knowledge_chunks"
                ).fetchone()["count"]
                if indexed_count != chunk_count:
                    self._rebuild_fts(connection)
            return True
        except sqlite3.OperationalError:
            return False

    @staticmethod
    def _rebuild_fts(connection: sqlite3.Connection) -> None:
        connection.execute("DELETE FROM knowledge_chunks_fts")
        connection.execute(
            """
            INSERT INTO knowledge_chunks_fts(chunk_id, document_id, title, heading, content)
            SELECT c.chunk_id, c.document_id, d.title, COALESCE(c.heading, ''), c.content
            FROM knowledge_chunks AS c
            JOIN knowledge_documents AS d ON d.document_id = c.document_id
            """
        )

    def document_hashes(self, vault_id: str) -> Dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT relative_path, content_hash FROM knowledge_documents WHERE vault_id = ?",
                (vault_id,),
            ).fetchall()
        return {row["relative_path"]: row["content_hash"] for row in rows}

    def upsert_document(self, document: KnowledgeDocument) -> None:
        indexed_at = utc_now()
        with self._connect() as connection:
            if self.fts5_available:
                connection.execute(
                    "DELETE FROM knowledge_chunks_fts WHERE document_id = ?",
                    (document.document_id,),
                )
            connection.execute(
                """
                INSERT INTO knowledge_documents(
                    document_id, vault_id, relative_path, title, content_hash,
                    size_bytes, modified_at_ns, frontmatter_json, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title = excluded.title,
                    content_hash = excluded.content_hash,
                    size_bytes = excluded.size_bytes,
                    modified_at_ns = excluded.modified_at_ns,
                    frontmatter_json = excluded.frontmatter_json,
                    indexed_at = excluded.indexed_at
                """,
                (
                    document.document_id,
                    document.vault_id,
                    document.relative_path,
                    document.title,
                    document.content_hash,
                    document.size_bytes,
                    document.modified_at_ns,
                    json.dumps(document.frontmatter, ensure_ascii=False, sort_keys=True),
                    indexed_at,
                ),
            )
            connection.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document.document_id,))
            connection.execute("DELETE FROM knowledge_tags WHERE document_id = ?", (document.document_id,))
            connection.execute("DELETE FROM knowledge_links WHERE document_id = ?", (document.document_id,))
            connection.executemany(
                """
                INSERT INTO knowledge_chunks(
                    chunk_id, document_id, ordinal, heading, heading_path_json,
                    content, start_line, end_line
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.ordinal,
                        chunk.heading,
                        json.dumps(chunk.heading_path, ensure_ascii=False),
                        chunk.content,
                        chunk.start_line,
                        chunk.end_line,
                    )
                    for chunk in document.chunks
                ],
            )
            connection.executemany(
                "INSERT INTO knowledge_tags(document_id, tag) VALUES (?, ?)",
                [(document.document_id, tag) for tag in document.tags],
            )
            connection.executemany(
                "INSERT INTO knowledge_links(document_id, target) VALUES (?, ?)",
                [(document.document_id, target) for target in document.wiki_links],
            )
            if self.fts5_available:
                connection.executemany(
                    """
                    INSERT INTO knowledge_chunks_fts(
                        chunk_id, document_id, title, heading, content
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            chunk.chunk_id,
                            document.document_id,
                            document.title,
                            chunk.heading or "",
                            chunk.content,
                        )
                        for chunk in document.chunks
                    ],
                )

    def delete_documents(self, vault_id: str, relative_paths: Iterable[str]) -> int:
        paths = list(relative_paths)
        if not paths:
            return 0
        deleted = 0
        with self._connect() as connection:
            for relative_path in paths:
                document_rows = connection.execute(
                    """
                    SELECT document_id FROM knowledge_documents
                    WHERE vault_id = ? AND relative_path = ?
                    """,
                    (vault_id, relative_path),
                ).fetchall()
                if self.fts5_available:
                    for row in document_rows:
                        connection.execute(
                            "DELETE FROM knowledge_chunks_fts WHERE document_id = ?",
                            (row["document_id"],),
                        )
                cursor = connection.execute(
                    "DELETE FROM knowledge_documents WHERE vault_id = ? AND relative_path = ?",
                    (vault_id, relative_path),
                )
                deleted += cursor.rowcount
        return deleted

    def get_document(self, document_id: str) -> Optional[KnowledgeDocument]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_documents WHERE document_id = ?", (document_id,)
            ).fetchone()
            if row is None:
                return None
            chunk_rows = connection.execute(
                "SELECT * FROM knowledge_chunks WHERE document_id = ? ORDER BY ordinal",
                (document_id,),
            ).fetchall()
            tags = connection.execute(
                "SELECT tag FROM knowledge_tags WHERE document_id = ? ORDER BY tag",
                (document_id,),
            ).fetchall()
            links = connection.execute(
                "SELECT target FROM knowledge_links WHERE document_id = ? ORDER BY target",
                (document_id,),
            ).fetchall()
        chunks: List[KnowledgeChunk] = [
            KnowledgeChunk(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                ordinal=item["ordinal"],
                heading=item["heading"],
                heading_path=json.loads(item["heading_path_json"]),
                content=item["content"],
                start_line=item["start_line"],
                end_line=item["end_line"],
            )
            for item in chunk_rows
        ]
        return KnowledgeDocument(
            document_id=row["document_id"],
            vault_id=row["vault_id"],
            relative_path=row["relative_path"],
            title=row["title"],
            content_hash=row["content_hash"],
            size_bytes=row["size_bytes"],
            modified_at_ns=row["modified_at_ns"],
            frontmatter=json.loads(row["frontmatter_json"]),
            tags=[item["tag"] for item in tags],
            wiki_links=[item["target"] for item in links],
            chunks=chunks,
        )

    def get_document_by_path(
        self, vault_id: str, relative_path: str
    ) -> Optional[KnowledgeDocument]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id FROM knowledge_documents
                WHERE vault_id = ? AND relative_path = ?
                """,
                (vault_id, relative_path),
            ).fetchone()
        if row is None:
            return None
        return self.get_document(row["document_id"])

    def get_chunk_reference(self, chunk_id: str) -> Optional[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT
                    c.chunk_id, c.document_id, d.vault_id, d.relative_path,
                    d.title, c.heading, c.heading_path_json, c.content,
                    c.start_line, c.end_line
                FROM knowledge_chunks c
                JOIN knowledge_documents d ON d.document_id = c.document_id
                WHERE c.chunk_id = ?
                """,
                (chunk_id,),
            ).fetchone()

    def keyword_candidates_fts(
        self,
        match_expression: str,
        vault_id: Optional[str],
        path_prefix: Optional[str],
        tags: Sequence[str],
        limit: int,
    ) -> List[sqlite3.Row]:
        if not self.fts5_available:
            return []
        where = ["knowledge_chunks_fts MATCH ?"]
        parameters: List[object] = [match_expression]
        if vault_id:
            where.append("d.vault_id = ?")
            parameters.append(vault_id)
        if path_prefix:
            where.append("d.relative_path LIKE ? ESCAPE '\\'")
            parameters.append(_escape_like(_normalize_path_prefix(path_prefix)) + "%")
        for tag in tags:
            where.append(
                "EXISTS (SELECT 1 FROM knowledge_tags t WHERE t.document_id = d.document_id AND t.tag = ?)"
            )
            parameters.append(tag)
        parameters.append(limit)
        query = """
            SELECT
                c.chunk_id, c.document_id, d.vault_id, d.relative_path, d.title,
                c.heading, c.heading_path_json, c.content, c.start_line, c.end_line,
                bm25(knowledge_chunks_fts, 0.0, 0.0, 2.0, 1.5, 1.0) AS raw_rank
            FROM knowledge_chunks_fts
            JOIN knowledge_chunks c ON c.chunk_id = knowledge_chunks_fts.chunk_id
            JOIN knowledge_documents d ON d.document_id = c.document_id
            WHERE %s
            ORDER BY raw_rank ASC, d.relative_path ASC, c.ordinal ASC
            LIMIT ?
        """ % " AND ".join(where)
        with self._connect() as connection:
            return connection.execute(query, parameters).fetchall()

    def keyword_candidates_fallback(
        self,
        vault_id: Optional[str],
        path_prefix: Optional[str],
        tags: Sequence[str],
    ) -> List[sqlite3.Row]:
        where = ["1 = 1"]
        parameters: List[object] = []
        if vault_id:
            where.append("d.vault_id = ?")
            parameters.append(vault_id)
        if path_prefix:
            where.append("d.relative_path LIKE ? ESCAPE '\\'")
            parameters.append(_escape_like(_normalize_path_prefix(path_prefix)) + "%")
        for tag in tags:
            where.append(
                "EXISTS (SELECT 1 FROM knowledge_tags t WHERE t.document_id = d.document_id AND t.tag = ?)"
            )
            parameters.append(tag)
        query = """
            SELECT
                c.chunk_id, c.document_id, d.vault_id, d.relative_path, d.title,
                c.heading, c.heading_path_json, c.content, c.start_line, c.end_line,
                c.ordinal, d.frontmatter_json AS metadata_text,
                COALESCE(
                    (SELECT group_concat(t.tag, ' ')
                     FROM knowledge_tags t WHERE t.document_id = d.document_id),
                    ''
                ) AS tags_text,
                COALESCE(
                    (SELECT group_concat(l.target, ' ')
                     FROM knowledge_links l WHERE l.document_id = d.document_id),
                    ''
                ) AS links_text
            FROM knowledge_chunks c
            JOIN knowledge_documents d ON d.document_id = c.document_id
            WHERE %s
            ORDER BY d.relative_path ASC, c.ordinal ASC
        """ % " AND ".join(where)
        with self._connect() as connection:
            return connection.execute(query, parameters).fetchall()


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _normalize_path_prefix(value: str) -> str:
    normalized = value.strip().replace("\\", "/").lstrip("/")
    if not normalized:
        raise ValueError("path prefix must not resolve to the vault root")
    return normalized
