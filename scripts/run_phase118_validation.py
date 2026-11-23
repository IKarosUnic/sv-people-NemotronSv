"""Run SALTBOR Phase 1.18 Santa Tecla Validation & Multi-Scale Performance Benchmarks."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from saltbor.census_intelligence.calibration import PopulationCalibrationEngine
from saltbor.census_intelligence.census_engine import NationalCensusDataIntegrationEngine
from saltbor.census_intelligence.household_generator import SyntheticHouseholdGenerationEngine
from saltbor.census_intelligence.pipeline import TerritorialPreparationPipeline
from saltbor.census_intelligence.schemas import (
    DiscoveredTerritorialContext,
    EvidenceClassification,
    GeographicGranularity,
    PopulationAllocationResult,
    TerritorialExpansionResult,
    TerritorialScaleArea,
    TerritorialSelectionInput,
    ZoneTier,
)
from saltbor.census_intelligence.validation_scenario import run_santa_tecla_school_validation


def _rss_mb() -> float:
    try:
        import ctypes
        import ctypes.wintypes as wt

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD),
                ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        proc = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(proc, ctypes.byref(pmc), pmc.cb):
            return round(pmc.WorkingSetSize / (1024.0 * 1024.0), 2)
    except Exception:
        pass
    return 0.0


def main() -> None:
    pipe = TerritorialPreparationPipeline()
    try:
        rss_start = _rss_mb()

        # 1. Section 17 Santa Tecla Residential Validation Scenario (4 educational scenarios)
        santa_tecla = run_santa_tecla_school_validation(pipeline=pipe, seed=42)

        # 2. Multi-scale scalability benchmarks
        benchmarks = {}

        # Scale A: Community / Urbanización polygon (~0.6 km2)
        t0 = time.perf_counter()
        prep_comm = pipe.prepare(
            TerritorialSelectionInput(
                lat=13.667,
                lon=-89.287,
                travel_time_minutes=15.0,
                sector="school",
                seed=42,
            ),
            max_sample_households=250,
        )
        benchmarks["community_point"] = {
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "represented_population": prep_comm.population_batch.represented_population_total,
            "sample_households": prep_comm.population_batch.simulated_sample_households,
            "srmse": prep_comm.calibration.srmse,
        }

        # Scale B: Full District (Santa Tecla 125,532 hab via weighted cohort)
        t0 = time.perf_counter()
        prep_dist = pipe.prepare(
            TerritorialSelectionInput(
                query="Santa Tecla",
                travel_time_minutes=15.0,
                sector="market",
                seed=42,
            ),
            max_sample_households=400,
        )
        benchmarks["district_santa_tecla"] = {
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "represented_population": prep_dist.population_batch.represented_population_total,
            "sample_households": prep_dist.population_batch.simulated_sample_households,
            "is_weighted_cohort": prep_dist.population_batch.is_weighted_cohort,
            "srmse": prep_dist.calibration.srmse,
        }

        # Scale C: Department & National batch synthesis (weighted cohorts across 14 depts = 5,922,921 allocated / 6,029,976 total)
        census_eng = pipe.census_engine
        hh_gen = SyntheticHouseholdGenerationEngine()
        cal_eng = PopulationCalibrationEngine()
        t0 = time.perf_counter()
        censo_data = census_eng._raw_bundles["censo_2024_onec_bcr"]
        dept_rows = censo_data["departments"]
        total_nat_rep = 0
        total_nat_sample_hh = 0
        dept_srmses = []
        for dept in dept_rows:
            code = dept["department_code"]
            d_pop = int(dept["total_population"])
            # Pick cabecera district for department
            cab_dist = next(
                (d for d in census_eng._districts.values() if d.department_code == code),
                None,
            )
            if cab_dist is None:
                continue
            q_res = census_eng.query_area_statistics(cab_dist.district_id, GeographicGranularity.DEPARTMENT)
            dummy_poly = {
                "type": "Polygon",
                "coordinates": [[
                    [cab_dist.longitude - 0.02, cab_dist.latitude - 0.02],
                    [cab_dist.longitude + 0.02, cab_dist.latitude - 0.02],
                    [cab_dist.longitude + 0.02, cab_dist.latitude + 0.02],
                    [cab_dist.longitude - 0.02, cab_dist.latitude + 0.02],
                    [cab_dist.longitude - 0.02, cab_dist.latitude - 0.02],
                ]],
            }
            dummy_area = TerritorialScaleArea(
                zone_tier=ZoneTier.PRIMARY_AREA,
                label=dept["name"],
                area_km2=100.0,
                radius_equiv_km=5.6,
                travel_time_minutes=0.0,
                transport_mode="walk",
                geometry_geojson=dummy_poly,
            )
            dummy_disc = DiscoveredTerritorialContext(
                selection_mode="administrative_query",
                center_lat=cab_dist.latitude,
                center_lon=cab_dist.longitude,
                primary_district_id=cab_dist.district_id,
                primary_district_name=dept["name"],
                municipality_id=cab_dist.municipality_id,
                municipality_name=cab_dist.municipality_id,
                department_code=code,
                department_name=dept["name"],
                is_urban=cab_dist.is_urban_core,
                elevation_m=cab_dist.elevation_m,
                slope_pct=4.0,
                tobler_walking_speed_factor=0.9,
                expansion=TerritorialExpansionResult(
                    primary_area=dummy_area,
                    influence_area=dummy_area,
                    contextual_area=dummy_area,
                    methodology="National batch synthesis benchmark",
                ),
            )
            dummy_alloc = PopulationAllocationResult(
                district_id=cab_dist.district_id,
                district_official_population=d_pop,
                target_area_km2=100.0,
                district_reference_residential_area_m2=1_000_000.0,
                polygon_residential_area_m2=1_000_000.0,
                polygon_share_of_district=1.0,
                allocated_population_target=d_pop,
                allocated_households_target=max(1, int(round(d_pop / 3.1))),
                buildings_analyzed=0,
                buildings_residential_confirmed=0,
                buildings_unknown_probabilistic=0,
                buildings_excluded_non_residential=0,
                allocation_method="Departmental Censo 2024 exact allocation",
                evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                uncertainty_pct=0.0,
            )
            raw_b = hh_gen.generate_population(dummy_disc, q_res, dummy_alloc, seed=42, max_sample_households=150)
            cal_b, cal_r = cal_eng.calibrate_batch(raw_b, q_res, dummy_alloc, seed=42)
            total_nat_rep += cal_b.represented_population_total
            total_nat_sample_hh += cal_b.simulated_sample_households
            dept_srmses.append(cal_r.srmse)

        benchmarks["national_14_departments"] = {
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 2),
            "departments_processed": len(dept_srmses),
            "represented_population_total": total_nat_rep,
            "sample_households_total": total_nat_sample_hh,
            "mean_srmse": round(sum(dept_srmses) / max(1, len(dept_srmses)), 4),
            "max_srmse": max(dept_srmses) if dept_srmses else 0.0,
        }

        rss_end = _rss_mb()
        out = {
            "santa_tecla_validation": santa_tecla,
            "scalability_benchmarks": benchmarks,
            "memory_rss_mb": {"start": rss_start, "end": rss_end},
        }
        Path("PHASE_118_VALIDATION_RESULTS.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print("Saved PHASE_118_VALIDATION_RESULTS.json")
        print(json.dumps({"benchmarks": benchmarks, "rss_mb": out["memory_rss_mb"], "st_elapsed_ms": santa_tecla["elapsed_ms"]}, indent=2))
    finally:
        pipe.close()


if __name__ == "__main__":
    main()
