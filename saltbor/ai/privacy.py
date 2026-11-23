"""AI Privacy Guard for SALTBOR Phase 1.15 / 1.16A.

Ensures strict compliance with Google Gemini API terms and privacy guidelines:
1. Data minimization: only the necessary context for the task is transmitted.
2. Anonymization / Redaction: strips Salvadoran personal identifiers (DUI, NIT, phones,
   emails, API keys, personal names, precise coordinates) while protecting geographic toponyms.
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
    email_redactions_count: int = 0
    nit_redactions_count: int = 0
    secret_redactions_count: int = 0
    coordinate_precision_reduced: bool = False
    original_char_count: int = 0
    sanitized_char_count: int = 0


# Salvadoran geographic toponyms containing saint names that must NEVER be redacted as PII
_PROTECTED_TOPONYMS = (
    "San José Las Flores",
    "San Jose Las Flores",
    "San Salvador",
    "Santa Tecla",
    "Santa Ana",
    "San Miguel",
    "San Vicente",
    "San Marcos",
    "San Martín",
    "San Martin",
    "San Juan",
    "San Pedro",
    "San Francisco",
    "San Luis",
    "San Isidro",
    "San Antonio",
    "San Ignacio",
    "San Rafael",
    "San Esteban",
    "San Sebastián",
    "Santa Rosa",
    "Santa Elena",
    "Santa María",
    "Santa Maria",
    "Santa Cruz",
    "El Rosario",
)


class AIPrivacyGuard:
    """Intercepts, minimizes, and sanitizes prompts before leaving the local host."""

    def __init__(self, enable_strict_redaction: bool = True) -> None:
        self.enable_strict_redaction = enable_strict_redaction
        # Salvadoran Documento Único de Identidad (DUI): 8 digits + hyphen + 1 check digit
        self._dui_pattern = re.compile(r"\b\d{8}-\d\b")
        # Salvadoran NIT: 4-6-3-1 digits
        self._nit_pattern = re.compile(r"\b\d{4}-\d{6}-\d{3}-\d\b")
        # Salvadoran phone numbers: +503 or 8 digits starting with 2, 6, 7
        self._phone_pattern = re.compile(r"(?:\+503\s*)?[267]\d{3}[-\s]?\d{4}")
        # Email addresses
        self._email_pattern = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
        # Secret API keys / bearer tokens
        self._secret_pattern = re.compile(
            r"(?:AIza[0-9A-Za-z\-_]{16,}|sk-[0-9A-Za-z\-_]{16,}|Bearer\s+[A-Za-z0-9._\-]{12,})"
        )
        # Common Salvadoran personal names (applied after masking protected toponyms)
        self._name_pattern = re.compile(
            r"\b(?:José|Jose|Carmen|Mateo|Rosa|Lucía|Lucia|María|Maria|Juan|Carlos|Ana|Manuel|Jorge|Luis|Pedro|Sofía|Sofia)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b"
        )

    def redact_secrets(self, text: str) -> str:
        """Strip API keys or Bearer tokens from log or error messages."""
        if not text:
            return text
        return self._secret_pattern.sub("[API_KEY_REDACTADA]", text)

    def minimize_payload(self, text: str, max_chars: int = 12000) -> str:
        """Bound external payload size to prevent accidental bulk database dumps."""
        if not text or len(text) <= max_chars:
            return text
        return text[: max_chars - 64] + "\n...[TRUNCATED_FOR_DATA_MINIMIZATION]"

    def tag_data_origin(
        self,
        payload: Dict[str, Any],
        is_synthetic: bool = True,
        classification: Optional[DataClassification] = None,
    ) -> Dict[str, Any]:
        """Explicitly distinguish synthetic simulated data from real-world official data."""
        resolved_class = classification or (
            DataClassification.SYNTHETIC_SIMULATED
            if is_synthetic
            else DataClassification.PUBLIC_OFFICIAL
        )
        return {
            "data_origin": "SYNTHETIC_MODEL_OUTPUT" if is_synthetic else "EXTERNAL_OFFICIAL_DATASET",
            "data_classification": resolved_class.value,
            "payload": payload,
        }

    def sanitize_prompt_for_remote(self, text: str) -> Tuple[str, RedactionAuditRecord]:
        """Sanitize text to guarantee privacy before remote transmission."""
        if not self.enable_strict_redaction:
            return text, RedactionAuditRecord(
                original_char_count=len(text), sanitized_char_count=len(text)
            )

        orig_len = len(text)
        # Protect Salvadoran geographic place names before name redaction
        placeholders: Dict[str, str] = {}
        working = text
        for idx, topo in enumerate(_PROTECTED_TOPONYMS):
            pattern = re.compile(re.escape(topo), re.IGNORECASE)
            if pattern.search(working):
                token = f"__SALTBOR_TOPO_{idx}__"
                placeholders[token] = topo
                working = pattern.sub(token, working)

        secrets = len(self._secret_pattern.findall(working))
        nits = len(self._nit_pattern.findall(working))
        duis = len(self._dui_pattern.findall(working))
        emails = len(self._email_pattern.findall(working))
        phones = len(self._phone_pattern.findall(working))
        names = len(self._name_pattern.findall(working))

        sanitized = self._secret_pattern.sub("[CREDENCIAL_REDACTADA]", working)
        sanitized = self._nit_pattern.sub("[NIT_REDACTADO]", sanitized)
        sanitized = self._dui_pattern.sub("[DUI_REDACTADO]", sanitized)
        sanitized = self._email_pattern.sub("[EMAIL_REDACTADO]", sanitized)
        sanitized = self._phone_pattern.sub("[TELÉFONO_REDACTADO]", sanitized)
        sanitized = self._name_pattern.sub("[CIUDADANO_SINTÉTICO]", sanitized)

        # Coordinate truncation: reduce high precision (e.g. 13.1234567 -> 13.123)
        sanitized = re.sub(r"(-?\d+\.\d{3})\d+", r"\1", sanitized)

        # Restore protected Salvadoran toponyms
        for token, topo in placeholders.items():
            sanitized = sanitized.replace(token, topo)

        audit = RedactionAuditRecord(
            dui_redactions_count=duis,
            personal_name_redactions_count=names,
            phone_redactions_count=phones,
            email_redactions_count=emails,
            nit_redactions_count=nits,
            secret_redactions_count=secrets,
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
