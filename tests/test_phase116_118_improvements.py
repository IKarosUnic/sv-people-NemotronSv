"""Verification Suite for SALTBOR Phases 1.16–1.18 Architectural & Scientific Improvements.

Validates:
1. EventBus monotonic cursor (`events_since`) resilience across `_max_log_size` log pruning.
2. TickStagePipeline per-stage telemetry and AdaptiveLODBudgetController time-budget throttling
   with strict protection of focal and crisis agents in LOD 0.
3. LiveScenarioBridge: natural language scenario compilation and live tick-by-tick execution
   inside `SimulationRunner` with absolute double-entry accounting conservation ($0.00 discrepancy).
4. Cuchubal weekly turn strict accounting conservation in `SimulationRunner`.
5. 262-District National Coverage Audit, Tobler Topographic Hazard Profile, and Hierarchical Supply Chain resolution.
6. Tier-5 Out-of-Sample Historical Backtesting (`EXTERNALLY_VALIDATED`) against BCR, ONEC/EHPM, and MINED series.
7. Modular FastAPI sub-routers (`pipeline_router`, `national_validation_router`) and Vanilla ES6 module asset delivery.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from saltbor.ai import AIComputeBudgetManager, AIModelRouter, NaturalLanguageScenarioBuilder
from saltbor.core.config import SimulationConfig
from saltbor.events.bus import EventBus
from saltbor.events.types import EventType, SimulationEvent
from saltbor.population.lod import CognitiveLOD
from saltbor.scientific.external_validation import ExternalHistoricalValidator
from saltbor.scientific.models import EvidenceValidationTier
from saltbor.simulation.runner import SimulationRunner
from saltbor.territory.territory_catalog import TerritoryCatalogService
from saltbor.visualization.controller import SimulationController
from saltbor.visualization.server import create_app


def _make_temp_runner(population_size: int = 12, seed: int = 42) -> tuple[SimulationRunner, Path]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    cfg = SimulationConfig(
        initial_population_size=population_size,
        random_seed=seed,
        database_path=str(db_path),
        checkpoint_interval_ticks=500,
    )
    runner = SimulationRunner(config=cfg)
    runner.initialize(load_existing=False)
    return runner, db_path


def test_event_bus_monotonic_cursor_survives_log_pruning() -> None:
    """Verify EventBus.events_since never loses events or returns negative counts when log is truncated."""
    bus = EventBus()
    bus._max_log_size = 10

    cursor = bus.total_emitted_count
    assert cursor == 0

    for i in range(6):
        bus.emit(SimulationEvent(event_type=EventType.DAY_STARTED, tick=i, data={"i": i}))

    batch1, cursor = bus.events_since(cursor)
    assert len(batch1) == 6
    assert cursor == 6

    # Emit 8 more events -> total 14 exceeds _max_log_size=10, triggering internal log slice
    for i in range(6, 14):
        bus.emit(SimulationEvent(event_type=EventType.DAY_STARTED, tick=i, data={"i": i}))

    assert bus.total_emitted_count == 14
    assert len(bus.event_log) < 14  # Log was pruned

    batch2, new_cursor = bus.events_since(cursor)
    assert new_cursor == 14
    assert len(batch2) > 0
    assert batch2[-1].tick == 13


def test_tick_pipeline_and_adaptive_lod_budget_protection() -> None:
    """Verify TickStagePipeline telemetry and AdaptiveLODBudgetController crisis/focal protection."""
    runner, db_path = _make_temp_runner(population_size=12, seed=42)
    try:
        # 1. Default small-population mode: 0 agents deferred
        runner.step()
        summary = runner.tick_pipeline.get_telemetry_summary()
        assert summary["ticks_sampled"] == 1
        assert summary["last_active_agents"] == 12
        assert summary["last_deferred_agents"] == 0
        assert "population_update_ms" in summary["stages_mean_ms"]

        # 2. Force adaptive throttling and verify crisis & focal agents stay in LOD 0
        humans = runner.population.get_all()
        focal_human = humans[0]
        crisis_human = humans[1]
        runner.lod_manager.set_focal_agent(focal_human.uid, True)
        crisis_human.physical_state.hunger = 0.90  # Acute hunger crisis

        runner.lod_budget_controller.force_adaptive = True
        runner.step()

        assert runner.lod_manager.get_assignment(focal_human.uid).tier == CognitiveLOD.LOD_0_FULL
        assert runner.lod_manager.get_assignment(crisis_human.uid).tier == CognitiveLOD.LOD_0_FULL
        summary2 = runner.tick_pipeline.get_telemetry_summary()
        assert summary2["last_deferred_agents"] > 0
        assert summary2["last_active_agents"] < 12
    finally:
        runner.close()
        db_path.unlink(missing_ok=True)


def test_live_scenario_bridge_natural_language_and_accounting_conservation() -> None:
    """Verify a natural-language scenario runs live in SimulationRunner with $0.00 accounting discrepancy."""
    runner, db_path = _make_temp_runner(population_size=10, seed=42)
    try:
        # Prepare low-cash agents to qualify for focused cash transfer
        for h in runner.population.get_all()[:3]:
            h.physical_state.money = 8.00
        runner.community_utility_treasury["balance"] = 200.00

        builder = NaturalLanguageScenarioBuilder(
            router=AIModelRouter(),
            budget_manager=AIComputeBudgetManager(),
            catalog=TerritoryCatalogService(),
        )
        built = builder.build_scenario_from_text(
            prompt=(
                "Simula un bloqueo por deslave de 2 días en Cantón El Rosario con "
                "alza de precios de alimentos y paquete de transferencia monetaria solidaria."
            )
        )
        # Ensure a focused cash transfer intervention is scheduled at start_tick=0
        if not built.scenario_definition.interventions:
            built.scenario_definition.interventions.append({
                "type": "FOCUSED_CASH_TRANSFER",
                "start_tick": 0,
                "transfer_amount_usd": 5.0,
            })

        total_before = sum(float(h.physical_state.money) for h in runner.population.get_all()) + float(
            runner.community_utility_treasury["balance"]
        )

        # Inject directly into live SimulationRunner and advance 1 tick (not midnight so only bridge transfers cash)
        runner.live_scenario_bridge.inject_scenario(built.scenario_definition)
        runner.step()

        total_after = sum(float(h.physical_state.money) for h in runner.population.get_all()) + float(
            runner.community_utility_treasury["balance"]
        )

        # Strict accounting conservation check
        assert abs(total_after - total_before) < 1e-4
        status = runner.live_scenario_bridge.get_status_summary()
        assert status["ledger_is_balanced"] is True
        assert status["net_accounting_discrepancy_usd"] == 0.0
        assert status["ledger_transactions_count"] >= 1
    finally:
        runner.close()
        db_path.unlink(missing_ok=True)


def test_national_262_districts_topographic_and_supply_chain_resolution() -> None:
    """Verify all 262 official districts resolve supply chains and topographic hazard profiles."""
    catalog = TerritoryCatalogService()
    audit = catalog.get_national_coverage_audit()
    assert audit["total_departments"] == 14
    assert audit["total_municipalities"] == 44
    assert audit["total_districts"] == 262
    assert audit["all_262_districts_resolvable"] is True

    # Compare mountainous district vs coastal district vs eastern dry corridor
    mountain = catalog.get_topographic_hazard_profile("San Ignacio")
    coastal = catalog.get_topographic_hazard_profile("Puerto de La Libertad")
    eastern = catalog.get_topographic_hazard_profile("San Miguel")

    assert mountain["landslide_risk_index"] > coastal["landslide_risk_index"]
    assert coastal["flood_inundation_risk_index"] > mountain["flood_inundation_risk_index"]
    assert eastern["drought_corridor_risk_index"] > 0.70

    sc = catalog.resolve_supply_chain_and_services("Cantón El Rosario")
    assert sc["distance_to_departmental_hub_km"] >= 0.0
    assert "primary_healthcare_ucsf" in sc["public_services"]
    assert "public_education_mined" in sc["public_services"]


def test_tier5_external_historical_validation_backtesting() -> None:
    """Verify ExternalHistoricalValidator elevates backtested series to Tier 5 EXTERNALLY_VALIDATED."""
    validator = ExternalHistoricalValidator()
    suite = validator.run_canonical_salvadoran_backtest_suite(seed=42)
    assert suite["total_series_evaluated"] == 4
    assert suite["externally_validated_count"] == 4
    assert suite["overall_tier"] == EvidenceValidationTier.EXTERNALLY_VALIDATED.value
    for item in suite["results"]:
        assert item["nrmse"] <= 0.22
        assert item["interval_coverage_rate"] >= 0.75
        assert item["pearson_r"] > 0.90


def test_modular_routers_and_es6_module_endpoints(tmp_path) -> None:
    """Verify FastAPI modular sub-routers and ES6 frontend module asset delivery."""
    db_file = tmp_path / "test_phase116_api.db"
    ctrl = SimulationController(seed=42, db_path=str(db_file))
    app = create_app(controller=ctrl, seed=42, db_path=str(db_file))
    try:
        with TestClient(app) as client:
            # 1. Pipeline telemetry endpoint
            r_pipe = client.get("/api/pipeline/telemetry")
            assert r_pipe.status_code == 200
            assert "pipeline" in r_pipe.json()
            assert "lod_budget" in r_pipe.json()

            # 2. Live scenario injection endpoint
            r_inj = client.post(
                "/api/ai/execution/inject_live",
                json={
                    "prompt": "Simula un deslave vial de 3 días en Cantón El Rosario con inflación de granos.",
                    "step_ticks_immediately": 2,
                },
            )
            assert r_inj.status_code == 200
            inj_data = r_inj.json()
            assert inj_data["status"] == "injected_into_live_runner"
            assert inj_data["ticks_advanced_immediately"] == 2
            assert inj_data["live_bridge_status"]["ledger_is_balanced"] is True

            # 3. 262-District National Audit & Supply Chain endpoints
            r_nat = client.get("/api/territory/national_audit")
            assert r_nat.status_code == 200
            assert r_nat.json()["total_districts"] == 262

            r_sc = client.get("/api/territory/supply_chain?territory=Arcatao")
            assert r_sc.status_code == 200
            assert "wholesale_supply_hub" in r_sc.json()

            # 4. External historical validation endpoint
            r_ext = client.get("/api/scientific/external_validation/backtest?seed=42")
            assert r_ext.status_code == 200
            assert r_ext.json()["overall_tier"] == "EXTERNALLY_VALIDATED"

            # 5. Native ES6 frontend module asset served offline
            r_mod = client.get("/modules/live_bridge_observatory.js")
            assert r_mod.status_code == 200
            assert "injectNaturalLanguageScenarioLive" in r_mod.text
            assert "runQuickCitizenSimulation" in r_mod.text

            # 6. 1-Click Quick Simulator Presets & Citizen Run Endpoint
            r_presets = client.get("/api/quick/presets")
            assert r_presets.status_code == 200
            assert len(r_presets.json()) >= 6

            r_qrun = client.post(
                "/api/quick/run",
                json={
                    "evento": "temporal_deslave",
                    "dias": 4,
                    "con_ayuda": True,
                },
            )
            assert r_qrun.status_code == 200
            qdata = r_qrun.json()
            assert qdata["status"] == "ok"
            assert len(qdata["tarjetas_impacto"]) == 4
            assert "$0.00 discrepancia" in qdata["tarjetas_impacto"][3]["valor"]

            # 7. Ultra-precise Pinpoint Map Inspection & Placement Endpoints
            r_insp = client.get("/api/quick/inspect_point?lat=13.69785&lon=-89.19142&radius_m=350")
            assert r_insp.status_code == 200
            assert "nearest_street_osm" in r_insp.json()

            r_pin = client.post(
                "/api/quick/pinpoint",
                json={
                    "lat": 13.69785,
                    "lon": -89.19142,
                    "descripcion": "Abrir pupusería 'El Comal de Oro' con pupusas a $0.85, 25 personas y $180 de capital",
                    "categoria": "pupuseria",
                    "radio_m": 350.0,
                    "dias": 7,
                },
            )
            assert r_pin.status_code == 200
            pdata = r_pin.json()
            assert pdata["status"] == "ok"
            assert pdata["injected_into_live_map"] is True
            assert pdata["parametros_especificos"]["nombre"] == "El Comal de Oro"
            assert pdata["parametros_especificos"]["precio_unitario_usd"] == 0.85
            assert pdata["metricas_negocio"]["ledger_balanced"] is True
    finally:
        ctrl.stop_worker()


def test_one_line_python_simular_helper() -> None:
    """Verify the 1-line `simular(...)` and `colocar_en_punto(...)` helpers work out-of-the-box."""
    from saltbor.simulation.quick_simulator import colocar_en_punto, simular

    res = simular("Sequía de 5 días en San Miguel", dias=5, con_ayuda=True)
    assert res["status"] == "ok"
    assert res["dias_simulados"] == 5
    assert res["incluyo_ayuda"] is True
    assert "resumen_sencillo" in res
    assert len(res["tarjetas_impacto"]) == 4

    pin = colocar_en_punto(
        lat=13.67340,
        lon=-89.27960,
        descripcion="Poner una farmacia 'San Rafael' con medicinas a $3.25 y $300 de capital",
        dias=7,
    )
    assert pin["status"] == "ok"
    assert pin["categoria"] == "farmacia"
    assert pin["parametros_especificos"]["nombre"] == "San Rafael"
    assert pin["parametros_especificos"]["precio_unitario_usd"] == 3.25
    assert pin["metricas_negocio"]["ledger_balanced"] is True


