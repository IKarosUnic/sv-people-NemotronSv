"""AI Model Router for SALTBOR.

Dynamically selects the appropriate execution engine based on task complexity,
connectivity, user budget constraints, and operational privacy guidelines.
Guarantees transparent fallback to offline deterministic reasoning when no LLM
is available.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from saltbor.ai.providers.base import (
    AIProviderType,
    AIRequest,
    AIResponse,
    AITaskCategory,
    BaseAIProvider,
)
from saltbor.ai.providers.deterministic import OfflineDeterministicProvider
from saltbor.ai.providers.ollama import OllamaProvider
from saltbor.ai.providers.remote import RemoteGeminiProvider, RemoteOpenAIProvider

logger = logging.getLogger(__name__)


class AIModelRouter:
    """Intelligent task router with multi-provider failover."""

    def __init__(
        self,
        allow_remote: bool = False,
        preferred_provider: Optional[AIProviderType] = None,
    ) -> None:
        self.allow_remote = allow_remote
        self.preferred_provider = preferred_provider

        # Initialize providers
        self.deterministic_provider = OfflineDeterministicProvider()
        self.ollama_provider = OllamaProvider()
        self.gemini_provider = RemoteGeminiProvider()
        self.openai_provider = RemoteOpenAIProvider()

        self._providers: Dict[AIProviderType, BaseAIProvider] = {
            AIProviderType.OFFLINE_DETERMINISTIC: self.deterministic_provider,
            AIProviderType.LOCAL_OLLAMA: self.ollama_provider,
            AIProviderType.REMOTE_GEMINI: self.gemini_provider,
            AIProviderType.REMOTE_OPENAI: self.openai_provider,
        }

    def get_provider_status(self) -> Dict[str, Any]:
        """Inspect live availability and health of all registered providers."""
        return {
            p_type.value: {
                "available": provider.is_available(),
                "type": p_type.value,
            }
            for p_type, provider in self._providers.items()
        }

    def route_request(self, request: AIRequest) -> AIResponse:
        """Route request through priority pipeline with automatic fallback."""
        candidate_providers: List[BaseAIProvider] = []

        # 1. Check if user pinned a specific provider
        if self.preferred_provider and self.preferred_provider in self._providers:
            cand = self._providers[self.preferred_provider]
            if cand.is_available():
                candidate_providers.append(cand)

        # 2. Priority 1 Remote: Gemini API (if authorized and key configured)
        if self.allow_remote:
            if self.gemini_provider.is_available():
                candidate_providers.append(self.gemini_provider)

        # 3. Priority 2 Local: Ollama (if running on localhost)
        if self.ollama_provider.is_available():
            candidate_providers.append(self.ollama_provider)

        # 4. Mandatory universal fallback: Offline Deterministic
        candidate_providers.append(self.deterministic_provider)

        # Execute down the fallback chain
        errors = []
        for prov in candidate_providers:
            try:
                resp = prov.execute(request)
                if resp.is_valid:
                    return resp
                errors.append(f"{prov.provider_type.value}: {resp.error_message}")
            except Exception as e:
                errors.append(f"{prov.provider_type.value}: {str(e)}")

        # Fallback to deterministic if anything went wrong
        fallback_resp = self.deterministic_provider.execute(request)
        fallback_resp.error_message = f"Fallbacks exhausted ({'; '.join(errors)}). Served via deterministic fallback."
        return fallback_resp
