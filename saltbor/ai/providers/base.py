"""Base interfaces and data structures for SALTBOR AI Intelligence Layer.

Provides provider-independent abstractions, structured request/response containers,
token usage accounting, and strict schema validation primitives.
"""

from __future__ import annotations

import abc
import dataclasses
import enum
import time
from typing import Any, Dict, List, Optional


class AIProviderType(str, enum.Enum):
    """Categorization of supported AI execution backends."""
    OFFLINE_DETERMINISTIC = "OFFLINE_DETERMINISTIC"
    LOCAL_OLLAMA = "LOCAL_OLLAMA"
    REMOTE_GEMINI = "REMOTE_GEMINI"
    REMOTE_OPENAI = "REMOTE_OPENAI"
    MOCK = "MOCK"


class AITaskCategory(str, enum.Enum):
    """Functional task categories for dynamic model routing."""
    SCENARIO_EXTRACTION = "SCENARIO_EXTRACTION"
    GEOGRAPHIC_VALIDATION = "GEOGRAPHIC_VALIDATION"
    CAUSAL_PROPOSAL = "CAUSAL_PROPOSAL"
    POLICY_PLANNING = "POLICY_PLANNING"
    RESULTS_ANALYSIS = "RESULTS_ANALYSIS"
    COUNTERFACTUAL_COMPARISON = "COUNTERFACTUAL_COMPARISON"


@dataclasses.dataclass
class TokenUsage:
    """Usage accounting metrics for AI model executions."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclasses.dataclass
class AIRequest:
    """Standardized request envelope for AI model invocations."""
    task_category: AITaskCategory
    prompt: str
    system_instruction: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 1000
    structured_schema: Optional[Dict[str, Any]] = None
    anonymize_sensitive_data: bool = True
    timeout_seconds: float = 10.0
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class AIResponse:
    """Standardized response envelope from an AI provider."""
    provider_type: AIProviderType
    model_name: str
    raw_text: str
    structured_data: Optional[Dict[str, Any]] = None
    is_valid: bool = True
    error_message: Optional[str] = None
    latency_ms: float = 0.0
    usage: TokenUsage = dataclasses.field(default_factory=TokenUsage)
    cached: bool = False


class BaseAIProvider(abc.ABC):
    """Abstract interface defining required capabilities for any AI provider in SALTBOR."""

    @property
    @abc.abstractmethod
    def provider_type(self) -> AIProviderType:
        """Return the enum classification of this provider."""
        raise NotImplementedError

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Perform a quick, non-blocking health check to verify availability."""
        raise NotImplementedError

    @abc.abstractmethod
    def execute(self, request: AIRequest) -> AIResponse:
        """Synchronously execute the request and return a standardized AIResponse."""
        raise NotImplementedError
