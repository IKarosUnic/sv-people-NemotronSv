"""Remote AI Provider Adapters (Gemini-First Architecture) for SALTBOR.

Includes:
- Gemini Flash-Lite: fast extraction, classification, structured JSON normalization.
- Gemini Flash: complex scenario formulation, causal planning, results interpretation.
- Robust HTTP status code handling: 429 (Resource Exhausted / Free Quota Exceeded),
  403 (Forbidden / Billing Not Enabled), 503 (Unavailable).
- Automatic Exponential Backoff and transparent failover triggering.
- Data minimization and privacy redaction via AIPrivacyGuard.
- Ephemeral in-memory BYOK (Bring Your Own Key) handling without disk persistence.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from saltbor.ai.privacy import AIPrivacyGuard
from saltbor.ai.providers.base import (
    AIProviderType,
    AIRequest,
    AIResponse,
    AITaskCategory,
    BaseAIProvider,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class GeminiModelTier(str):
    """Supported Google Gemini model identifiers."""
    FLASH_LITE = "gemini-2.0-flash-lite"
    FLASH = "gemini-1.5-flash"
    PRO = "gemini-1.5-pro"


class RemoteGeminiProvider(BaseAIProvider):
    """Primary Remote Provider implementing Google Gemini API integration."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: str = GeminiModelTier.FLASH,
        privacy_guard: Optional[AIPrivacyGuard] = None,
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.default_model = default_model
        self.privacy_guard = privacy_guard or AIPrivacyGuard()
        self.quota_exhausted: bool = False
        self.last_error_code: Optional[int] = None
        self.last_error_message: Optional[str] = None

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.REMOTE_GEMINI

    def set_byok_key(self, api_key: str) -> None:
        """Dynamically configure or rotate user's BYOK key in memory."""
        self._api_key = api_key.strip()
        self.quota_exhausted = False
        self.last_error_code = None
        self.last_error_message = None

    def clear_byok_key(self) -> None:
        """Clear the in-memory API key completely."""
        self._api_key = None
        self.quota_exhausted = False

    def is_available(self) -> bool:
        """Check if an API key is configured and not permanently blocked by 429."""
        return bool(self._api_key) and not self.quota_exhausted

    def _select_model_for_task(self, request: AIRequest) -> str:
        """Select appropriate Gemini tier based on task complexity."""
        # Simple extraction and validation -> Flash-Lite
        if request.task_category in [AITaskCategory.SCENARIO_EXTRACTION, AITaskCategory.GEOGRAPHIC_VALIDATION]:
            return GeminiModelTier.FLASH_LITE
        # Complex reasoning, planning, and counterfactuals -> Flash
        return GeminiModelTier.FLASH

    def execute(self, request: AIRequest) -> AIResponse:
        start_t = time.perf_counter()
        if not self.is_available():
            err = "Quota exhausted (HTTP 429)" if self.quota_exhausted else "Gemini API key not configured (BYOK required)."
            return AIResponse(
                provider_type=self.provider_type,
                model_name=self.default_model,
                raw_text="",
                structured_data=None,
                is_valid=False,
                error_message=err,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        model_name = self._select_model_for_task(request)

        # 1. Apply privacy sanitization
        sanitized_prompt, audit = self.privacy_guard.sanitize_prompt_for_remote(request.prompt)

        # 2. Build Gemini REST API payload
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self._api_key}"
        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": sanitized_prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if request.system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": request.system_instruction}]}
        if request.structured_schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        # 3. Execute with error detection & backoff
        max_retries = 2
        backoff_delay = 1.0

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=request.timeout_seconds) as resp:
                    res_body = json.loads(resp.read().decode("utf-8"))

                candidates = res_body.get("candidates", [])
                raw_text = ""
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        raw_text = parts[0].get("text", "")

                structured = None
                if request.structured_schema or "{" in raw_text:
                    try:
                        structured = json.loads(raw_text)
                    except Exception:
                        pass

                latency_ms = (time.perf_counter() - start_t) * 1000.0
                usage_meta = res_body.get("usageMetadata", {})
                prompt_tokens = usage_meta.get("promptTokenCount", max(1, len(sanitized_prompt) // 4))
                cand_tokens = usage_meta.get("candidatesTokenCount", max(1, len(raw_text) // 4))

                # Rate estimates for Gemini Free/Paid Tier
                cost_estimate = (prompt_tokens * 0.075 + cand_tokens * 0.30) / 1_000_000.0

                return AIResponse(
                    provider_type=self.provider_type,
                    model_name=model_name,
                    raw_text=raw_text,
                    structured_data=structured,
                    is_valid=True,
                    latency_ms=latency_ms,
                    usage=TokenUsage(
                        prompt_tokens=prompt_tokens,
                        completion_tokens=cand_tokens,
                        total_tokens=prompt_tokens + cand_tokens,
                        estimated_cost_usd=cost_estimate,
                    ),
                )
            except urllib.error.HTTPError as he:
                self.last_error_code = he.code
                if he.code == 429:
                    self.quota_exhausted = True
                    self.last_error_message = "Gemini API free quota limit exceeded (HTTP 429). Conmuting to local/offline engine."
                    logger.warning("Gemini 429 Resource Exhausted. Triggering failover.")
                    break
                elif he.code in [401, 403]:
                    self.last_error_message = f"Gemini API authentication failed (HTTP {he.code}). Check BYOK key."
                    break
                elif he.code >= 500 and attempt < max_retries - 1:
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
                    continue
                else:
                    self.last_error_message = f"HTTP Error {he.code}: {he.reason}"
                    break
            except Exception as e:
                self.last_error_message = str(e)
                break

        return AIResponse(
            provider_type=self.provider_type,
            model_name=model_name,
            raw_text="",
            is_valid=False,
            error_message=self.last_error_message or "Gemini API call failed",
            latency_ms=(time.perf_counter() - start_t) * 1000.0,
        )


class RemoteOpenAIProvider(BaseAIProvider):
    """Optional OpenAI Compatible Provider (Disabled by default)."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.enabled = False  # Disabled by default per architecture rule

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.REMOTE_OPENAI

    def is_available(self) -> bool:
        return self.enabled and bool(self._api_key)

    def execute(self, request: AIRequest) -> AIResponse:
        start_t = time.perf_counter()
        if not self.is_available():
            return AIResponse(
                provider_type=self.provider_type,
                model_name=self.model,
                raw_text="",
                is_valid=False,
                error_message="OpenAI compatible provider is disabled by default.",
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        # Standard minimal implementation
        return AIResponse(
            provider_type=self.provider_type,
            model_name=self.model,
            raw_text="",
            is_valid=False,
            error_message="OpenAI execution skipped.",
            latency_ms=(time.perf_counter() - start_t) * 1000.0,
        )
