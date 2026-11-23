"""SALTBOR Phase 1.16A — Conversational Territorial Intelligence Studio Package."""

from saltbor.conversational.decision_analyst import GeminiDecisionAnalyst
from saltbor.conversational.evidence_engine import SyntheticPopulationEvidenceEngine
from saltbor.conversational.intervention_designer import TerritorialInterventionDesigner
from saltbor.conversational.orchestrator import SALTBORConversationalOrchestrator
from saltbor.conversational.persistence import ConversationalPersistenceStore
from saltbor.conversational.population_activation import (
    NationalPopulationActivationManager,
    TerritorialPopulationContextEngine,
)
from saltbor.conversational.progressive_reports import ProgressiveReportBuilder
from saltbor.conversational.scenario_comparison import TerritorialScenarioComparisonEngine
from saltbor.conversational.schemas import (
    ActivationLOD,
    AnalysisStage,
    AnalyticalVerdict,
    BasicReportView,
    ConversationIntent,
    ConversationSessionState,
    ConversationTurn,
    DataProvenance,
    DecisionRecommendation,
    EvidenceBundle,
    EvidenceIndicator,
    EvidenceProvenance,
    ExpertReportView,
    ExplainedMetricCard,
    GeographicCandidate,
    IntermediateReportView,
    InterventionCategory,
    InterventionSpec,
    ParsedUserRequest,
    PopulationCategory,
    PreliminaryAssessment,
    ProgressiveReportBundle,
    ReportDepthLevel,
    ScenarioComparisonEntry,
    ScenarioComparisonReport,
    SimulationStudioResult,
    SyntheticOpinionRecord,
    TemporalHorizonSpec,
    TerritorialContext,
    UniversalEvidenceOrigin,
)
from saltbor.conversational.temporal_controller import ConversationalTemporalController, TemporalCheckpoint
from saltbor.conversational.territorial_context import NationalTerritorialContextEngine

__all__ = [
    "ActivationLOD",
    "AnalysisStage",
    "AnalyticalVerdict",
    "ConversationIntent",
    "ConversationSessionState",
    "ConversationTurn",
    "ConversationalPersistenceStore",
    "ConversationalTemporalController",
    "DataProvenance",
    "DecisionRecommendation",
    "EvidenceBundle",
    "EvidenceIndicator",
    "EvidenceProvenance",
    "GeminiDecisionAnalyst",
    "GeographicCandidate",
    "InterventionCategory",
    "InterventionSpec",
    "NationalPopulationActivationManager",
    "NationalTerritorialContextEngine",
    "ParsedUserRequest",
    "PopulationCategory",
    "PreliminaryAssessment",
    "ProgressiveReportBuilder",
    "ProgressiveReportBundle",
    "ReportDepthLevel",
    "SALTBORConversationalOrchestrator",
    "BasicReportView",
    "IntermediateReportView",
    "ExpertReportView",
    "ExplainedMetricCard",
    "UniversalEvidenceOrigin",
    "ScenarioComparisonEntry",
    "ScenarioComparisonReport",
    "SimulationStudioResult",
    "SyntheticOpinionRecord",
    "SyntheticPopulationEvidenceEngine",
    "TemporalCheckpoint",
    "TemporalHorizonSpec",
    "TerritorialContext",
    "TerritorialInterventionDesigner",
    "TerritorialPopulationContextEngine",
    "TerritorialScenarioComparisonEngine",
]
