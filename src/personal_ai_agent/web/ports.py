"""Stable business boundary exposed to the web adapter."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from ..application import ApplicationService
from ..config import ApplicationConfig
from .demo import create_demo_model_gateway


class WebApplicationPort(Protocol):
    def health(self) -> Dict[str, object]:
        ...

    def knowledge_status(self) -> Dict[str, object]:
        ...

    def search(
        self,
        text: str,
        limit: int = 10,
        path_prefix: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Any:
        ...

    def run_research(self, *args, **kwargs) -> Dict[str, object]:
        ...

    def show_task(self, task_id: str) -> Dict[str, object]:
        ...

    def cancel_task(self, task_id: str) -> Dict[str, object]:
        ...

    def pending_memory_candidates(self, task_id: str) -> List[Dict[str, object]]:
        ...

    def resolve_memory(self, *args, **kwargs) -> Dict[str, object]:
        ...

    def observability_summary(self, *args, **kwargs) -> Dict[str, object]:
        ...


class ApplicationServiceWebAdapter:
    """Keep Flask routes independent from repositories and provider adapters."""

    def __init__(self, service: ApplicationService, demo_mode: bool = False) -> None:
        self._service = service
        self._demo_mode = bool(demo_mode)

    @classmethod
    def from_file(
        cls,
        config_path: str,
        demo_mode: bool = False,
        demo_data_root: Optional[str] = None,
    ) -> "ApplicationServiceWebAdapter":
        factory = None
        config = ApplicationConfig.load(config_path)
        if demo_mode:
            _validate_demo_paths(config, demo_data_root)
            factory = lambda service: create_demo_model_gateway(service.event_store)
        return cls(ApplicationService(config, factory), demo_mode)

    def health(self) -> Dict[str, object]:
        validation = self._service.validate()
        return {
            "status": "ok",
            "config_loaded": validation.get("valid") is True,
            "storage_ready": True,
            "demo_mode": self._demo_mode,
        }

    def knowledge_status(self) -> Dict[str, object]:
        validation = self._service.validate()
        return {
            "vault_id": validation["vault_id"],
            "fts5_available": validation["fts5_available"],
            "model_provider_ids": validation["config"]["model_provider_ids"],
            "embedding_provider_ids": validation["config"][
                "embedding_provider_ids"
            ],
        }

    def search(self, *args, **kwargs):
        return self._service.search(*args, **kwargs)

    def run_research(self, *args, **kwargs):
        return self._service.run_research(*args, **kwargs)

    def show_task(self, task_id: str):
        return self._service.show_task(task_id)

    def cancel_task(self, task_id: str):
        return self._service.cancel_task(task_id)

    def pending_memory_candidates(self, task_id: str):
        return self._service.pending_memory_candidates(task_id)

    def resolve_memory(self, *args, **kwargs):
        return self._service.resolve_memory(*args, **kwargs)

    def observability_summary(self, *args, **kwargs):
        return self._service.observability_summary(*args, **kwargs)


def _validate_demo_paths(
    config: ApplicationConfig, demo_data_root: Optional[str]
) -> None:
    if not demo_data_root:
        raise ValueError("demo data root must be explicitly configured")
    root = Path(demo_data_root).resolve()
    if not root.is_dir():
        raise ValueError("demo data root must be an existing directory")
    for path in (config.vault_path, config.data_directory):
        try:
            path.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "demo vault and runtime must stay inside the demo data root"
            ) from exc
