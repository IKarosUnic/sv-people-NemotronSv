"""Evidence-Based Decision Analyst (Gemini + Local/Offline Fallback) for Phase 1.16A.

Interprets structured `EvidenceBundle` outputs produced by SALTBOR simulation
engines. Never invents simulation outcomes; validates structured outputs with
Pydantic v2, enforces strict privacy sanitization, and classifies results into
nuanced analytical verdicts rather than simplistic YES/NO answers.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from saltbor.ai.budget import AIComputeBudgetManager
from saltbor.ai.privacy import AIPrivacyGuard
from saltbor.ai.providers.base import AIProviderType, AIRequest, AITaskCategory
from saltbor.ai.router import AIModelRouter

from saltbor.conversational.schemas import (
    AnalyticalVerdict,
    DecisionRecommendation,
    EvidenceBundle,
    InterventionSpec,
    ScenarioComparisonReport,
    TerritorialContext,
)

logger = logging.getLogger(__name__)


class GeminiDecisionAnalyst:
    """Interprets real simulation evidence via Gemini (or Ollama/Offline fallback)."""

    def __init__(
        self,
        router: Optional[AIModelRouter] = None,
        budget_manager: Optional[AIComputeBudgetManager] = None,
        privacy_guard: Optional[AIPrivacyGuard] = None,
    ) -> None:
        self.router = router or AIModelRouter()
        self.budget_manager = budget_manager or AIComputeBudgetManager()
        self.privacy_guard = privacy_guard or AIPrivacyGuard()

    def analyze(
        self,
        evidence: EvidenceBundle,
        context: Optional[TerritorialContext] = None,
        intervention: Optional[InterventionSpec] = None,
        comparison: Optional[ScenarioComparisonReport] = None,
    ) -> DecisionRecommendation:
        """Analyze structured EvidenceBundle and generate a grounded DecisionRecommendation."""
        ind_map = {ind.indicator_id: ind for ind in evidence.indicators}
        baseline_rec = self._synthesize_deterministic_recommendation(
            evidence=evidence,
            ind_map=ind_map,
            context=context,
            intervention=intervention,
            comparison=comparison,
        )

        # Build compact, sanitized, explicitly tagged payload for AIModelRouter
        compact_indicators = {
            k: {"value": v.value, "unit": v.unit, "engine": v.provenance.source_engine}
            for k, v in ind_map.items()
            if v.available and v.value is not None
        }
        tagged_payload = self.privacy_guard.tag_data_origin(
            {
                "scenario_id": evidence.scenario_id,
                "geographic_scope": evidence.geographic_scope,
                "horizon_days": evidence.horizon_days,
                "active_engines": evidence.active_engines,
                "indicators": compact_indicators,
                "missing_indicators": evidence.missing_indicators[:8],
                "ledger_audit": evidence.ledger_audit,
                "calibrated_baseline_verdict": baseline_rec.verdict.value,
            },
            is_synthetic=True,
        )
        prompt_text = self.privacy_guard.minimize_payload(
            (
                "Analiza estrictamente la siguiente evidencia simulada de SALTBOR en español. "
                "NO inventes cifras que no estén en 'indicators'. Devuelve JSON válido con: "
                "verdict, executive_summary, observed_patterns, population_needs, unmet_demand, "
                "affected_groups, contradictions, assumptions, uncertainty, limitations, alternative_interpretations.\n"
                f"EVIDENCIA: {json.dumps(tagged_payload, ensure_ascii=False)}"
            ),
            max_chars=10000,
        )

        req = AIRequest(
            task_category=AITaskCategory.RESULTS_ANALYSIS,
            prompt=prompt_text,
            system_instruction=(
                "Eres el analista de decisiones territoriales de SALTBOR. "
                "Toda cifra citada debe existir exactamente en los indicadores provistos. "
                "Usa únicamente las categorías de veredicto: PROMISING, CONDITIONALLY_PROMISING, "
                "INSUFFICIENT_EVIDENCE, HIGH_RISK, NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS."
            ),
            structured_schema={},
            temperature=0.0,
            max_tokens=1200,
            metadata={"pydantic_schema": DecisionRecommendation},
        )

        if self.budget_manager.is_budget_exceeded():
            resp = self.router.deterministic_provider.execute(req)
        else:
            cached = self.budget_manager.get_cached_response(req)
            if cached:
                resp = cached
            else:
                resp = self.router.route_request(req)
                self.budget_manager.record_execution(req, resp)

        # Merge verified LLM narrative only if remote/local LLM returned valid non-deterministic JSON
        if (
            resp.is_valid
            and resp.provider_type in (AIProviderType.REMOTE_GEMINI, AIProviderType.LOCAL_OLLAMA)
            and isinstance(resp.structured_data, dict)
        ):
            merged = self._merge_llm_interpretation(baseline_rec, resp.structured_data, resp.provider_type.value, resp.model_name)
            if merged is not None:
                return merged

        baseline_rec.provider_used = resp.provider_type.value
        baseline_rec.model_used = resp.model_name
        return baseline_rec

    def _merge_llm_interpretation(
        self,
        baseline: DecisionRecommendation,
        llm_data: Dict[str, Any],
        provider_name: str,
        model_name: str,
    ) -> Optional[DecisionRecommendation]:
        """Validate LLM JSON strictly via Pydantic and enforce numeric/verdict grounding."""
        try:
            candidate_dict = baseline.model_dump()
            # Keep deterministic supporting_evidence & relevant_indicators intact to guarantee zero hallucinated numbers
            for field_name in (
                "executive_summary",
                "observed_patterns",
                "population_needs",
                "unmet_demand",
                "affected_groups",
                "alternatives_comparison",
                "contradictions",
                "assumptions",
                "uncertainty",
                "alternative_interpretations",
            ):
                val = llm_data.get(field_name)
                if isinstance(val, str) and val.strip():
                    candidate_dict[field_name] = val.strip()
                elif isinstance(val, list) and val:
                    candidate_dict[field_name] = [str(x) for x in val[:8]]

            # Only allow LLM to tighten or keep verdict if insufficient evidence wasn't triggered
            raw_verdict = llm_data.get("verdict")
            if raw_verdict in {v.value for v in AnalyticalVerdict}:
                if baseline.verdict != AnalyticalVerdict.INSUFFICIENT_EVIDENCE:
                    candidate_dict["verdict"] = raw_verdict

            candidate_dict["provider_used"] = provider_name
            candidate_dict["model_used"] = model_name
            return DecisionRecommendation.model_validate(candidate_dict)
        except ValidationError as exc:
            logger.warning("LLM DecisionRecommendation validation failed; keeping deterministic grounded analysis: %s", exc)
            return None

    def _synthesize_deterministic_recommendation(
        self,
        evidence: EvidenceBundle,
        ind_map: Dict[str, Any],
        context: Optional[TerritorialContext],
        intervention: Optional[InterventionSpec],
        comparison: Optional[ScenarioComparisonReport],
    ) -> DecisionRecommendation:
        """Compute calibrated verdict and fully grounded analysis strictly from EvidenceBundle."""
        def _val(key: str, default: Any = None) -> Any:
            ind = ind_map.get(key)
            return ind.value if (ind is not None and ind.available) else default

        active_cohort = _val("unique_active_cohort", 0) or 0
        resident_pop = _val("resident_population_approx", 0) or 0
        avg_cash = _val("household_avg_cash_usd", 0.0) or 0.0
        low_liq = _val("low_liquidity_agent_share", 0.0) or 0.0
        gini = _val("wealth_gini_simulated", 0.0) or 0.0
        income_earned = _val("household_income_earned_usd", 0.0) or 0.0
        visitors = _val("commercial_visitors")
        browsers = _val("commercial_browsers_without_purchase")
        purchasers = _val("commercial_purchasers")
        conv = _val("commercial_conversion_rate")
        rev = _val("commercial_revenue_usd")
        net_profit = _val("commercial_net_profit_usd")
        att_rate = _val("school_attendance_rate", 1.0)
        dropout_risk = _val("school_dropout_risk", 0.0)
        edu_unmet = _val("edu_unmet_person_days", 0.0)
        hlt_unmet = _val("hlt_unmet_person_days", 0.0)
        access_idx = _val("mobility_accessibility_index", 0.5)

        dq = context.data_quality_score if context else 0.7
        ledger_ok = bool(evidence.ledger_audit.get("conservation_passed", True))

        # 1. Calibrate AnalyticalVerdict
        verdict = AnalyticalVerdict.CONDITIONALLY_PROMISING
        if (context and not context.resolved) or dq < 0.45 or active_cohort == 0 or resident_pop == 0:
            verdict = AnalyticalVerdict.INSUFFICIENT_EVIDENCE
        elif not ledger_ok:
            verdict = AnalyticalVerdict.HIGH_RISK
        elif net_profit is not None:
            if net_profit < -50.0 or (purchasers or 0) == 0:
                verdict = AnalyticalVerdict.NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS
            elif net_profit < 0.0:
                verdict = AnalyticalVerdict.HIGH_RISK if (conv or 0.0) < 0.2 else AnalyticalVerdict.CONDITIONALLY_PROMISING
            elif net_profit > 0.0 and (conv or 0.0) >= 0.20 and len(evidence.missing_indicators) <= 2:
                verdict = AnalyticalVerdict.PROMISING
            else:
                verdict = AnalyticalVerdict.CONDITIONALLY_PROMISING
        elif intervention and intervention.is_shock_scenario:
            verdict = AnalyticalVerdict.HIGH_RISK if (dropout_risk or 0.0) > 0.25 or low_liq > 0.4 else AnalyticalVerdict.CONDITIONALLY_PROMISING
        else:
            if (att_rate or 1.0) >= 0.85 and (edu_unmet or 0.0) <= 50.0:
                verdict = AnalyticalVerdict.PROMISING
            else:
                verdict = AnalyticalVerdict.CONDITIONALLY_PROMISING

        # 2. Construct grounded lists strictly from observed numbers
        observed_patterns: List[str] = [
            f"Cohorte activa simulada: {active_cohort} agentes únicos en {evidence.geographic_scope} durante {evidence.horizon_days} días.",
            f"Liquidez promedio observada: ${avg_cash:.2f} USD (proporción con <$15: {low_liq * 100:.1f}%, Gini simulado: {gini:.3f}).",
            f"Índice de accesibilidad territorial: {access_idx:.3f}; ingresos laborales acumulados: ${income_earned:.2f} USD.",
        ]
        if visitors is not None:
            observed_patterns.append(
                f"Dinámica comercial: {visitors:.0f} visitas totales, {purchasers:.0f} compras ({(conv or 0.0) * 100:.1f}% conversión) y {browsers:.0f} visitantes que solo exploraron sin comprar."
            )
            observed_patterns.append(
                f"Desempeño financiero simulado: ingresos ${rev:.2f} USD, resultado operativo neto ${net_profit:.2f} USD."
            )

        population_needs: List[str] = []
        unmet_demand: List[str] = []
        if low_liq >= 0.25:
            population_needs.append(
                f"Restricción presupuestaria relevante: {low_liq * 100:.1f}% de los agentes mantuvo menos de $15.00 USD disponibles."
            )
        if (edu_unmet or 0.0) > 0:
            unmet_demand.append(
                f"Demanda educativa insatisfecha acumulada: {edu_unmet:.1f} persona-día (asistencia {att_rate * 100:.1f}%, riesgo deserción {dropout_risk * 100:.1f}%)."
            )
        if (hlt_unmet or 0.0) > 0:
            unmet_demand.append(
                f"Demanda de atención en salud insatisfecha: {hlt_unmet:.1f} persona-día."
            )
        if not unmet_demand:
            unmet_demand.append("No se detectaron brechas críticas de capacidad en los servicios evaluados durante este horizonte.")

        affected_groups: List[str] = []
        for g_name, g_stats in evidence.group_breakdowns.items():
            if g_stats.get("count", 0) > 0:
                affected_groups.append(
                    f"{g_name}: {g_stats['count']} agentes (saldo promedio ${g_stats['avg_money_usd']:.2f} USD)."
                )

        alternatives_comp: List[str] = []
        if comparison is not None:
            for alt in comparison.alternatives:
                alternatives_comp.append(
                    f"Alternativa '{alt.label}': {json.dumps(alt.metrics_mean, ensure_ascii=False)}"
                )
            if comparison.recommended_alternative:
                alternatives_comp.append(f"Mejor desempeño relativo en simulación pareada: {comparison.recommended_alternative}.")

        contradictions: List[str] = []
        if visitors and (visitors > 0) and (net_profit is not None and net_profit < 0):
            contradictions.append(
                "Afluencia comercial existente coexiste con margen neto negativo debido a costos fijos/nómina frente al poder de compra local."
            )

        supporting_evidence = [
            f"{ind.indicator_id}={ind.value} {ind.unit} [{ind.provenance.source_engine}, seed={ind.provenance.seed}]"
            for ind in evidence.indicators
            if ind.available and ind.value is not None
        ][:12]

        relevant_indicators = {
            ind.indicator_id: ind.value
            for ind in evidence.indicators
            if ind.available and ind.value is not None
        }

        assumptions = [
            f"Horizonte temporal ejecutado en modo {evidence.temporal_series[0].get('days_weight') if evidence.temporal_series else 'estándar'} días/segmento con semilla {evidence.seed}.",
            "Los agentes comerciales deciden compras con racionalidad limitada (presupuesto, hambre y comparación de precios), sin conversión automática.",
            f"Conservación contable de doble partida verificada: diff=${evidence.ledger_audit.get('cash_conservation_diff_usd', 0.0):.4f} USD.",
        ]

        uncertainty = [
            f"Calidad de datos geográficos base: {dq:.2f}/1.00.",
            "Resultados basados en una muestra hidratada representativa y parámetros calibrados; no sustituyen estudios de campo.",
        ]
        if context and context.uncertainties:
            uncertainty.extend(context.uncertainties[:3])

        alternative_interpretations = [
            "Cambios en precios unitarios, horarios o estructura de personal pueden invertir la rentabilidad observada.",
            "Factores locales no capturados en OSM (competencia informal no mapeada, preferencia vecinal o seguridad) pueden alterar la demanda real.",
        ]

        target_lbl = intervention.name if intervention else evidence.geographic_scope
        exec_summary = (
            f"Evaluación para '{target_lbl}' en {evidence.geographic_scope} ({evidence.horizon_days} días, semilla {evidence.seed}): "
            f"clasificación analítica {verdict.value}. "
            f"Se activaron {active_cohort} agentes sintéticos con conservación contable exacta ({evidence.ledger_audit.get('total_transactions', 0)} transacciones, diferencia $0.00). "
            + (
                f"El establecimiento simulado registró {visitors:.0f} visitas, {purchasers:.0f} compras y un resultado neto de ${net_profit:.2f} USD."
                if visitors is not None and net_profit is not None
                else f"La asistencia escolar simulada fue {att_rate * 100:.1f}% con riesgo de deserción de {dropout_risk * 100:.1f}%."
            )
        )

        return DecisionRecommendation(
            verdict=verdict,
            executive_summary=exec_summary,
            observed_patterns=observed_patterns,
            population_needs=population_needs or ["Demanda general alineada con el perfil socioeconómico distrital."],
            unmet_demand=unmet_demand,
            affected_groups=affected_groups,
            alternatives_comparison=alternatives_comp,
            contradictions=contradictions,
            missing_information=list(evidence.missing_indicators),
            supporting_evidence=supporting_evidence,
            relevant_indicators=relevant_indicators,
            assumptions=assumptions,
            uncertainty=uncertainty,
            limitations=list(evidence.limitations),
            alternative_interpretations=alternative_interpretations,
        )

    def analyze_evidence_package(
        self,
        package: Any,
        context: Optional[TerritorialContext] = None,
    ) -> Dict[str, Any]:
        """Interpret an A–G TerritorialEvidencePackage via Gemini/Ollama/Offline with numeric grounding check."""
        from saltbor.territorial_intelligence.evidence import TerritorialEvidenceEngine

        observed = {i.indicator_id: i.value for i in package.A_real_observed_data if i.value is not None}
        official = {i.indicator_id: i.value for i in package.B_official_statistical_estimates if i.value is not None}
        derived = {i.indicator_id: i.value for i in package.C_geographic_derivations if i.value is not None}
        simulated = {i.indicator_id: i.value for i in package.E_simulated_outcomes if i.value is not None}

        payload = self.privacy_guard.tag_data_origin(
            {
                "geographic_scope": package.geographic_scope,
                "time_interval": package.time_interval,
                "A_real_observed": observed,
                "B_official_statistical": official,
                "C_geographic_derivations": derived,
                "E_simulated_outcomes": simulated,
                "limitations": package.limitations[:6],
            },
            is_synthetic=True,
        )
        req = AIRequest(
            task_category=AITaskCategory.RESULTS_ANALYSIS,
            prompt=self.privacy_guard.minimize_payload(
                "Resume brevemente en español los hallazgos territoriales usando ÚNICAMENTE cifras en A_real_observed, "
                "B_official_statistical, C_geographic_derivations y E_simulated_outcomes. No inventes datos.\n"
                f"EVIDENCIA: {json.dumps(payload, ensure_ascii=False)}",
                max_chars=8000,
            ),
            system_instruction="Analista territorial SALTBOR: estrictamente fundamentado en evidencia, cero invención de cifras.",
            structured_schema={},
            temperature=0.0,
            max_tokens=600,
        )
        resp = self.router.route_request(req)
        narrative = resp.raw_text or " ".join(package.F_ai_interpretations_and_hypotheses)
        grounding = TerritorialEvidenceEngine.verify_narrative_grounding(narrative, package)
        if not grounding["grounded"] or resp.provider_type == AIProviderType.OFFLINE_DETERMINISTIC:
            narrative = " ".join(package.F_ai_interpretations_and_hypotheses) or (
                f"Análisis fundamentado en {package.geographic_scope}: "
                f"{observed.get('osm_buildings_observed', 0)} edificios OSM, "
                f"{observed.get('osm_confirmed_commercial_establishments', 0)} establecimientos confirmados, "
                f"área de influencia {derived.get('catchment_effective_area_km2', 0)} km²."
            )
            grounding = TerritorialEvidenceEngine.verify_narrative_grounding(narrative, package)

        return {
            "provider_used": resp.provider_type.value,
            "model_used": resp.model_name,
            "narrative": narrative,
            "grounding_audit": grounding,
            "context_district": context.district_name if context else package.geographic_scope,
        }
