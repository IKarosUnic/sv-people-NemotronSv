"""SALTBOR AI Intelligence Layer Module.

Provides:
- AIProvider abstraction (Deterministic, Ollama, Gemini, OpenAI)
- AIModelRouter with automatic offline fallback
- AIComputeBudgetManager with token accounting and caching
- NaturalLanguageScenarioBuilder for zero-code scenario compilation
- AICausalOrchestrationAssistant for scientific causal verification
- ScenarioPlanningAssistant for territorial policy guidance
- AISimulationExecutionController for lifecycle management
- SimulationResultsAnalyst for evidence-grounded interpretation
- AIScenarioComparisonAssistant for counterfactual analysis
- AIMemoryAndContext for strict knowledge partitioning
"""

from saltbor.ai.budget import AIComputeBudgetManager, BudgetLimits
from saltbor.ai.causal_orchestrator import AICausalOrchestrationAssistant, CausalValidationStatus
from saltbor.ai.context import AIMemoryAndContext, KnowledgePartition
from saltbor.ai.execution_controller import AISimulationExecutionController, ExecutionRecord, ExecutionState
from saltbor.ai.planning_assistant import PolicyAlternative, ScenarioPlanningAssistant
from saltbor.ai.providers.base import (
    AIProviderType,
    AIRequest,
    AIResponse,
    AITaskCategory,
    BaseAIProvider,
    TokenUsage,
)
from saltbor.ai.providers.deterministic import OfflineDeterministicProvider
from saltbor.ai.providers.ollama import OllamaProvider
from saltbor.ai.privacy import AIPrivacyGuard, DataClassification, RedactionAuditRecord
from saltbor.ai.providers.remote import GeminiModelTier, RemoteGeminiProvider, RemoteOpenAIProvider
from saltbor.ai.results_analyst import ScientificResultInterpretation, SimulationResultsAnalyst
from saltbor.ai.router import AIModelRouter
from saltbor.ai.scenario_builder import NaturalLanguageScenarioBuilder, ScenarioBuildResult
from saltbor.ai.scenario_comparator import AIScenarioComparisonAssistant, CounterfactualComparisonReport

__all__ = [
    "AIProviderType",
    "AITaskCategory",
    "TokenUsage",
    "AIRequest",
    "AIResponse",
    "BaseAIProvider",
    "OfflineDeterministicProvider",
    "OllamaProvider",
    "RemoteGeminiProvider",
    "RemoteOpenAIProvider",
    "AIModelRouter",
    "AIComputeBudgetManager",
    "BudgetLimits",
    "NaturalLanguageScenarioBuilder",
    "ScenarioBuildResult",
    "AICausalOrchestrationAssistant",
    "CausalValidationStatus",
    "ScenarioPlanningAssistant",
    "PolicyAlternative",
    "AISimulationExecutionController",
    "ExecutionState",
    "ExecutionRecord",
    "SimulationResultsAnalyst",
    "ScientificResultInterpretation",
    "AIScenarioComparisonAssistant",
    "CounterfactualComparisonReport",
    "AIMemoryAndContext",
    "KnowledgePartition",
    "AIPrivacyGuard",
    "DataClassification",
    "RedactionAuditRecord",
    "GeminiModelTier",
]
