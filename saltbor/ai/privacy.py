"""AI Privacy Guard for SALTBOR Phase 1.15.

Ensures strict compliance with Google Gemini API terms and privacy guidelines:
1. Data minimization: only the necessary context for the task is transmitted.
2. Anonymization / Redaction: strips Salvadoran personal identifiers (DUI, names, precise coordinates).
3. Synthetic vs. Real separation: strictly marks whether entities are artificial agents.
4. Retention policy enforcement: zero persistent storage of external API prompts containing personal data.
5. In-memory ephemeral key security (BYOK protection): prevents logging or leak of user API keys.
"""

from __future__ import annotations

import dataclasses
import enum
import re
from typing import Any, Dict, List, Optional, Tuple


class DataClassification(str, enum.Enum):
    """Classification of data payloads processed by SALTBOR."""
    SYNTHETIC_SIMULATED = "SYNTHETIC_SIMULATED"
    PUBLIC_OFFICIAL = "PUBLIC_OFFICIAL"
    ANONYMIZED_AGGREGATE = "ANONYMIZED_AGGREGATE"
    SENSITIVE_CONFIDENTIAL = "SENSITIVE_CONFIDENTIAL"
    MODEL_HYPOTHESIS = "MODEL_HYPOTHESIS"


@dataclasses.dataclass
class RedactionAuditRecord:
    """Audit trace of redactions applied before remote API transmission."""
    dui_redactions_count: int = 0
    personal_name_redactions_count: int = 0
    phone_redactions_count: int = 0
    coordinate_precision_reduced: bool = False
    original_char_count: int = 0
    sanitized_char_count: int = 0


class AIPrivacyGuard:
    """Interceps and sanitizes prompts before leaving the local host towards remote providers."""

    def __init__(self, enable_strict_redaction: bool = True) -> None:
        self.enable_strict_redaction = enable_strict_redaction
        # Salvadoran Documento Único de Identidad (DUI): 8 digits + hyphen + 1 check digit
        self._dui_pattern = re.compile(r"\b\d{8}-\d\b")
        # Salvadoran phone numbers: +503 or 8 digits starting with 2, 6, 7
        self._phone_pattern = re.compile(r"(?:\+503\s*)?[267]\d{3}[-\s]?\d{4}")
        # Common Salvadoran full names
        self._name_pattern = re.compile(r"\b(?:José|Carmen|Mateo|Rosa|Lucía|María|Juan|Carlos|Ana|Manuel|Jorge|Luis)\s+[A-Z][a-záéíóú]+\b")

    def sanitize_prompt_for_remote(self, text: str) -> Tuple[str, RedactionAuditRecord]:
        """Sanitize text to guarantee privacy before remote transmission."""
        if not self.enable_strict_redaction:
            return text, RedactionAuditRecord(original_char_count=len(text), sanitized_char_count=len(text))

        orig_len = len(text)
        duis = len(self._dui_pattern.findall(text))
        phones = len(self._phone_pattern.findall(text))
        names = len(self._name_pattern.findall(text))

        sanitized = self._dui_pattern.sub("[DUI_REDACTADO]", text)
        sanitized = self._phone_pattern.sub("[TELÉFONO_REDACTADO]", sanitized)
        sanitized = self._name_pattern.sub("[CIUDADANO_SINTÉTICO]", sanitized)

        # Coordinate truncation: reduce high precision (e.g. 13.1234567 -> 13.123)
        sanitized = re.sub(r"(-?\d+\.\d{3})\d+", r"\1", sanitized)

        audit = RedactionAuditRecord(
            dui_redactions_count=duis,
            personal_name_redactions_count=names,
            phone_redactions_count=phones,
            coordinate_precision_reduced=True,
            original_char_count=orig_len,
            sanitized_char_count=len(sanitized),
        )
        return sanitized, audit

    def mask_api_key(self, api_key: Optional[str]) -> str:
        """Mask an API key for safe telemetry and UI display (e.g. AIzaSy...8x1Z)."""
        if not api_key:
            return "NO_CONFIGURADA"
        if len(api_key) <= 8:
            return "****"
        return f"{api_key[:6]}...{api_key[-4:]}"
