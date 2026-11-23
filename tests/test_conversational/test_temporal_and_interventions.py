"""Tests for Spanish temporal parsing, defaults, business & school interventions, and checkpoints."""

from __future__ import annotations

import threading

from saltbor.conversational import (
    ActivationLOD,
    ConversationIntent,
    ConversationalTemporalController,
    InterventionCategory,
    NationalPopulationActivationManager,
    NationalTerritorialContextEngine,
    SALTBORConversationalOrchestrator,
)


def test_temporal_parsing_and_domain_defaults():
    ctrl = ConversationalTemporalController()
    assert ctrl.parse_temporal_horizon("esta semana").horizon_days == 7
    assert ctrl.parse_temporal_horizon("durante 30 días").horizon_days == 30
    assert ctrl.parse_temporal_horizon("durante tres meses").horizon_days == 90
    y1 = ctrl.parse_temporal_horizon("durante un año")
    assert y1.horizon_days == 365
    assert y1.seasonal_profile == "ANNUAL_CYCLE"
    assert y1.requires_confirmation is True

    rainy = ctrl.parse_temporal_horizon("durante la época lluviosa")
    assert rainy.horizon_days == 180
    assert rainy.seasonal_profile == "RAINY_SEASON"

    y5 = ctrl.parse_temporal_horizon("durante los próximos cinco años")
    assert y5.horizon_days == 1825
    assert y5.resolution_mode == "LONG_TERM_AGGREGATED"

    # Defaults when omitted
    biz_def = ctrl.parse_temporal_horizon("Quiero poner una pupusería", intent=ConversationIntent.BUSINESS_PLACEMENT)
    assert biz_def.horizon_days == 30 and biz_def.inferred_default is True
    edu_def = ctrl.parse_temporal_horizon("Hace falta una escuela", intent=ConversationIntent.EDUCATIONAL_INFRASTRUCTURE)
    assert edu_def.horizon_days == 365 and edu_def.seasonal_profile == "SCHOOL_CALENDAR"


def test_business_intervention_real_visits_no_auto_conversion_and_conservation(tmp_path):
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "biz.db", seed=42)
    try:
        stage_a = orch.handle_message("Quiero poner una pupusería en Santa Tecla durante 30 días.")
        assert stage_a.proposed_intervention.category == InterventionCategory.PUPUSERIA
        stage_b = orch.execute_stage_b(stage_a.conversation_id, stage_a.scenario_id, seed=42)

        ind_map = {i.indicator_id: i for i in stage_b.evidence.indicators}
        visitors = ind_map["commercial_visitors"].value
        browsers = ind_map["commercial_browsers_without_purchase"].value
        purchasers = ind_map["commercial_purchasers"].value
        conv = ind_map["commercial_conversion_rate"].value

        assert visitors > 0
        assert browsers > 0  # Passersby are NOT auto-converted into buyers!
        assert purchasers <= visitors
        assert 0.0 <= conv < 1.0
        assert stage_b.evidence.ledger_audit["conservation_passed"] is True
        assert stage_b.evidence.ledger_audit["cash_conservation_diff_usd"] == 0.0
    finally:
        orch.close()


def test_school_intervention_and_transport_comparison(tmp_path):
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "edu.db", seed=42)
    try:
        stage_a = orch.handle_message(
            "Compara construir una escuela con mejorar el transporte escolar en Cantón San José Las Flores."
        )
        stage_b = orch.execute_stage_b(
            stage_a.conversation_id,
            stage_a.scenario_id,
            seed=42,
            compare_alternatives=True,
        )
        assert stage_b.comparison is not None
        assert len(stage_b.comparison.alternatives) >= 2
        alt_labels = [a.label for a in stage_b.comparison.alternatives]
        assert any("transporte" in lbl for lbl in alt_labels)
        assert "school_attendance_rate" in stage_b.comparison.baseline.metrics_mean
        assert "school_dropout_risk" in stage_b.comparison.baseline.metrics_mean
    finally:
        orch.close()


def test_one_year_simulation_checkpoint_recovery_and_cancellation():
    ctrl = ConversationalTemporalController()
    spec = ctrl.parse_temporal_horizon("durante un año", seed=99)

    cancel_evt = threading.Event()
    calls = []

    def _step(seg, idx):
        calls.append(idx)
        if idx == 3:
            cancel_evt.set()
        return {"metric": idx * 10}

    partial = ctrl.execute_with_checkpoints("SCEN_365", spec, _step, cancel_event=cancel_evt)
    assert partial["cancelled"] is True
    assert partial["segments_completed"] == 4
    ckpt = partial["checkpoint"]
    assert ckpt is not None and ckpt.completed_steps == 4

    # Resume from saved checkpoint to full 365 days
    resumed = ctrl.execute_with_checkpoints("SCEN_365", spec, lambda s, i: {"metric": i * 10}, checkpoint=ckpt)
    assert resumed["completed"] is True
    assert resumed["simulated_days_elapsed"] == 365.0
    assert resumed["wall_clock_seconds"] < 2.0
