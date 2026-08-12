"""Deterministic research evidence workflow and citation verifier."""

import hashlib
from typing import Any, Dict, List, Optional, Protocol, Sequence

from .knowledge import HybridSearchQuery, KnowledgeSearchResult
from .knowledge_repository import SQLiteKnowledgeRepository
from .models import (
    AgentTaskState,
    Artifact,
    ErrorRecord,
    Evidence,
    PlanStep,
    StepResult,
)


RESEARCH_ARTIFACT_SCHEMA = "research_evidence_pack_v1"


class SearchEngine(Protocol):
    def search(self, query: HybridSearchQuery) -> Sequence[KnowledgeSearchResult]:
        ...


class ResearchWorkflow:
    """Retrieves citation-ready evidence without inventing model conclusions."""

    def __init__(self, search_engine: SearchEngine) -> None:
        self.search_engine = search_engine

    def __call__(self, state: AgentTaskState, step: PlanStep) -> StepResult:
        query_text = str(step.inputs.get("query") or state.user_goal).strip()
        if not query_text:
            raise ValueError("research query must be non-empty")
        limit = _integer_input(step.inputs, "limit", 8, minimum=1, maximum=50)
        query = HybridSearchQuery(
            text=query_text,
            vault_id=_optional_string(step.inputs.get("vault_id")),
            path_prefix=_optional_string(step.inputs.get("path_prefix")),
            tags=_string_list(step.inputs.get("tags", []), "tags"),
            limit=limit,
            keyword_weight=_float_input(step.inputs, "keyword_weight", 1.0),
            vector_weight=_float_input(step.inputs, "vector_weight", 1.0),
        )
        results = list(self.search_engine.search(query))
        if not results:
            raise ValueError("research workflow found no supporting evidence")

        evidence = [_evidence_from_result(item) for item in results]
        citations = [
            {
                "citation_id": index,
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "vault_id": item.vault_id,
                "relative_path": item.relative_path,
                "title": item.title,
                "heading": item.heading,
                "heading_path": item.heading_path,
                "start_line": item.start_line,
                "end_line": item.end_line,
                "score": item.score,
                "match_method": item.match_method,
                "content": item.content,
                "content_hash": _content_hash(item.content),
            }
            for index, item in enumerate(results, start=1)
        ]
        pack: Dict[str, Any] = {
            "schema": RESEARCH_ARTIFACT_SCHEMA,
            "task_id": state.task_id,
            "query": query_text,
            "citation_count": len(citations),
            "citations": citations,
            "markdown": _render_evidence_markdown(query_text, citations),
        }
        context = [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "relative_path": item.relative_path,
                "line_range": [item.start_line, item.end_line],
                "content": item.content,
                "score": item.score,
            }
            for item in results
        ]
        return StepResult(
            artifacts=[Artifact("research_evidence_pack", pack)],
            evidence=evidence,
            retrieved_context=context,
        )


class CitationIntegrityVerifier:
    """Verifies every structured citation against the current knowledge index."""

    def __init__(
        self,
        repository: SQLiteKnowledgeRepository,
        require_evidence: bool = True,
    ) -> None:
        self.repository = repository
        self.require_evidence = require_evidence

    def __call__(self, state: AgentTaskState) -> bool:
        issues: List[str] = []
        if self.require_evidence and not state.evidence:
            issues.append("task contains no evidence")
        for index, evidence in enumerate(state.evidence, start=1):
            issues.extend(self._verify_evidence(index, evidence))
        issues.extend(self._verify_artifacts(state))
        for issue in issues:
            state.errors.append(
                ErrorRecord(
                    step_id=None,
                    error_type="CitationIntegrityError",
                    message=issue,
                )
            )
        return not issues

    def _verify_evidence(self, index: int, evidence: Evidence) -> List[str]:
        prefix = "evidence[%s]" % index
        if not evidence.chunk_id:
            return ["%s has no chunk_id" % prefix]
        row = self.repository.get_chunk_reference(evidence.chunk_id)
        if row is None:
            return ["%s references a missing chunk" % prefix]
        expected_hash = _content_hash(row["content"])
        comparisons = {
            "source_id": (evidence.source_id, row["document_id"]),
            "vault_id": (evidence.vault_id, row["vault_id"]),
            "relative_path": (evidence.relative_path, row["relative_path"]),
            "start_line": (evidence.start_line, row["start_line"]),
            "end_line": (evidence.end_line, row["end_line"]),
            "content": (evidence.content, row["content"]),
            "content_hash": (evidence.content_hash, expected_hash),
        }
        issues = []
        for field_name, (actual, expected) in comparisons.items():
            if actual != expected:
                issues.append("%s %s does not match indexed chunk" % (prefix, field_name))
        expected_location = _location(row["relative_path"], row["start_line"], row["end_line"])
        if evidence.location != expected_location:
            issues.append("%s location does not match indexed chunk" % prefix)
        return issues

    @staticmethod
    def _verify_artifacts(state: AgentTaskState) -> List[str]:
        evidence_ids = [item.chunk_id for item in state.evidence if item.chunk_id]
        evidence_by_id = {item.chunk_id: item for item in state.evidence if item.chunk_id}
        issues: List[str] = []
        for artifact in state.artifacts:
            if artifact.artifact_type != "research_evidence_pack":
                continue
            if not isinstance(artifact.content, dict):
                issues.append("research evidence artifact must be an object")
                continue
            if artifact.content.get("schema") != RESEARCH_ARTIFACT_SCHEMA:
                issues.append("research evidence artifact has an unsupported schema")
            citations = artifact.content.get("citations")
            if not isinstance(citations, list):
                issues.append("research evidence artifact citations must be a list")
                continue
            citation_ids = [item.get("chunk_id") for item in citations if isinstance(item, dict)]
            if citation_ids != evidence_ids:
                issues.append("research artifact citation order and task evidence differ")
            if artifact.content.get("citation_count") != len(citations):
                issues.append("research artifact citation_count is incorrect")
            for position, citation in enumerate(citations, start=1):
                if not isinstance(citation, dict):
                    issues.append("research artifact citation[%s] must be an object" % position)
                    continue
                evidence = evidence_by_id.get(citation.get("chunk_id"))
                if evidence is None:
                    continue
                comparisons = {
                    "document_id": evidence.source_id,
                    "vault_id": evidence.vault_id,
                    "relative_path": evidence.relative_path,
                    "start_line": evidence.start_line,
                    "end_line": evidence.end_line,
                    "content": evidence.content,
                    "content_hash": evidence.content_hash,
                }
                for field_name, expected in comparisons.items():
                    if citation.get(field_name) != expected:
                        issues.append(
                            "research artifact citation[%s] %s differs from task evidence"
                            % (position, field_name)
                        )
        return issues


def register_research_workflow(registry: Any, search_engine: SearchEngine) -> None:
    registry.register("research.retrieve", ResearchWorkflow(search_engine))


def _evidence_from_result(result: KnowledgeSearchResult) -> Evidence:
    return Evidence(
        source_id=result.document_id,
        location=_location(result.relative_path, result.start_line, result.end_line),
        content=result.content,
        chunk_id=result.chunk_id,
        vault_id=result.vault_id,
        relative_path=result.relative_path,
        start_line=result.start_line,
        end_line=result.end_line,
        content_hash=_content_hash(result.content),
    )


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _location(relative_path: str, start_line: int, end_line: int) -> str:
    return "%s:L%s-L%s" % (relative_path, start_line, end_line)


def _render_evidence_markdown(query: str, citations: Sequence[Dict[str, Any]]) -> str:
    lines = ["# Research Evidence", "", "Query: %s" % query, ""]
    for citation in citations:
        heading = " / ".join(citation["heading_path"]) or citation["title"]
        lines.extend(
            [
                "## [%s] %s" % (citation["citation_id"], heading),
                "",
                "Source: `%s:L%s-L%s`" % (
                    citation["relative_path"],
                    citation["start_line"],
                    citation["end_line"],
                ),
                "",
                citation["content"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any, name: str) -> List[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("%s must be a list" % name)
    return [str(item) for item in value]


def _integer_input(
    values: Dict[str, Any], name: str, default: int, minimum: int, maximum: int
) -> int:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer" % name)
    if value < minimum or value > maximum:
        raise ValueError("%s must be between %s and %s" % (name, minimum, maximum))
    return value


def _float_input(values: Dict[str, Any], name: str, default: float) -> float:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s must be a number" % name)
    return float(value)
