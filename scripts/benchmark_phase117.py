"""Sustained Performance & Spatial Index Benchmark for SALTBOR Phase 1.17."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psutil

from saltbor.datasets.gis.pipeline import IngestedGeography
from saltbor.simulation.experiments.phase117_territorial_experiments import run_all_phase117_experiments
from saltbor.simulation.runner import SimulationRunner
from saltbor.territorial_intelligence import OnDemandTerritorialSimulationEngine


def main() -> None:
    proc = psutil.Process(os.getpid())
    rss_start_mb = round(proc.memory_info().rss / (1024 * 1024), 2)

    # 1. R-Tree spatial query benchmark across 795,877 national features
    geo = IngestedGeography()
    rtree_timings_ms = {}
    for name, bbox in (
        ("soyapango_buildings_500", (-89.16, 13.69, -89.13, 13.72)),
        ("santa_tecla_buildings_500", (-89.30, 13.66, -89.27, 13.69)),
        ("san_miguel_buildings_500", (-88.19, 13.47, -88.16, 13.50)),
        ("santa_ana_buildings_500", (-89.57, 13.98, -89.54, 14.01)),
    ):
        t0 = time.perf_counter()
        rows = geo.features_in_bbox(bbox, layer="buildings", limit=500)
        rtree_timings_ms[name] = {
            "count": len(rows),
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    geo.close()

    # 2. On-demand multi-department single-scenario latency
    eng = OnDemandTerritorialSimulationEngine(seed=42)
    t_cov0 = time.perf_counter()
    cov = eng.coverage_registry.get_national_summary(force_refresh=True)
    cov_ms = round((time.perf_counter() - t_cov0) * 1000.0, 2)

    scenario_timings_ms = {}
    for loc in ("Soyapango", "San Miguel", "Santa Ana", "Chalatenango"):
        t0 = time.perf_counter()
        rec = eng.create_and_run_scenario(location_query=loc, objective=f"Benchmark {loc}", horizon_days=30, seed=42)
        scenario_timings_ms[loc] = {
            "state": rec.state.value,
            "latency_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "buildings": rec.building_intelligence.total_buildings_observed if rec.building_intelligence else 0,
        }
    eng.close()

    # 3. 4 concurrent cross-department scenarios
    def _conc(loc: str) -> float:
        e = OnDemandTerritorialSimulationEngine(seed=42)
        t0 = time.perf_counter()
        try:
            e.create_and_run_scenario(location_query=loc, objective="Concurrent benchmark", horizon_days=15, seed=42, max_active_agents=24)
            return round((time.perf_counter() - t0) * 1000.0, 2)
        finally:
            e.close()

    t_c0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        conc_ms = list(pool.map(_conc, ["Soyapango", "Santa Tecla", "San Miguel", "Santa Ana"]))
    conc_wall_ms = round((time.perf_counter() - t_c0) * 1000.0, 2)

    # 4. Historic Center regression ms/tick benchmark (96 ticks = 1 simulated day)
    hc = SimulationRunner.create_historic_center_benchmark(seed=42, db_path=":memory:", population_size=20)
    hc.initialize(load_existing=False)
    t_hc0 = time.perf_counter()
    for _ in range(96):
        hc.step()
    hc_ms_per_tick = round(((time.perf_counter() - t_hc0) * 1000.0) / 96.0, 3)
    hc.close()

    # 5. Execute and persist all 20 experiments record
    exp_summary = run_all_phase117_experiments(seed=42)

    rss_end_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
    payload = {
        "phase": "1.17",
        "hardware_target": "Ryzen 7 8700G / 32 GB RAM / Radeon 780M",
        "rss_start_mb": rss_start_mb,
        "rss_end_mb": rss_end_mb,
        "rtree_queries": rtree_timings_ms,
        "national_262_district_coverage_ms": cov_ms,
        "coverage_tier_counts": cov.tier_counts,
        "single_scenario_timings_ms": scenario_timings_ms,
        "concurrent_4_scenarios_wall_ms": conc_wall_ms,
        "concurrent_worker_ms": conc_ms,
        "historic_center_96tick_ms_per_tick": hc_ms_per_tick,
        "experiments_passed": f"{exp_summary['passed_count']}/{exp_summary['total_experiments']}",
    }
    Path("PHASE_117_BENCHMARKS.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
