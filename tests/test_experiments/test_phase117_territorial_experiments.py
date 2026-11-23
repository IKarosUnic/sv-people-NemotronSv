"""Pytest validation suite for all 20 Phase 1.17 experiments (EXP_117_A..EXP_117_T)
and the Decisive End-to-End Test across Soyapango + 2 additional Salvadoran departments.
"""

from __future__ import annotations

from saltbor.conversational import SALTBORConversationalOrchestrator
from saltbor.simulation.experiments.phase117_territorial_experiments import run_all_phase117_experiments
from saltbor.territorial_intelligence import OnDemandTerritorialSimulationEngine


def test_all_20_phase117_experiments_execute_and_pass(tmp_path):
    rec_path = tmp_path / "phase117_experiments_record.json"
    summary = run_all_phase117_experiments(seed=42, output_json_path=rec_path)
    assert summary["total_experiments"] == 20
    failed = [e["experiment_id"] for e in summary["experiments"] if not e["passed"]]
    assert summary["all_passed"] is True, f"Failed experiments: {failed}"
    assert rec_path.exists()


def test_decisive_end_to_end_soyapango_and_two_other_departments():
    """Decisive End-to-End Test required by Section 15 across Soyapango, San Miguel, and Santa Ana."""
    orch = SALTBORConversationalOrchestrator(persistence_path=":memory:", seed=42)
    eng = OnDemandTerritorialSimulationEngine(seed=42)
    try:
        # 1. Primary Decisive Test prompt in Soyapango
        soya_prompt = (
            "Analiza el flujo de personas, los edificios comerciales, los negocios y las oportunidades de empleo "
            "alrededor de esta ubicación en Soyapango. Quiero comprender qué actividad económica existe y qué "
            "oportunidades podrían desarrollarse durante los próximos 12 meses."
        )
        stage_a = orch.handle_message(soya_prompt, map_visible=False)
        assert stage_a.territorial_context.resolved is True
        assert stage_a.territorial_context.district_name == "Soyapango"
        assert stage_a.territorial_context.district_id != "0614"  # Not Historic Center!
        assert stage_a.temporal_horizon.horizon_days == 360  # 12 meses
        assert stage_a.territorial_intelligence["buildings"]["total_observed"] > 500
        assert stage_a.territorial_intelligence["commerce"]["confirmed_establishments"] > 50
        assert stage_a.computational_estimate["map_required"] is False

        stage_b = orch.execute_stage_b(
            conversation_id=stage_a.conversation_id,
            scenario_id=stage_a.scenario_id,
            seed=42,
            map_visible=False,
        )
        ti = stage_b.territorial_intelligence
        assert stage_b.territorial_context.district_name == "Soyapango"
        assert ti["mobility"]["role_breakdown"]
        assert ti["mobility"]["measured_flows_available"] is False
        assert ti["employment"]["verified_job_vacancies_count"] == 0
        assert ti["employment"]["known_employers_count"] > 10
        assert ti["evidence_tiers"]["A_real_observed_data"]
        assert ti["evidence_tiers"]["E_simulated_outcomes"]
        assert ti["evidence_tiers"]["F_ai_interpretations_and_hypotheses"]
        assert ti["evidence_tiers"]["G_recommendations"]
        assert stage_b.evidence.ledger_audit["conservation_passed"] is True

        # 2. Repeat in 2 additional Salvadoran departments (San Miguel & Santa Ana)
        sm_rec = eng.create_and_run_scenario(
            location_query="San Miguel",
            objective="Analiza el flujo de personas, edificios comerciales y oportunidades de empleo durante 12 meses.",
            service_type="commercial_center",
            horizon_days=365,
            seed=42,
        )
        sa_rec = eng.create_and_run_scenario(
            location_query="Santa Ana",
            objective="Analiza el flujo de personas, edificios comerciales y oportunidades de empleo durante 12 meses.",
            service_type="commercial_center",
            horizon_days=365,
            seed=42,
        )
        for rec, expected_dept in ((sm_rec, "San Miguel"), (sa_rec, "Santa Ana")):
            assert rec.state.value == "COMPLETED"
            assert rec.resolved_location["department_name"] == expected_dept
            assert rec.resolved_location["district_id"] != "0614"
            assert rec.building_intelligence.total_buildings_observed > 200
            assert rec.commercial_context.concentration_metrics.confirmed_establishments_count > 20
            assert rec.evidence_package is not None
            assert len(rec.evidence_package.A_real_observed_data) >= 3
            assert len(rec.evidence_package.E_simulated_outcomes) >= 3
    finally:
        eng.close()
        orch.close()
