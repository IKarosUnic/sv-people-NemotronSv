"""Mandatory End-to-End Territorial & Population Preparation Pipeline (Phase 1.18 Section 2).

Enforces the exact architectural chain before simulation execution:
  TerritorialContextDiscoveryEngine (OSM + Dynamic 3-Scale Expansion)
  -> NationalCensusDataIntegrationEngine (Censo 2024 + EHPM + MINED + SAE)
  -> GeospatialPopulationAllocationEngine (Dasymetric residential allocation)
  -> SyntheticHouseholdGenerationEngine (Households-first generation)
  -> PopulationCalibrationEngine (IPF + Raking + Combinatorial Optimization)
  -> InfrastructureServiceDiscoveryEngine (Deduplicated 5-domain inventory)
  -> HumanMobilityAccessibilityEngine (Household-to-service accessibility)
  -> SectorSpecificContextEngine (Adaptive sector context & gaps)
  -> Universal 8-Class Provenance Validation & Preparation Certificate
"""

from __future__ import annotations

import time
from typing import Optional
from uuid import uuid4

from saltbor.conversational.territorial_context import NationalTerritorialContextEngine
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography

from saltbor.census_intelligence.calibration import PopulationCalibrationEngine
from saltbor.census_intelligence.census_engine import NationalCensusDataIntegrationEngine
from saltbor.census_intelligence.household_generator import SyntheticHouseholdGenerationEngine
from saltbor.census_intelligence.infrastructure_discovery import InfrastructureServiceDiscoveryEngine
from saltbor.census_intelligence.mobility_accessibility import HumanMobilityAccessibilityEngine
from saltbor.census_intelligence.population_allocation import GeospatialPopulationAllocationEngine
from saltbor.census_intelligence.schemas import (
    EvidenceClassification,
    GeographicGranularity,
    ProvenancedIndicator,
    TerritorialPreparationResult,
    TerritorialSelectionInput,
    validate_provenance_integrity,
)
from saltbor.census_intelligence.sector_context import SectorSpecificContextEngine
from saltbor.census_intelligence.territorial_discovery import TerritorialContextDiscoveryEngine


class TerritorialPreparationPipeline:
    """Mandatory unified pipeline preparing grounded territory & calibrated synthetic population."""

    def __init__(
        self,
        geography: Optional[IngestedGeography] = None,
        territorial_engine: Optional[NationalTerritorialContextEngine] = None,
        census_engine: Optional[NationalCensusDataIntegrationEngine] = None,
        cache_db_path: str = ":memory:",
    ) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self._owns_territorial = territorial_engine is None
        self.territorial_engine = territorial_engine or NationalTerritorialContextEngine()
        self.census_engine = census_engine or NationalCensusDataIntegrationEngine()

        self.discovery_engine = TerritorialContextDiscoveryEngine(
            territorial_engine=self.territorial_engine,
            geography=self.geography,
            cache_db_path=cache_db_path,
        )
        self.allocation_engine = GeospatialPopulationAllocationEngine(
            geography=self.geography,
            census_engine=self.census_engine,
        )
        self.household_generator = SyntheticHouseholdGenerationEngine()
        self.calibration_engine = PopulationCalibrationEngine()
        self.infrastructure_engine = InfrastructureServiceDiscoveryEngine(
            geography=self.geography,
            census_engine=self.census_engine,
        )
        self.mobility_engine = HumanMobilityAccessibilityEngine()
        self.sector_engine = SectorSpecificContextEngine()

    def close(self) -> None:
        self.discovery_engine.close()
        if self._owns_territorial:
            self.territorial_engine.close()
        if self._owns_geo:
            self.geography.close()

    def prepare(
        self,
        selection: TerritorialSelectionInput,
        max_sample_households: int = 450,
    ) -> TerritorialPreparationResult:
        """Execute full mandatory Phase 1.18 preparation chain."""
        t0 = time.perf_counter()

        # 1. Territorial Context Discovery & Dynamic 3-Scale Expansion (incl. OSM intelligence)
        discovery = self.discovery_engine.discover(selection)

        # 2. Geospatial Population Allocation + Census/SAE Integration
        allocation = self.allocation_engine.allocate_population(discovery=discovery)
        census_query = self.census_engine.query_area_statistics(
            district_id=discovery.primary_district_id,
            requested_granularity=(
                self.census_engine.resolve_geographic_unit(discovery.primary_district_id)[2]
                if discovery.selection_mode == "administrative_query" and discovery.expansion.primary_area.area_km2 >= 0.5
                else GeographicGranularity.CUSTOM_POLYGON
            ),
            custom_area_label=discovery.expansion.primary_area.label,
            local_residential_share=allocation.polygon_share_of_district,
            local_building_capacity_estimate=allocation.allocated_population_target,
        )

        # 3. Synthetic Household & Person Generation (households first)
        raw_batch = self.household_generator.generate_population(
            discovery=discovery,
            census=census_query,
            allocation=allocation,
            seed=selection.seed,
            max_sample_households=max_sample_households,
        )

        # 4. Mandatory Population Calibration (IPF + Raking + Combinatorial Optimization)
        calibrated_batch, calibration_report = self.calibration_engine.calibrate_batch(
            batch=raw_batch,
            census=census_query,
            allocation=allocation,
            seed=selection.seed,
        )
        scope = f"{discovery.primary_district_name} ({discovery.primary_district_id}), {discovery.department_name}"
        certificate = self.calibration_engine.build_preparation_certificate(
            seed=selection.seed,
            territorial_scope=scope,
            census=census_query,
            allocation=allocation,
            calibration=calibration_report,
        )

        # 5. Infrastructure & Service Discovery across 3 scales
        inventory = self.infrastructure_engine.discover_inventory(discovery=discovery)

        # 6. Human Mobility & Accessibility connecting households to services
        mobility = self.mobility_engine.analyze_accessibility(
            discovery=discovery,
            batch=calibrated_batch,
            inventory=inventory,
            sector=selection.sector,
            travel_time_budget_min=selection.travel_time_minutes,
        )

        # 7. Adaptive Sector-Specific Context
        sector_ctx = self.sector_engine.analyze(
            sector=selection.sector,
            discovery=discovery,
            census=census_query,
            batch=calibrated_batch,
            inventory=inventory,
            mobility=mobility,
        )

        # 8. Consolidate & Validate Universal Provenance Integrity
        indicators = [
            ProvenancedIndicator(
                indicator_id="prep_parent_official_population",
                name="Población oficial de unidad censal de referencia",
                value=census_query.official_population,
                unit="habitantes",
                source="VII Censo de Población y VI de Vivienda 2024 (ONEC/BCR)",
                evidence_type=EvidenceClassification.PUBLIC_OFFICIAL,
                reference_date="2024-10-29",
                territorial_coverage=scope,
                method="Official Censo 2024 dataset lookup",
                confidence_level=0.97,
            ),
            ProvenancedIndicator(
                indicator_id="prep_allocated_area_population",
                name="Población asignada al Área Principal",
                value=allocation.allocated_population_target,
                unit="habitantes",
                source="GeospatialPopulationAllocationEngine + Censo 2024",
                evidence_type=allocation.evidence_type,
                reference_date="2024-10-29",
                territorial_coverage=discovery.expansion.primary_area.label,
                method=allocation.allocation_method,
                confidence_level=round(max(0.35, 1.0 - allocation.uncertainty_pct / 100.0), 2),
                uncertainty=f"±{allocation.uncertainty_pct:.1f}%",
            ),
            ProvenancedIndicator(
                indicator_id="prep_calibrated_synthetic_households",
                name="Hogares sintéticos representados",
                value=calibrated_batch.represented_households_total,
                unit="hogares",
                source="SyntheticHouseholdGenerationEngine + PopulationCalibrationEngine",
                evidence_type=calibration_report.evidence_classification,
                reference_date="2026-11-23",
                territorial_coverage=discovery.expansion.primary_area.label,
                method=", ".join(calibration_report.methods_applied),
                confidence_level=calibration_report.confidence_level,
                uncertainty=f"SRMSE={calibration_report.srmse:.4f}",
            ),
        ]
        indicators.extend(sector_ctx.provenanced_indicators)
        indicators.extend(mobility.provenanced_indicators)

        integrity = validate_provenance_integrity(indicators)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        return TerritorialPreparationResult(
            preparation_id=f"PREP_118_{uuid4().hex[:8]}",
            discovery=discovery,
            census_query=census_query,
            allocation=allocation,
            population_batch=calibrated_batch,
            calibration=calibration_report,
            certificate=certificate,
            infrastructure=inventory,
            sector_context=sector_ctx,
            mobility_accessibility=mobility,
            provenanced_indicators=indicators,
            provenance_integrity=integrity,
            elapsed_ms=elapsed_ms,
        )
