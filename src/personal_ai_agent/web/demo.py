"""Deterministic, evidence-bound model used only by the offline course demo."""

from typing import Any, Optional
from ..model_gateway import (
    CostLevel,
    ModelCapabilityRegistry,
    ModelGateway,
    ModelProfile,
    ModelRequest,
    PrivacyLevel,
    ProviderResponse,
)


class DemoModelProvider:
    """Build a valid summary by copying supplied evidence without network I/O."""

    provider_id = "demo-model"

    def generate(self, request: ModelRequest) -> ProviderResponse:
        evidence = request.payload.get("evidence") or []
        if not evidence:
            raise ValueError("demo model requires evidence")
        language = str(request.payload.get("language") or "zh-CN")
        title = "离线演示研究" if language.lower().startswith("zh") else "Offline demo research"
        heading = "基于本地知识库的证据" if language.lower().startswith("zh") else "Local evidence"
        paragraphs = [
            {
                "text": str(item["content"]).strip(),
                "citations": [int(item["citation_id"])],
            }
            for item in evidence
            if str(item.get("content") or "").strip()
        ]
        if not paragraphs:
            raise ValueError("demo model requires non-empty evidence")
        return ProviderResponse(
            data={
                "title": title,
                "sections": [{"heading": heading, "paragraphs": paragraphs}],
            },
            model_id="demo-deterministic-v1",
            input_tokens=max(1, request.estimated_input_tokens),
            output_tokens=max(1, sum(len(item["text"]) for item in paragraphs) // 4),
        )


def create_demo_model_gateway(event_store: Optional[Any] = None) -> ModelGateway:
    profile = ModelProfile(
        provider=DemoModelProvider(),
        capabilities=frozenset({"structured_output", "chinese"}),
        max_context_tokens=32768,
        cost_level=CostLevel.LOW,
        max_privacy_level=PrivacyLevel.PERSONAL,
        priority=1,
    )
    return ModelGateway(
        registry=ModelCapabilityRegistry([profile]),
        max_retries=0,
        event_store=event_store,
    )


__all__ = ["DemoModelProvider", "create_demo_model_gateway"]
