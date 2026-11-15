"""Local Ollama AI Provider for SALTBOR.

Integrates local LLMs (e.g. Llama 3.2, Mistral, Qwen) using Ollama HTTP endpoints.
Includes health check, connection timeout handling, structured output parsing,
and usage accounting.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any, Dict, Optional

from saltbor.ai.providers.base import (
    AIProviderType,
    AIRequest,
    AIResponse,
    BaseAIProvider,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class OllamaProvider(BaseAIProvider):
    """Adapter for local Ollama instances running on host."""

    def __init__(
        self,
        endpoint: str = "http://localhost:11434/api/generate",
        model: str = "llama3.2",
        timeout_seconds: float = 3.0,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._checked = False
        self._available = False

    @property
    def provider_type(self) -> AIProviderType:
        return AIProviderType.LOCAL_OLLAMA

    def is_available(self) -> bool:
        try:
            tags_url = self.endpoint.replace("/generate", "/tags")
            req = urllib.request.Request(tags_url)
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                self._available = (resp.status == 200)
        except Exception:
            self._available = False
        self._checked = True
        return self._available

    def execute(self, request: AIRequest) -> AIResponse:
        start_t = time.perf_counter()
        if not self.is_available():
            return AIResponse(
                provider_type=self.provider_type,
                model_name=self.model,
                raw_text="",
                structured_data=None,
                is_valid=False,
                error_message="Ollama daemon is not reachable on localhost:11434",
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )

        prompt = request.prompt
        if request.system_instruction:
            prompt = f"System: {request.system_instruction}\n\nUser: {prompt}"

        payload_dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        if request.structured_schema:
            payload_dict["format"] = "json"

        try:
            data = json.dumps(payload_dict).encode("utf-8")
            req = urllib.request.Request(
                self.endpoint,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=request.timeout_seconds) as resp:
                raw_body = resp.read().decode("utf-8")
                res_json = json.loads(raw_body)
                raw_text = res_json.get("response", "")

            structured_data = None
            if request.structured_schema or "{" in raw_text:
                try:
                    structured_data = json.loads(raw_text)
                except Exception:
                    pass

            latency_ms = (time.perf_counter() - start_t) * 1000.0
            prompt_tokens = res_json.get("prompt_eval_count", max(1, len(prompt) // 4))
            eval_tokens = res_json.get("eval_count", max(1, len(raw_text) // 4))

            return AIResponse(
                provider_type=self.provider_type,
                model_name=self.model,
                raw_text=raw_text,
                structured_data=structured_data,
                is_valid=True,
                error_message=None,
                latency_ms=latency_ms,
                usage=TokenUsage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=eval_tokens,
                    total_tokens=prompt_tokens + eval_tokens,
                    estimated_cost_usd=0.0,
                ),
            )
        except Exception as e:
            return AIResponse(
                provider_type=self.provider_type,
                model_name=self.model,
                raw_text="",
                structured_data=None,
                is_valid=False,
                error_message=f"Ollama execution failed: {str(e)}",
                latency_ms=(time.perf_counter() - start_t) * 1000.0,
            )
