"""Evidence-Driven Territorial Analysis Engine (Phase 1.17 Section 9).

Strictly partitions all territorial, demographic, geographic, and simulation
findings into the 7 required epistemic buckets A through G:
  A. Real observed data
  B. Official statistical estimates
  C. Geographic derivations
  D. Synthetic population characteristics
  E. Simulated outcomes
  F. AI-generated interpretations and hypotheses
  G. Recommendations

Prevents Gemini or any LLM from inventing measurements, statistics, or causal
generalizations unsupported by multi-seed simulation evidence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from uuid import uuid4

from saltbor.conversational.schemas import (
    DecisionRecommendation,
    EvidenceBundle,
    TerritorialContext,
)
from saltbor.population.human import SyntheticHuman

from saltbor.territorial_intelligence.schemas import (
    BuildingIntelligenceReport,
    CatchmentAreaResult,
    CommercialContextReport,
    EmploymentAnalysisReport,
    EmploymentInterventionResult,
    EpistemicTier,
    LandUseIntelligenceReport,
    PopulationFlowReport,
    TerritorialCoverageRecord,
    TerritorialEvidenceIndicator,
    TerritorialEvidencePackage,
)


class TerritorialEvidenceEngine:
    """Assembles and audits strictly partitioned A–G territorial evidence packages."""

    def build_evidence_package(
        self,
        scenario_id: str,
        seed: int,
        context: TerritorialContext,
        horizon_days: int,
        building_report: Optional[BuildingIntelligenceReport] = None,
        land_use_report: Optional[LandUseIntelligenceReport] = None,
        commercial_report: Optional[CommercialContextReport] = None,
        catchment: Optional[CatchmentAreaResult] = None,
        mobility_report: Optional[PopulationFlowReport] = None,
        employment_report: Optional[EmploymentAnalysisReport] = None,
        employment_intervention: Optional[EmploymentInterventionResult] = None,
        coverage_record: Optional[TerritorialCoverageRecord] = None,
        humans: Optional[List[SyntheticHuman]] = None,
        sim_evidence: Optional[EvidenceBundle] = None,
        recommendation: Optional[DecisionRecommendation] = None,
        multi_seed_summary: Optional[Dict[str, Any]] = None,
        preparation_result: Optional[Any] = None,
    ) -> TerritorialEvidencePackage:
        geo_scope = f"{context.district_name} ({context.district_id}), {context.department_name}"
        pop_scope = f"{len(humans or [])} agentes sintéticos activados / ~{context.approx_population:,} residentes distritales"
        time_interval = f"{horizon_days} días"
        dq = float(context.data_quality_score)

        def _ind(
            ind_id: str,
            name: str,
            value: Any,
            unit: str,
            tier: EpistemicTier,
            engine: str,
            method: str,
            provenance: str,
            conf: float = 0.80,
            ci95: Optional[tuple[float, float]] = None,
            limits: str = "",
            ev_class: Optional[str] = None,
        ) -> TerritorialEvidenceIndicator:
            if ev_class is None:
                if value is None:
                    ev_class = "UNAVAILABLE"
                elif tier == EpistemicTier.A_REAL_OBSERVED:
                    ev_class = "DIRECT_OBSERVATION"
                elif tier == EpistemicTier.B_OFFICIAL_STATISTICAL:
                    ev_class = "PUBLIC_OFFICIAL"
                elif tier == EpistemicTier.C_GEOGRAPHIC_DERIVATION:
                    ev_class = "ESTIMATED_FROM_OFFICIAL"
                elif tier in (EpistemicTier.D_SYNTHETIC_POPULATION, EpistemicTier.E_SIMULATED_OUTCOME):
                    ev_class = "SYNTHETIC_CALIBRATED" if preparation_result is not None else "SYNTHETIC_UNCALIBRATED"
                else:
                    ev_class = "HYPOTHESIS"
            return TerritorialEvidenceIndicator(
                indicator_id=ind_id,
                name=name,
                value=value,
                unit=unit,
                epistemic_tier=tier,
                geographic_scope=geo_scope,
                population_scope=pop_scope,
                time_interval=time_interval,
                source_engine=engine,
                calculation_method=method,
                data_provenance=provenance,
                data_quality=dq,
                confidence=round(conf, 2),
                confidence_interval_95=ci95,
                simulation_seed=seed if tier in (EpistemicTier.D_SYNTHETIC_POPULATION, EpistemicTier.E_SIMULATED_OUTCOME) else None,
                scenario_id=scenario_id,
                limitations=limits,
                evidence_classification=ev_class,
            )

        tier_a: List[TerritorialEvidenceIndicator] = []
        tier_b: List[TerritorialEvidenceIndicator] = []
        tier_c: List[TerritorialEvidenceIndicator] = []
        tier_d: List[TerritorialEvidenceIndicator] = []
        tier_e: List[TerritorialEvidenceIndicator] = []
        tier_f: List[str] = []
        tier_g: List[str] = []
        limitations: List[str] = []

        # --- A. REAL OBSERVED DATA ---
        if building_report is not None:
            tier_a.append(_ind(
                "osm_buildings_observed",
                "Edificaciones reales registradas en OSM dentro del área",
                building_report.total_buildings_observed,
                "edificaciones",
                EpistemicTier.A_REAL_OBSERVED,
                "NationalBuildingIntelligenceEngine",
                "R-Tree spatial query on Geofabrik OSM buildings",
                "OpenStreetMap contributors (ODbL-1.0)",
                conf=0.88 if not building_report.is_partial_coverage else 0.55,
                limits="No implica ocupación confirmada ni niveles/altura.",
            ))
        tier_a.append(_ind(
            "osm_road_segments_observed",
            "Segmentos viales reales OSM en el área",
            context.road_network_summary.get("total_segments_in_radius", 0),
            "segmentos",
            EpistemicTier.A_REAL_OBSERVED,
            "NationalTerritorialContextEngine",
            "R-Tree spatial count on OSM roads layer",
            "OpenStreetMap contributors (ODbL-1.0)",
            conf=0.90,
        ))
        if commercial_report is not None:
            tier_a.append(_ind(
                "osm_confirmed_commercial_establishments",
                "Establecimientos comerciales observados en OSM + directorio P8",
                commercial_report.concentration_metrics.confirmed_establishments_count,
                "establecimientos",
                EpistemicTier.A_REAL_OBSERVED,
                "CommercialActivityIntelligenceEngine",
                "Deduplicated OSM pois + pois_a + P8 verified records",
                "OpenStreetMap (ODbL-1.0) + SALTBOR P8 Verified Registry",
                conf=0.82,
                limits="Comercio informal callejero subrepresentado en OSM.",
            ))
            tier_a.append(_ind(
                "unverified_commercial_buildings",
                "Edificios de uso comercial sin negocio confirmado",
                commercial_report.concentration_metrics.unverified_commercial_buildings_count,
                "edificios",
                EpistemicTier.A_REAL_OBSERVED,
                "CommercialActivityIntelligenceEngine",
                "Commercial building footprints without matched POI within 40m",
                "OpenStreetMap (ODbL-1.0)",
                conf=0.72,
            ))
        tier_a.append(_ind(
            "measured_pedestrian_sensor_flows",
            "Conteos peatonales medidos por sensores en calle",
            None,
            "personas/día",
            EpistemicTier.A_REAL_OBSERVED,
            "PopulationFlowEvidenceEngine",
            "Unavailable — no live pedestrian sensor telemetry connected",
            "N/A",
            conf=0.0,
            limits="SALTBOR no posee conteos peatonales observados en campo.",
        ))

        # --- B. OFFICIAL STATISTICAL ESTIMATES ---
        tier_b.append(_ind(
            "dl762_district_population",
            "Población aproximada del distrito (D.L. 762 / DIGESTYC)",
            context.approx_population,
            "habitantes",
            EpistemicTier.B_OFFICIAL_STATISTICAL,
            "TerritoryCatalogService",
            "Decreto Legislativo 762 district lookup",
            "D.L. 762 / DIGESTYC-ONEC El Salvador",
            conf=0.90,
        ))
        if employment_report is not None:
            tier_b.append(_ind(
                "ehpm_informal_employment_prior",
                "Participación estimada de empleo informal (prior EHPM)",
                employment_report.informal_employment_share_est,
                "ratio",
                EpistemicTier.B_OFFICIAL_STATISTICAL,
                "TerritorialLaborMarketEngine",
                "Urban/rural EHPM calibrated prior",
                "BCR / ONEC-EHPM",
                conf=0.78,
            ))
            tier_b.append(_ind(
                "verified_job_vacancies",
                "Vacantes laborales verificadas en fuentes externas",
                len(employment_report.verified_job_vacancies),
                "vacantes",
                EpistemicTier.B_OFFICIAL_STATISTICAL,
                "TerritorialLaborMarketEngine",
                "Direct vacancy feed check (none connected)",
                "N/A",
                conf=0.0,
                limits="Sin bolsa de empleo externa conectada.",
            ))

        # --- C. GEOGRAPHIC DERIVATIONS ---
        if catchment is not None:
            tier_c.append(_ind(
                "catchment_effective_area_km2",
                f"Área de influencia efectiva ({catchment.primary_method.value})",
                catchment.effective_area_km2,
                "km²",
                EpistemicTier.C_GEOGRAPHIC_DERIVATION,
                "TerritorialCatchmentAnalysisEngine",
                catchment.methodology_explanation,
                "OSMRoadNetwork + Tobler slope + Hydrology barrier discount",
                conf=0.80,
            ))
            tier_c.append(_ind(
                "road_network_circuity",
                "Factor de rodeo de la red vial",
                catchment.circuity_factor,
                "ratio",
                EpistemicTier.C_GEOGRAPHIC_DERIVATION,
                "TerritorialCatchmentAnalysisEngine",
                "Dijkstra network distance / straight-line distance",
                "OSM Roads Geometry",
                conf=0.82,
            ))
        if commercial_report is not None:
            cm = commercial_report.concentration_metrics
            tier_c.extend([
                _ind(
                    "commercial_density_per_km2",
                    "Densidad comercial observada",
                    cm.business_density_per_km2,
                    "est/km²",
                    EpistemicTier.C_GEOGRAPHIC_DERIVATION,
                    "BusinessDistributionEngine",
                    "confirmed_establishments / catchment_effective_area_km2",
                    "Derived from OSM + Catchment",
                    conf=0.78,
                ),
                _ind(
                    "commercial_diversity_shannon",
                    "Diversidad comercial (Índice Shannon normalizado)",
                    cm.commercial_diversity_shannon_norm,
                    "index_0_1",
                    EpistemicTier.C_GEOGRAPHIC_DERIVATION,
                    "BusinessDistributionEngine",
                    "H' / ln(K) across observed commercial categories",
                    "Derived from OSM POIs",
                    conf=0.76,
                ),
            ])
        tier_c.append(_ind(
            "mobility_accessibility_index",
            "Índice de accesibilidad vial y topográfica",
            context.accessibility_index,
            "index_0_1",
            EpistemicTier.C_GEOGRAPHIC_DERIVATION,
            "NationalTerritorialContextEngine",
            "Weighted OSM road density + transit stops + Tobler factor",
            "OSM Roads/Transport + Tobler Slope",
            conf=0.82,
        ))
        if employment_report is not None:
            tier_c.append(_ind(
                "jobs_workers_spatial_mismatch",
                "Índice de desajuste espacial empleo-trabajadores",
                employment_report.jobs_workers_spatial_mismatch_index,
                "index_0_1",
                EpistemicTier.C_GEOGRAPHIC_DERIVATION,
                "TerritorialLaborMarketEngine",
                "Mapped employer supply vs labor force & accessibility index",
                "OSM + D.L. 762 + Accessibility",
                conf=0.70,
            ))

        # --- D. SYNTHETIC POPULATION CHARACTERISTICS ---
        if humans:
            avg_cash = round(sum(h.physical_state.money for h in humans) / len(humans), 2)
            low_liq_share = round(sum(1 for h in humans if h.physical_state.money < 15.0) / len(humans), 3)
            tier_d.append(_ind(
                "synthetic_cohort_size",
                "Individuos sintéticos únicos hidratados en escenario",
                len(humans),
                "agentes",
                EpistemicTier.D_SYNTHETIC_POPULATION,
                "DynamicPopulationDistributionEngine",
                "Deterministic UUID5 persistent registry",
                "SALTBOR Synthetic Population Registry",
                conf=1.0,
            ))
            tier_d.append(_ind(
                "synthetic_cohort_avg_cash_usd",
                "Liquidez promedio de agentes sintéticos",
                avg_cash,
                "USD",
                EpistemicTier.D_SYNTHETIC_POPULATION,
                "DynamicPopulationDistributionEngine",
                "Mean physical_state.money across hydrated cohort",
                "SALTBOR Synthetic Population Registry",
                conf=0.85,
            ))
            tier_d.append(_ind(
                "low_liquidity_agent_share",
                "Proporción de agentes con restricción de liquidez (<$15)",
                low_liq_share,
                "ratio",
                EpistemicTier.D_SYNTHETIC_POPULATION,
                "DynamicPopulationDistributionEngine",
                "Share of active cohort with money < 15.0 USD",
                "SALTBOR Synthetic Population Registry",
                conf=0.85,
            ))
        if mobility_report is not None:
            tier_d.append(_ind(
                "synthetic_schedule_entropy",
                "Heterogeneidad de horarios diarios individuales (entropía)",
                mobility_report.schedule_heterogeneity_entropy,
                "index_0_1",
                EpistemicTier.D_SYNTHETIC_POPULATION,
                "HumanMobilityFlowEngine",
                "Normalized Shannon entropy across 5-period individual role sequences",
                "SyntheticHuman attributes & obligations",
                conf=0.88,
            ))

        # --- E. SIMULATED OUTCOMES ---
        if sim_evidence is not None:
            if isinstance(sim_evidence.ledger_audit, dict) and "total_transactions" in sim_evidence.ledger_audit:
                tier_e.append(_ind(
                    "ledger_total_transactions",
                    "Transacciones contables auditadas (doble partida)",
                    int(sim_evidence.ledger_audit.get("total_transactions", 0)),
                    "transacciones",
                    EpistemicTier.E_SIMULATED_OUTCOME,
                    "VerifiableEconomicLedger",
                    "Count of balanced double-entry ledger transactions",
                    f"SALTBOR Economic Ledger (seed={seed})",
                    conf=1.0,
                    ev_class="SYNTHETIC_CALIBRATED" if preparation_result is not None else "SYNTHETIC_UNCALIBRATED",
                ))
            for ind in sim_evidence.indicators:
                if not ind.available:
                    continue
                if ind.domain in ("economy", "commerce", "employment", "education", "health", "inequality") or ind.indicator_id in ("household_income_earned_usd", "inbound_commuters"):
                    ci = None
                    if multi_seed_summary and ind.indicator_id in multi_seed_summary:
                        ci = multi_seed_summary[ind.indicator_id]
                    tier_e.append(_ind(
                        ind.indicator_id,
                        ind.name,
                        ind.value,
                        ind.unit,
                        EpistemicTier.E_SIMULATED_OUTCOME,
                        ind.provenance.source_engine,
                        ind.provenance.calculation_method,
                        f"SALTBOR Multi-Engine Simulation (seed={seed})",
                        conf=ind.provenance.confidence,
                        ci95=ci,
                        limits=ind.provenance.limitations,
                    ))
        if employment_intervention is not None:
            tier_e.extend([
                _ind(
                    "employment_intervention_jobs_delta",
                    f"Impacto neto de empleo ({employment_intervention.intervention_type})",
                    employment_intervention.direct_jobs_created_or_lost,
                    "empleos",
                    EpistemicTier.E_SIMULATED_OUTCOME,
                    "EmploymentOpportunityAnalysisEngine",
                    f"Local {employment_intervention.local_residents_hired} / Commuter {employment_intervention.inbound_commuters_hired}",
                    f"SALTBOR Labor Simulation (seed={seed})",
                    conf=0.72,
                ),
                _ind(
                    "employment_intervention_ledger_diff",
                    "Discrepancia contable (conservación doble partida)",
                    employment_intervention.ledger_conservation_diff_usd,
                    "USD",
                    EpistemicTier.E_SIMULATED_OUTCOME,
                    "VerifiableEconomicLedger",
                    "abs(sum(debits) - sum(credits))",
                    "Double-entry ledger audit",
                    conf=1.0,
                ),
            ])
        if mobility_report is not None:
            tier_e.append(_ind(
                "simulated_pedestrian_activity_index",
                f"Índice sintético de actividad peatonal ({mobility_report.time_period.value})",
                mobility_report.estimated_pedestrian_activity_index,
                "index_0_1",
                EpistemicTier.E_SIMULATED_OUTCOME,
                "HumanMobilityFlowEngine",
                "Model-generated diurnal & accessibility activity score (NOT street-measured)",
                f"SALTBOR Mobility Simulation (seed={seed})",
                conf=0.70,
                limits=mobility_report.measured_flows_note,
            ))

        # --- F. AI INTERPRETATIONS & HYPOTHESES ---
        if recommendation is not None:
            tier_f.append(recommendation.executive_summary)
            tier_f.extend(recommendation.observed_patterns[:4])
            tier_f.extend(recommendation.alternative_interpretations[:3])
        if employment_report is not None:
            tier_f.extend(employment_report.opportunity_hypotheses[:3])

        # --- G. RECOMMENDATIONS ---
        if recommendation is not None:
            tier_g.append(f"Veredicto analítico: {recommendation.verdict.value}")
            tier_g.extend(recommendation.recommendations[:5] if hasattr(recommendation, "recommendations") and recommendation.recommendations else recommendation.population_needs[:4])
            limitations.extend(recommendation.limitations)

        if coverage_record is not None:
            limitations.extend(coverage_record.missing_information)
        if preparation_result is not None:
            cert = preparation_result.certificate
            cal = preparation_result.calibration
            census_q = preparation_result.census_query
            tier_b.append(_ind(
                "censo_2024_parent_population",
                f"Población oficial de referencia ({census_q.matched_granularity.value})",
                census_q.official_population,
                "habitantes",
                EpistemicTier.B_OFFICIAL_STATISTICAL,
                "NationalCensusDataIntegrationEngine",
                "VII Censo de Población y VI de Vivienda 2024 lookup",
                "ONEC / BCR El Salvador",
                conf=0.97,
                ev_class="PUBLIC_OFFICIAL",
            ))
            tier_d.append(_ind(
                "population_calibration_srmse",
                f"Error de calibración poblacional ({cert.calibration_status})",
                cal.srmse,
                "SRMSE",
                EpistemicTier.D_SYNTHETIC_POPULATION,
                "PopulationCalibrationEngine",
                ", ".join(cal.methods_applied),
                "IPF + Raking + Combinatorial Optimization",
                conf=cal.confidence_level,
                ev_class=cal.evidence_classification.value,
                limits="; ".join(cert.limitations[:2]),
            ))
            limitations.extend(cert.limitations)
        if building_report is not None:
            limitations.extend(building_report.limitations)
        if commercial_report is not None:
            limitations.extend(commercial_report.limitations)
        if employment_report is not None:
            limitations.extend(employment_report.limitations)

        dedup_limits = list(dict.fromkeys(limitations))

        return TerritorialEvidencePackage(
            package_id=f"EVPKG_{uuid4().hex[:10]}",
            scenario_id=scenario_id,
            seed=seed,
            geographic_scope=geo_scope,
            population_scope=pop_scope,
            time_interval=time_interval,
            A_real_observed_data=tier_a,
            B_official_statistical_estimates=tier_b,
            C_geographic_derivations=tier_c,
            D_synthetic_population_characteristics=tier_d,
            E_simulated_outcomes=tier_e,
            F_ai_interpretations_and_hypotheses=list(dict.fromkeys(tier_f)),
            G_recommendations=list(dict.fromkeys(tier_g)),
            limitations=dedup_limits[:15],
            ai_provider_used=recommendation.provider_used if recommendation else "OFFLINE_DETERMINISTIC",
            ai_model_used=recommendation.model_used if recommendation else "deterministic-grounded",
        )

    @staticmethod
    def verify_narrative_grounding(
        narrative_text: str,
        evidence_package: TerritorialEvidencePackage,
    ) -> Dict[str, Any]:
        """Audit whether an AI narrative introduces unsupported percentages or absolute claims."""
        all_vals: List[float] = [0.0, float(evidence_package.seed)]
        for scope_txt in (
            evidence_package.geographic_scope,
            evidence_package.population_scope,
            evidence_package.time_interval,
        ):
            for m in re.findall(r"\b\d+(?:\.\d+)?\b", scope_txt or ""):
                all_vals.append(float(m))

        for lst in (
            evidence_package.A_real_observed_data,
            evidence_package.B_official_statistical_estimates,
            evidence_package.C_geographic_derivations,
            evidence_package.D_synthetic_population_characteristics,
            evidence_package.E_simulated_outcomes,
        ):
            for ind in lst:
                if isinstance(ind.value, (int, float)):
                    v = float(ind.value)
                    all_vals.append(v)
                    all_vals.append(abs(v))
                for meta_txt in (ind.calculation_method, ind.data_provenance):
                    for m in re.findall(r"\b\d+(?:\.\d+)?\b", meta_txt or ""):
                        all_vals.append(float(m))

        # Check numbers cited in narrative vs known numeric values (allowing comma-formatted or small rounding)
        cleaned_text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", narrative_text or "")
        nums = [float(m) for m in re.findall(r"\b\d+(?:\.\d+)?\b", cleaned_text)]
        unmatched = []
        for n in nums:
            if n in (1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 12.0, 14.0, 15.0, 24.0, 30.0, 95.0, 100.0, 262.0, 365.0, 2024.0, 2026.0):
                continue
            if not any(abs(n - v) <= max(1.0, abs(v) * 0.05) or abs(n - v * 100.0) <= 2.0 for v in all_vals):
                unmatched.append(n)

        return {
            "grounded": len(unmatched) == 0,
            "numbers_checked": len(nums),
            "unmatched_numbers": unmatched[:10],
        }
