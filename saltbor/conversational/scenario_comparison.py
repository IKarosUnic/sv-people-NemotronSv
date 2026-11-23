"""Territorial Scenario Comparison Engine (Phase 1.16A).

Executes comparable multi-seed simulations (Baseline vs Proposed Intervention
vs Alternative Interventions or Operating Conditions) using identical initial
population snapshots, computing paired deltas, 95% confidence intervals, and
multi-scale breakdowns without claiming naive causal proof.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

from saltbor.conversational.evidence_engine import SyntheticPopulationEvidenceEngine
from saltbor.conversational.intervention_designer import TerritorialInterventionDesigner
from saltbor.conversational.population_activation import NationalPopulationActivationManager
from saltbor.conversational.schemas import (
    ActivationLOD,
    InterventionCategory,
    InterventionSpec,
    ScenarioComparisonEntry,
    ScenarioComparisonReport,
    TerritorialContext,
    TemporalHorizonSpec,
)
from saltbor.conversational.temporal_controller import ConversationalTemporalController

logger = logging.getLogger(__name__)


class TerritorialScenarioComparisonEngine:
    """Compares baseline, proposed, and alternative scenarios across multiple seeds."""

    def __init__(
        self,
        activation_manager: NationalPopulationActivationManager,
        intervention_designer: TerritorialInterventionDesigner,
        temporal_controller: ConversationalTemporalController,
        evidence_engine: SyntheticPopulationEvidenceEngine,
    ) -> None:
        self.activation_manager = activation_manager
        self.designer = intervention_designer
        self.temporal = temporal_controller
        self.evidence = evidence_engine

    def compare_scenarios(
        self,
        context: TerritorialContext,
        base_intervention: InterventionSpec,
        temporal: TemporalHorizonSpec,
        alternatives: Optional[List[Tuple[str, InterventionSpec]]] = None,
        seeds: Optional[List[int]] = None,
        max_active_agents: int = 36,
    ) -> ScenarioComparisonReport:
        """Compare Baseline vs Proposed vs Alternatives under matched seeds and initial states."""
        used_seeds = list(seeds or [42, 101, 202])
        self.activation_manager.activate_region(
            context=context,
            target_lod=ActivationLOD.LOD_3_INDIVIDUAL_FULL,
            max_active_agents=max_active_agents,
            seed=used_seeds[0],
        )
        baseline_snapshot = self.activation_manager.capture_baseline_snapshot()

        def _run_arm(label: str, spec: InterventionSpec, include_intervention: bool) -> ScenarioComparisonEntry:
            per_seed_metrics: Dict[str, List[float]] = {
                "household_avg_cash_usd": [],
                "school_attendance_rate": [],
                "school_dropout_risk": [],
                "edu_unmet_person_days": [],
                "hlt_unmet_person_days": [],
                "commercial_revenue_usd": [],
                "commercial_net_profit_usd": [],
                "wealth_gini_simulated": [],
                "accessibility_index": [],
            }
            for s in used_seeds:
                self.activation_manager.restore_baseline_snapshot(baseline_snapshot)
                humans = self.activation_manager.get_active_humans_for_district(context.district_id)
                pop_acc = self.activation_manager.get_district_population_accounting(context.district_id)
                sim_out = self.designer.execute_intervention_simulation(
                    spec=spec,
                    context=context,
                    humans=humans,
                    temporal=temporal,
                    temporal_controller=self.temporal,
                    seed=s,
                    include_intervention=include_intervention,
                )
                ev = self.evidence.collect_evidence(
                    scenario_id=f"{spec.intervention_id}_{label}",
                    seed=s,
                    context=context,
                    temporal=temporal,
                    intervention=spec if include_intervention else None,
                    sim_output=sim_out,
                    humans=humans,
                    pop_accounting=pop_acc,
                )
                ind_map = {ind.indicator_id: ind.value for ind in ev.indicators if ind.available and ind.value is not None}
                per_seed_metrics["household_avg_cash_usd"].append(float(ind_map.get("household_avg_cash_usd", 0.0)))
                per_seed_metrics["school_attendance_rate"].append(float(ind_map.get("school_attendance_rate", 0.0)))
                per_seed_metrics["school_dropout_risk"].append(float(ind_map.get("school_dropout_risk", 0.0)))
                per_seed_metrics["edu_unmet_person_days"].append(float(ind_map.get("edu_unmet_person_days", 0.0)))
                per_seed_metrics["hlt_unmet_person_days"].append(float(ind_map.get("hlt_unmet_person_days", 0.0)))
                per_seed_metrics["commercial_revenue_usd"].append(float(ind_map.get("commercial_revenue_usd", 0.0)))
                per_seed_metrics["commercial_net_profit_usd"].append(float(ind_map.get("commercial_net_profit_usd", 0.0)))
                per_seed_metrics["wealth_gini_simulated"].append(float(ind_map.get("wealth_gini_simulated", 0.0)))
                per_seed_metrics["accessibility_index"].append(float(ind_map.get("mobility_accessibility_index", context.accessibility_index)))

            means: Dict[str, float] = {}
            ci95: Dict[str, Tuple[float, float]] = {}
            for k, vals in per_seed_metrics.items():
                arr = np.array(vals, dtype=float)
                m = float(np.mean(arr))
                se = float(np.std(arr, ddof=1) / np.sqrt(len(arr))) if len(arr) > 1 else 0.0
                means[k] = round(m, 4)
                ci95[k] = (round(m - 1.96 * se, 4), round(m + 1.96 * se, 4))

            multi_scale = {
                "individual_household": {
                    "avg_cash_usd": means["household_avg_cash_usd"],
                    "school_attendance_rate": means["school_attendance_rate"],
                    "dropout_risk": means["school_dropout_risk"],
                },
                "business_service": {
                    "revenue_usd": means["commercial_revenue_usd"],
                    "net_profit_usd": means["commercial_net_profit_usd"],
                    "edu_unmet_person_days": means["edu_unmet_person_days"],
                    "hlt_unmet_person_days": means["hlt_unmet_person_days"],
                },
                "community_district": {
                    "district_id": context.district_id,
                    "district_name": context.district_name,
                    "gini_simulated": means["wealth_gini_simulated"],
                    "accessibility_index": means["accessibility_index"],
                },
                "municipal_departmental": {
                    "municipality_id": context.municipality_id,
                    "department_code": context.department_code,
                    "department_name": context.department_name,
                },
            }
            return ScenarioComparisonEntry(
                label=label,
                scenario_id=spec.intervention_id,
                seeds=used_seeds,
                metrics_mean=means,
                metrics_ci95=ci95,
                multi_scale_views=multi_scale,
            )

        baseline_entry = _run_arm("baseline_sin_intervencion", base_intervention, include_intervention=False)
        proposed_entry = _run_arm(f"propuesta_{base_intervention.category.value.lower()}", base_intervention, include_intervention=True)

        alt_entries: List[ScenarioComparisonEntry] = [proposed_entry]
        if alternatives:
            for alt_label, alt_spec in alternatives:
                alt_entries.append(_run_arm(alt_label, alt_spec, include_intervention=True))
        elif base_intervention.category == InterventionCategory.SCHOOL:
            # Built-in domain alternative: compare new school construction vs improving school transport
            transport_alt = base_intervention.model_copy(deep=True)
            transport_alt.intervention_id = f"{base_intervention.intervention_id}_alt_transporte"
            transport_alt.category = InterventionCategory.PUBLIC_TRANSPORT
            transport_alt.name = f"Transporte Escolar Mejorado ({context.district_name})"
            transport_alt.daily_fixed_cost_usd = 20.0
            transport_alt.initial_capital_usd = 850.0
            alt_entries.append(_run_arm("alternativa_transporte_escolar", transport_alt, include_intervention=True))

        # Restore baseline snapshot after comparison so persistent population isn't mutated
        self.activation_manager.restore_baseline_snapshot(baseline_snapshot)

        paired_deltas: Dict[str, Dict[str, float]] = {}
        for entry in alt_entries:
            paired_deltas[entry.label] = {
                k: round(entry.metrics_mean[k] - baseline_entry.metrics_mean[k], 4)
                for k in baseline_entry.metrics_mean
            }

        # Pick top alternative by composite improvement (profit + attendance - dropout risk)
        def _score(entry: ScenarioComparisonEntry) -> float:
            d = paired_deltas[entry.label]
            return (
                d.get("school_attendance_rate", 0.0) * 100.0
                - d.get("school_dropout_risk", 0.0) * 100.0
                + d.get("commercial_net_profit_usd", 0.0) * 0.05
                + d.get("household_avg_cash_usd", 0.0) * 1.5
            )

        best = max(alt_entries, key=_score)
        return ScenarioComparisonReport(
            comparison_id=f"CMP_{uuid4().hex[:8]}",
            baseline=baseline_entry,
            alternatives=alt_entries,
            paired_deltas=paired_deltas,
            recommended_alternative=best.label,
        )
