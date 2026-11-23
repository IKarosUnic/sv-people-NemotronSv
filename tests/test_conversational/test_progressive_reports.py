"""Comprehensive verification suite for SALTBOR Progressive Intelligence & Multilevel Reports (Fases 1-7)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from saltbor.conversational import (
    BasicReportView,
    EvidenceIndicator,
    EvidenceProvenance,
    ExpertReportView,
    ExplainedMetricCard,
    IntermediateReportView,
    ProgressiveReportBuilder,
    ProgressiveReportBundle,
    ReportDepthLevel,
    SALTBORConversationalOrchestrator,
    UniversalEvidenceOrigin,
)
from saltbor.conversational.progressive_reports import (
    classify_empirical_calibration,
    enrich_indicator,
    generate_contextual_explanations,
    normalize_evidence_origin,
)
from saltbor.visualization.api import router
from saltbor.visualization.routers.conversational_studio_router import set_studio_orchestrator
from saltbor.visualization.server import create_app


def _make_indicator(
    indicator_id: str,
    name: str,
    value,
    *,
    unit: str = "USD",
    data_origin: str = "SYNTHETIC_SIMULATED",
    source_engine: str = "CommercialEngine",
    calculation_method: str = "agent-based bounded rationality",
    population_scope: str = "n=40 hydrated cohort",
    available: bool = True,
) -> EvidenceIndicator:
    return EvidenceIndicator(
        indicator_id=indicator_id,
        domain="commercial",
        name=name,
        definition=f"Definición auditable de {name}.",
        value=value,
        unit=unit,
        data_origin=data_origin,
        uncertainty="Incertidumbre asociada al muestreo de cohorte sintética.",
        is_synthetic=(data_origin not in ("GEOGRAPHIC_DATASET",)),
        available=available,
        provenance=EvidenceProvenance(
            source_engine=source_engine,
            source_entity="Santa Tecla",
            calculation_method=calculation_method,
            time_interval="14 días (336 ticks eq.)",
            population_scope=population_scope,
            geographic_scope="Santa Tecla, La Libertad",
            seed=42,
            data_quality=0.85,
            confidence=0.75,
            limitations="Modelo sintético local sin calibración POS empírica.",
        ),
    )


@pytest.fixture()
def prog_client(tmp_path) -> Iterator[TestClient]:
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "prog_api.db", seed=42)
    set_studio_orchestrator(orch)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    try:
        yield client
    finally:
        set_studio_orchestrator(None)
        orch.close()


def test_fase1_presentation_only_default_basic_and_numeric_preservation(tmp_path) -> None:
    """Level selection changes only presentation, defaults to BASIC, preserves conservation & all numbers."""
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "f1.db", seed=42)
    try:
        s = orch.handle_message("Quiero abrir una pupusería en Santa Tecla durante 14 días.")
        res = orch.execute_stage_b(s.conversation_id, s.scenario_id, seed=42, compare_alternatives=True)

        assert res.evidence.ledger_audit["conservation_passed"] is True
        assert abs(res.evidence.ledger_audit["cash_conservation_diff_usd"]) < 1e-6

        prog = res.progressive_report
        assert isinstance(prog, ProgressiveReportBundle)
        assert prog.default_level == ReportDepthLevel.BASIC
        assert prog.available_levels == [
            ReportDepthLevel.BASIC,
            ReportDepthLevel.INTERMEDIATE,
            ReportDepthLevel.EXPERT,
        ]
        assert prog.source_seed == 42
        assert prog.source_execution_id == res.execution_id
        assert prog.source_scenario_id == res.scenario_id

        # Rebuilding progressive views is pure & idempotent (never re-runs simulation or alters numbers)
        ev_before = {i.indicator_id: i.value for i in res.evidence.indicators}
        rebuilt = ProgressiveReportBuilder.build_from_studio_result(res)
        ev_after = {i.indicator_id: i.value for i in res.evidence.indicators}
        assert ev_before == ev_after
        assert rebuilt.canonical_numeric_fingerprint == prog.canonical_numeric_fingerprint

        # Zero lost indicators in EXPERT view
        assert len(prog.expert.all_indicators) == len(res.evidence.indicators)
        expert_map = {c.indicator_id: c.raw_value for c in prog.expert.all_indicators}
        assert expert_map == ev_before

        # Accounting consistency between BASIC summary cards and underlying revenue - net_profit
        rev_val = ev_before.get("commercial_revenue_usd")
        net_val = ev_before.get("commercial_net_profit_usd")
        if rev_val is not None and net_val is not None and prog.basic.estimated_expenses is not None:
            expected_exp = round(float(rev_val) - float(net_val), 2)
            assert prog.basic.estimated_expenses.raw_value == pytest.approx(expected_exp, abs=0.01)
    finally:
        orch.close()


def test_fase2_basic_view_required_sections_and_non_guarantee(tmp_path) -> None:
    """BASIC level exposes plain Spanish explanations for all required blocks and never guarantees profits."""
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "f2.db", seed=42)
    try:
        s = orch.handle_message("Quiero abrir una farmacia en San Miguel durante 21 días.")
        res = orch.execute_stage_b(s.conversation_id, s.scenario_id, seed=42)
        basic = res.progressive_report.basic
        assert isinstance(basic, BasicReportView)

        assert basic.what_was_evaluated
        assert "San Miguel" in basic.where_was_evaluated
        assert "21" in basic.temporal_horizon_summary
        assert basic.overall_verdict_plain
        assert basic.overall_result_headline
        assert basic.understandable_recommendation
        assert len(basic.main_opportunities) >= 1
        assert len(basic.main_risks) >= 1

        # Non-guarantee safeguard
        notice_low = basic.non_guarantee_notice.lower()
        assert "no " in notice_low and "garantiz" in notice_low

        # Every metric card has everyday Spanish explanation + non-guaranteed disclaimer
        for card in (
            basic.estimated_revenue,
            basic.estimated_expenses,
            basic.operating_result,
            basic.potential_demand,
            basic.potential_customers,
        ):
            assert isinstance(card, ExplainedMetricCard)
            assert card.basic_explanation.strip()
            assert card.not_guaranteed_note.strip()
    finally:
        orch.close()


def test_fase3_intermediate_decision_domains_and_documented_envelopes(tmp_path) -> None:
    """INTERMEDIATE level covers all decision domains and builds Conservative/Base/Optimistic without invented params."""
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "f3.db", seed=42)
    try:
        s = orch.handle_message("Quiero abrir una tienda en Soyapango durante 14 días.")
        res = orch.execute_stage_b(s.conversation_id, s.scenario_id, seed=42, compare_alternatives=True)
        inter = res.progressive_report.intermediate
        assert isinstance(inter, IntermediateReportView)

        for field_name in (
            "demand_and_market",
            "competition",
            "consumer_behavior",
            "economic_capacity",
            "territorial_mobility",
            "accessibility",
            "employment",
            "costs_and_profitability",
        ):
            val = getattr(inter, field_name)
            assert isinstance(val, str) and len(val.strip()) > 10, f"Missing {field_name}"

        assert len(inter.commercial_risks) >= 1
        assert len(inter.actionable_recommendations) >= 1

        # Alternative scenarios must explicitly document methodology & parameters used
        labels = [e.scenario_label for e in inter.alternative_scenarios]
        assert any("Conservador" in lbl for lbl in labels)
        assert any("Base" in lbl for lbl in labels)
        assert any("Optimista" in lbl for lbl in labels)
        for entry in inter.alternative_scenarios:
            assert entry.derivation_note.strip()
            assert isinstance(entry.parameters_used, dict) and len(entry.parameters_used) >= 1
    finally:
        orch.close()


def test_fase4_expert_level_full_audit_provenance_and_metadata(tmp_path) -> None:
    """EXPERT level exposes execution metadata, all indicators, segments, accounting, extrapolations & limitations."""
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "f4.db", seed=101)
    try:
        s = orch.handle_message("Quiero abrir una panadería en Santa Ana durante 14 días.")
        res = orch.execute_stage_b(s.conversation_id, s.scenario_id, seed=101)
        expert = res.progressive_report.expert
        assert isinstance(expert, ExpertReportView)

        meta = expert.execution_metadata
        assert meta["execution_id"] == res.execution_id
        assert meta["scenario_id"] == res.scenario_id
        assert meta["seed"] == 101
        assert "engine_version" in meta and meta["engine_version"]
        assert isinstance(meta["active_engines"], list) and len(meta["active_engines"]) >= 1
        assert isinstance(meta["reproducible_parameters"], dict)

        assert expert.transactions_and_accounting["conservation_passed"] is True
        assert abs(expert.transactions_and_accounting["cash_conservation_diff_usd"]) < 1e-6
        assert isinstance(expert.synthetic_agents_summary, dict)
        assert isinstance(expert.simulation_events_and_segments, list)
        assert isinstance(expert.extrapolations, dict)
        assert isinstance(expert.territorial_sources_and_quality, dict)
        assert len(expert.methodology_and_assumptions) >= 1
        assert len(expert.uncertainty) >= 1
        assert len(expert.limitations) >= 1
        assert sum(expert.evidence_origin_counts.values()) == len(expert.all_indicators)
    finally:
        orch.close()


def test_fase5_universal_evidence_classification_all_8_origins() -> None:
    """All 8 UniversalEvidenceOrigin categories resolve deterministically with strict empirical calibration guards."""
    cases = [
        (
            _make_indicator("i_obs", "Vías OSM", 124, unit="vías", data_origin="GEOGRAPHIC_DATASET", source_engine="OSMTerritorialLoader"),
            UniversalEvidenceOrigin.OBSERVED,
            "CARTOGRAPHIC_OBSERVED",
        ),
        (
            _make_indicator("i_pub", "Población D.L. 762", 150000, unit="hab", data_origin="GEOGRAPHIC_DATASET", source_engine="ElSalvadorCatalog"),
            UniversalEvidenceOrigin.PUBLIC_OFFICIAL,
            "PUBLIC_OFFICIAL_APPROX",
        ),
        (
            _make_indicator("i_est", "Capacidad proxy", 0.65, unit="ratio", data_origin="FALLBACK_ESTIMATE", source_engine="SpatialFallback"),
            UniversalEvidenceOrigin.ESTIMATED,
            "HEURISTIC_UNVERIFIED",
        ),
        (
            _make_indicator("i_ext", "Visitas proyectadas", 4200.0, unit="visitas", data_origin="EXTRAPOLATED_COHORT"),
            UniversalEvidenceOrigin.EXTRAPOLATED,
            "UNCALIBRATED_SYNTHETIC",
        ),
        (
            _make_indicator("i_syn", "Gini liquidez", 0.31, unit="indice", data_origin="SYNTHETIC_SIMULATED", source_engine="EconomicEngine"),
            UniversalEvidenceOrigin.SYNTHETIC_SIMULATED,
            "UNCALIBRATED_SYNTHETIC",
        ),
        (
            _make_indicator("i_evt", "Jornadas educativas", 120, unit="persona-días", data_origin="DIRECT_SIMULATION_EVENT", source_engine="EducationEngine"),
            UniversalEvidenceOrigin.DIRECT_SIMULATION_EVENT,
            "UNCALIBRATED_SYNTHETIC",
        ),
        (
            _make_indicator("i_mul", "Costos fijos diarios", 45.0, unit="USD", data_origin="DETERMINISTIC_MULTIPLIER"),
            UniversalEvidenceOrigin.DETERMINISTIC_MULTIPLIER,
            "HEURISTIC_UNVERIFIED",
        ),
        (
            _make_indicator("i_unv", "Dato faltante", None, unit="USD", data_origin="UNAVAILABLE", available=False),
            UniversalEvidenceOrigin.UNAVAILABLE,
            "UNAVAILABLE",
        ),
    ]

    for ind, expected_origin, expected_calib in cases:
        origin = normalize_evidence_origin(ind)
        calib = classify_empirical_calibration(ind, origin)
        enriched = enrich_indicator(ind, cohort_size=40)
        assert origin == expected_origin
        assert calib == expected_calib
        assert enriched.evidence_origin == expected_origin
        assert enriched.empirical_calibration_status == expected_calib
        # Synthetic models must never claim empirical calibration
        if origin in (
            UniversalEvidenceOrigin.SYNTHETIC_SIMULATED,
            UniversalEvidenceOrigin.EXTRAPOLATED,
            UniversalEvidenceOrigin.DIRECT_SIMULATION_EVENT,
        ):
            assert enriched.empirical_calibration_status == "UNCALIBRATED_SYNTHETIC"


def test_fase6_dynamic_contextual_explanations() -> None:
    """Contextual explainability translates indicators into everyday BASIC Spanish and rigorous EXPERT prose."""
    ind_quarter = _make_indicator(
        "low_liquidity_agent_share",
        "Agentes con liquidez inferior a $15",
        0.25,
        unit="ratio",
        calculation_method="count(cash < 15.0) / 40",
    )
    b_q, e_q = generate_contextual_explanations(ind_quarter, cohort_size=40)
    assert "aproximadamente una de cada cuatro" in b_q.lower()
    assert "$15" in b_q
    assert "25%" in e_q
    assert "n=40" in e_q
    assert "no representa una estimación censal" in e_q.lower()

    ind_half = _make_indicator(
        "low_liquidity_agent_share",
        "Agentes con liquidez inferior a $15",
        0.50,
        unit="ratio",
        calculation_method="count(cash < 15.0) / 40",
    )
    b_h, _ = generate_contextual_explanations(ind_half, cohort_size=40)
    assert "aproximadamente la mitad" in b_h.lower()


def test_fase7_api_depth_endpoints_legacy_persistence_and_ui_assets(tmp_path) -> None:
    """Verify REST /executions/{id}/report?level=..., backward compatibility, read-only legacy DB & Studio UI assets."""
    # 1. End-to-end API flow in isolated temp DB
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "f7_api.db", seed=42)
    set_studio_orchestrator(orch)
    app = create_app(seed=42, db_path=str(tmp_path / "f7_sim.db"))
    try:
        with TestClient(app) as client:
            r_chat = client.post(
                "/api/studio/chat",
                json={"message": "Quiero abrir una pupusería en Santa Tecla durante 14 días.", "map_visible": False},
            )
            assert r_chat.status_code == 200
            cid = r_chat.json()["conversation_id"]
            sid = r_chat.json()["scenario_id"]

            r_exec = client.post(
                "/api/studio/execute",
                json={"conversation_id": cid, "scenario_id": sid, "seed": 42, "map_visible": False},
            )
            assert r_exec.status_code == 200
            d_exec = r_exec.json()
            exec_id = d_exec["execution_id"]
            fp_live = d_exec["progressive_report"]["canonical_numeric_fingerprint"]

            # Fetch all 3 depth levels from REST endpoint; fingerprint stays invariant
            for lvl, key in (("BASIC", "basic"), ("INTERMEDIATE", "intermediate"), ("EXPERT", "expert")):
                r_rep = client.get(f"/api/studio/executions/{exec_id}/report?level={lvl}")
                assert r_rep.status_code == 200
                payload = r_rep.json()
                assert payload["execution_id"] == exec_id
                assert payload["selected_level"] == lvl
                assert key in payload["progressive_report"]
                assert payload["progressive_report"]["canonical_numeric_fingerprint"] == fp_live

            # Error paths
            assert client.get(f"/api/studio/executions/{exec_id}/report?level=UNKNOWN").status_code == 400
            assert client.get("/api/studio/executions/EXEC_DOES_NOT_EXIST/report?level=BASIC").status_code == 404

            # Conversation reopen returns progressive_report inside persisted executions
            r_conv = client.get(f"/api/studio/conversations/{cid}")
            assert r_conv.status_code == 200
            execs = r_conv.json()["executions"]
            assert len(execs) == 1
            assert execs[0]["progressive_report"]["default_level"] == "BASIC"
            assert execs[0]["progressive_report"]["canonical_numeric_fingerprint"] == fp_live

            # Studio frontend JS & CSS expose progressive depth switcher & origin badges
            js_resp = client.get("/modules/territorial_studio.js")
            assert js_resp.status_code == 200
            for marker in (
                "Resumen sencillo",
                "Análisis de decisiones",
                "Análisis exhaustivo",
                "studio-depth-switcher",
                "_renderPersistedProgressiveCard",
            ):
                assert marker in js_resp.text

            css_resp = client.get("/studio.css")
            assert css_resp.status_code == 200
            assert ".studio-depth-switcher" in css_resp.text
            assert ".studio-origin-badge" in css_resp.text
    finally:
        set_studio_orchestrator(None)
        orch.close()

    # 2. Synthetic legacy row matching persistence.list_executions_for_conversation schema
    legacy_row = {
        "execution_id": "EXEC_LEGACY_ROW",
        "scenario_id": "SCEN_LEGACY",
        "conversation_id": "CONV_LEGACY",
        "seed": 42,
        "active_engines": ["NationalTerritorialContextEngine", "CommercialEngine"],
        "evidence_ref": {
            "horizon_days": 14,
            "simulated_ticks": 1344,
            "district_id": "LIB_ST_TECLA",
            "active_engines": ["NationalTerritorialContextEngine", "CommercialEngine"],
            "ledger_audit": {"conservation_passed": True, "cash_conservation_diff_usd": 0.0, "total_transactions": 120},
            "indicator_values": {
                "resident_population_approx": 150000,
                "unique_active_cohort": 40,
                "commercial_revenue_usd": 3290.50,
                "commercial_net_profit_usd": -1386.56,
                "commercial_visitors": 7945.1,
                "commercial_purchasers": 3656.2,
                "commercial_conversion_rate": 0.4602,
            },
        },
        "analysis": {
            "verdict": "HIGH_RISK",
            "executive_summary": "Escenario heredado reconstruido desde registro histórico.",
            "assumptions": ["Registro legado previo a ProgressiveReportBundle."],
            "uncertainty": ["Reconstrucción sin re-ejecución."],
            "limitations": ["Cifras tomadas del archivo persistido."],
        },
        "provenance": {"district_id": "LIB_ST_TECLA"},
        "created_at": "2026-01-01T00:00:00Z",
    }
    legacy_bundle = ProgressiveReportBuilder.build_from_persisted_execution(legacy_row, None)
    assert legacy_bundle.default_level == ReportDepthLevel.BASIC
    assert legacy_bundle.basic.estimated_revenue is not None
    assert legacy_bundle.basic.estimated_revenue.raw_value == pytest.approx(3290.50)
    assert len(legacy_bundle.expert.all_indicators) == 7

    # 3. Read-only backward compatibility inspection on saltbor_studio.db if present (never mutating it)
    studio_db = Path("saltbor_studio.db")
    if studio_db.exists():
        conn = sqlite3.connect(f"file:{studio_db.resolve()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM conv_executions LIMIT 1").fetchone()
            if row is not None:
                import json

                raw = dict(row)
                decoded = {
                    "execution_id": raw["execution_id"],
                    "conversation_id": raw["conversation_id"],
                    "scenario_id": raw["scenario_id"],
                    "seed": raw["seed"],
                    "active_engines": json.loads(raw.get("active_engines_json") or "[]"),
                    "evidence_ref": json.loads(raw.get("evidence_ref_json") or "{}"),
                    "analysis": json.loads(raw.get("analysis_json") or "{}"),
                    "provenance": json.loads(raw.get("provenance_json") or "{}"),
                    "checkpoint_id": raw.get("checkpoint_id"),
                    "created_at": raw.get("created_at"),
                }
                ro_bundle = ProgressiveReportBuilder.build_from_persisted_execution(decoded, None)
                assert ro_bundle.default_level == ReportDepthLevel.BASIC
                assert ro_bundle.source_execution_id == decoded["execution_id"]
        finally:
            conn.close()
