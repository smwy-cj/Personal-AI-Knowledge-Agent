"""Personal AI Knowledge Agent runtime primitives."""

from .application import ApplicationService
from .cancellation import CancellationToken, OperationCancelled
from .config import (
    ApplicationConfig,
    ConfigurationError,
    EmbeddingProviderConfig,
    ModelProviderConfig,
)
from .execution_control import (
    ExecutionControlInfo,
    SQLiteExecutionControl,
    TaskLeaseConflict,
    TaskLeaseLost,
)
from .evaluation import (
    RetrievalEvaluationDataset,
    RetrievalEvaluationReport,
    evaluate_retrieval,
)
from .hybrid_search import HybridSearchEngine
from .knowledge import HybridSearchQuery, KeywordSearchQuery, KnowledgeSearchResult
from .models import AgentTaskState, PlanStep, StepResult, TaskBudget, TaskStatus
from .memory_repository import SQLiteMemoryRepository
from .memory_workflow import (
    MemoryCandidateWorkflow,
    MemoryPersistenceWorkflow,
    register_memory_workflows,
)
from .model_gateway import (
    CostLevel,
    ModelGateway,
    ModelCapabilityRegistry,
    ModelCallBudgetExceeded,
    ModelProfile,
    ModelRequest,
    ModelProvider,
    ProviderResponse,
    RetryableModelError,
    PrivacyLevel,
)
from .orchestrator import Orchestrator, WorkflowRegistry
from .observability import ObservationEvent, SQLiteEventStore
from .provider_adapters import (
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleModelProvider,
    ProviderConfigurationError,
    ProviderPayloadTooLarge,
    ProviderProtocolError,
)
from .rate_limiter import ProviderRateLimitExceeded, SQLiteProviderRateLimiter
from .quality_evaluation import (
    MemoryGovernanceEvaluationDataset,
    ResearchSummaryEvaluationDataset,
    apply_observability_gates,
    apply_retrieval_gates,
    evaluate_memory_governance,
    evaluate_research_summaries,
)
from .knowledge_repository import SQLiteKnowledgeRepository
from .obsidian import ObsidianVaultIngester
from .obsidian_writer import (
    ControlledObsidianWriter,
    ObsidianWritebackWorkflow,
    register_obsidian_writeback_workflow,
)
from .repository import SQLiteTaskRepository
from .research_workflow import (
    CitationIntegrityVerifier,
    ResearchWorkflow,
    register_research_workflow,
)
from .research_summary import (
    CompositeVerifier,
    ResearchSummaryVerifier,
    ResearchSummaryWorkflow,
    register_research_summary_workflow,
)
from .search import KeywordSearchEngine
from .vector import EmbeddingProvider, SQLiteVectorIndex

__all__ = [
    "AgentTaskState",
    "ApplicationConfig",
    "ApplicationService",
    "CancellationToken",
    "ConfigurationError",
    "EmbeddingProviderConfig",
    "ExecutionControlInfo",
    "RetrievalEvaluationDataset",
    "RetrievalEvaluationReport",
    "ResearchSummaryEvaluationDataset",
    "MemoryGovernanceEvaluationDataset",
    "ModelProviderConfig",
    "OpenAICompatibleEmbeddingProvider",
    "OpenAICompatibleModelProvider",
    "ProviderConfigurationError",
    "ProviderPayloadTooLarge",
    "ProviderProtocolError",
    "ProviderRateLimitExceeded",
    "OperationCancelled",
    "SQLiteExecutionControl",
    "SQLiteEventStore",
    "SQLiteProviderRateLimiter",
    "ObservationEvent",
    "TaskLeaseConflict",
    "TaskLeaseLost",
    "ModelGateway",
    "ModelCapabilityRegistry",
    "ModelCallBudgetExceeded",
    "ModelProfile",
    "CostLevel",
    "PrivacyLevel",
    "SQLiteMemoryRepository",
    "MemoryCandidateWorkflow",
    "MemoryPersistenceWorkflow",
    "register_memory_workflows",
    "ModelRequest",
    "ModelProvider",
    "ProviderResponse",
    "RetryableModelError",
    "KeywordSearchEngine",
    "HybridSearchEngine",
    "HybridSearchQuery",
    "KeywordSearchQuery",
    "KnowledgeSearchResult",
    "Orchestrator",
    "ObsidianVaultIngester",
    "ControlledObsidianWriter",
    "ObsidianWritebackWorkflow",
    "register_obsidian_writeback_workflow",
    "PlanStep",
    "StepResult",
    "SQLiteTaskRepository",
    "SQLiteKnowledgeRepository",
    "SQLiteVectorIndex",
    "EmbeddingProvider",
    "CitationIntegrityVerifier",
    "ResearchWorkflow",
    "register_research_workflow",
    "CompositeVerifier",
    "ResearchSummaryVerifier",
    "ResearchSummaryWorkflow",
    "register_research_summary_workflow",
    "TaskBudget",
    "TaskStatus",
    "WorkflowRegistry",
    "evaluate_retrieval",
    "evaluate_research_summaries",
    "evaluate_memory_governance",
    "apply_retrieval_gates",
    "apply_observability_gates",
]
