"""Application service that assembles the local P0 knowledge loop."""

from dataclasses import asdict
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

from .cancellation import CancellationToken
from .config import ApplicationConfig, EmbeddingProviderConfig
from .hybrid_search import HybridSearchEngine
from .knowledge import (
    HybridSearchQuery,
    KeywordSearchQuery,
    KnowledgeSearchResult,
    SyncResult,
    VectorSyncResult,
)
from .knowledge_repository import SQLiteKnowledgeRepository
from .execution_control import SQLiteExecutionControl, TaskLeaseConflict
from .evaluation import RetrievalEvaluationDataset, evaluate_retrieval
from .memory_repository import MemoryRecord, SQLiteMemoryRepository
from .memory_workflow import register_memory_workflows
from .model_gateway import (
    CostLevel,
    ModelCapabilityRegistry,
    ModelGateway,
    ModelProfile,
    PrivacyLevel,
)
from .models import AgentTaskState, PlanStep
from .obsidian import ObsidianVaultIngester
from .obsidian_writer import ControlledObsidianWriter, register_obsidian_writeback_workflow
from .observability import SQLiteEventStore, record_event_safely
from .orchestrator import Orchestrator, WorkflowRegistry
from .provider_adapters import (
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleModelProvider,
)
from .rate_limiter import SQLiteProviderRateLimiter
from .quality_baseline import (
    observability_baseline_scope,
    resolve_quality_baseline,
    retrieval_baseline_scope,
)
from .quality_evaluation import (
    MemoryGovernanceEvaluationDataset,
    ResearchSummaryEvaluationDataset,
    apply_observability_gates,
    apply_retrieval_gates,
    evaluate_memory_governance,
    evaluate_research_summaries,
)
from .repository import SQLiteTaskRepository
from .research_summary import (
    CompositeVerifier,
    ResearchSummaryVerifier,
    register_research_summary_workflow,
)
from .research_workflow import CitationIntegrityVerifier, register_research_workflow
from .search import KeywordSearchEngine
from .serialization import task_state_to_dict
from .vector import SQLiteVectorIndex


class ApplicationService:
    def __init__(self, config: ApplicationConfig) -> None:
        self.config = config
        config.data_directory.mkdir(parents=True, exist_ok=True)
        self.knowledge_repository = SQLiteKnowledgeRepository(
            config.data_directory / "knowledge.sqlite3"
        )
        self.task_repository = SQLiteTaskRepository(
            config.data_directory / "tasks.sqlite3"
        )
        self.execution_control = SQLiteExecutionControl(
            config.data_directory / "tasks.sqlite3"
        )
        self.event_store = SQLiteEventStore(
            config.data_directory / "observability.sqlite3"
        )
        self.rate_limiter = SQLiteProviderRateLimiter(
            config.data_directory / "rate_limits.sqlite3"
        )
        self.memory_repository = SQLiteMemoryRepository(
            config.data_directory / "memory.sqlite3"
        )
        self.ingester = ObsidianVaultIngester(
            config.vault_path, self.knowledge_repository
        )
        self.writer = ControlledObsidianWriter(
            config.vault_path,
            config.managed_memory_directory,
            self.memory_repository,
        )
        self.keyword_search = KeywordSearchEngine(self.knowledge_repository)

    @classmethod
    def from_file(cls, config_path: str) -> "ApplicationService":
        return cls(ApplicationConfig.load(config_path))

    def validate(self) -> Dict[str, object]:
        return {
            "valid": True,
            "config": self.config.as_public_dict(),
            "fts5_available": self.knowledge_repository.fts5_available,
            "vault_id": self.ingester.vault_id,
        }

    def sync_vault(self) -> SyncResult:
        return self.ingester.sync()

    def search(
        self,
        text: str,
        limit: int = 10,
        path_prefix: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[KnowledgeSearchResult]:
        return self.keyword_search.search(
            KeywordSearchQuery(
                text=text,
                vault_id=self.ingester.vault_id,
                path_prefix=path_prefix,
                tags=tags or [],
                limit=limit,
            )
        )

    def vector_sync(self, provider_id: Optional[str] = None) -> VectorSyncResult:
        _, index = self._vector_index(provider_id)
        return index.sync()

    def hybrid_search(
        self,
        text: str,
        provider_id: Optional[str] = None,
        limit: int = 10,
        path_prefix: Optional[str] = None,
        tags: Optional[List[str]] = None,
        keyword_weight: float = 1.0,
        vector_weight: float = 1.0,
    ) -> List[KnowledgeSearchResult]:
        _, index = self._vector_index(provider_id)
        engine = HybridSearchEngine(self.keyword_search, index)
        return engine.search(
            HybridSearchQuery(
                text=text,
                vault_id=self.ingester.vault_id,
                path_prefix=path_prefix,
                tags=tags or [],
                limit=limit,
                keyword_weight=keyword_weight,
                vector_weight=vector_weight,
            )
        )

    def run_research(
        self,
        goal: str,
        thread_id: str,
        model_provider_id: Optional[str] = None,
        embedding_provider_id: Optional[str] = None,
        limit: int = 8,
        language: str = "zh-CN",
    ) -> Dict[str, object]:
        if not goal.strip() or not thread_id.strip():
            raise ValueError("goal and thread_id must be non-empty")
        state = AgentTaskState.create(
            thread_id.strip(), goal.strip(), {"language": language}
        )
        token = CancellationToken(
            lambda: self.execution_control.cancellation_requested(state.task_id)
        )
        state._cancellation_token = token
        gateway = self._model_gateway()
        search_engine = self.keyword_search
        if embedding_provider_id is not None:
            _, vector_index = self._vector_index(
                embedding_provider_id, cancellation_token=token
            )
            search_engine = HybridSearchEngine(self.keyword_search, vector_index)
        registry = WorkflowRegistry()
        register_research_workflow(registry, search_engine)
        register_research_summary_workflow(registry, gateway)
        register_memory_workflows(registry, self.memory_repository)
        register_obsidian_writeback_workflow(registry, self.writer, self.ingester)
        runtime = Orchestrator(
            registry,
            verifier=CompositeVerifier(
                CitationIntegrityVerifier(self.knowledge_repository),
                ResearchSummaryVerifier(),
            ),
            checkpoint_store=self.task_repository,
            event_store=self.event_store,
        )
        plan = [
            PlanStep(
                "retrieve",
                "research",
                "research.retrieve",
                {"query": goal.strip(), "limit": limit},
            ),
            PlanStep(
                "summarize",
                "research",
                "research.summarize",
                {
                    "language": language,
                    **(
                        {"provider_id": model_provider_id}
                        if model_provider_id is not None
                        else {}
                    ),
                },
                depends_on=("retrieve",),
            ),
            PlanStep("propose", "memory", "memory.propose", depends_on=("summarize",)),
            PlanStep("persist", "memory", "memory.persist", depends_on=("propose",)),
            PlanStep(
                "writeback",
                "memory",
                "obsidian.writeback",
                depends_on=("persist",),
            ),
        ]
        return task_state_to_dict(
            self._run_with_lease(runtime, state, plan, cancellation_token=token)
        )

    def show_task(self, task_id: str) -> Dict[str, object]:
        return task_state_to_dict(self.task_repository.load(task_id))

    def list_thread_tasks(self, thread_id: str, limit: int = 50) -> List[Dict[str, object]]:
        return [
            task_state_to_dict(item)
            for item in self.task_repository.list_by_thread(thread_id, limit)
        ]

    def pending_memory_candidates(self, task_id: str) -> List[Dict[str, object]]:
        state = self.task_repository.load(task_id)
        return [
            asdict(item)
            for item in state.memory_candidates
            if item.governance_status == "PENDING" and item.requires_approval
        ]

    def resolve_memory(
        self,
        task_id: str,
        approved_ids: Iterable[str],
        rejected_ids: Iterable[str],
    ) -> Dict[str, object]:
        state = self.task_repository.load(task_id)
        registry = WorkflowRegistry()
        register_memory_workflows(registry, self.memory_repository)
        register_obsidian_writeback_workflow(registry, self.writer, self.ingester)
        verifier = CompositeVerifier(
            CitationIntegrityVerifier(self.knowledge_repository),
            ResearchSummaryVerifier(),
        )
        token = CancellationToken(
            lambda: self.execution_control.cancellation_requested(task_id)
        )
        state._cancellation_token = token
        owner_id = "executor_%s" % uuid4().hex
        with self.execution_control.lease(task_id, owner_id) as lease:
            runtime = Orchestrator(
                registry,
                verifier=verifier,
                checkpoint_store=self.task_repository,
                cancellation_token=token,
                execution_guard=lease.assert_owned,
                event_store=self.event_store,
            )
            resolved = runtime.resolve_memory_approval(
                state, approved_ids=approved_ids, rejected_ids=rejected_ids
            )
        return task_state_to_dict(resolved)

    def cancel_task(self, task_id: str) -> Dict[str, object]:
        state = self.task_repository.load(task_id)
        if state.status.value in {"COMPLETED", "PARTIAL_SUCCESS", "FAILED", "CANCELLED"}:
            return {
                "task_id": task_id,
                "status": state.status.value,
                "cancel_requested": False,
                "final": True,
            }
        info = self.execution_control.request_cancel(task_id)
        owner_id = "canceller_%s" % uuid4().hex
        immediate = self.execution_control.acquire(task_id, owner_id, 5.0)
        if immediate:
            try:
                state = self.task_repository.cancel_snapshot(task_id)
                record_event_safely(
                    self.event_store,
                    "task_cancelled",
                    task_id=task_id,
                    attributes={
                        "final_status": state.status.value,
                        "tool_calls": state.tool_calls,
                        "model_call_count": state.model_call_count,
                        "token_usage": state.token_usage,
                        "retry_count": state.retry_count,
                    },
                )
            finally:
                self.execution_control.release(task_id, owner_id)
        return {
            "task_id": task_id,
            "status": state.status.value,
            "cancel_requested": True,
            "immediate": immediate,
            "active_owner": info.owner_id if not immediate else None,
        }

    def list_memories(self) -> List[MemoryRecord]:
        return self.memory_repository.list_all()

    def task_events(self, task_id: str, limit: int = 200) -> List[object]:
        self.task_repository.load(task_id)
        return self.event_store.list_task_events(task_id, limit)

    def observability_summary(
        self,
        limit: int = 1000,
        minimums: Optional[Dict[str, float]] = None,
        maximums: Optional[Dict[str, float]] = None,
        baseline_path: Optional[str] = None,
    ) -> Dict[str, object]:
        resolved_minimums, resolved_maximums, baseline = resolve_quality_baseline(
            baseline_path,
            observability_baseline_scope(limit),
            minimums or {},
            maximums or {},
        )
        output = apply_observability_gates(
            self.event_store.aggregate(limit), resolved_minimums, resolved_maximums
        )
        if baseline is not None:
            output["quality_baseline"] = baseline
        return output

    def prune_observability_events(
        self, retention_days: Optional[int] = None, apply: bool = False
    ) -> Dict[str, object]:
        days = (
            self.config.observability_retention_days
            if retention_days is None
            else retention_days
        )
        return self.event_store.prune(days, apply)

    def evaluate_retrieval(
        self,
        dataset_path: str,
        engine: str = "keyword",
        provider_id: Optional[str] = None,
        limit: int = 10,
        minimums: Optional[Dict[str, float]] = None,
        maximums: Optional[Dict[str, float]] = None,
        baseline_path: Optional[str] = None,
    ) -> Dict[str, object]:
        dataset = RetrievalEvaluationDataset.load(dataset_path)
        resolved_minimums, resolved_maximums, baseline = resolve_quality_baseline(
            baseline_path,
            retrieval_baseline_scope(dataset.name, engine, limit, provider_id),
            minimums or {},
            maximums or {},
        )
        if engine == "keyword":
            search = lambda query, size: self.search(query, size)
        elif engine == "hybrid":
            search = lambda query, size: self.hybrid_search(
                query, provider_id=provider_id, limit=size
            )
        else:
            raise ValueError("evaluation engine must be keyword or hybrid")
        report = evaluate_retrieval(dataset, search, engine, limit)
        output = apply_retrieval_gates(
            report.as_dict(), resolved_minimums, resolved_maximums
        )
        if baseline is not None:
            output["quality_baseline"] = baseline
        record_event_safely(
            self.event_store,
            "evaluation_completed",
            attributes={
                "evaluation_type": "retrieval",
                "dataset_name": report.dataset_name,
                "engine": report.engine,
                "limit": report.limit,
                "case_count": report.case_count,
                "recall_at_k": report.recall_at_k,
                "hit_rate_at_k": report.hit_rate_at_k,
                "mrr_at_k": report.mrr_at_k,
                "p50_latency_ms": report.p50_latency_ms,
                "p95_latency_ms": report.p95_latency_ms,
                "gate_passed": output["gate_passed"],
            },
        )
        return output

    def evaluate_research_summaries(
        self,
        dataset_path: str,
        minimums: Optional[Dict[str, float]] = None,
    ) -> Dict[str, object]:
        report = evaluate_research_summaries(
            ResearchSummaryEvaluationDataset.load(dataset_path), minimums
        )
        record_event_safely(
            self.event_store,
            "evaluation_completed",
            attributes={
                "evaluation_type": "research_summary",
                "dataset_name": report.dataset_name,
                "case_count": report.case_count,
                "structure_valid_rate": report.structure_valid_rate,
                "paragraph_coverage_rate": report.paragraph_coverage_rate,
                "exact_citation_set_rate": report.exact_citation_set_rate,
                "citation_precision": report.citation_precision,
                "citation_recall": report.citation_recall,
                "citation_f1": report.citation_f1,
                "gate_passed": report.gate_passed,
            },
        )
        return report.as_dict()

    def evaluate_memory_governance(
        self,
        dataset_path: str,
        minimums: Optional[Dict[str, float]] = None,
    ) -> Dict[str, object]:
        report = evaluate_memory_governance(
            MemoryGovernanceEvaluationDataset.load(dataset_path), minimums
        )
        record_event_safely(
            self.event_store,
            "evaluation_completed",
            attributes={
                "evaluation_type": "memory_governance",
                "dataset_name": report.dataset_name,
                "case_count": report.case_count,
                "status_accuracy": report.status_accuracy,
                "reason_accuracy": report.reason_accuracy,
                "approval_accuracy": report.approval_accuracy,
                "decision_accuracy": report.decision_accuracy,
                "gate_passed": report.gate_passed,
            },
        )
        return report.as_dict()

    def _vector_index(
        self,
        provider_id: Optional[str],
        cancellation_token: Optional[CancellationToken] = None,
    ) -> tuple:
        config = _select_provider(
            self.config.embedding_providers, provider_id, "embedding"
        )
        provider = OpenAICompatibleEmbeddingProvider(
            config,
            rate_limiter=self.rate_limiter,
            cancellation_token=cancellation_token,
        )
        return config, SQLiteVectorIndex(
            self.knowledge_repository, provider, batch_size=config.batch_size
        )

    def _model_gateway(self) -> ModelGateway:
        if not self.config.model_providers:
            raise ValueError("no model providers are configured")
        cost_levels = {
            "low": CostLevel.LOW,
            "medium": CostLevel.MEDIUM,
            "high": CostLevel.HIGH,
        }
        privacy_levels = {
            "public": PrivacyLevel.PUBLIC,
            "personal": PrivacyLevel.PERSONAL,
            "sensitive": PrivacyLevel.SENSITIVE,
        }
        profiles = [
            ModelProfile(
                provider=OpenAICompatibleModelProvider(
                    item, rate_limiter=self.rate_limiter
                ),
                capabilities=item.capabilities,
                max_context_tokens=item.max_context_tokens,
                cost_level=cost_levels[item.cost_level],
                max_privacy_level=privacy_levels[item.max_privacy_level],
                priority=item.priority,
                input_cost_per_million_tokens_usd=item.input_cost_per_million_tokens_usd,
                output_cost_per_million_tokens_usd=item.output_cost_per_million_tokens_usd,
            )
            for item in self.config.model_providers
        ]
        return ModelGateway(
            registry=ModelCapabilityRegistry(profiles),
            max_retries=1,
            event_store=self.event_store,
        )

    def _run_with_lease(
        self,
        runtime: Orchestrator,
        state: AgentTaskState,
        plan: List[PlanStep],
        cancellation_token: Optional[CancellationToken] = None,
    ) -> AgentTaskState:
        owner_id = "executor_%s" % uuid4().hex
        token = cancellation_token or CancellationToken(
            lambda: self.execution_control.cancellation_requested(state.task_id)
        )
        state._cancellation_token = token
        with self.execution_control.lease(state.task_id, owner_id) as lease:
            runtime.cancellation_token = token
            runtime.execution_guard = lease.assert_owned
            return runtime.run(state, plan)


def _select_provider(
    providers: List[EmbeddingProviderConfig],
    provider_id: Optional[str],
    provider_type: str,
) -> EmbeddingProviderConfig:
    if provider_id is not None:
        for item in providers:
            if item.provider_id == provider_id:
                return item
        raise ValueError("unknown %s provider_id: %s" % (provider_type, provider_id))
    if not providers:
        raise ValueError("no %s providers are configured" % provider_type)
    if len(providers) > 1:
        raise ValueError("multiple %s providers are configured; select one" % provider_type)
    return providers[0]
