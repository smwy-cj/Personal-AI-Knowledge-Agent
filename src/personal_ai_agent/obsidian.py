"""Dependency-free Obsidian Markdown parsing and incremental ingestion."""

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from .knowledge import KnowledgeChunk, KnowledgeDocument, SyncResult


HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
WIKI_LINK_RE = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TAG_RE = re.compile(r"(?<![\w/#])#([\w\-]+(?:/[\w\-]+)*)", re.UNICODE)
FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


class VaultPathError(ValueError):
    pass


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
    return "%s_%s" % (prefix, digest)


def vault_id_for(root: Path) -> str:
    return _stable_id("vault", root.resolve().as_posix().casefold())


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item) for item in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lowered = value.casefold()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "~"}:
        return None
    return value


def parse_frontmatter(lines: Sequence[str]) -> Tuple[Dict[str, Any], int]:
    """Parse the common flat subset of YAML used by Obsidian properties.

    Returns metadata and the zero-based index where Markdown content starts.
    Unsupported nested YAML remains a string instead of being guessed.
    """

    if not lines or lines[0].strip() != "---":
        return {}, 0
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None:
        return {}, 0

    metadata: Dict[str, Any] = {}
    current_list_key: Optional[str] = None
    for raw_line in lines[1:end]:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_list_key:
            current_value = metadata.setdefault(current_list_key, [])
            if isinstance(current_value, list):
                current_value.append(_parse_scalar(stripped[2:]))
            continue
        if ":" not in raw_line:
            current_list_key = None
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        parsed = _parse_scalar(value)
        metadata[key] = parsed
        current_list_key = key if parsed == "" else None
        if current_list_key:
            metadata[key] = []
    return metadata, end + 1


def _visible_markdown(lines: Sequence[str], content_start: int) -> List[Tuple[int, str]]:
    visible: List[Tuple[int, str]] = []
    fence_character: Optional[str] = None
    fence_length = 0
    for index in range(content_start, len(lines)):
        line = lines[index]
        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is None:
            visible.append((index, line))
    return visible


def _frontmatter_tags(frontmatter: Dict[str, Any]) -> Set[str]:
    raw = frontmatter.get("tags", frontmatter.get("tag", []))
    values = raw if isinstance(raw, list) else [raw]
    return {str(value).strip().lstrip("#") for value in values if str(value).strip()}


def parse_obsidian_markdown(
    vault_id: str,
    relative_path: str,
    content: str,
    content_hash: str,
    size_bytes: int,
    modified_at_ns: int,
) -> KnowledgeDocument:
    lines = content.splitlines()
    frontmatter, content_start = parse_frontmatter(lines)
    visible = _visible_markdown(lines, content_start)
    document_id = _stable_id("doc", "%s:%s" % (vault_id, relative_path.casefold()))

    headings: List[Tuple[int, int, str, List[str]]] = []
    hierarchy: List[str] = []
    for line_index, line in visible:
        match = HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        heading = match.group(2).strip()
        hierarchy = hierarchy[: level - 1]
        hierarchy.append(heading)
        headings.append((line_index, level, heading, list(hierarchy)))

    chunks: List[KnowledgeChunk] = []
    boundaries: List[Tuple[int, Optional[str], List[str]]] = []
    if content_start < len(lines) and (not headings or content_start < headings[0][0]):
        boundaries.append((content_start, None, []))
    boundaries.extend((line, heading, path) for line, _, heading, path in headings)
    for ordinal, (start, heading, heading_path) in enumerate(boundaries):
        end = boundaries[ordinal + 1][0] - 1 if ordinal + 1 < len(boundaries) else len(lines) - 1
        chunk_content = "\n".join(lines[start : end + 1]).strip()
        if not chunk_content:
            continue
        chunks.append(
            KnowledgeChunk(
                chunk_id=_stable_id("chunk", "%s:%s" % (document_id, ordinal)),
                document_id=document_id,
                ordinal=ordinal,
                heading=heading,
                heading_path=heading_path,
                content=chunk_content,
                start_line=start + 1,
                end_line=end + 1,
            )
        )

    visible_text = "\n".join(line for _, line in visible)
    wiki_links = sorted({match.strip() for match in WIKI_LINK_RE.findall(visible_text) if match.strip()})
    tags = sorted(_frontmatter_tags(frontmatter) | set(TAG_RE.findall(visible_text)))
    first_heading = headings[0][2] if headings else None
    title = str(frontmatter.get("title") or first_heading or Path(relative_path).stem)
    return KnowledgeDocument(
        document_id=document_id,
        vault_id=vault_id,
        relative_path=relative_path,
        title=title,
        content_hash=content_hash,
        size_bytes=size_bytes,
        modified_at_ns=modified_at_ns,
        frontmatter=frontmatter,
        tags=tags,
        wiki_links=wiki_links,
        chunks=chunks,
    )


class ObsidianVaultIngester:
    def __init__(self, vault_root: Union[str, Path], repository: Any) -> None:
        self.vault_root = Path(vault_root).resolve()
        if not self.vault_root.is_dir():
            raise VaultPathError("vault root must be an existing directory")
        self.vault_id = vault_id_for(self.vault_root)
        self.repository = repository

    def sync(self) -> SyncResult:
        known = self.repository.document_hashes(self.vault_id)
        seen: Set[str] = set()
        added = updated = unchanged = failed = 0

        for path in self._markdown_files():
            relative_path = path.relative_to(self.vault_root).as_posix()
            seen.add(relative_path)
            try:
                raw = path.read_bytes()
                content_hash = hashlib.sha256(raw).hexdigest()
                if known.get(relative_path) == content_hash:
                    unchanged += 1
                    continue
                stat = path.stat()
                document = parse_obsidian_markdown(
                    vault_id=self.vault_id,
                    relative_path=relative_path,
                    content=raw.decode("utf-8-sig"),
                    content_hash=content_hash,
                    size_bytes=len(raw),
                    modified_at_ns=stat.st_mtime_ns,
                )
                self.repository.upsert_document(document)
                if relative_path in known:
                    updated += 1
                else:
                    added += 1
            except (OSError, UnicodeError, ValueError):
                failed += 1

        deleted_paths = set(known) - seen
        deleted = self.repository.delete_documents(self.vault_id, deleted_paths)
        return SyncResult(added, updated, unchanged, deleted, failed)

    def _markdown_files(self) -> Iterable[Path]:
        for path in sorted(self.vault_root.rglob("*.md")):
            if ".obsidian" in path.relative_to(self.vault_root).parts:
                continue
            resolved = path.resolve()
            try:
                resolved.relative_to(self.vault_root)
            except ValueError as exc:
                raise VaultPathError("markdown path escapes vault: %s" % path) from exc
            if resolved.is_file():
                yield resolved
