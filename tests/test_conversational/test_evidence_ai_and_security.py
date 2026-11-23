"""Tests for evidence provenance, grounded opinions, Gemini/Ollama/offline fallback, security, and WAL persistence."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

from saltbor.ai.privacy import AIPrivacyGuard
from saltbor.ai.providers.base import AIProviderType, AIRequest, AITaskCategory
from saltbor.ai.providers.remote import RemoteGeminiProvider
from saltbor.ai.router import AIModelRouter
from saltbor.conversational import (
    AnalyticalVerdict,
    SALTBORConversationalOrchestrator,
)


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._raw = json.dumps(body).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_evidence_provenance_synthetic_opinions_and_missing_data(tmp_path):
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "ev.db", seed=42)
    try:
        a1 = orch.handle_message("Quiero abrir una tienda en Soyapango.")
        b1 = orch.execute_stage_b(a1.conversation_id, a1.scenario_id, seed=42)

        assert b1.evidence.data_classification == "SYNTHETIC_SIMULATED"
        assert len(b1.evidence.indicators) >= 8
        for ind in b1.evidence.indicators:
            assert ind.provenance.source_engine
            assert ind.provenance.seed == 42
            assert ind.provenance.geographic_scope

        assert len(b1.evidence.synthetic_opinions) >= 1
        for op in b1.evidence.synthetic_opinions:
            assert op.is_independent_sample is False
            assert "NOT independent" in op.correlation_warning

        # Missing / unresolved location triggers INSUFFICIENT_EVIDENCE
        a2 = orch.handle_message("Quiero poner una clínica en Aldea Inexistente XYZ.")
        assert a2.clarification_needed is True
        b2 = orch.execute_stage_b(a2.conversation_id, a2.scenario_id, seed=42)
        assert b2.recommendation.verdict == AnalyticalVerdict.INSUFFICIENT_EVIDENCE
    finally:
        orch.close()


def test_deterministic_reproducibility_and_session_resumption(tmp_path):
    db_file = tmp_path / "resume.db"
    orch1 = SALTBORConversationalOrchestrator(persistence_path=db_file, seed=101)
    try:
        s1 = orch1.handle_message("Quiero poner una pupusería en Santa Tecla.")
        r1 = orch1.execute_stage_b(s1.conversation_id, s1.scenario_id, seed=101)
        cid = s1.conversation_id
        rev1 = next(i.value for i in r1.evidence.indicators if i.indicator_id == "commercial_revenue_usd")
    finally:
        orch1.close()

    # Resume conversation in a brand-new orchestrator instance reading SQLite WAL
    orch2 = SALTBORConversationalOrchestrator(persistence_path=db_file, seed=101)
    try:
        loaded = orch2.persistence.load_session(cid)
        assert loaded is not None
        assert loaded.active_district_id is not None
        assert len(loaded.turns) >= 3
        fu = orch2.handle_message("¿Y si contrato dos empleados más?", conversation_id=cid)
        assert fu.parsed_request.is_follow_up is True
        assert fu.proposed_intervention.workforce_count == 4

        # Same seed yields identical commercial revenue
        orch_cmp = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "cmp.db", seed=101)
        try:
            s_cmp = orch_cmp.handle_message("Quiero poner una pupusería en Santa Tecla.")
            r_cmp = orch_cmp.execute_stage_b(s_cmp.conversation_id, s_cmp.scenario_id, seed=101)
            rev_cmp = next(i.value for i in r_cmp.evidence.indicators if i.indicator_id == "commercial_revenue_usd")
            assert rev1 == rev_cmp
        finally:
            orch_cmp.close()
    finally:
        orch2.close()


def test_gemini_mock_ollama_fallback_and_offline_mode(tmp_path):
    # 1. Mocked Gemini success (validates header auth, Flash model routing, and Pydantic merge)
    router = AIModelRouter(allow_remote=True)
    router.gemini_provider.set_byok_key("AIzaSyFakeStudioKey1234567890")
    orch = SALTBORConversationalOrchestrator(router=router, persistence_path=tmp_path / "gem.db", seed=42)
    try:
        stage_a = orch.handle_message("Quiero abrir una pupusería en Santa Tecla.")
        captured_requests = []

        def _mock_urlopen(req, timeout=10.0):
            captured_requests.append((req.full_url, dict(req.header_items())))
            body = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "verdict": "CONDITIONALLY_PROMISING",
                                            "executive_summary": "Demanda simulada favorable condicionada al control de costos.",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 25},
            }
            return _FakeHTTPResponse(body)

        with patch("urllib.request.urlopen", side_effect=_mock_urlopen):
            res = orch.execute_stage_b(stage_a.conversation_id, stage_a.scenario_id, seed=42)

        assert res.recommendation.provider_used == AIProviderType.REMOTE_GEMINI.value
        assert len(captured_requests) >= 1
        req_url, req_headers = captured_requests[-1]
        assert "key=" not in req_url  # API key must NOT leak in URL query string!
        assert any(k.lower() == "x-goog-api-key" for k in req_headers)

        # 2. Gemini 429 failure -> falls back cleanly to Ollama or OfflineDeterministic
        def _mock_429(req, timeout=10.0):
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b""))

        orch.budget_manager._cache.clear()
        with patch("urllib.request.urlopen", side_effect=_mock_429):
            res_fb = orch.execute_stage_b(stage_a.conversation_id, stage_a.scenario_id, seed=43)

        assert res_fb.recommendation.provider_used in (
            AIProviderType.LOCAL_OLLAMA.value,
            AIProviderType.OFFLINE_DETERMINISTIC.value,
        )
        assert res_fb.evidence.ledger_audit["conservation_passed"] is True
    finally:
        orch.close()


def test_privacy_redaction_preserves_toponyms_and_blocks_code_execution():
    guard = AIPrivacyGuard()
    raw = (
        "Evaluar en Cantón San José Las Flores y Santa Tecla para Juan Pérez "
        "DUI 01234567-8 NIT 0614-120590-102-3 tel +503 7123-4567 email juan@example.com "
        "key AIzaSySecretTokenValue123456 coord 13.6978567,-89.1914231"
    )
    sanitized, audit = guard.sanitize_prompt_for_remote(raw)
    assert "San José Las Flores" in sanitized
    assert "Santa Tecla" in sanitized
    assert "01234567-8" not in sanitized
    assert "0614-120590-102-3" not in sanitized
    assert "7123-4567" not in sanitized
    assert "juan@example.com" not in sanitized
    assert "AIzaSySecretTokenValue" not in sanitized
    assert "Juan Pérez" not in sanitized
    assert "13.697," in sanitized
    assert audit.dui_redactions_count == 1
    assert audit.nit_redactions_count == 1
    assert audit.email_redactions_count == 1
    assert audit.secret_redactions_count == 1

    # Reject code execution payloads returned by remote model
    gemini = RemoteGeminiProvider(api_key="AIzaSyFakeKey987654321", max_requests_per_minute=2)
    with patch(
        "urllib.request.urlopen",
        return_value=_FakeHTTPResponse(
            {"candidates": [{"content": {"parts": [{"text": "__import__('os').system('calc')"}]}}]}
        ),
    ):
        resp = gemini.execute(AIRequest(task_category=AITaskCategory.RESULTS_ANALYSIS, prompt="Test"))
        assert resp.is_valid is False
        assert "unsafe" in (resp.error_message or "").lower()

    # Rate limit enforcement (2 req/min configured above -> 2nd succeeds or fails, 3rd rate-limited)
    with patch("urllib.request.urlopen", return_value=_FakeHTTPResponse({"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})):
        _ = gemini.execute(AIRequest(task_category=AITaskCategory.SCENARIO_EXTRACTION, prompt="Test 2"))
        r3 = gemini.execute(AIRequest(task_category=AITaskCategory.SCENARIO_EXTRACTION, prompt="Test 3"))
        assert r3.is_valid is False
        assert "rate limit" in (r3.error_message or "").lower()
