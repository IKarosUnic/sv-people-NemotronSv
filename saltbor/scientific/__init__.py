"""SALTBOR Scientific Experimentation & Causal Inference Package (Phase 1.12)."""

from saltbor.scientific.causal import CausalInferenceEngine, StructuralEquation
from saltbor.scientific.counterfactual import CounterfactualCivilizationEngine
from saltbor.scientific.experimentation import ScientificExperimentationEngine
from saltbor.scientific.models import (
    CausalEdge,
    CausalLinkQuality,
    CausalRelationshipType,
    CausalTraceStep,
    CausalTraceTier,
    CausalVariable,
    CounterfactualTrajectoryComparison,
    EvidenceValidationTier,
    ExperimentType,
    InterventionDomain,
    MediationResult,
    MultiSeedExperimentResult,
    MultiTierCausalTrace,
    ScientificExperimentProtocol,
    SensitivityClass,
    SensitivitySweepResult,
    SingleRunResult,
    StratifiedSampleSpec,
    TreatmentEffectEstimate,
)
from saltbor.scientific.salvadoran_context import (
    ElSalvadorResearchContext,
    SALVADORAN_DEPARTMENT_PROFILES,
)
from saltbor.scientific.sampling import PopulationSamplingEngine
from saltbor.scientific.sensitivity import ParameterSensitivityEngine
from saltbor.scientific.traceability import CausalEventTraceabilityEngine
from saltbor.scientific.validation import (
    ExternalBenchmark,
    SALVADORAN_EXTERNAL_BENCHMARKS,
    ScientificValidationFramework,
)
from saltbor.scientific.external_validation import (
    BacktestValidationResult,
    ExternalHistoricalValidator,
    HistoricalTimeSeriesBenchmark,
    SALVADORAN_HISTORICAL_SERIES,
)

__all__ = [
    "BacktestValidationResult",
    "CausalEdge",
    "CausalInferenceEngine",
    "CausalLinkQuality",
    "CausalRelationshipType",
    "CausalTraceStep",
    "CausalTraceTier",
    "CausalVariable",
    "CounterfactualCivilizationEngine",
    "CounterfactualTrajectoryComparison",
    "ElSalvadorResearchContext",
    "EvidenceValidationTier",
    "ExperimentType",
    "ExternalBenchmark",
    "ExternalHistoricalValidator",
    "HistoricalTimeSeriesBenchmark",
    "InterventionDomain",
    "MediationResult",
    "MultiSeedExperimentResult",
    "MultiTierCausalTrace",
    "ParameterSensitivityEngine",
    "PopulationSamplingEngine",
    "SALVADORAN_DEPARTMENT_PROFILES",
    "SALVADORAN_EXTERNAL_BENCHMARKS",
    "SALVADORAN_HISTORICAL_SERIES",
    "ScientificExperimentProtocol",
    "ScientificExperimentationEngine",
    "ScientificValidationFramework",
    "SensitivityClass",
    "SensitivitySweepResult",
    "SingleRunResult",
    "StratifiedSampleSpec",
    "StructuralEquation",
    "TreatmentEffectEstimate",
    "CausalEventTraceabilityEngine",
]
