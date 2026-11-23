"""Remote AI Provider Adapters (Gemini-First Architecture) for SALTBOR.

Includes:
- Configurable Gemini model IDs (no hardcoded obsolete model versions):
  * Flash-Lite (default via env SALTBOR_GEMINI_FLASH_LITE_MODEL or gemini-2.5-flash-lite):
    fast intent extraction, structured JSON normalization, geographic validation.
  * Flash (default via env SALTBOR_GEMINI_FLASH_MODEL or gemini-2.5-flash):
    evidence synthesis, counterfactual reasoning, uncertainty analysis.
- Secure header-based BYOK transmission (`x-goog-api-key`), never in URL query params.
- Sliding-window rate limiting and daily quota protection.
- Optional protected backend proxy support.
- Pydantic v2 structured output validation and anti-code-execution safety guard.
- Robust HTTP status code handling (429, 401, 403, 5xx) with automatic failover.
- Data minimization and privacy redaction via AIPrivacyGuard.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Deque, Dict, Optional, Type

from pydantic import BaseModel, ValidationError

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

_FORBIDDEN_CODE_EXEC_PATTERN = re.compile(
    r"(?:__import__\s*\(|subprocess\.(?:run|Popen|call)|os\.system\s*\(|\beval\s*\(|\bexec\s*\()",
    re.IGNORECASE,
)


class GeminiModelTier(str):
    """Configurable Google Gemini model identifiers (non-obsolete defaults)."""

    FLASH_LITE = os.getenv("SALTBOR_GEMINI_FLASH_LITE_MODEL", "gemini-2.5-flash-lite")
    FLASH = os.getenv("SALTBOR_GEMINI_FLASH_MODEL", "gemini-2.5-flash")
    PRO = os.getenv("SALTBOR_GEMINI_PRO_MODEL", "gemini-2.5-pro")


def validate_structured_output(
    raw_data: Any,
    schema_model: Type[BaseModel],
) -> tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Validate structured dictionary/JSON output strictly against a Pydantic v2 model."""
    if not isinstance(raw_data, dict):
        return False, None, "Structured output must be a JSON object."
    try:
        validated = schema_model.model_validate(raw_data)
        return True, validated.model_dump(mode="json"), None
    except ValidationError as ve:
        return False, None, f"Structured output failed Pydantic validation: {ve.error_count()} error(s)"


class RemoteGeminiProvider(BaseAIProvider):
    """Primary Remote Provider implementing Google Gemini API integration."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
        flash_lite_model: Optional[str] = None,
        flash_model: Optional[str] = None,
        privacy_guard: Optional[AIPrivacyGuard] = None,
        max_requests_per_minute: int = 30,
        max_daily_requests: int = 1000,
        proxy_url: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.flash_lite_model = flash_lite_model or os.getenv(
            "SALTBOR_GEMINI_FLASH_LITE_MODEL", GeminiModelTier.FLASH_LITE
        )
        self.flash_model = flash_model or os.getenv(
            "SALTBOR_GEMINI_FLASH_MODEL", GeminiModelTier.FLASH
        )
        self.default_model = default_model or self.flash_model
        self.privacy_guard = privacy_guard or AIPrivacyGuard()
        self.proxy_url = proxy_url or os.getenv("SALTBOR_GEMINI_PROXY_URL")

        self.max_requests_per_minute = max(1, int(max_requests_per_minute))
        self.max_daily_requests = max(1, int(max_daily_requests))
        self._recent_timestamps: Deque[float] = collections.deque()
        self._daily_window_start: float = time.time()
        self._daily_count: int = 0

        self.quota_exhausted: bool = False
        self.last_error_code: Optional[int] = None
        self.last_error_message: Optional[str] = None

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.REMOTE_GEMINI

    def configure_models(
        self,
        flash_lite_model: Optional[str] = None,
        flash_model: Optional[str] = None,
    ) -> None:
        """Update configurable Gemini model identifiers at runtime."""
        if flash_lite_model and flash_lite_model.strip():
            self.flash_lite_model = flash_lite_model.strip()
        if flash_model and flash_model.strip():
            self.flash_model = flash_model.strip()
            self.default_model = self.flash_model

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
        """Check if an API key (or proxy) is configured and quota is not exhausted."""
        has_auth = bool(self._api_key) or bool(self.proxy_url)
        return has_auth and not self.quota_exhausted

    def _check_and_record_rate_limit(self) -> Optional[str]:
        """Enforce sliding-window RPM and daily quotas locally before remote call."""
        now = time.time()
        if now - self._daily_window_start >= 86400.0:
            self._daily_window_start = now
            self._daily_count = 0

        while self._recent_timestamps and (now - self._recent_timestamps[0]) >= 60.0:
            self._recent_timestamps.popleft()

        if len(self._recent_timestamps) >= self.max_requests_per_minute:
            return f"Local rate limit reached ({self.max_requests_per_minute} req/min)."
        if self._daily_count >= self.max_daily_requests:
            return f"Local daily quota reached ({self.max_daily_requests} req/day)."

        self._recent_timestamps.append(now)
        self._daily_count += 1
        return None

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Expose current rate-limit & quota counters without revealing secrets."""
        now = time.time()
        active_rpm = sum(1 for ts in self._recent_timestamps if (now - ts) < 60.0)
        return {
            "requests_last_minute": active_rpm,
            "max_requests_per_minute": self.max_requests_per_minute,
            "daily_requests": self._daily_count,
            "max_daily_requests": self.max_daily_requests,
            "flash_lite_model": self.flash_lite_model,
            "flash_model": self.flash_model,
            "proxy_configured": bool(self.proxy_url),
        }

    def _select_model_for_task(self, request: AIRequest) -> str:
        """Select appropriate Gemini tier based on task complexity."""
        override_model = request.metadata.get("model_override")
        if isinstance(override_model, str) and override_model.strip():
            return override_model.strip()

        if request.task_category in (
            AITaskCategory.SCENARIO_EXTRACTION,
            AITaskCategory.GEOGRAPHIC_VALIDATION,
        ):
            return self.flash_lite_model
        return self.flash_model

    def _build_endpoint_url(self, model_name: str) -> str:
        """Construct endpoint URL without embedding API keys in query strings."""
        if self.proxy_url:
            base = self.proxy_url.rstrip("/")
            return f"{base}/v1beta/models/{model_name}:generateContent"
        return f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

    @staticmethod
    def _contains_unsafe_code_payload(text: str) -> bool:
        """Reject model outputs that attempt executable code injection."""
        return bool(_FORBIDDEN_CODE_EXEC_PATTERN.search(text or ""))

    def execute(self, request: AIRequest) -> AIResponse:
        start_t = time.perf_counter()
        if not self.is_available():
            err = (
                "Quota exhausted (HTTP 429)"
                if self.quota_exhausted
                else "Gemini API key not configured (BYOK required)."
            )
            return AIResponse(
                provider_type=self.provider_type,
                model_name=self.default_model,
                raw_text="",
                structured_data=None,
                is_valid=False,
                error_message=err,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        rate_err = self._check_and_record_rate_limit()
        if rate_err:
            self.last_error_message = rate_err
            return AIResponse(
                provider_type=self.provider_type,
                model_name=self.default_model,
                raw_text="",
                structured_data=None,
                is_valid=False,
                error_message=rate_err,
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        model_name = self._select_model_for_task(request)

        # 1. Apply privacy sanitization + payload minimization
        minimized_prompt = self.privacy_guard.minimize_payload(request.prompt, max_chars=12000)
        sanitized_prompt, _audit = self.privacy_guard.sanitize_prompt_for_remote(minimized_prompt)

        # 2. Build Gemini REST API payload (key sent strictly via header)
        url = self._build_endpoint_url(model_name)
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["x-goog-api-key"] = self._api_key

        generation_cfg: Dict[str, Any] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
        }
        if request.structured_schema:
            generation_cfg["responseMimeType"] = "application/json"
            if isinstance(request.structured_schema, dict) and request.structured_schema:
                generation_cfg["responseSchema"] = request.structured_schema

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": sanitized_prompt}]}],
            "generationConfig": generation_cfg,
        }
        if request.system_instruction:
            sanitized_sys, _ = self.privacy_guard.sanitize_prompt_for_remote(request.system_instruction)
            payload["systemInstruction"] = {"parts": [{"text": sanitized_sys}]}

        # 3. Execute with error detection & backoff
        max_retries = 2
        backoff_delay = 1.0

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                )
                with urllib.request.urlopen(req, timeout=request.timeout_seconds) as resp:
                    res_body = json.loads(resp.read().decode("utf-8"))

                candidates = res_body.get("candidates", [])
                raw_text = ""
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        raw_text = parts[0].get("text", "")

                if self._contains_unsafe_code_payload(raw_text):
                    self.last_error_message = "Rejected unsafe code-like content returned by remote model."
                    return AIResponse(
                        provider_type=self.provider_type,
                        model_name=model_name,
                        raw_text="",
                        structured_data=None,
                        is_valid=False,
                        error_message=self.last_error_message,
                        latency_ms=(time.perf_counter() - start_t) * 1000.0,
                    )

                structured = None
                if request.structured_schema or "{" in raw_text:
                    try:
                        structured = json.loads(raw_text)
                    except Exception:
                        structured = None

                pydantic_model = request.metadata.get("pydantic_schema")
                if pydantic_model is not None:
                    ok, validated_dict, val_err = validate_structured_output(structured, pydantic_model)
                    if not ok:
                        return AIResponse(
                            provider_type=self.provider_type,
                            model_name=model_name,
                            raw_text=raw_text,
                            structured_data=None,
                            is_valid=False,
                            error_message=val_err,
                            latency_ms=(time.perf_counter() - start_t) * 1000.0,
                        )
                    structured = validated_dict

                latency_ms = (time.perf_counter() - start_t) * 1000.0
                usage_meta = res_body.get("usageMetadata", {})
                prompt_tokens = usage_meta.get("promptTokenCount", max(1, len(sanitized_prompt) // 4))
                cand_tokens = usage_meta.get("candidatesTokenCount", max(1, len(raw_text) // 4))
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
                    self.last_error_message = (
                        "Gemini API free quota limit exceeded (HTTP 429). Conmuting to local/offline engine."
                    )
                    logger.warning("Gemini 429 Resource Exhausted. Triggering failover.")
                    break
                if he.code in (401, 403):
                    self.last_error_message = (
                        f"Gemini API authentication failed (HTTP {he.code}). Check BYOK key."
                    )
                    break
                if he.code >= 500 and attempt < max_retries - 1:
                    time.sleep(backoff_delay)
                    backoff_delay *= 2.0
                    continue
                self.last_error_message = f"HTTP Error {he.code}: {he.reason}"
                break
            except Exception as e:
                safe_msg = self.privacy_guard.redact_secrets(str(e))
                self.last_error_message = safe_msg
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

        return AIResponse(
            provider_type=self.provider_type,
            model_name=self.model,
            raw_text="",
            is_valid=False,
            error_message="OpenAI execution skipped.",
            latency_ms=(time.perf_counter() - start_t) * 1000.0,
        )
