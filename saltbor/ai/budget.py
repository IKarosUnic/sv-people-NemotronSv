"""AI Compute Budget and Usage Manager for SALTBOR.

Tracks tokens, estimated expenditures, request latencies, in-memory caching,
and enforces spending and request limits.
"""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from saltbor.ai.providers.base import (
    AIRequest,
    AIResponse,
    TokenUsage,
)

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class BudgetLimits:
    """Configurable spending and usage constraints."""
    max_monthly_budget_usd: float = 10.0
    max_requests_per_session: int = 500
    enforce_offline_at_budget_exhaustion: bool = True


class AIComputeBudgetManager:
    """Manages AI request accounting, token metrics, and caching."""

    def __init__(self, limits: Optional[BudgetLimits] = None) -> None:
        self.limits = limits or BudgetLimits()
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.total_spend_usd: float = 0.0
        self.total_requests: int = 0
        self.request_history: List[Dict[str, Any]] = []
        self._cache: Dict[str, AIResponse] = {}

    def _compute_cache_key(self, request: AIRequest) -> str:
        """Create a deterministic hash for request caching."""
        key_content = f"{request.task_category.value}:{request.prompt}:{request.temperature}"
        return hashlib.sha256(key_content.encode("utf-8")).hexdigest()

    def get_cached_response(self, request: AIRequest) -> Optional[AIResponse]:
        """Retrieve cached response if available."""
        key = self._compute_cache_key(request)
        if key in self._cache:
            cached = self._cache[key]
            # Return copy marked as cached
            return dataclasses.replace(cached, cached=True)
        return None

    def record_execution(self, request: AIRequest, response: AIResponse) -> None:
        """Record token consumption and cache successful result."""
        self.total_requests += 1
        self.total_prompt_tokens += response.usage.prompt_tokens
        self.total_completion_tokens += response.usage.completion_tokens
        self.total_spend_usd += response.usage.estimated_cost_usd

        # Log entry
        self.request_history.append({
            "timestamp": time.time(),
            "category": request.task_category.value,
            "provider": response.provider_type.value,
            "model": response.model_name,
            "latency_ms": response.latency_ms,
            "tokens": response.usage.total_tokens,
            "cost_usd": response.usage.estimated_cost_usd,
            "cached": response.cached,
        })

        # Cache valid response if not already cached
        if response.is_valid and not response.cached:
            key = self._compute_cache_key(request)
            self._cache[key] = response

    def is_budget_exceeded(self) -> bool:
        """Check if user-configured spending or request limits are reached."""
        if self.total_spend_usd >= self.limits.max_monthly_budget_usd:
            return True
        if self.total_requests >= self.limits.max_requests_per_session:
            return True
        return False

    def get_summary_report(self) -> Dict[str, Any]:
        """Generate cumulative usage and cost accounting metrics."""
        return {
            "total_requests": self.total_requests,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_spend_usd": round(self.total_spend_usd, 6),
            "budget_limit_usd": self.limits.max_monthly_budget_usd,
            "budget_exceeded": self.is_budget_exceeded(),
            "cache_entries": len(self._cache),
            "recent_requests_count": len(self.request_history),
        }
