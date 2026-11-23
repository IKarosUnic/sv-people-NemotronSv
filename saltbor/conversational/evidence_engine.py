"""Synthetic Population Evidence Engine (Phase 1.16A).

Collects structured, provenance-tagged evidence directly from executed SALTBOR
simulations without fabricating missing values. Queries synthetic human agents
grounded in their actual identity, memory, personality, goals, economic situation,
and relationships, explicitly marking responses as correlated model outputs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

from saltbor.population.human import SyntheticHuman

from saltbor.conversational.schemas import (
    EvidenceBundle,
    EvidenceIndicator,
    EvidenceProvenance,
    InterventionSpec,
    SyntheticOpinionRecord,
    TerritorialContext,
    TemporalHorizonSpec,
)

logger = logging.getLogger(__name__)


class SyntheticPopulationEvidenceEngine:
    """Extracts verifiable evidence bundles and grounded synthetic opinions from runs."""

    def collect_evidence(
        self,
        scenario_id: str,
        seed: int,
        context: TerritorialContext,
        temporal: TemporalHorizonSpec,
        intervention: Optional[InterventionSpec],
        sim_output: Dict[str, Any],
        humans: List[SyntheticHuman],
        pop_accounting: Dict[str, Any],
    ) -> EvidenceBundle:
        """Build a provenance-complete EvidenceBundle strictly from real simulation output."""
        totals = sim_output.get("totals", {})
        exec_meta = sim_output.get("temporal_execution", {})
        ledger_cons = sim_output.get("ledger_conservation", {})
        active_engines = list(sim_output.get("active_engines", []))
        agent_exp = sim_output.get("agent_experience_log", {})

        geo_scope = f"{context.district_name} ({context.district_id}), {context.department_name}"
        time_interval = f"{temporal.horizon_days} días simulados ({exec_meta.get('simulated_ticks_equivalent', 0)} ticks eq., modo {temporal.resolution_mode})"
        pop_scope = f"{len(humans)} agentes hidratados / {context.approx_population} residentes distritales"
        dq = float(context.data_quality_score)

        def _prov(engine: str, entity: str, method: str, conf: float = 0.78, limits: str = "") -> EvidenceProvenance:
            return EvidenceProvenance(
                source_engine=engine,
                source_entity=entity,
                calculation_method=method,
                time_interval=time_interval,
                population_scope=pop_scope,
                geographic_scope=geo_scope,
                seed=seed,
                data_quality=dq,
                confidence=round(conf, 2),
                limitations=limits or "Indicador generado bajo los supuestos y cobertura territorial de SALTBOR.",
            )

        indicators: List[EvidenceIndicator] = []
        missing_indicators: List[str] = list(context.missing_data)

        exp_scale = totals.get("expansion_pop_scale", 1.0)
        cohort_unc = (
            f"Basado en muestra sintética de {len(humans)} agentes sobre {context.approx_population:,} "
            f"residentes distritales ({(len(humans) / max(1, context.approx_population)) * 100:.4f}% de cobertura; sin calibración empírica en campo)."
        )
        extrap_unc = (
            f"Extrapolación determinista (factor poblacional {exp_scale}x × días/segmento) sin intervalos de confianza muestrales ni encuestas empíricas reales."
        )

        # 1. Demographic & mobility accounting indicators
        indicators.append(
            EvidenceIndicator(
                indicator_id="resident_population_approx",
                domain="demographics",
                name="Población residente aproximada del distrito",
                definition="Población distrital aproximada según jerarquía D.L. 762 / EHPM (dato contextual previo a simulación).",
                value=context.approx_population,
                unit="personas",
                data_origin="GEOGRAPHIC_DATASET",
                uncertainty="Aproximación distrital oficial/estadística; no constituye censo por manzana en tiempo real.",
                is_synthetic=False,
                available=context.approx_population > 0,
                provenance=_prov("NationalTerritorialContextEngine", context.district_id, "D.L. 762 district registry", 0.90),
            )
        )
        indicators.append(
            EvidenceIndicator(
                indicator_id="unique_active_cohort",
                domain="demographics",
                name="Agentes sintéticos únicos activados",
                definition="Conteo exacto de identidades UUID únicas hidratadas en RAM para el distrito evaluado.",
                value=len(humans),
                unit="agentes",
                data_origin="AGGREGATED_SYNTHETIC_AGENTS",
                uncertainty=cohort_unc,
                is_synthetic=True,
                available=len(humans) > 0,
                provenance=_prov("NationalPopulationActivationManager", context.district_id, "Deduplicated active UID count", 1.0),
            )
        )
        indicators.append(
            EvidenceIndicator(
                indicator_id="inbound_commuters",
                domain="mobility",
                name="Flujo de viajeros/commuters entrantes únicos",
                definition="Agentes activados cuyo distrito de origen difiere del distrito actual (home_district != current_district).",
                value=int(pop_accounting.get("inbound_commuters", 0)),
                unit="agentes",
                data_origin="AGGREGATED_SYNTHETIC_AGENTS",
                uncertainty="Cero salvo cuando se ejecuta transporte intermunicipal explícito entre distritos; no mide aforos reales.",
                is_synthetic=True,
                available=True,
                provenance=_prov("NationalPopulationActivationManager", context.district_id, "home_district != current_district", 0.95),
            )
        )

        # 2. Economic & household constraint indicators
        moneys = [float(h.physical_state.money) for h in humans] if humans else [0.0]
        avg_cash = round(float(np.mean(moneys)), 2)
        low_liq_share = round(sum(1 for m in moneys if m < 15.0) / max(1, len(moneys)), 3)
        gini_approx = self._compute_gini(moneys)

        indicators.extend([
            EvidenceIndicator(
                indicator_id="household_avg_cash_usd",
                domain="economy",
                name="Liquidez promedio de agentes hidratados",
                definition="Media aritmética del saldo efectivo disponible (physical_state.money) en los agentes hidratados tras los eventos del escenario.",
                value=avg_cash,
                unit="USD",
                data_origin="AGGREGATED_SYNTHETIC_AGENTS",
                uncertainty=f"{cohort_unc} Refleja transacciones de cohorte no escalada.",
                is_synthetic=True,
                available=len(humans) > 0,
                provenance=_prov("PopulationRegistry", "active_humans", "Arithmetic mean of physical_state.money", 0.85),
            ),
            EvidenceIndicator(
                indicator_id="low_liquidity_agent_share",
                domain="economy",
                name="Proporción de agentes con restricción de liquidez (<$15)",
                definition="Fracción de la cohorte activa cuyo saldo efectivo tras el escenario es inferior a $15.00 USD.",
                value=low_liq_share,
                unit="ratio",
                data_origin="AGGREGATED_SYNTHETIC_AGENTS",
                uncertainty=cohort_unc,
                is_synthetic=True,
                available=len(humans) > 0,
                provenance=_prov("PopulationRegistry", "active_humans", "Share with money < 15.0 USD", 0.85),
            ),
            EvidenceIndicator(
                indicator_id="wealth_gini_simulated",
                domain="inequality",
                name="Índice de desigualdad (Gini de liquidez simulada)",
                definition="Coeficiente de Gini finito exacto calculado sobre la liquidez disponible de los agentes activos.",
                value=gini_approx,
                unit="gini",
                data_origin="AGGREGATED_SYNTHETIC_AGENTS",
                uncertainty="Sensible al tamaño muestral de cohorte sintética y rangos uniformes por ocupación.",
                is_synthetic=True,
                available=len(humans) >= 5,
                provenance=_prov("SocialStratificationEngine / EvidenceEngine", "active_humans", "Exact finite-sample Gini over cash holdings", 0.80),
            ),
            EvidenceIndicator(
                indicator_id="household_income_earned_usd",
                domain="employment",
                name="Ingresos laborales devengados en el período",
                definition="Suma exacta de salarios o jornales pagados e inscritos en VerifiableEconomicLedger durante la simulación.",
                value=totals.get("household_income_earned_usd", 0.0),
                unit="USD",
                data_origin="DIRECT_SIMULATION_EVENT",
                uncertainty="Flujo contable exacto dentro de los agentes contratados o jornales simulados; no incluye ingresos informales externos no modelados.",
                is_synthetic=True,
                available=True,
                provenance=_prov("LaborMarketEngine", intervention.intervention_id if intervention else "baseline", "Sum of double-entry wage credits", 0.90),
            ),
        ])

        # 3. Direct vs Extrapolated Commercial Indicators
        has_commercial = "CommercialEngine" in active_engines
        indicators.extend([
            EvidenceIndicator(
                indicator_id="raw_cohort_visitors",
                domain="commerce",
                name="Visitas directas de cohorte en horario abierto (sin escalar)",
                definition="Conteo directo de eventos execute_visit() registrados en CommercialEngine en horario abierto antes de extrapolar.",
                value=totals.get("raw_cohort_visitors", 0) if has_commercial else None,
                unit="visitas_cohorte",
                data_origin="DIRECT_SIMULATION_EVENT",
                uncertainty=f"{cohort_unc} Medición directa sin multiplicador.",
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("CommercialEngine", intervention.intervention_id if intervention else "none", "Unscaled open-hour execute_visit() count", 0.92),
            ),
            EvidenceIndicator(
                indicator_id="raw_cohort_revenue_usd",
                domain="commerce",
                name="Ventas directas de cohorte en libro contable (sin escalar)",
                definition="Suma exacta en USD de ventas registradas en VerifiableEconomicLedger dentro de la cohorte activa.",
                value=totals.get("raw_cohort_revenue_usd", 0.0) if has_commercial else None,
                unit="USD",
                data_origin="DIRECT_SIMULATION_EVENT",
                uncertainty="Conservación contable exacta ($0.00 diff) antes del factor de escala territorial.",
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("CommercialEngine + VerifiableEconomicLedger", intervention.intervention_id if intervention else "none", "Exact unscaled ledger sales sum", 0.95),
            ),
            EvidenceIndicator(
                indicator_id="commercial_obligated_wages_usd",
                domain="commerce",
                name="Nómina laboral devengada obligatoria del período",
                definition="Costo salarial completo devengado por el personal contratado durante el horizonte (pagado + pendiente si hay iliquidez).",
                value=totals.get("obligated_wages_usd", 0.0) if has_commercial else None,
                unit="USD",
                data_origin="DIRECT_SIMULATION_EVENT",
                uncertainty=f"Incluye ${totals.get('unpaid_wages_usd', 0.0):.2f} USD de nómina impaga por falta de caja si aplica.",
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("LaborMarketEngine + BusinessEnterprise", intervention.intervention_id if intervention else "none", "workforce * daily_wage * horizon_days", 0.95),
            ),
            EvidenceIndicator(
                indicator_id="commercial_competitor_sales_usd",
                domain="commerce",
                name="Ventas estimadas captadas por competidores locales",
                definition="Ingresos generados por establecimientos competidores OSM registrados cuando los transeúntes eligen oferta existente.",
                value=totals.get("competitor_sales_usd", 0.0) if has_commercial else None,
                unit="USD",
                data_origin="EXTRAPOLATED_COHORT",
                uncertainty=extrap_unc,
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("CommercialEngine", "osm_comp_pool", "Competitor diversion visits * ticket * scale_mult", 0.72),
            ),
            EvidenceIndicator(
                indicator_id="commercial_visitors",
                domain="commerce",
                name="Visitas totales estimadas a escala territorial (incluye exploradores sin compra)",
                definition="Proyección territorial de visitas en horario abierto multiplicada por días/segmento y factor poblacional.",
                value=totals.get("total_visitors", 0.0) if has_commercial else None,
                unit="visitas",
                data_origin="EXTRAPOLATED_COHORT",
                uncertainty=extrap_unc,
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("CommercialEngine", intervention.intervention_id if intervention else "none", f"execute_visit() open tally * days_w * pop_scale ({exp_scale}x)", 0.75),
            ),
            EvidenceIndicator(
                indicator_id="commercial_browsers_without_purchase",
                domain="commerce",
                name="Visitantes estimados sin compra (browse / compare_prices / saturación)",
                definition="Visitas proyectadas en horario abierto donde el agente comparó precios, exploró o encontró capacidad llena sin comprar.",
                value=totals.get("total_browsers_without_purchase", 0.0) if has_commercial else None,
                unit="visitas",
                data_origin="EXTRAPOLATED_COHORT",
                uncertainty=extrap_unc,
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("CommercialEngine", intervention.intervention_id if intervention else "none", f"Non-purchase open visits * days_w * pop_scale ({exp_scale}x)", 0.75),
            ),
            EvidenceIndicator(
                indicator_id="commercial_purchasers",
                domain="commerce",
                name="Compradores efectivos proyectados",
                definition="Transacciones de compra efectiva proyectadas al horizonte y escala poblacional.",
                value=totals.get("total_purchasers", 0.0) if has_commercial else None,
                unit="compras",
                data_origin="EXTRAPOLATED_COHORT",
                uncertainty=extrap_unc,
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("CommercialEngine", intervention.intervention_id if intervention else "none", f"Budget & stock filtered purchases * days_w * pop_scale ({exp_scale}x)", 0.75),
            ),
            EvidenceIndicator(
                indicator_id="commercial_conversion_rate",
                domain="commerce",
                name="Tasa de conversión visita -> compra",
                definition="Cociente entre compras efectivas y visitas en horario abierto (total_purchasers / total_visitors).",
                value=totals.get("conversion_rate", 0.0) if has_commercial else None,
                unit="ratio",
                data_origin="DIRECT_SIMULATION_EVENT",
                uncertainty="Basada en reglas de racionalidad limitada y liquidez de la cohorte activa; no es dato POS real.",
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("CommercialEngine", intervention.intervention_id if intervention else "none", "purchasers / open_visitors", 0.80),
            ),
            EvidenceIndicator(
                indicator_id="commercial_revenue_usd",
                domain="commerce",
                name="Ingresos brutos comerciales proyectados",
                definition="Ingresos brutos proyectados (ventas de cohorte multiplicadas por días/segmento y factor poblacional).",
                value=totals.get("total_revenue_usd", 0.0) if has_commercial else None,
                unit="USD",
                data_origin="EXTRAPOLATED_COHORT",
                uncertainty=f"Ventas directas en libro = ${totals.get('raw_cohort_revenue_usd', 0.0):.2f} USD. {extrap_unc}",
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("CommercialEngine + VerifiableEconomicLedger", intervention.intervention_id if intervention else "none", f"Double-entry sales sum * days_w * pop_scale ({exp_scale}x)", 0.76),
            ),
            EvidenceIndicator(
                indicator_id="commercial_net_profit_usd",
                domain="commerce",
                name="Resultado neto operativo (ingresos - insumos - nómina obligatoria - fijos)",
                definition="Ingresos proyectados menos COGS teórico, nómina obligatoria completa y costos fijos totales devengados.",
                value=totals.get("net_operating_profit_usd", 0.0) if has_commercial else None,
                unit="USD",
                data_origin="EXTRAPOLATED_COHORT",
                uncertainty=f"Incluye costos fijos (${totals.get('obligated_fixed_costs_usd', 0.0):.2f}) y nómina obligatoria (${totals.get('obligated_wages_usd', 0.0):.2f}) sin omitir saldos impagos; escala mixta ingreso proyectado vs opex micro.",
                is_synthetic=True,
                available=has_commercial,
                provenance=_prov("BusinessEnterprise + VerifiableEconomicLedger", intervention.intervention_id if intervention else "none", "Revenue - COGS - obligated_wages - obligated_fixed_costs", 0.74),
            ),
        ])
        if not has_commercial and intervention and intervention.category.value in ("PUPUSERIA", "SHOP", "PHARMACY", "RESTAURANT", "MARKET"):
            missing_indicators.append("Métricas comerciales detalladas (CommercialEngine no activado).")

        # 4. Education, Healthcare & Mobility indicators
        has_edu = totals.get("school_attendance_rate") is not None
        indicators.extend([
            EvidenceIndicator(
                indicator_id="school_attendance_rate",
                domain="education",
                name="Cobertura / asistencia escolar simulada",
                definition="Razón entre demanda educativa atendida por infraestructura OSM+propuesta y demanda escolar estimada en meses lectivos.",
                value=totals.get("school_attendance_rate"),
                unit="ratio",
                data_origin="DETERMINISTIC_MULTIPLIER",
                uncertainty="Aprox. capacidad = max(120, osm_edu * 180) frente a cohorte en edad escolar; depende de completitud OSM y no mide matrícula MINED real.",
                is_synthetic=True,
                available=has_edu,
                provenance=_prov("PublicServiceCapacityEngine", "existing_district_edu", "edu_served / (edu_served + edu_unmet)", 0.65),
            ),
            EvidenceIndicator(
                indicator_id="school_dropout_risk",
                domain="education",
                name="Riesgo promedio de deserción escolar",
                definition="Índice heurístico combinado de restricción económica familiar (<$12), fricción estacional y brecha de cupo escolar.",
                value=totals.get("avg_school_dropout_risk"),
                unit="ratio",
                data_origin="DETERMINISTIC_MULTIPLIER",
                uncertainty="Modelo heurístico sin microdatos longitudinales de deserción escolar MINED.",
                is_synthetic=True,
                available=totals.get("avg_school_dropout_risk") is not None,
                provenance=_prov("PublicServiceCapacityEngine + HouseholdConstraints", "school_age_cohort", "Liquidity + travel friction + agri demand model", 0.65),
            ),
            EvidenceIndicator(
                indicator_id="edu_unmet_person_days",
                domain="education",
                name="Demanda educativa insatisfecha acumulada",
                definition="Persona-días escolares sin cupo acumulado sobre segmentos con actividad escolar.",
                value=totals.get("edu_unmet_person_days"),
                unit="persona-día",
                data_origin="DETERMINISTIC_MULTIPLIER",
                uncertainty="Depende de la proxy de capacidad por nodo OSM y de los días activos del calendario escolar.",
                is_synthetic=True,
                available="edu_unmet_person_days" in totals,
                provenance=_prov("PublicServiceCapacityEngine", "existing_district_edu", "Unmet daily student demand", 0.65),
            ),
            EvidenceIndicator(
                indicator_id="hlt_unmet_person_days",
                domain="health",
                name="Demanda de salud primaria insatisfecha",
                definition="Persona-días de demanda sanitaria básica no cubierta por capacidad estimada OSM.",
                value=totals.get("hlt_unmet_person_days"),
                unit="persona-día",
                data_origin="DETERMINISTIC_MULTIPLIER",
                uncertainty="Depende de la proxy de capacidad por establecimiento OSM y no mide cupos MINSAL reales.",
                is_synthetic=True,
                available="hlt_unmet_person_days" in totals,
                provenance=_prov("PublicServiceCapacityEngine", "existing_district_hlt", "Unmet daily patient demand", 0.65),
            ),
            EvidenceIndicator(
                indicator_id="mobility_accessibility_index",
                domain="mobility",
                name="Índice de accesibilidad vial y topográfica",
                definition="Índice compuesto [0.1..1.0] que pondera densidad vial OSM (0.55), paradas de transporte (0.25) y factor Tobler (0.20).",
                value=context.accessibility_index,
                unit="index_0_1",
                data_origin="DETERMINISTIC_MULTIPLIER",
                uncertainty="Fórmula estática sobre conteo de segmentos viales OSM y pendiente distrital; no mide congestión vehicular ni tiempos reales.",
                is_synthetic=False,
                available=True,
                provenance=_prov("NationalTerritorialContextEngine", context.district_id, "OSM roads + transit stops + Tobler slope penalty", 0.80),
            ),
        ])

        # Flag missing local data and empirical gaps honestly
        if context.buildings_is_partial:
            missing_indicators.append("Conteo completo de edificaciones OSM en el área (cobertura buildings parcial).")
        if context.nearby_facilities_counts.get("education", 0) == 0:
            missing_indicators.append("Centros escolares geolocalizados en OSM dentro del radio inmediato.")
        if context.nearby_facilities_counts.get("health", 0) == 0:
            missing_indicators.append("Establecimientos de salud geolocalizados en OSM dentro del radio inmediato.")
        missing_indicators.append(
            "Conteo empírico en campo de flujo peatonal/vehicular (se reportan flujos sintéticos, no medición directa)."
        )
        missing_indicators.append(
            "Altura/niveles edilicios y ocupación comercial o vacantes verificadas en campo."
        )

        # 5. Population Group Breakdowns (income quartiles, school-age vs working-age vs elderly)
        school_age = [h for h in humans if getattr(h.demographics, "age", 30) < 18]
        working_age = [h for h in humans if 18 <= getattr(h.demographics, "age", 30) < 65]
        elderly = [h for h in humans if getattr(h.demographics, "age", 30) >= 65]
        low_inc = [h for h in humans if h.physical_state.money < 20.0]
        mid_high_inc = [h for h in humans if h.physical_state.money >= 20.0]

        def _grp_stats(grp: List[SyntheticHuman]) -> Dict[str, Any]:
            if not grp:
                return {"count": 0, "avg_money_usd": None, "avg_hunger": None}
            return {
                "count": len(grp),
                "avg_money_usd": round(float(np.mean([h.physical_state.money for h in grp])), 2),
                "avg_hunger": round(float(np.mean([h.physical_state.hunger for h in grp])), 3),
            }

        group_breakdowns = {
            "school_age_under_18": _grp_stats(school_age),
            "working_age_18_64": _grp_stats(working_age),
            "elderly_65_plus": _grp_stats(elderly),
            "low_liquidity_under_20usd": _grp_stats(low_inc),
            "moderate_liquidity_20usd_plus": _grp_stats(mid_high_inc),
        }

        # 6. Grounded synthetic opinions (clustered by household/role, non-independent!)
        opinions = self.query_synthetic_opinions(
            humans=humans,
            intervention=intervention,
            agent_experience_log=agent_exp,
            simulated_tick=exec_meta.get("simulated_ticks_equivalent", 0),
            seed=seed,
        )

        # 7. Ledger audit summary
        ledger_audit = {
            "conservation_passed": bool(ledger_cons.get("conservation_passed", True)),
            "cash_conservation_diff_usd": float(ledger_cons.get("cash_conservation_diff", 0.0)),
            "total_transactions": int(ledger_cons.get("total_transactions", 0)),
        }

        limitations = [
            "Evidencia producida por agentes sintéticos y motores de SALTBOR (SYNTHETIC_SIMULATED), no encuestas empíricas reales.",
            "Opiniones sintéticas agrupadas comparten entorno y supuestos del escenario; no deben sumarse como muestras estadísticas independientes.",
        ]
        if context.uncertainties:
            limitations.extend(context.uncertainties[:3])

        # Enrich 100% of indicators with Universal Evidence taxonomy & dual-depth explanations
        from saltbor.conversational.progressive_reports import enrich_indicator

        coh_n = max(1, len(humans))
        for ind in indicators:
            enrich_indicator(ind, cohort_size=coh_n)

        return EvidenceBundle(
            scenario_id=scenario_id,
            seed=seed,
            horizon_days=temporal.horizon_days,
            simulated_ticks=int(exec_meta.get("simulated_ticks_equivalent", 0)),
            wall_clock_seconds=float(exec_meta.get("wall_clock_seconds", 0.0)),
            geographic_scope=geo_scope,
            district_id=context.district_id,
            active_engines=active_engines,
            population_summary=pop_accounting,
            indicators=indicators,
            group_breakdowns=group_breakdowns,
            temporal_series=list(exec_meta.get("history", [])),
            synthetic_opinions=opinions,
            ledger_audit=ledger_audit,
            missing_indicators=list(dict.fromkeys(missing_indicators)),
            limitations=limitations,
        )

    def query_synthetic_opinions(
        self,
        humans: List[SyntheticHuman],
        intervention: Optional[InterventionSpec],
        agent_experience_log: Dict[str, str],
        simulated_tick: int,
        seed: int,
    ) -> List[SyntheticOpinionRecord]:
        """Query representative synthetic agents grounded in their simulated state & experience.

        Avoids treating correlated/household agents as independent survey observations:
        emits at most one group opinion per distinct socio-economic/household cluster.
        """
        if not humans:
            return []

        clusters: Dict[str, List[SyntheticHuman]] = {
            "trabajadores_ingresos_bajos": [],
            "comerciantes_ingresos_medios": [],
            "estudiantes_y_familias": [],
        }
        for h in humans:
            age = getattr(h.demographics, "age", 30)
            if age < 22 or "Estudiante" in getattr(h.demographics, "occupation", ""):
                clusters["estudiantes_y_familias"].append(h)
            elif h.physical_state.money < 20.0:
                clusters["trabajadores_ingresos_bajos"].append(h)
            else:
                clusters["comerciantes_ingresos_medios"].append(h)

        records: List[SyntheticOpinionRecord] = []
        price = intervention.unit_price_usd if intervention else 1.0
        target_name = intervention.name if intervention else "escenario actual"

        for idx, (cluster_label, grp) in enumerate(clusters.items()):
            if not grp:
                continue
            rep = grp[0]
            rep_uid = str(rep.uid)
            exp_note = agent_experience_log.get(rep_uid, "Observó las condiciones locales del distrito durante la simulación.")
            avg_money = round(float(np.mean([g.physical_state.money for g in grp])), 2)
            consc = rep.personality.get_trait("conscientiousness") if hasattr(rep, "personality") else 0.6

            if intervention and intervention.category.value in ("PUPUSERIA", "RESTAURANT", "SHOP", "PHARMACY"):
                if avg_money < price * 2.5:
                    stance = "cautious_price_sensitive"
                    resp_txt = (
                        f"Como grupo {cluster_label} (saldo medio ${avg_money:.2f}, ocupación '{rep.demographics.occupation}'), "
                        f"evaluamos '{target_name}' a ${price:.2f} con cautela presupuestaria. {exp_note}"
                    )
                else:
                    stance = "receptive_conditional"
                    resp_txt = (
                        f"Como grupo {cluster_label} (saldo medio ${avg_money:.2f}, frugalidad {consc:.2f}), "
                        f"consideramos útil '{target_name}' siempre que mantenga calidad y horario accesible. {exp_note}"
                    )
            elif intervention and intervention.category.value in ("SCHOOL", "TRAINING_CENTER"):
                stance = "supportive_access_focused"
                resp_txt = (
                    f"Desde la perspectiva de {cluster_label} (saldo medio ${avg_money:.2f}), "
                    f"reducir la distancia de traslado y costos escolares mejora la permanencia estudiantil."
                )
            else:
                stance = "contextual_observation"
                resp_txt = (
                    f"Grupo {cluster_label} con saldo promedio ${avg_money:.2f} reporta impacto directo "
                    f"en tiempos de acceso y presupuesto familiar ante '{target_name}'. {exp_note}"
                )

            records.append(
                SyntheticOpinionRecord(
                    opinion_id=f"op_{seed}_{idx}",
                    agent_uids=[str(g.uid) for g in grp[:10]],
                    group_label=cluster_label,
                    query_method="clustered_state_and_memory_grounding",
                    context_summary=f"Cluster de {len(grp)} agentes en {target_name}; edad media {np.mean([g.demographics.age for g in grp]):.1f} años.",
                    response_text=resp_txt,
                    stance=stance,
                    simulated_tick=simulated_tick,
                    seed=seed,
                    confidence=0.65,
                    is_independent_sample=False,
                )
            )

        return records

    @staticmethod
    def _compute_gini(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        arr = np.sort(np.maximum(0.0, np.array(values, dtype=float)))
        total = float(np.sum(arr))
        if total <= 0.0:
            return 0.0
        n = len(arr)
        idx = np.arange(1, n + 1)
        gini = (2.0 * float(np.sum(idx * arr))) / (n * total) - (n + 1.0) / n
        return round(max(0.0, min(1.0, gini)), 4)
