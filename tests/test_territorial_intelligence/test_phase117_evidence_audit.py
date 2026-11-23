"""Regression tests for Phase 1.17 Mandatory Addendum: Real-World Territorial Evidence Audit."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from saltbor.conversational.orchestrator import SALTBORConversationalOrchestrator
from saltbor.conversational.population_activation import NationalPopulationActivationManager
from saltbor.conversational.schemas import (
    ActivationLOD,
    InterventionCategory,
    InterventionSpec,
)
from saltbor.conversational.temporal_controller import ConversationalTemporalController
from saltbor.conversational.territorial_context import NationalTerritorialContextEngine
from saltbor.conversational.intervention_designer import TerritorialInterventionDesigner
from saltbor.economy.commerce.commercial_engine import (
    CommercialEngine,
    CommercialEstablishment,
    CommercialProduct,
    EstablishmentType,
    VisitIntent,
)
from saltbor.economy.business.enterprise import BusinessStatus


def test_archived_studio_db_santa_tecla_records_untouched():
    """Audit rule: never rewrite archived findings inside saltbor_studio.db when present."""
    db_path = Path("saltbor_studio.db")
    if not db_path.exists():
        return
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT execution_id, scenario_id, evidence_ref_json FROM conv_executions "
            "WHERE execution_id IN ('EXEC_89a6765e8c', 'EXEC_41fad3fac1')"
        ).fetchall()
    finally:
        conn.close()

    by_id = {r[0]: json.loads(r[2]) for r in rows}
    if "EXEC_41fad3fac1" in by_id:
        vals = by_id["EXEC_41fad3fac1"]["indicator_values"]
        assert vals["commercial_visitors"] == 7945.1
        assert vals["commercial_revenue_usd"] == 3290.5
        assert vals["commercial_net_profit_usd"] == 1386.56
        assert vals["school_attendance_rate"] == 0.3543


def test_scenario_isolation_restores_all_mutable_agent_state():
    """DEF-01: Sequential runs must not leak occupation, work_location_id, or energy across scenarios."""
    tc = NationalTerritorialContextEngine()
    pm = NationalPopulationActivationManager(seed=42)
    temp = ConversationalTemporalController()
    des = TerritorialInterventionDesigner()
    try:
        ctx = tc.resolve_location(query="Santa Tecla")
        pm.activate_region(ctx, target_lod=ActivationLOD.LOD_3_INDIVIDUAL_FULL, max_active_agents=40, seed=42)
        snap = pm.capture_baseline_snapshot()
        humans = pm.get_active_humans_for_district(ctx.district_id)

        pre_state = {
            str(h.uid): (
                h.demographics.occupation,
                h.employment_status,
                h.physical_state.work_location_id,
                h.physical_state.current_location_id,
                round(h.physical_state.energy, 4),
                round(h.physical_state.money, 2),
                round(h.physical_state.hunger, 4),
            )
            for h in humans
        }

        spec = InterventionSpec(
            intervention_id="INT_ISO_TEST",
            category=InterventionCategory.COMMERCIAL_ESTABLISHMENT,
            name="Comercio Test Aislamiento",
            location_query="Santa Tecla",
            lat=ctx.lat,
            lon=ctx.lon,
            district_id=ctx.district_id,
            workforce_count=3,
            duration_days=30,
        )
        tspec = temp.parse_temporal_horizon(None, seed=42, explicit_days=30)
        des.execute_intervention_simulation(spec, ctx, humans, tspec, temp, seed=42, include_intervention=True)
        pm.restore_baseline_snapshot(snap)

        for h in humans:
            post = (
                h.demographics.occupation,
                h.employment_status,
                h.physical_state.work_location_id,
                h.physical_state.current_location_id,
                round(h.physical_state.energy, 4),
                round(h.physical_state.money, 2),
                round(h.physical_state.hunger, 4),
            )
            assert post == pre_state[str(h.uid)], f"State leaked for agent {h.uid}: {pre_state[str(h.uid)]} != {post}"
    finally:
        tc.close()


def test_commercial_closed_hours_stock_capacity_competitors_and_honest_pnl():
    """DEF-02..DEF-05: Open hours only, DINE stock decrement, capacity constraint, competitors & honest opex."""
    # 1. Verify VisitIntent.DINE decrements stock and blocks sales at stockout
    tc = NationalTerritorialContextEngine()
    pm = NationalPopulationActivationManager(seed=42)
    temp = ConversationalTemporalController()
    des = TerritorialInterventionDesigner()
    try:
        ctx = tc.resolve_location(query="Santa Tecla")
        pm.activate_region(ctx, target_lod=ActivationLOD.LOD_3_INDIVIDUAL_FULL, max_active_agents=40, seed=42)
        humans = pm.get_active_humans_for_district(ctx.district_id)

        ce = CommercialEngine()
        ce.register_establishment(
            CommercialEstablishment(
                establishment_id="pup_stock",
                name="Pupusería Stock Test",
                establishment_type=EstablishmentType.COMEDOR_PUPUSERIA,
                location_id="loc_test",
                opening_hours=(6, 21),
                catalog={
                    "meal": CommercialProduct(
                        product_id="meal",
                        name="Pupusa",
                        category="prepared_meal",
                        unit_price_usd=1.0,
                        current_stock=1.0,
                    )
                },
            )
        )
        buyer = humans[0]
        buyer.physical_state.money = 50.0
        o1 = ce.execute_visit(buyer, "pup_stock", VisitIntent.DINE, current_hour=12)
        o2 = ce.execute_visit(buyer, "pup_stock", VisitIntent.DINE, current_hour=12)
        assert o1.purchased is True
        assert ce.get_establishment("pup_stock").catalog["meal"].current_stock == 0.0
        assert o2.purchased is False and "out of stock" in o2.reasoning.lower()

        # 2. Verify narrow opening hours exclude closed visits, competitors earn sales, and full opex hits P&L
        spec = InterventionSpec(
            intervention_id="INT_PNL_AUDIT",
            category=InterventionCategory.PUPUSERIA,
            name="Pupusería P&L Audit",
            location_query="Santa Tecla",
            lat=13.67529,
            lon=-89.28761,
            district_id=ctx.district_id,
            capacity=4,
            opening_hour=8,
            closing_hour=16,
            workforce_count=2,
            daily_wage_usd=12.0,
            unit_price_usd=0.90,
            unit_cost_ratio=0.50,
            daily_fixed_cost_usd=7.0,
            initial_capital_usd=220.0,
            duration_days=30,
        )
        tspec = temp.parse_temporal_horizon(None, seed=42, explicit_days=30)
        out = des.execute_intervention_simulation(spec, ctx, humans, tspec, temp, seed=42, include_intervention=True)
        tot = out["totals"]
        est_open_visits = out["commerce_engine"].get_establishment("INT_PNL_AUDIT").daily_visitors

        assert tot["raw_cohort_visitors"] == est_open_visits
        assert tot["closed_hour_passersby"] > 0
        assert tot["competitor_sales_usd"] > 0.0
        assert tot["obligated_wages_usd"] == 720.0
        assert tot["obligated_fixed_costs_usd"] == 210.0
        assert tot["unpaid_wages_usd"] > 0.0
        assert tot["enterprise_status"] in (BusinessStatus.DISTRESSED.value, BusinessStatus.INSOLVENT.value)
        expected_pnl = round(
            tot["total_revenue_usd"]
            - tot["total_cogs_usd"]
            - tot["obligated_wages_usd"]
            - tot["obligated_fixed_costs_usd"],
            2,
        )
        assert tot["net_operating_profit_usd"] == expected_pnl
        assert out["ledger_conservation"]["conservation_passed"] is True
        assert out["ledger_conservation"]["cash_conservation_diff"] == 0.0
    finally:
        tc.close()


def test_question_specific_data_quality_and_no_false_100_percent(tmp_path):
    """DEF-06..DEF-07: No 1.00/1.00 offline score; question-specific quality assessment; no January school overflow."""
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "audit_dq.db", seed=42)
    try:
        stage_a = orch.handle_message("Quiero abrir una pupusería en Santa Tecla.")
        ctx = stage_a.territorial_context
        assert ctx.data_quality_score < 1.0
        assert ctx.question_data_quality is not None
        qdq = ctx.question_data_quality
        assert qdq.confidence_score < 1.0
        assert len(qdq.required_datasets) >= 5
        assert qdq.freshness
        assert qdq.provenance
        assert len(qdq.missing_fields) >= 2

        stage_b = orch.execute_stage_b(stage_a.conversation_id, stage_a.scenario_id, seed=42)
        ind_map = {i.indicator_id: i for i in stage_b.evidence.indicators}
        # January commercial simulation should not fabricate a 2,460 person-day school deficit
        assert ind_map["edu_unmet_person_days"].value == 0.0
        assert ind_map["school_attendance_rate"].available is False
    finally:
        orch.close()


def test_evidence_report_integrity_metadata_completeness(tmp_path):
    """DEF-08: 100% of evidence indicators expose definition, origin, uncertainty, and full provenance."""
    orch = SALTBORConversationalOrchestrator(persistence_path=tmp_path / "audit_rep.db", seed=42)
    try:
        stage_a = orch.handle_message("Quiero abrir un negocio en Santa Tecla.")
        stage_b = orch.execute_stage_b(stage_a.conversation_id, stage_a.scenario_id, seed=42)
        inds = stage_b.evidence.indicators
        assert len(inds) >= 15

        origins_seen = {i.data_origin for i in inds}
        assert "DIRECT_SIMULATION_EVENT" in origins_seen
        assert "EXTRAPOLATED_COHORT" in origins_seen
        assert "GEOGRAPHIC_DATASET" in origins_seen

        for ind in inds:
            assert ind.definition.strip(), f"Missing definition for {ind.indicator_id}"
            assert ind.unit.strip(), f"Missing unit for {ind.indicator_id}"
            assert ind.data_origin.strip(), f"Missing data_origin for {ind.indicator_id}"
            assert ind.uncertainty.strip(), f"Missing uncertainty for {ind.indicator_id}"
            assert ind.provenance.source_engine
            assert ind.provenance.calculation_method
            assert ind.provenance.geographic_scope
            assert ind.provenance.time_interval
            assert ind.provenance.population_scope
            assert ind.provenance.limitations
            if ind.data_origin in ("DIRECT_SIMULATION_EVENT", "AGGREGATED_SYNTHETIC_AGENTS", "EXTRAPOLATED_COHORT"):
                assert ind.is_synthetic is True
    finally:
        orch.close()
