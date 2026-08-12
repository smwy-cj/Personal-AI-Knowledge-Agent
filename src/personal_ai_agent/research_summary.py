"""Evidence-bound model generation and deterministic citation coverage checks."""

import re
from typing import Any, Dict, List, Optional, Sequence

from .model_gateway import CostLevel, ModelGateway, ModelRequest, PrivacyLevel
from .models import AgentTaskState, Artifact, ErrorRecord, PlanStep, StepResult
from .research_workflow import RESEARCH_ARTIFACT_SCHEMA


RESEARCH_SUMMARY_SCHEMA = "research_summary_v1"
CITATION_RE = re.compile(r"\[(\d+)\]")


class ResearchSummaryWorkflow:
    def __init__(self, gateway: ModelGateway) -> None:
        self.gateway = gateway

    def __call__(self, state: AgentTaskState, step: PlanStep) -> StepResult:
        evidence_pack = _latest_artifact(state, "research_evidence_pack")
        if evidence_pack is None or evidence_pack.get("schema") != RESEARCH_ARTIFACT_SCHEMA:
            raise ValueError("research summary requires a verified evidence pack")
        citations = evidence_pack.get("citations")
        if not isinstance(citations, list) or not citations:
            raise ValueError("research summary requires non-empty citations")

        remaining_tokens = state.budget.max_tokens - state.token_usage
        if remaining_tokens <= 0:
            raise ValueError("task has no remaining token budget for research summary")
        remaining_model_calls = state.budget.max_model_calls - state.model_call_count
        if remaining_model_calls <= 0:
            raise ValueError("task has no remaining model call budget")

        language = str(step.inputs.get("language") or state.user_constraints.get("language") or "zh-CN")
        request = ModelRequest(
            task_type="research_summary",
            prompt_version=str(step.inputs.get("prompt_version", "research-summary-v1")),
            payload={
                "goal": state.user_goal,
                "language": language,
                "instructions": (
                    "Use only the supplied evidence. Return sections with cited paragraphs. "
                    "Every paragraph must cite one or more citation_id values."
                ),
                "evidence": [
                    {
                        "citation_id": item["citation_id"],
                        "source": "%s:L%s-L%s"
                        % (item["relative_path"], item["start_line"], item["end_line"]),
                        "content": item["content"],
                    }
                    for item in citations
                ],
            },
            timeout_seconds=_positive_number(step.inputs, "timeout_seconds", 30.0),
            max_output_tokens=min(
                _positive_integer(step.inputs, "max_output_tokens", 2_000),
                remaining_tokens,
            ),
            estimated_input_tokens=_non_negative_integer(
                step.inputs,
                "estimated_input_tokens",
                _estimate_payload_tokens(citations, state.user_goal),
            ),
            max_cost_level=_cost_level(step.inputs.get("max_cost_level", "high")),
            privacy_level=_privacy_level(
                step.inputs.get(
                    "privacy_level", state.user_constraints.get("privacy_level", "personal")
                )
            ),
            schema_name=RESEARCH_SUMMARY_SCHEMA,
            cancellation_token=getattr(state, "_cancellation_token", None),
            task_id=state.task_id,
            step_id=step.step_id,
        )
        response = self.gateway.generate(
            request,
            lambda data: validate_research_summary(data, len(citations)),
            provider_id=_optional_string(step.inputs.get("provider_id")),
            max_model_calls=remaining_model_calls,
        )
        structured = dict(response.data)
        structured["schema"] = RESEARCH_SUMMARY_SCHEMA
        structured["evidence_schema"] = RESEARCH_ARTIFACT_SCHEMA
        markdown = render_research_summary(structured)
        structured["markdown"] = markdown
        return StepResult(
            artifacts=[Artifact("research_summary", structured)],
            model_calls=[response.trace],
            model_call_count=response.model_call_count,
            final_answer=markdown,
            token_usage=response.trace.input_tokens + response.trace.output_tokens,
        )


class ResearchSummaryVerifier:
    def __call__(self, state: AgentTaskState) -> bool:
        issues: List[str] = []
        evidence_pack = _latest_artifact(state, "research_evidence_pack")
        summary = _latest_artifact(state, "research_summary")
        if summary is None:
            issues.append("task contains no research summary")
        elif evidence_pack is None:
            issues.append("research summary has no evidence pack")
        else:
            citation_count = evidence_pack.get("citation_count", 0)
            try:
                validate_research_summary(summary, citation_count)
            except (KeyError, TypeError, ValueError) as exc:
                issues.append("research summary structure is invalid: %s" % exc)
            expected_markdown = render_research_summary(summary)
            if summary.get("markdown") != expected_markdown:
                issues.append("research summary markdown differs from structured content")
            if state.final_answer != expected_markdown:
                issues.append("final answer differs from verified research summary")
            referenced = {
                citation
                for section in summary.get("sections", [])
                for paragraph in section.get("paragraphs", [])
                for citation in paragraph.get("citations", [])
            }
            if not referenced:
                issues.append("research summary does not cite any evidence")
        for issue in issues:
            state.errors.append(
                ErrorRecord(None, "ResearchSummaryVerificationError", issue)
            )
        return not issues


class CompositeVerifier:
    def __init__(self, *verifiers: Any) -> None:
        if not verifiers:
            raise ValueError("at least one verifier is required")
        self.verifiers = verifiers

    def __call__(self, state: AgentTaskState) -> bool:
        valid = True
        for verifier in self.verifiers:
            if not verifier(state):
                valid = False
        return valid


def register_research_summary_workflow(
    registry: Any, gateway: ModelGateway
) -> None:
    registry.register("research.summarize", ResearchSummaryWorkflow(gateway))


def validate_research_summary(data: Dict[str, Any], citation_count: int) -> None:
    title = data.get("title")
    sections = data.get("sections")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title must be a non-empty string")
    if not isinstance(sections, list) or not sections:
        raise ValueError("sections must be a non-empty list")
    for section_index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            raise ValueError("section[%s] must be an object" % section_index)
        heading = section.get("heading")
        paragraphs = section.get("paragraphs")
        if not isinstance(heading, str) or not heading.strip():
            raise ValueError("section[%s].heading must be non-empty" % section_index)
        if not isinstance(paragraphs, list) or not paragraphs:
            raise ValueError("section[%s].paragraphs must be non-empty" % section_index)
        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            if not isinstance(paragraph, dict):
                raise ValueError("paragraph must be an object")
            text = paragraph.get("text")
            citations = paragraph.get("citations")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("paragraph text must be non-empty")
            if CITATION_RE.search(text):
                raise ValueError("paragraph text must not contain inline citation markers")
            if not isinstance(citations, list) or not citations:
                raise ValueError("every paragraph must contain citations")
            if any(isinstance(item, bool) or not isinstance(item, int) for item in citations):
                raise ValueError("citations must be integer ids")
            if len(citations) != len(set(citations)):
                raise ValueError("paragraph citations must be unique")
            if any(item < 1 or item > citation_count for item in citations):
                raise ValueError("paragraph references an unknown citation")


def render_research_summary(data: Dict[str, Any]) -> str:
    lines = ["# %s" % data["title"].strip(), ""]
    for section in data["sections"]:
        lines.extend(["## %s" % section["heading"].strip(), ""])
        for paragraph in section["paragraphs"]:
            markers = "".join("[%s]" % item for item in paragraph["citations"])
            lines.extend(["%s %s" % (paragraph["text"].strip(), markers), ""])
    return "\n".join(lines).rstrip() + "\n"


def _latest_artifact(state: AgentTaskState, artifact_type: str) -> Optional[Dict[str, Any]]:
    for artifact in reversed(state.artifacts):
        if artifact.artifact_type == artifact_type and isinstance(artifact.content, dict):
            return artifact.content
    return None


def _positive_number(values: Dict[str, Any], name: str, default: float) -> float:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("%s must be a positive number" % name)
    return float(value)


def _positive_integer(values: Dict[str, Any], name: str, default: int) -> int:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("%s must be a positive integer" % name)
    return value


def _non_negative_integer(values: Dict[str, Any], name: str, default: int) -> int:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("%s must be a non-negative integer" % name)
    return value


def _estimate_payload_tokens(citations: Sequence[Dict[str, Any]], goal: str) -> int:
    character_count = len(goal) + sum(len(str(item.get("content", ""))) for item in citations)
    return max(1, (character_count + 3) // 4)


def _cost_level(value: Any) -> CostLevel:
    mapping = {"low": CostLevel.LOW, "medium": CostLevel.MEDIUM, "high": CostLevel.HIGH}
    try:
        return mapping[str(value).strip().casefold()]
    except KeyError as exc:
        raise ValueError("max_cost_level must be low, medium or high") from exc


def _privacy_level(value: Any) -> PrivacyLevel:
    mapping = {
        "public": PrivacyLevel.PUBLIC,
        "personal": PrivacyLevel.PERSONAL,
        "sensitive": PrivacyLevel.SENSITIVE,
    }
    try:
        return mapping[str(value).strip().casefold()]
    except KeyError as exc:
        raise ValueError("privacy_level must be public, personal or sensitive") from exc


def _optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
