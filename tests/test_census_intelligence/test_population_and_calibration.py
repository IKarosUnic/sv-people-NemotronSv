"""Tests B: Synthetic Households, Family Coherence, Calibration (IPF/Raking/CO) & Reproducibility."""

from __future__ import annotations

from saltbor.census_intelligence import (
    EvidenceClassification,
    NationalCensusDataIntegrationEngine,
    PopulationCalibrationEngine,
    SyntheticHouseholdGenerationEngine,
    TerritorialContextDiscoveryEngine,
    TerritorialSelectionInput,
    GeospatialPopulationAllocationEngine,
    GeographicGranularity,
)


def test_households_first_generation_family_coherence_and_reproducibility():
    discovery_eng = TerritorialContextDiscoveryEngine()
    census_eng = NationalCensusDataIntegrationEngine()
    alloc_eng = GeospatialPopulationAllocationEngine(geography=discovery_eng.geography, census_engine=census_eng)
    hh_gen = SyntheticHouseholdGenerationEngine()
    cal_eng = PopulationCalibrationEngine()

    try:
        disc = discovery_eng.discover(
            TerritorialSelectionInput(lat=13.667, lon=-89.287, travel_time_minutes=15.0, sector="school", seed=77)
        )
        alloc = alloc_eng.allocate_population(disc)
        census_q = census_eng.query_area_statistics(
            disc.primary_district_id,
            GeographicGranularity.CUSTOM_POLYGON,
            local_residential_share=alloc.polygon_share_of_district,
            local_building_capacity_estimate=alloc.allocated_population_target,
        )

        raw_1 = hh_gen.generate_population(disc, census_q, alloc, seed=77)
        cal_1, rep_1 = cal_eng.calibrate_batch(raw_1, census_q, alloc, seed=77)

        raw_2 = hh_gen.generate_population(disc, census_q, alloc, seed=77)
        cal_2, rep_2 = cal_eng.calibrate_batch(raw_2, census_q, alloc, seed=77)

        # Deterministic reproducibility
        assert [p.person_id for p in cal_1.persons] == [p.person_id for p in cal_2.persons]
        assert rep_1.srmse == rep_2.srmse
        assert rep_1.ipf_converged is True
        assert rep_1.raking_converged is True
        assert rep_1.calibration_passed is True
        assert rep_1.srmse <= 0.14
        assert rep_1.evidence_classification == EvidenceClassification.SYNTHETIC_CALIBRATED

        # Verify households-first family age coherence (every child younger than household head by >= 15 years)
        by_hh = {}
        for p in cal_1.persons:
            by_hh.setdefault(p.household_id, []).append(p)
        for hh in cal_1.households:
            members = by_hh[hh.household_id]
            assert len(members) == hh.household_size
            heads = [m for m in members if m.relationship_to_head == "head"]
            assert len(heads) == 1
            head_age = heads[0].age
            for m in members:
                if m.relationship_to_head == "child":
                    assert head_age - m.age >= 15
    finally:
        discovery_eng.close()


def test_uncalibrated_warning_and_confidence_reduction_on_strict_threshold():
    discovery_eng = TerritorialContextDiscoveryEngine()
    census_eng = NationalCensusDataIntegrationEngine()
    alloc_eng = GeospatialPopulationAllocationEngine(geography=discovery_eng.geography, census_engine=census_eng)
    hh_gen = SyntheticHouseholdGenerationEngine()
    # Set ultra-strict impossible threshold (srmse <= 0.0001) to verify warning & confidence downgrade
    strict_cal = PopulationCalibrationEngine(srmse_threshold=0.0001, max_rel_error_threshold_pct=0.01)

    try:
        disc = discovery_eng.discover(TerritorialSelectionInput(lat=13.667, lon=-89.287, seed=42))
        alloc = alloc_eng.allocate_population(disc)
        census_q = census_eng.query_area_statistics(disc.primary_district_id, GeographicGranularity.CUSTOM_POLYGON)
        raw = hh_gen.generate_population(disc, census_q, alloc, seed=42)
        _, rep = strict_cal.calibrate_batch(raw, census_q, alloc, seed=42)

        assert rep.calibration_passed is False
        assert rep.evidence_classification == EvidenceClassification.SYNTHETIC_UNCALIBRATED
        assert len(rep.warnings) >= 1
        assert len(rep.uncalibrated_variables) >= 1
        assert rep.confidence_level < 0.55
    finally:
        discovery_eng.close()
