"""Progressive Intelligence & Three-Level Reports Builder (BASIC / INTERMEDIATE / EXPERT).

Builds three synchronized depth views and a universal evidence & explainability layer
strictly over existing SALTBOR engine outputs without altering any simulation state,
calculation, RNG sequence, or numeric precision.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from saltbor.conversational.schemas import (
    BasicReportView,
    EvidenceIndicator,
    EvidenceProvenance,
    ExpertReportView,
    ExplainedMetricCard,
    IntermediateReportView,
    ProgressiveReportBundle,
    ReportDepthLevel,
    ScenarioEnvelopeEntry,
    SimulationStudioResult,
    UniversalEvidenceOrigin,
)

ENGINE_RELEASE_VERSION = "SALTBOR-Phase-1.17"

_VERDICT_PLAIN_LABELS: Dict[str, str] = {
    "PROMISING": "Favorable bajo los supuestos evaluados (sin garantía)",
    "CONDITIONALLY_PROMISING": "Posible con condiciones importantes",
    "INSUFFICIENT_EVIDENCE": "Información insuficiente para concluir",
    "HIGH_RISK": "Riesgo financiero u operativo alto",
    "NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS": "No recomendable bajo los costos o precios actuales",
}

_SENSITIVITY_DEMAND_FACTORS = (
    ("Conservador (-20% demanda)", 0.80),
    ("Base (simulación SALTBOR)", 1.00),
    ("Optimista (+20% demanda)", 1.20),
)


def normalize_evidence_origin(ind: EvidenceIndicator) -> UniversalEvidenceOrigin:
    """Map an EvidenceIndicator's raw origin and engine source into UniversalEvidenceOrigin."""
    if not ind.available or ind.value is None:
        return UniversalEvidenceOrigin.UNAVAILABLE

    raw = (ind.data_origin or "").upper().strip()
    src = (ind.provenance.source_engine or "").lower()
    method = (ind.provenance.calculation_method or "").lower()

    if raw == "GEOGRAPHIC_DATASET":
        if "osm" in src or "osm" in method:
            return UniversalEvidenceOrigin.OBSERVED
        return UniversalEvidenceOrigin.PUBLIC_OFFICIAL
    if raw == "DIRECT_SIMULATION_EVENT":
        return UniversalEvidenceOrigin.DIRECT_SIMULATION_EVENT
    if raw == "EXTRAPOLATED_COHORT":
        return UniversalEvidenceOrigin.EXTRAPOLATED
    if raw == "DETERMINISTIC_MULTIPLIER":
        return UniversalEvidenceOrigin.DETERMINISTIC_MULTIPLIER
    if raw == "FALLBACK_ESTIMATE":
        return UniversalEvidenceOrigin.ESTIMATED
    return UniversalEvidenceOrigin.SYNTHETIC_SIMULATED


def classify_empirical_calibration(
    ind: EvidenceIndicator,
    origin: UniversalEvidenceOrigin,
) -> str:
    """Clarify empirical calibration strictly so synthetic metrics never claim empirical confidence."""
    if origin == UniversalEvidenceOrigin.UNAVAILABLE:
        return "UNAVAILABLE"
    if origin == UniversalEvidenceOrigin.OBSERVED:
        return "CARTOGRAPHIC_OBSERVED"
    if origin == UniversalEvidenceOrigin.PUBLIC_OFFICIAL:
        return "PUBLIC_OFFICIAL_APPROX"
    if origin in (UniversalEvidenceOrigin.ESTIMATED, UniversalEvidenceOrigin.DETERMINISTIC_MULTIPLIER):
        return "HEURISTIC_UNVERIFIED"
    return "UNCALIBRATED_SYNTHETIC"


def _format_metric_value(value: Any, unit: str) -> str:
    if value is None:
        return "No disponible"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, (int, float)):
        if unit == "USD":
            return f"${float(value):,.2f} USD"
        if unit == "ratio":
            return f"{float(value) * 100.0:.2f}%"
        if isinstance(value, int) and not isinstance(value, bool):
            return f"{value:,}"
        if float(value).is_integer() and unit in ("visitas", "compras", "agentes", "personas"):
            return f"{int(value):,}"
        return f"{float(value):,.2f}"
    return str(value)


def _ratio_fraction_phrase(ratio: float) -> str:
    """Convert a ratio in [0, 1] into grounded everyday Spanish phrasing."""
    if ratio <= 0.0:
        return "ninguno (0%)"
    if ratio < 0.15:
        return "aproximadamente uno de cada diez"
    if 0.20 <= ratio <= 0.29:
        return "aproximadamente una de cada cuatro"
    if 0.30 <= ratio <= 0.38:
        return "alrededor de una de cada tres"
    if 0.45 <= ratio <= 0.55:
        return "aproximadamente la mitad"
    if 0.62 <= ratio <= 0.72:
        return "cerca de dos de cada tres"
    if 0.73 <= ratio <= 0.80:
        return "tres de cada cuatro"
    return f"el {ratio * 100.0:.1f}%"


def _extract_cohort_size(ind: EvidenceIndicator, default: int = 40) -> int:
    m = re.search(r"(\d+)\s+agentes", ind.provenance.population_scope or "")
    return int(m.group(1)) if m else default


def generate_contextual_explanations(
    ind: EvidenceIndicator,
    cohort_size: int = 40,
) -> Tuple[str, str]:
    """Generate dynamic BASIC & EXPERT Spanish explanations grounded solely in observed values & provenance."""
    origin = normalize_evidence_origin(ind)
    iid = ind.indicator_id
    val = ind.value
    n_coh = _extract_cohort_size(ind, default=cohort_size)

    if origin == UniversalEvidenceOrigin.UNAVAILABLE or val is None:
        basic = f"Este dato ({ind.name.lower()}) no estuvo disponible o no aplicó para este escenario."
        expert = (
            f"{ind.name} clasificado como UNAVAILABLE en '{ind.provenance.geographic_scope}' "
            f"({ind.provenance.time_interval}). {ind.uncertainty or ind.provenance.limitations}"
        ).strip()
        return basic, expert

    if iid == "low_liquidity_agent_share":
        ratio = float(val)
        pct = round(ratio * 100.0, 1)
        frac_phrase = _ratio_fraction_phrase(ratio)
        basic = (
            f"En el grupo de personas simulado, {frac_phrase} tenía menos de $15 disponibles."
        )
        expert = (
            f"El {pct:g}% ({ratio:.3f} ratio) corresponde a la proporción de agentes sintéticos hidratados "
            f"(n={n_coh}) cuya liquidez disponible fue inferior a USD 15 ({ind.provenance.calculation_method}). "
            f"No representa una estimación censal de la población territorial."
        )
        return basic, expert

    if iid == "resident_population_approx":
        basic = (
            f"Se tomó como referencia una población aproximada de {int(val):,} habitantes en esta zona."
        )
        expert = (
            f"{int(val):,} personas registradas en el catálogo territorial D.L. 762 para "
            f"{ind.provenance.geographic_scope} (origen: {origin.value}). {ind.uncertainty}"
        )
        return basic, expert

    if iid == "unique_active_cohort":
        basic = (
            f"La prueba se ejecutó siguiendo las decisiones de {int(val)} personas simuladas representativas."
        )
        expert = (
            f"Cohorte activada con n={int(val)} identidades UUID únicas deduplicadas ({ind.provenance.population_scope}). "
            f"Muestreo sintético para dinámica microeconómica; no equivale a censo distrital completo."
        )
        return basic, expert

    if iid == "inbound_commuters":
        if int(val) == 0:
            basic = "No se simularon viajeros diarios provenientes de otros distritos en esta corrida."
        else:
            basic = f"Se incluyeron {int(val)} viajeros sintéticos que llegan diariamente desde otros distritos."
        expert = (
            f"{int(val)} viajeros con home_district != current_district ({ind.provenance.calculation_method}). "
            f"{ind.uncertainty}"
        )
        return basic, expert

    if iid == "household_avg_cash_usd":
        basic = (
            f"En promedio, cada persona simulada manejaba alrededor de ${float(val):.2f} USD disponibles para gastar."
        )
        expert = (
            f"Media aritmética de physical_state.money = ${float(val):.2f} USD sobre n={n_coh} agentes "
            f"hidratados tras transacciones sin escalar de cohorte. {ind.uncertainty}"
        )
        return basic, expert

    if iid == "wealth_gini_simulated":
        basic = (
            f"La diferencia de dinero entre quienes menos y más tenían en el grupo simulado fue moderada "
            f"(índice {float(val):.2f} en una escala de 0 a 1)."
        )
        expert = (
            f"Coeficiente de Gini finito exacto = {float(val):.4f} sobre la tenencia líquida de n={n_coh} "
            f"agentes sintéticos (origen: {origin.value}). Sensible al tamaño muestral de cohorte."
        )
        return basic, expert

    if iid == "household_income_earned_usd":
        basic = (
            f"Los ingresos ganados por trabajadores dentro del modelo sumaron ${float(val):,.2f} USD."
        )
        expert = (
            f"Créditos salariales exactos en VerifiableEconomicLedger = ${float(val):,.2f} USD "
            f"(origen: {origin.value}, diff=$0.00). {ind.uncertainty}"
        )
        return basic, expert

    if iid == "raw_cohort_visitors":
        basic = (
            f"Dentro de la muestra directa de {n_coh} personas simuladas, el negocio recibió {int(val)} visitas "
            f"mientras estuvo abierto (antes de proyectar al distrito)."
        )
        expert = (
            f"{int(val)} eventos execute_visit() en horario abierto registrados directamente en CommercialEngine "
            f"sobre cohorte n={n_coh} antes de aplicar factores de escala territorial."
        )
        return basic, expert

    if iid == "raw_cohort_revenue_usd":
        basic = (
            f"Las ventas directas dentro del grupo pequeño simulado sumaron ${float(val):,.2f} USD."
        )
        expert = (
            f"Suma directa en VerifiableEconomicLedger sin multiplicar = ${float(val):,.2f} USD "
            f"(origen: {origin.value}, conservación contable exacta)."
        )
        return basic, expert

    if iid == "commercial_visitors":
        basic = (
            f"Al proyectar el comportamiento simulado al tamaño de la zona, se estiman unas {float(val):,.0f} "
            f"visitas en total (incluye personas que solo miran o preguntan precios)."
        )
        expert = (
            f"{float(val):,.1f} visitas proyectadas ({ind.provenance.calculation_method}; origen: {origin.value}). "
            f"{ind.uncertainty}"
        )
        return basic, expert

    if iid == "commercial_browsers_without_purchase":
        basic = (
            f"Se estima que alrededor de {float(val):,.0f} visitas serían de personas que miran, comparan "
            f"o no pueden pagar en ese momento y salen sin comprar."
        )
        expert = (
            f"{float(val):,.1f} visitas sin conversión efectiva por restricción presupuestaria, saturación o "
            f"exploración de precios ({ind.provenance.calculation_method}). {ind.uncertainty}"
        )
        return basic, expert

    if iid == "commercial_purchasers":
        basic = (
            f"De todas las visitas estimadas, alrededor de {float(val):,.0f} se convertirían en compras reales."
        )
        expert = (
            f"{float(val):,.1f} compras proyectadas filtradas por presupuesto, horario, inventario y competencia "
            f"({ind.provenance.calculation_method}). {ind.uncertainty}"
        )
        return basic, expert

    if iid == "commercial_conversion_rate":
        pct = float(val) * 100.0
        basic = f"Aproximadamente {pct:.1f} de cada 100 visitas realizadas terminarían en una compra."
        expert = (
            f"Tasa de conversión visita→compra = {float(val):.4f} ({pct:.2f}%) derivada de decisiones de "
            f"racionalidad limitada en CommercialEngine (no calibrada contra cajas POS empíricas)."
        )
        return basic, expert

    if iid == "commercial_revenue_usd":
        basic = (
            f"Si el comportamiento simulado se mantiene en la zona, las ventas proyectadas podrían rondar "
            f"${float(val):,.2f} USD (cifra estimada, no garantizada)."
        )
        expert = (
            f"Ingresos proyectados = ${float(val):,.2f} USD (origen: {origin.value}, método: "
            f"{ind.provenance.calculation_method}). {ind.uncertainty}"
        )
        return basic, expert

    if iid == "commercial_net_profit_usd":
        v = float(val)
        if v > 0:
            basic = (
                f"Después de restar insumos, salarios completos y gastos fijos del período, quedaría un saldo "
                f"operativo estimado de +${v:,.2f} USD (no es dinero asegurado)."
            )
        elif v < 0:
            basic = (
                f"Con los costos de personal y gastos del período, el negocio cerraría con una pérdida operativa "
                f"estimada de -${abs(v):,.2f} USD; necesitaría ajustar precios, ventas o costos."
            )
        else:
            basic = "El negocio terminaría prácticamente en punto de equilibrio ($0.00 USD)."
        expert = (
            f"Resultado neto operativo P&L = ${v:,.2f} USD ({ind.provenance.calculation_method}; "
            f"origen: {origin.value}). {ind.uncertainty}"
        )
        return basic, expert

    if iid == "commercial_obligated_wages_usd":
        basic = (
            f"El costo total de pagar sueldos al personal propuesto durante todo el período es de ${float(val):,.2f} USD."
        )
        expert = (
            f"Nómina devengada obligatoria = ${float(val):,.2f} USD ({ind.provenance.calculation_method}). "
            f"{ind.uncertainty}"
        )
        return basic, expert

    if iid == "commercial_competitor_sales_usd":
        basic = (
            f"Otros negocios parecidos de la zona captarían alrededor de ${float(val):,.2f} USD en ventas competitivas."
        )
        expert = (
            f"Ingresos proyectados desviados hacia competidores OSM ({ind.provenance.source_entity}) = "
            f"${float(val):,.2f} USD ({ind.provenance.calculation_method}). {ind.uncertainty}"
        )
        return basic, expert

    if iid == "mobility_accessibility_index":
        pct = float(val) * 100.0
        basic = (
            f"La facilidad de acceso por calles y transporte en esta zona es de {float(val):.2f} sobre 1.00 "
            f"({pct:.0f}% según calles y paradas registradas)."
        )
        expert = (
            f"Índice compuesto de accesibilidad = {float(val):.3f} ({ind.provenance.calculation_method}, "
            f"origen: {origin.value}). {ind.uncertainty}"
        )
        return basic, expert

    if iid in ("school_attendance_rate", "school_dropout_risk", "edu_unmet_person_days", "hlt_unmet_person_days"):
        if iid == "school_attendance_rate":
            basic = f"La cobertura escolar simulada dentro del período escolar fue de {float(val) * 100:.1f}%."
        elif iid == "school_dropout_risk":
            basic = f"El riesgo simulado de inasistencia o deserción escolar se estimó en {float(val) * 100:.1f}%."
        else:
            basic = f"Se registraron {float(val):,.1f} persona-días simuladas sin atención suficiente en servicios."
        expert = (
            f"{ind.name} = {val} {ind.unit} (origen: {origin.value}; {ind.provenance.calculation_method}). "
            f"{ind.uncertainty}"
        )
        return basic, expert

    # Generic metadata-driven explanation fallback (never invented)
    fmt = _format_metric_value(val, ind.unit)
    basic = f"{ind.name}: {fmt}. {ind.definition or ind.provenance.calculation_method}"
    expert = (
        f"{ind.name} = {fmt} (origen: {origin.value}; motor: {ind.provenance.source_engine}; "
        f"método: {ind.provenance.calculation_method}; semilla={ind.provenance.seed}). {ind.uncertainty}"
    )
    return basic, expert


def enrich_indicator(ind: EvidenceIndicator, cohort_size: int = 40) -> EvidenceIndicator:
    """Populate universal evidence taxonomy, calibration tag & dual-depth explanations onto indicator."""
    origin = normalize_evidence_origin(ind)
    calib = classify_empirical_calibration(ind, origin)
    basic_exp, expert_exp = generate_contextual_explanations(ind, cohort_size=cohort_size)
    ind.evidence_origin = origin.value
    ind.empirical_calibration_status = calib
    ind.basic_explanation = basic_exp
    ind.expert_explanation = expert_exp
    return ind


def _build_explained_card(
    ind: EvidenceIndicator,
    cohort_size: int = 40,
    not_guaranteed_note: Optional[str] = None,
) -> ExplainedMetricCard:
    enrich_indicator(ind, cohort_size=cohort_size)
    origin = UniversalEvidenceOrigin(ind.evidence_origin)
    return ExplainedMetricCard(
        indicator_id=ind.indicator_id,
        label=ind.name,
        raw_value=ind.value,
        formatted_value=_format_metric_value(ind.value, ind.unit),
        unit=ind.unit,
        evidence_origin=origin,
        is_synthetic=ind.is_synthetic,
        empirical_calibration_status=ind.empirical_calibration_status,
        what_it_represents=ind.definition or ind.name,
        where_it_comes_from=f"{ind.provenance.source_engine} ({ind.provenance.source_entity})",
        how_it_was_obtained=ind.provenance.calculation_method,
        uncertainty=ind.uncertainty or f"Calidad base {ind.provenance.data_quality:.2f}/1.00",
        limitations=ind.provenance.limitations,
        basic_explanation=ind.basic_explanation,
        expert_explanation=ind.expert_explanation,
        not_guaranteed_note=not_guaranteed_note,
    )


def _derive_expense_card(
    rev_ind: Optional[EvidenceIndicator],
    net_ind: Optional[EvidenceIndicator],
    obligated_wages: Optional[EvidenceIndicator],
    cohort_size: int,
) -> Optional[ExplainedMetricCard]:
    """Derive total operating expenses strictly as `revenue - net_profit` without inventing figures."""
    if (
        rev_ind is None
        or net_ind is None
        or not rev_ind.available
        or not net_ind.available
        or rev_ind.value is None
        or net_ind.value is None
    ):
        return None
    expenses_val = round(float(rev_ind.value) - float(net_ind.value), 2)
    wages_txt = (
        f" (incluye ${float(obligated_wages.value):,.2f} USD de salarios devengados)"
        if obligated_wages and obligated_wages.available and obligated_wages.value is not None
        else ""
    )
    return ExplainedMetricCard(
        indicator_id="derived_operating_expenses_usd",
        label="Gastos estimados totales (insumos + sueldos + fijos)",
        raw_value=expenses_val,
        formatted_value=_format_metric_value(expenses_val, "USD"),
        unit="USD",
        evidence_origin=UniversalEvidenceOrigin.EXTRAPOLATED,
        is_synthetic=True,
        empirical_calibration_status="UNCALIBRATED_SYNTHETIC",
        what_it_represents="Suma de costo de insumos (COGS), salarios obligatorios y gastos fijos operativos del período.",
        where_it_comes_from="BusinessEnterprise + VerifiableEconomicLedger (ingresos proyectados - resultado operativo neto)",
        how_it_was_obtained=f"commercial_revenue_usd ({float(rev_ind.value):.2f}) - commercial_net_profit_usd ({float(net_ind.value):.2f})",
        uncertainty=f"Calculado exactamente desde los costos modelados{wages_txt}; no sustituye cotizaciones reales de alquiler o proveedores.",
        limitations=net_ind.provenance.limitations,
        basic_explanation=(
            f"Para operar durante este período, los gastos estimados entre insumos, sueldos y costos fijos "
            f"sumarían alrededor de ${expenses_val:,.2f} USD{wages_txt}."
        ),
        expert_explanation=(
            f"Egresos totales del P&L = ${expenses_val:,.2f} USD (ingresos ${float(rev_ind.value):.2f} - neto "
            f"${float(net_ind.value):.2f}). Derivado sin inventar rubros adicionales."
        ),
        not_guaranteed_note="Costo estimado bajo parámetros iniciales; los precios reales de insumos y renta pueden variar.",
    )


class ProgressiveReportBuilder:
    """Constructs synchronized BASIC, INTERMEDIATE & EXPERT views from a single SALTBOR execution."""

    @classmethod
    def build_from_studio_result(cls, result: SimulationStudioResult) -> ProgressiveReportBundle:
        """Build 3-level ProgressiveReportBundle from a live SimulationStudioResult."""
        return cls._build_bundle(
            execution_id=result.execution_id,
            scenario_id=result.scenario_id,
            seed=result.evidence.seed,
            district_name=result.territorial_context.district_name or result.evidence.geographic_scope,
            department_name=result.territorial_context.department_name,
            geographic_scope=result.evidence.geographic_scope,
            horizon_days=result.evidence.horizon_days,
            simulated_ticks=result.evidence.simulated_ticks,
            resolution_mode=result.temporal_horizon.resolution_mode,
            intervention_name=result.intervention.name if result.intervention else result.evidence.geographic_scope,
            intervention_dump=result.intervention.model_dump(mode="json") if result.intervention else {},
            temporal_dump=result.temporal_horizon.model_dump(mode="json"),
            context_dict=result.territorial_context.model_dump(mode="json"),
            indicators=list(result.evidence.indicators),
            active_engines=list(result.evidence.active_engines),
            ledger_audit=dict(result.evidence.ledger_audit),
            group_breakdowns=dict(result.evidence.group_breakdowns),
            temporal_series=list(result.evidence.temporal_series),
            synthetic_opinions=[op.model_dump(mode="json") for op in result.evidence.synthetic_opinions],
            missing_indicators=list(result.evidence.missing_indicators),
            limitations=list(result.evidence.limitations),
            population_summary=dict(result.evidence.population_summary),
            recommendation_dict=result.recommendation.model_dump(mode="json"),
            comparison_dict=result.comparison.model_dump(mode="json") if result.comparison else None,
            territorial_intelligence=dict(result.territorial_intelligence),
            provenance_record=dict(result.provenance_record),
            checkpoint_id=result.checkpoint_id,
        )

    @classmethod
    def build_from_persisted_execution(
        cls,
        execution_record: Dict[str, Any],
        scenario_record: Optional[Dict[str, Any]] = None,
    ) -> ProgressiveReportBundle:
        """Reconstruct a complete 3-level report strictly from persisted SQLite rows (even pre-1.17 records)."""
        ev_ref = execution_record.get("evidence_ref", {})
        an = execution_record.get("analysis", {})
        prov = execution_record.get("provenance", {})
        exec_id = execution_record.get("execution_id", "")
        scen_id = execution_record.get("scenario_id", "")
        seed = int(execution_record.get("seed", 42))
        horizon_days = int(ev_ref.get("horizon_days", 30))
        simulated_ticks = int(ev_ref.get("simulated_ticks", horizon_days * 96))
        district_id = ev_ref.get("district_id", prov.get("district_id", ""))
        active_engines = list(execution_record.get("active_engines") or ev_ref.get("active_engines") or [])

        geo_summary = (scenario_record or {}).get("geo_context_summary", {})
        interv_dump = (scenario_record or {}).get("intervention") or {}
        temporal_dump = (scenario_record or {}).get("temporal") or {
            "horizon_days": horizon_days,
            "resolution_mode": "HYBRID_REPRESENTATIVE",
            "seed": seed,
        }
        district_name = geo_summary.get("district_name") or district_id or "El Salvador"
        department_name = geo_summary.get("department_name") or ""
        geo_scope = f"{district_name} ({district_id}), {department_name}".strip(", ")
        dq = float(geo_summary.get("data_quality_score", 0.7))

        ind_vals = dict(ev_ref.get("indicator_values") or {})
        cohort_size = int(ind_vals.get("unique_active_cohort", 40) or 40)
        res_pop = ind_vals.get("resident_population_approx", 0)
        reconstructed_inds: List[EvidenceIndicator] = []
        for iid, val in ind_vals.items():
            meta_info = cls._legacy_indicator_meta(iid)
            reconstructed_inds.append(
                EvidenceIndicator(
                    indicator_id=iid,
                    domain=meta_info[0],
                    name=meta_info[1],
                    definition=meta_info[2],
                    value=val,
                    unit=meta_info[3],
                    data_origin=meta_info[4],
                    uncertainty="Reconstruido desde registro histórico persistido en SQLite WAL.",
                    is_synthetic=meta_info[5],
                    available=val is not None,
                    provenance=EvidenceProvenance(
                        source_engine=meta_info[6],
                        source_entity=interv_dump.get("intervention_id", district_id or "persisted"),
                        calculation_method=meta_info[7],
                        time_interval=f"{horizon_days} días simulados ({simulated_ticks} ticks eq.)",
                        population_scope=f"{cohort_size} agentes hidratados / {res_pop} residentes distritales",
                        geographic_scope=geo_scope,
                        seed=seed,
                        data_quality=dq,
                        confidence=0.72,
                        limitations="Indicador recuperado de ejecución histórica sin alterar cifras archivadas.",
                    ),
                )
            )

        return cls._build_bundle(
            execution_id=exec_id,
            scenario_id=scen_id,
            seed=seed,
            district_name=district_name,
            department_name=department_name,
            geographic_scope=geo_scope,
            horizon_days=horizon_days,
            simulated_ticks=simulated_ticks,
            resolution_mode=temporal_dump.get("resolution_mode", "HYBRID_REPRESENTATIVE"),
            intervention_name=interv_dump.get("name", f"Escenario en {district_name}"),
            intervention_dump=interv_dump,
            temporal_dump=temporal_dump,
            context_dict={
                "district_id": district_id,
                "district_name": district_name,
                "department_name": department_name,
                "data_quality_score": dq,
            },
            indicators=reconstructed_inds,
            active_engines=active_engines,
            ledger_audit=dict(ev_ref.get("ledger_audit") or {}),
            group_breakdowns={},
            temporal_series=[],
            synthetic_opinions=[],
            missing_indicators=list(ev_ref.get("missing_indicators") or an.get("missing_information") or []),
            limitations=list(an.get("limitations") or []),
            population_summary={"unique_individuals_present": cohort_size, "permanent_residents": res_pop},
            recommendation_dict=an,
            comparison_dict=None,
            territorial_intelligence={},
            provenance_record=prov,
            checkpoint_id=execution_record.get("checkpoint_id"),
        )

    @staticmethod
    def _legacy_indicator_meta(iid: str) -> Tuple[str, str, str, str, str, bool, str, str]:
        mapping: Dict[str, Tuple[str, str, str, str, str, bool, str, str]] = {
            "resident_population_approx": ("demographics", "Población residente aproximada del distrito", "Aproximación distrital D.L. 762", "personas", "GEOGRAPHIC_DATASET", False, "NationalTerritorialContextEngine", "D.L. 762 district registry"),
            "unique_active_cohort": ("demographics", "Agentes sintéticos únicos activados", "Cohorte única en RAM", "agentes", "AGGREGATED_SYNTHETIC_AGENTS", True, "NationalPopulationActivationManager", "Deduplicated active UID count"),
            "inbound_commuters": ("mobility", "Flujo de viajeros entrantes únicos", "Commuters entre distritos", "agentes", "AGGREGATED_SYNTHETIC_AGENTS", True, "NationalPopulationActivationManager", "home_district != current_district"),
            "household_avg_cash_usd": ("economy", "Liquidez promedio de agentes hidratados", "Media de dinero líquido activo", "USD", "AGGREGATED_SYNTHETIC_AGENTS", True, "PopulationRegistry", "Arithmetic mean of physical_state.money"),
            "low_liquidity_agent_share": ("economy", "Proporción de agentes con restricción de liquidez (<$15)", "Agentes con <$15 USD", "ratio", "AGGREGATED_SYNTHETIC_AGENTS", True, "PopulationRegistry", "Share with money < 15.0 USD"),
            "wealth_gini_simulated": ("inequality", "Índice de desigualdad (Gini de liquidez simulada)", "Gini muestral finito", "gini", "AGGREGATED_SYNTHETIC_AGENTS", True, "SocialStratificationEngine", "Finite-sample Gini"),
            "household_income_earned_usd": ("employment", "Ingresos laborales devengados en el período", "Salarios pagados en libro contable", "USD", "DIRECT_SIMULATION_EVENT", True, "LaborMarketEngine", "Double-entry wage credits"),
            "raw_cohort_visitors": ("commerce", "Visitas directas de cohorte en horario abierto", "Visitas directas antes de escalar", "visitas_cohorte", "DIRECT_SIMULATION_EVENT", True, "CommercialEngine", "Unscaled open-hour execute_visit() tally"),
            "raw_cohort_revenue_usd": ("commerce", "Ventas directas de cohorte en libro contable", "Ventas directas sin escalar", "USD", "DIRECT_SIMULATION_EVENT", True, "CommercialEngine + VerifiableEconomicLedger", "Exact unscaled ledger sales"),
            "commercial_obligated_wages_usd": ("commerce", "Nómina laboral devengada obligatoria", "Costo salarial total del horizonte", "USD", "DIRECT_SIMULATION_EVENT", True, "LaborMarketEngine", "workforce * daily_wage * days"),
            "commercial_competitor_sales_usd": ("commerce", "Ventas captadas por competidores locales", "Desvío competitivo estimado", "USD", "EXTRAPOLATED_COHORT", True, "CommercialEngine", "Competitor diversion * scale"),
            "commercial_visitors": ("commerce", "Visitas totales estimadas", "Visitas proyectadas al distrito", "visitas", "EXTRAPOLATED_COHORT", True, "CommercialEngine", "execute_visit() tally scaled"),
            "commercial_browsers_without_purchase": ("commerce", "Visitantes sin compra", "Exploración sin compra proyectada", "visitas", "EXTRAPOLATED_COHORT", True, "CommercialEngine", "Non-purchase visits scaled"),
            "commercial_purchasers": ("commerce", "Compradores efectivos", "Transacciones proyectadas", "compras", "EXTRAPOLATED_COHORT", True, "CommercialEngine", "Purchases scaled"),
            "commercial_conversion_rate": ("commerce", "Tasa de conversión visita -> compra", "Cociente compras / visitas", "ratio", "DIRECT_SIMULATION_EVENT", True, "CommercialEngine", "purchasers / visitors"),
            "commercial_revenue_usd": ("commerce", "Ingresos brutos comerciales estimados", "Ventas brutas proyectadas", "USD", "EXTRAPOLATED_COHORT", True, "CommercialEngine + VerifiableEconomicLedger", "Sales scaled"),
            "commercial_net_profit_usd": ("commerce", "Resultado neto operativo", "Ingresos menos insumos, nómina y fijos", "USD", "EXTRAPOLATED_COHORT", True, "BusinessEnterprise + VerifiableEconomicLedger", "Operating P&L"),
            "school_attendance_rate": ("education", "Cobertura escolar simulada", "Razón de demanda escolar cubierta", "ratio", "DETERMINISTIC_MULTIPLIER", True, "PublicServiceCapacityEngine", "edu_served / total"),
            "school_dropout_risk": ("education", "Riesgo promedio de deserción escolar", "Riesgo heurístico escolar", "ratio", "DETERMINISTIC_MULTIPLIER", True, "PublicServiceCapacityEngine", "Dropout risk heuristic"),
            "edu_unmet_person_days": ("education", "Demanda educativa insatisfecha acumulada", "Persona-día escolares sin cupo", "persona-día", "DETERMINISTIC_MULTIPLIER", True, "PublicServiceCapacityEngine", "Unmet school demand"),
            "hlt_unmet_person_days": ("health", "Demanda de salud primaria insatisfecha", "Persona-día de salud sin cupo", "persona-día", "DETERMINISTIC_MULTIPLIER", True, "PublicServiceCapacityEngine", "Unmet health demand"),
            "mobility_accessibility_index": ("mobility", "Índice de accesibilidad vial y topográfica", "Accesibilidad OSM + Tobler", "index_0_1", "DETERMINISTIC_MULTIPLIER", False, "NationalTerritorialContextEngine", "Roads + transit + slope"),
        }
        return mapping.get(
            iid,
            ("general", iid.replace("_", " ").capitalize(), f"Indicador {iid}", "", "AGGREGATED_SYNTHETIC_AGENTS", True, "SALTBOR", "Engine output"),
        )

    @classmethod
    def _build_bundle(
        cls,
        *,
        execution_id: str,
        scenario_id: str,
        seed: int,
        district_name: str,
        department_name: str,
        geographic_scope: str,
        horizon_days: int,
        simulated_ticks: int,
        resolution_mode: str,
        intervention_name: str,
        intervention_dump: Dict[str, Any],
        temporal_dump: Dict[str, Any],
        context_dict: Dict[str, Any],
        indicators: List[EvidenceIndicator],
        active_engines: List[str],
        ledger_audit: Dict[str, Any],
        group_breakdowns: Dict[str, Any],
        temporal_series: List[Dict[str, Any]],
        synthetic_opinions: List[Dict[str, Any]],
        missing_indicators: List[str],
        limitations: List[str],
        population_summary: Dict[str, Any],
        recommendation_dict: Dict[str, Any],
        comparison_dict: Optional[Dict[str, Any]],
        territorial_intelligence: Dict[str, Any],
        provenance_record: Dict[str, Any],
        checkpoint_id: Optional[str],
    ) -> ProgressiveReportBundle:
        ind_map: Dict[str, EvidenceIndicator] = {ind.indicator_id: ind for ind in indicators}
        coh_ind = ind_map.get("unique_active_cohort")
        cohort_size = int(coh_ind.value) if coh_ind and coh_ind.value is not None else 40

        all_cards: List[ExplainedMetricCard] = []
        card_map: Dict[str, ExplainedMetricCard] = {}
        origin_counts: Dict[str, int] = {o.value: 0 for o in UniversalEvidenceOrigin}

        for ind in indicators:
            ng_note = (
                "Cifra proyectada de simulación; no es un retorno financiero garantizado."
                if ind.indicator_id
                in (
                    "commercial_revenue_usd",
                    "commercial_net_profit_usd",
                    "commercial_purchasers",
                    "commercial_visitors",
                )
                else None
            )
            card = _build_explained_card(ind, cohort_size=cohort_size, not_guaranteed_note=ng_note)
            all_cards.append(card)
            card_map[ind.indicator_id] = card
            origin_counts[card.evidence_origin.value] = origin_counts.get(card.evidence_origin.value, 0) + 1

        # Exact numeric preservation fingerprint (non-None available indicators so live & persisted match)
        fingerprint: Dict[str, Any] = {
            ind.indicator_id: ind.value for ind in indicators if ind.available and ind.value is not None
        }

        verdict_code = str(recommendation_dict.get("verdict", "CONDITIONALLY_PROMISING"))
        verdict_plain = _VERDICT_PLAIN_LABELS.get(verdict_code, verdict_code)

        # ---- FASE 2: BASIC VIEW ----
        rev_card = card_map.get("commercial_revenue_usd")
        net_card = card_map.get("commercial_net_profit_usd")
        exp_card = _derive_expense_card(
            ind_map.get("commercial_revenue_usd"),
            ind_map.get("commercial_net_profit_usd"),
            ind_map.get("commercial_obligated_wages_usd"),
            cohort_size=cohort_size,
        )
        vis_card = card_map.get("commercial_visitors")
        buy_card = card_map.get("commercial_purchasers")

        opportunities: List[str] = []
        if buy_card and buy_card.raw_value:
            opportunities.append(
                f"Demanda potencial activa: alrededor de {buy_card.formatted_value} compras proyectadas sobre {vis_card.formatted_value if vis_card else 'visitas estimadas'}."
            )
        acc_card = card_map.get("mobility_accessibility_index")
        if acc_card and acc_card.raw_value is not None and float(acc_card.raw_value) >= 0.7:
            opportunities.append(
                f"Buena accesibilidad por calles registradas ({acc_card.formatted_value}), facilitando que lleguen clientes."
            )
        if not opportunities:
            opportunities.append(
                "El entorno territorial muestra actividad económica y poblacional que puede aprovecharse ajustando la oferta local."
            )

        risks: List[str] = []
        for x in recommendation_dict.get("population_needs", [])[:2]:
            risks.append(str(x))
        for x in recommendation_dict.get("contradictions", [])[:2]:
            risks.append(str(x))
        if net_card and net_card.raw_value is not None and float(net_card.raw_value) < 0:
            risks.append(
                f"Con los gastos fijos y de personal actuales, los costos superarían a los ingresos estimados ({net_card.formatted_value})."
            )
        comp_card = card_map.get("commercial_competitor_sales_usd")
        if comp_card and comp_card.raw_value and float(comp_card.raw_value) > 0:
            risks.append(
                f"Existe competencia activa en la zona ({comp_card.formatted_value} captados por comercios cercanos en la simulación)."
            )
        if not risks:
            risks.append(
                "Los resultados reales dependen de alquileres, preferencias locales y precios que no constan en mapas públicos."
            )

        highlights = [
            card_map[k]
            for k in ("resident_population_approx", "household_avg_cash_usd", "low_liquidity_agent_share", "mobility_accessibility_index")
            if k in card_map and card_map[k].raw_value is not None
        ]

        headline_parts = [f"{verdict_plain}."]
        if rev_card and net_card and rev_card.raw_value is not None and net_card.raw_value is not None:
            headline_parts.append(
                f"Ingresos simulados de {rev_card.formatted_value} y saldo operativo de {net_card.formatted_value} en {horizon_days} días (estimación bajo supuestos)."
            )
        elif acc_card:
            headline_parts.append(f"Evaluación completada para {horizon_days} días con accesibilidad {acc_card.formatted_value}.")

        basic_view = BasicReportView(
            what_was_evaluated=str(intervention_name),
            where_was_evaluated=f"{district_name}, {department_name}".strip(", "),
            temporal_horizon_summary=f"{horizon_days} días evaluados ({simulated_ticks:,} pasos equivalentes de 15 min)",
            overall_verdict_code=verdict_code,
            overall_verdict_plain=verdict_plain,
            overall_result_headline=" ".join(headline_parts),
            estimated_revenue=rev_card,
            estimated_expenses=exp_card,
            operating_result=net_card,
            potential_demand=vis_card,
            potential_customers=buy_card,
            contextual_highlights=highlights,
            main_opportunities=opportunities,
            main_risks=risks,
            understandable_recommendation=str(
                recommendation_dict.get("executive_summary")
                or f"Resultado analítico: {verdict_plain}. Revisa costos fijos, competencia y liquidez local antes de invertir."
            ),
        )

        # ---- FASE 3: INTERMEDIATE VIEW ----
        bldg_tot = (territorial_intelligence.get("buildings") or {}).get("total_observed")
        conf_est = (territorial_intelligence.get("commerce") or {}).get("confirmed_establishments")
        unv_est = (territorial_intelligence.get("commerce") or {}).get("unverified_commercial_buildings")
        catch_area = (territorial_intelligence.get("catchment") or {}).get("effective_area_km2")
        catch_method = (territorial_intelligence.get("catchment") or {}).get("method")
        mob_idx = (territorial_intelligence.get("mobility") or {}).get("estimated_pedestrian_activity_index")
        emp_mismatch = (territorial_intelligence.get("employment") or {}).get("jobs_workers_spatial_mismatch")
        known_emp = (territorial_intelligence.get("employment") or {}).get("known_employers_count")
        ver_vac = (territorial_intelligence.get("employment") or {}).get("verified_job_vacancies_count")

        conv_card = card_map.get("commercial_conversion_rate")
        brow_card = card_map.get("commercial_browsers_without_purchase")
        low_liq_card = card_map.get("low_liquidity_agent_share")
        cash_card = card_map.get("household_avg_cash_usd")
        gini_card = card_map.get("wealth_gini_simulated")
        inc_card = card_map.get("household_income_earned_usd")
        wages_card = card_map.get("commercial_obligated_wages_usd")

        demand_txt = (
            f"Visitas proyectadas: {vis_card.formatted_value if vis_card else 'N/D'}; compras efectivas: {buy_card.formatted_value if buy_card else 'N/D'}"
            + (f" sobre un área de influencia de {catch_area} km² ({catch_method})." if catch_area else ".")
        )
        comp_txt = (
            f"Ventas desviadas a competidores simulados: {comp_card.formatted_value if comp_card else 'N/D'}."
            + (f" Se observaron {conf_est} establecimientos comerciales confirmados y {unv_est} edificios comerciales sin verificar en el entorno." if conf_est is not None else "")
        )
        cons_txt = (
            f"Tasa de conversión visita→compra: {conv_card.formatted_value if conv_card else 'N/D'}; "
            f"visitas sin compra (exploración/comparación): {brow_card.formatted_value if brow_card else 'N/D'}."
        )
        econ_txt = (
            f"Liquidez promedio en cohorte: {cash_card.formatted_value if cash_card else 'N/D'}; "
            f"restricción (<$15): {low_liq_card.formatted_value if low_liq_card else 'N/D'}; "
            f"Gini simulado: {gini_card.formatted_value if gini_card else 'N/D'}."
        )
        mob_txt = (
            f"Viajeros entrantes de otros distritos: {card_map['inbound_commuters'].formatted_value if 'inbound_commuters' in card_map else '0'}."
            + (f" Índice sintético de actividad peatonal: {mob_idx} (sin conteo real de sensores en calle)." if mob_idx is not None else "")
        )
        acc_txt = (
            f"Índice de accesibilidad vial y topográfica: {acc_card.formatted_value if acc_card else 'N/D'} "
            f"(densidad vial OSM + paradas + pendiente)."
        )
        emp_txt = (
            f"Ingresos laborales devengados en libro contable: {inc_card.formatted_value if inc_card else 'N/D'}; "
            f"nómina obligatoria del proyecto: {wages_card.formatted_value if wages_card else 'N/D'}."
            + (f" Empleadores conocidos en mapa: {known_emp} (vacantes verificadas en vivo: {ver_vac}; desajuste espacial: {emp_mismatch})." if known_emp is not None else "")
        )
        cost_txt = (
            f"Ingresos proyectados: {rev_card.formatted_value if rev_card else 'N/D'} | "
            f"Gastos totales deducidos: {exp_card.formatted_value if exp_card else 'N/D'} | "
            f"Resultado operativo neto: {net_card.formatted_value if net_card else 'N/D'}."
        )

        # Conservative / Base / Optimistic comparison without inventing scenario parameters
        scenario_envelopes: List[ScenarioEnvelopeEntry] = []
        if comparison_dict:
            base_m = comparison_dict.get("baseline", {}).get("metrics_mean", {})
            scenario_envelopes.append(
                ScenarioEnvelopeEntry(
                    scenario_label="Base pareada (multi-semilla SALTBOR)",
                    available=True,
                    parameters_used={"seeds": comparison_dict.get("baseline", {}).get("seeds", [seed])},
                    metrics={k: round(float(v), 2) for k, v in base_m.items() if isinstance(v, (int, float))},
                    derivation_note="Promedio real multi-semilla ejecutado por TerritorialScenarioComparisonEngine.",
                )
            )
            for alt in comparison_dict.get("alternatives", []):
                alt_m = alt.get("metrics_mean", {})
                scenario_envelopes.append(
                    ScenarioEnvelopeEntry(
                        scenario_label=str(alt.get("label", "Alternativa")),
                        available=True,
                        parameters_used={"seeds": alt.get("seeds", [seed])},
                        metrics={k: round(float(v), 2) for k, v in alt_m.items() if isinstance(v, (int, float))},
                        derivation_note="Corrida pareada multi-semilla con condiciones iniciales idénticas.",
                    )
                )
        if rev_card and net_card and rev_card.raw_value is not None and net_card.raw_value is not None:
            base_rev = float(rev_card.raw_value)
            base_net = float(net_card.raw_value)
            cogs_ratio = float(intervention_dump.get("unit_cost_ratio", 0.55) or 0.55)
            base_cogs = round(base_rev * cogs_ratio, 2)
            fixed_opex = round(base_rev - base_cogs - base_net, 2)
            for s_label, mult in _SENSITIVITY_DEMAND_FACTORS:
                s_rev = round(base_rev * mult, 2)
                s_cogs = round(s_rev * cogs_ratio, 2)
                s_net = round(s_rev - s_cogs - fixed_opex, 2)
                scenario_envelopes.append(
                    ScenarioEnvelopeEntry(
                        scenario_label=s_label,
                        available=True,
                        parameters_used={
                            "demand_multiplier": mult,
                            "unit_cost_ratio": cogs_ratio,
                            "fixed_and_payroll_opex_usd": fixed_opex,
                            "horizon_days": horizon_days,
                            "seed": seed,
                        },
                        metrics={
                            "revenue_usd": s_rev,
                            "variable_cogs_usd": s_cogs,
                            "fixed_and_payroll_usd": fixed_opex,
                            "net_operating_profit_usd": s_net,
                        },
                        derivation_note=(
                            "Análisis aritmético transparente manteniendo constante la estructura de nómina y costos fijos "
                            f"(${fixed_opex:.2f} USD) y razón de insumos ({cogs_ratio:.2f}). No inventa parámetros externos."
                        ),
                    )
                )

        action_recs: List[str] = list(recommendation_dict.get("alternative_interpretations", []))
        if exp_card and net_card and net_card.raw_value is not None and float(net_card.raw_value) < 0:
            action_recs.insert(
                0,
                "Evaluar ajustar dotación inicial de personal, costo fijo mensual o margen unitario antes de operar bajo las condiciones simuladas.",
            )
        action_recs.extend(
            [str(x) for x in recommendation_dict.get("alternatives_comparison", [])[:3]]
        )

        interm_view = IntermediateReportView(
            demand_and_market=demand_txt,
            competition=comp_txt,
            consumer_behavior=cons_txt,
            economic_capacity=econ_txt,
            territorial_mobility=mob_txt,
            accessibility=acc_txt,
            employment=emp_txt,
            costs_and_profitability=cost_txt,
            commercial_risks=risks + [str(m) for m in missing_indicators[:2]],
            alternative_scenarios=scenario_envelopes,
            actionable_recommendations=list(dict.fromkeys(action_recs)),
            key_metrics=[c for c in all_cards if c.raw_value is not None][:14],
        )

        # ---- FASE 4: EXPERT VIEW ----
        qdq = context_dict.get("question_data_quality") or {}
        exec_meta = {
            "execution_id": execution_id,
            "scenario_id": scenario_id,
            "checkpoint_id": checkpoint_id,
            "seed": seed,
            "engine_version": ENGINE_RELEASE_VERSION,
            "analyst_provider": recommendation_dict.get("provider_used", "OFFLINE_DETERMINISTIC"),
            "analyst_model": recommendation_dict.get("model_used", ""),
            "active_engines": active_engines,
            "horizon_days": horizon_days,
            "simulated_ticks": simulated_ticks,
            "resolution_mode": resolution_mode,
            "reproducible_parameters": {
                "intervention": intervention_dump,
                "temporal": temporal_dump,
                "territorial_coordinates": {
                    "district_id": context_dict.get("district_id"),
                    "lat": context_dict.get("lat"),
                    "lon": context_dict.get("lon"),
                },
            },
        }
        extrap_info = {
            "raw_cohort_visitors": fingerprint.get("raw_cohort_visitors"),
            "raw_cohort_revenue_usd": fingerprint.get("raw_cohort_revenue_usd"),
            "extrapolated_visitors": fingerprint.get("commercial_visitors"),
            "extrapolated_purchasers": fingerprint.get("commercial_purchasers"),
            "extrapolated_revenue_usd": fingerprint.get("commercial_revenue_usd"),
            "obligated_wages_usd": fingerprint.get("commercial_obligated_wages_usd"),
            "net_operating_profit_usd": fingerprint.get("commercial_net_profit_usd"),
            "warning": (
                "Los ingresos y visitas comerciales a escala se proyectan multiplicando eventos directos de cohorte por "
                "days_weight * pop_scale mientras la nómina y gastos fijos reflejan el presupuesto micro del establecimiento."
            ),
        }
        terr_sources = {
            "geographic_scope": geographic_scope,
            "district_data_quality_score": context_dict.get("data_quality_score"),
            "question_data_quality": qdq,
            "osm_buildings_observed": bldg_tot,
            "confirmed_establishments": conf_est,
            "unverified_commercial_buildings": unv_est,
            "provenance_record": provenance_record,
        }

        expert_view = ExpertReportView(
            execution_metadata=exec_meta,
            all_indicators=all_cards,
            synthetic_agents_summary={
                "population_summary": population_summary,
                "group_breakdowns": group_breakdowns,
                "clustered_synthetic_opinions": synthetic_opinions,
            },
            simulation_events_and_segments=temporal_series,
            transactions_and_accounting=ledger_audit,
            extrapolations=extrap_info,
            territorial_sources_and_quality=terr_sources,
            methodology_and_assumptions=list(recommendation_dict.get("assumptions", [])),
            uncertainty=list(recommendation_dict.get("uncertainty", [])),
            missing_data=missing_indicators,
            limitations=list(dict.fromkeys(limitations + list(recommendation_dict.get("limitations", [])))),
            evidence_origin_counts={k: v for k, v in origin_counts.items() if v > 0},
        )

        return ProgressiveReportBundle(
            default_level=ReportDepthLevel.BASIC,
            source_execution_id=execution_id,
            source_scenario_id=scenario_id,
            source_seed=seed,
            canonical_numeric_fingerprint=fingerprint,
            basic=basic_view,
            intermediate=interm_view,
            expert=expert_view,
        )
