"""Tests E: Human Mobility, Barriers, Service Assignment & Extensible Sector Context Engine."""

from __future__ import annotations

from saltbor.census_intelligence import (
    EvidenceClassification,
    SectorContextReport,
    SectorAnalyzer,
    TerritorialPreparationPipeline,
    TerritorialSelectionInput,
)


class _CustomWaterSectorAnalyzer(SectorAnalyzer):
    sector_name = "water"

    def analyze(self, discovery, census, batch, inventory, mobility) -> SectorContextReport:
        return SectorContextReport(
            sector_name="water",
            target_population_summary={"represented_households": batch.represented_households_total},
            existing_facilities_summary={"waterways": len([e for e in inventory.entities if e.domain == "ENVIRONMENT"])},
            accessibility_summary={"connected_households": mobility.households_connected},
        )


def test_mobility_separates_observed_estimated_synthetic_and_sector_plugins():
    pipe = TerritorialPreparationPipeline()
    try:
        # Built-in sectors: school, health, market, road
        for sec in ("school", "health", "market", "road"):
            prep = pipe.prepare(
                TerritorialSelectionInput(lat=13.667, lon=-89.287, travel_time_minutes=15.0, sector=sec, seed=42),
                max_sample_households=100,
            )
            assert prep.sector_context.sector_name == sec
            assert prep.mobility_accessibility.observed_mobility_available is False
            assert prep.mobility_accessibility.households_connected > 0
            assert prep.provenance_integrity["valid"] is True

            # Verify OBSERVED mobility is explicitly UNAVAILABLE while synthetic choices have declared hypotheses
            obs_ind = next(i for i in prep.mobility_accessibility.provenanced_indicators if i.indicator_id == "mobility_observed_od_counts")
            assert obs_ind.evidence_type == EvidenceClassification.UNAVAILABLE
            assert obs_ind.value is None
            assert len(prep.mobility_accessibility.declared_hypotheses) >= 2

        # Register new custom sector without rewriting core engine
        pipe.sector_engine.register_sector("water", _CustomWaterSectorAnalyzer())
        prep_w = pipe.prepare(
            TerritorialSelectionInput(lat=13.667, lon=-89.287, sector="water", seed=42),
            max_sample_households=60,
        )
        assert prep_w.sector_context.sector_name == "water"
        assert prep_w.sector_context.target_population_summary["represented_households"] > 0
    finally:
        pipe.close()
