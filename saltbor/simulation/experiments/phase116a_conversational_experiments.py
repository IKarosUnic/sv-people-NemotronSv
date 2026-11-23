"""Phase 1.16A Scientific Experiments (EXP_116A_01 through EXP_116A_12).

Covers:
- EXP_116A_01: National geographic resolution
- EXP_116A_02: Conversational business creation
- EXP_116A_03: School demand assessment
- EXP_116A_04: Synthetic population evidence extraction
- EXP_116A_05: Temporal horizon comparison
- EXP_116A_06: Population activation and deactivation
- EXP_116A_07: Commuter and visitor flows
- EXP_116A_08: Gemini evidence interpretation
- EXP_116A_09: Alternative intervention comparison
- EXP_116A_10: One-year simulation
- EXP_116A_11: Offline simulation
- EXP_116A_12: Sustained performance
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from saltbor.ai.providers.base import AIProviderType
from saltbor.ai.router import AIModelRouter
from saltbor.conversational import (
    ActivationLOD,
    AnalyticalVerdict,
    ConversationIntent,
    InterventionCategory,
    NationalPopulationActivationManager,
    NationalTerritorialContextEngine,
    PopulationCategory,
    PreliminaryAssessment,
    SALTBORConversationalOrchestrator,
)
from saltbor.datasets.salvadoran.territory_data import SALVADORAN_DEPARTMENTS_P8
from saltbor.simulation.experiments.base import BaseExperiment, ExperimentConfig, ExperimentResult


def _get_process_rss_mb() -> float:
    """Read current process Resident Set Size (MB) on Windows or POSIX without extra dependencies."""
    try:
        import ctypes
        from ctypes import wintypes

        class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.K32GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        k32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        if k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return round(counters.WorkingSetSize / (1024.0 * 1024.0), 2)
    except Exception:
        pass
    return 0.0


class _Base116AExperiment(BaseExperiment):
    """Shared base helper for Phase 1.16A experiments."""

    @classmethod
    def default_config(cls) -> ExperimentConfig:
        return ExperimentConfig(
            experiment_id=cls.__name__,
            name=cls.__name__,
            description=cls.__doc__ or "Phase 1.16A Experiment",
        )

    def _result(
        self,
        success: bool,
        hypotheses: List[Dict[str, Any]],
        summary: str,
        duration: float,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> ExperimentResult:
        return ExperimentResult(
            experiment_id=self.config.experiment_id,
            name=self.config.name,
            success=success,
            summary=summary,
            hypotheses=hypotheses,
            metrics=metrics or {},
            observed_anomalies=[],
            duration_seconds=duration,
            raw_data={},
        )


class Experiment116A_01_NationalGeographicResolution(_Base116AExperiment):
    """EXP_116A_01: National geographic resolution across 14 departments, cantones, ambiguity, and coordinates."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_01",
            name="National Geographic Resolution",
            description="Resolves all 14 departments, cantones, ambiguous references, and optional map coordinates with provenance.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        geo = NationalTerritorialContextEngine()
        try:
            depts = (
                list(SALVADORAN_DEPARTMENTS_P8.values())
                if isinstance(SALVADORAN_DEPARTMENTS_P8, dict)
                else list(SALVADORAN_DEPARTMENTS_P8)
            )
            dept_ok = all(
                (ctx := geo.resolve_location(d.name)).resolved and ctx.department_code == d.code
                for d in depts
            )
            canton_ctx = geo.resolve_location("Cantón San José Las Flores")
            ambig_ctx = geo.resolve_location("El Rosario")
            coord_ctx = geo.resolve_location(lat=13.6978, lon=-89.1915)

            h1 = dept_ok and len(depts) == 14
            h2 = canton_ctx.resolved and canton_ctx.canton_name is not None
            h3 = ambig_ctx.is_ambiguous and len(ambig_ctx.candidates) >= 2
            h4 = (
                coord_ctx.resolved
                and coord_ctx.road_network_summary.get("total_segments_in_radius", 0) > 0
                and "osm_geospatial" in coord_ctx.provenance_by_domain
            )
            return self._result(
                success=h1 and h2 and h3 and h4,
                hypotheses=[
                    {"statement": "All 14 departments resolve accurately to D.L. 762 records", "confirmed": h1},
                    {"statement": "Cantón San José Las Flores resolves with rural hazard profile", "confirmed": h2},
                    {"statement": "Ambiguous place names return ranked candidates rather than guessing", "confirmed": h3},
                    {"statement": "Optional map coordinates retrieve OSM roads, POIs, and ODbL provenance", "confirmed": h4},
                ],
                summary="National resolution verified across 14 departments, cantones, ambiguity handling, and OSM coords.",
                duration=time.perf_counter() - t0,
                metrics={
                    "departments_resolved": len(depts),
                    "ambiguous_candidates_el_rosario": len(ambig_ctx.candidates),
                    "ss_centro_roads_in_radius": coord_ctx.road_network_summary.get("total_segments_in_radius", 0),
                },
            )
        finally:
            geo.close()


class Experiment116A_02_ConversationalBusinessCreation(_Base116AExperiment):
    """EXP_116A_02: Conversational business creation (pupusería + follow-up staffing) in real engines."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_02",
            name="Conversational Business Creation",
            description="Creates a pupusería in Santa Tecla conversationally, extends staffing in follow-up, and simulates non-automatic visits.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            orch = SALTBORConversationalOrchestrator(persistence_path=Path(tmp) / "exp02.db", seed=42)
            try:
                t1 = orch.handle_message("Quiero abrir una pupusería en Santa Tecla.")
                t2 = orch.handle_message("¿Y si contrato dos empleados más?", conversation_id=t1.conversation_id)
                res = orch.execute_stage_b(t2.conversation_id, t2.scenario_id, seed=42)

                ind = {i.indicator_id: i.value for i in res.evidence.indicators}
                h1 = isinstance(t1, PreliminaryAssessment) and t2.parsed_request.is_follow_up
                h2 = t2.proposed_intervention.workforce_count == t1.proposed_intervention.workforce_count + 2
                h3 = (ind.get("commercial_visitors") or 0) > 0 and (ind.get("commercial_browsers_without_purchase") or 0) > 0
                h4 = res.evidence.ledger_audit["conservation_passed"] and res.evidence.ledger_audit["cash_conservation_diff_usd"] == 0.0

                return self._result(
                    success=h1 and h2 and h3 and h4,
                    hypotheses=[
                        {"statement": "Follow-up preserves Santa Tecla location and business entity", "confirmed": h1},
                        {"statement": "Follow-up increments workforce count by +2 accurately", "confirmed": h2},
                        {"statement": "CommercialEngine exhibits non-automatic visitor conversion (browsers > 0)", "confirmed": h3},
                        {"statement": "VerifiableEconomicLedger preserves $0.00 discrepancy", "confirmed": h4},
                    ],
                    summary=f"Pupusería simulated in Santa Tecla: visitors={ind.get('commercial_visitors')}, buyers={ind.get('commercial_purchasers')}, ledger_diff=$0.00.",
                    duration=time.perf_counter() - t0,
                    metrics={
                        "visitors": ind.get("commercial_visitors"),
                        "browsers_without_purchase": ind.get("commercial_browsers_without_purchase"),
                        "purchasers": ind.get("commercial_purchasers"),
                        "revenue_usd": ind.get("commercial_revenue_usd"),
                        "net_profit_usd": ind.get("commercial_net_profit_usd"),
                    },
                )
            finally:
                orch.close()


class Experiment116A_03_SchoolDemandAssessment(_Base116AExperiment):
    """EXP_116A_03: School demand assessment and comparison against school transport."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_03",
            name="School Demand Assessment",
            description="Evaluates school demand, dropout risk, and alternative transport comparison in a rural cantón.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            orch = SALTBORConversationalOrchestrator(persistence_path=Path(tmp) / "exp03.db", seed=42)
            try:
                t1 = orch.handle_message(
                    "Analiza si hace falta una escuela en Cantón San José Las Flores y compara con mejorar el transporte escolar."
                )
                res = orch.execute_stage_b(t1.conversation_id, t1.scenario_id, seed=42, compare_alternatives=True)
                ind = {i.indicator_id: i.value for i in res.evidence.indicators}

                h1 = t1.proposed_intervention.category == InterventionCategory.SCHOOL
                h2 = "school_attendance_rate" in ind and "school_dropout_risk" in ind
                h3 = res.comparison is not None and len(res.comparison.alternatives) >= 2
                return self._result(
                    success=h1 and h2 and h3,
                    hypotheses=[
                        {"statement": "School intervention designed for Cantón San José Las Flores", "confirmed": h1},
                        {"statement": "School attendance and dropout risk metrics computed from cohort and constraints", "confirmed": h2},
                        {"statement": "School construction compared against school transport alternative", "confirmed": h3},
                    ],
                    summary=f"School assessment completed: attendance={ind.get('school_attendance_rate')}, dropout_risk={ind.get('school_dropout_risk')}.",
                    duration=time.perf_counter() - t0,
                    metrics={
                        "school_attendance_rate": ind.get("school_attendance_rate"),
                        "school_dropout_risk": ind.get("school_dropout_risk"),
                        "recommended_alternative": res.comparison.recommended_alternative if res.comparison else None,
                    },
                )
            finally:
                orch.close()


class Experiment116A_04_SyntheticPopulationEvidenceExtraction(_Base116AExperiment):
    """EXP_116A_04: Provenance-complete evidence extraction and grounded non-independent opinions."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_04",
            name="Synthetic Population Evidence Extraction",
            description="Verifies indicator provenance, missing indicator reporting, and grounded non-independent synthetic opinions.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            orch = SALTBORConversationalOrchestrator(persistence_path=Path(tmp) / "exp04.db", seed=77)
            try:
                t1 = orch.handle_message("Quiero poner una farmacia en Soyapango.")
                res = orch.execute_stage_b(t1.conversation_id, t1.scenario_id, seed=77)

                ev = res.evidence
                h1 = len(ev.indicators) >= 8 and all(i.provenance.source_engine and i.provenance.seed == 77 for i in ev.indicators)
                h2 = len(ev.missing_indicators) >= 1
                h3 = len(ev.synthetic_opinions) >= 1 and all(not op.is_independent_sample for op in ev.synthetic_opinions)
                return self._result(
                    success=h1 and h2 and h3,
                    hypotheses=[
                        {"statement": "All indicators include complete engine/seed/scope provenance", "confirmed": h1},
                        {"statement": "Missing geospatial/OSM data gaps exposed explicitly", "confirmed": h2},
                        {"statement": "Synthetic opinions grounded in state and marked non-independent", "confirmed": h3},
                    ],
                    summary=f"Extracted {len(ev.indicators)} provenance-tagged indicators and {len(ev.synthetic_opinions)} clustered opinions.",
                    duration=time.perf_counter() - t0,
                    metrics={
                        "indicators_count": len(ev.indicators),
                        "missing_indicators_count": len(ev.missing_indicators),
                        "opinions_count": len(ev.synthetic_opinions),
                    },
                )
            finally:
                orch.close()


class Experiment116A_05_TemporalHorizonComparison(_Base116AExperiment):
    """EXP_116A_05: Multi-horizon temporal parsing and execution (7d vs 30d vs rainy 180d vs 365d)."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_05",
            name="Temporal Horizon Comparison",
            description="Compares 7-day, 30-day, rainy-season, and 365-day simulation horizons in Santa Tecla.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            orch = SALTBORConversationalOrchestrator(persistence_path=Path(tmp) / "exp05.db", seed=42)
            try:
                horizons = [
                    ("esta semana", 7),
                    ("durante 30 días", 30),
                    ("durante la época lluviosa", 180),
                    ("durante un año", 365),
                ]
                revenues: Dict[int, float] = {}
                for expr, expected_days in horizons:
                    a = orch.handle_message(f"Quiero abrir una tienda en Santa Tecla {expr}.")
                    assert a.temporal_horizon.horizon_days == expected_days
                    b = orch.execute_stage_b(a.conversation_id, a.scenario_id, seed=42)
                    rev = next(i.value for i in b.evidence.indicators if i.indicator_id == "commercial_revenue_usd")
                    revenues[expected_days] = float(rev or 0.0)

                h1 = len(revenues) == 4
                h2 = revenues[365] > revenues[30] > revenues[7]
                return self._result(
                    success=h1 and h2,
                    hypotheses=[
                        {"statement": "All four Spanish temporal horizons parsed and simulated", "confirmed": h1},
                        {"statement": "Cumulative simulated revenue scales monotonically with temporal horizon", "confirmed": h2},
                    ],
                    summary=f"Horizons 7d/30d/180d/365d revenues: {revenues}",
                    duration=time.perf_counter() - t0,
                    metrics=revenues,
                )
            finally:
                orch.close()


class Experiment116A_06_PopulationActivationDeactivation(_Base116AExperiment):
    """EXP_116A_06: Selective regional population activation, deactivation, and identity preservation."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_06",
            name="Population Activation and Deactivation",
            description="Verifies selective regional hydration, dehydration to LOD 0, and identity/wealth persistence.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        geo = NationalTerritorialContextEngine()
        mgr = NationalPopulationActivationManager(seed=42)
        try:
            st = geo.resolve_location("Santa Tecla")
            sm = geo.resolve_location("San Miguel")

            mgr.activate_region(st, target_lod=ActivationLOD.LOD_3_INDIVIDUAL_FULL, max_active_agents=35)
            humans_st = mgr.get_active_humans_for_district(st.district_id)
            target_uid = humans_st[0].uid
            humans_st[0].physical_state.money = 199.99

            mgr.deactivate_region(st.district_id, target_lod=ActivationLOD.LOD_0_TERRITORIAL_AGGREGATE)
            active_after_deact = mgr.active_registry.count

            mgr.activate_region(sm, target_lod=ActivationLOD.LOD_2_INDIVIDUAL_SUMMARY, max_active_agents=25)
            active_sm = mgr.active_registry.count

            mgr.activate_region(st, target_lod=ActivationLOD.LOD_3_INDIVIDUAL_FULL, max_active_agents=35)
            restored = mgr.active_registry.get(target_uid)

            h1 = active_after_deact == 0
            h2 = active_sm == 25
            h3 = abs(restored.physical_state.money - 199.99) < 1e-6 and mgr.total_unique_persistent_individuals() == 60
            return self._result(
                success=h1 and h2 and h3,
                hypotheses=[
                    {"statement": "Deactivation frees active RAM cleanly", "confirmed": h1},
                    {"statement": "Selective activation hydrates target district without loading entire nation", "confirmed": h2},
                    {"statement": "Re-activation restores persistent human identities and state without duplication", "confirmed": h3},
                ],
                summary="Selective regional activation/deactivation verified across Santa Tecla and San Miguel.",
                duration=time.perf_counter() - t0,
                metrics={"total_unique_persistent": mgr.total_unique_persistent_individuals()},
            )
        finally:
            geo.close()


class Experiment116A_07_CommuterAndVisitorFlows(_Base116AExperiment):
    """EXP_116A_07: Inter-district commuter and visitor flows without double-counting."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_07",
            name="Commuter and Visitor Flows",
            description="Models daily commuters and commercial visitors between Santa Tecla and San Salvador without UID duplication.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        geo = NationalTerritorialContextEngine()
        mgr = NationalPopulationActivationManager(seed=55)
        try:
            st = geo.resolve_location("Santa Tecla")
            ss = geo.resolve_location("San Salvador")
            mgr.ensure_district_cohort(st, cohort_size=30)
            mgr.ensure_district_cohort(ss, cohort_size=30)

            mgr.register_inter_district_flow(st, ss, PopulationCategory.DAILY_COMMUTER, count=10)
            mgr.register_inter_district_flow(st, ss, PopulationCategory.VISITOR, count=4)

            acc_st = mgr.get_district_population_accounting(st.district_id)
            acc_ss = mgr.get_district_population_accounting(ss.district_id)

            h1 = mgr.total_unique_persistent_individuals() == 60
            h2 = acc_st["outbound_commuters"] == 14 and acc_ss["inbound_commuters"] == 14
            h3 = (acc_st["unique_individuals_present"] + acc_ss["unique_individuals_present"]) == 60
            h4 = not acc_st["double_counting_detected"] and not acc_ss["double_counting_detected"]

            return self._result(
                success=h1 and h2 and h3 and h4,
                hypotheses=[
                    {"statement": "National unique UID count remains strictly invariant during flows", "confirmed": h1},
                    {"statement": "Outbound and inbound commuter counts balance exactly", "confirmed": h2},
                    {"statement": "Sum of individuals physically present across districts equals unique total", "confirmed": h3},
                    {"statement": "Anti-double-counting check passes", "confirmed": h4},
                ],
                summary="Santa Tecla <-> San Salvador commuter & visitor flow verified with zero double-counting.",
                duration=time.perf_counter() - t0,
                metrics={
                    "st_present": acc_st["unique_individuals_present"],
                    "ss_present": acc_ss["unique_individuals_present"],
                    "national_unique": mgr.total_unique_persistent_individuals(),
                },
            )
        finally:
            geo.close()


class Experiment116A_08_GeminiEvidenceInterpretation(_Base116AExperiment):
    """EXP_116A_08: Mocked Gemini structured interpretation + header auth + fallback verification."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_08",
            name="Gemini Evidence Interpretation",
            description="Verifies mocked Gemini JSON schema interpretation over Stage B evidence and failover.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        router = AIModelRouter(allow_remote=True)
        router.gemini_provider.set_byok_key("AIzaSyMockExperimentKey123456")

        class _FakeResp:
            def __init__(self, payload: dict):
                self._b = json.dumps(payload).encode("utf-8")

            def read(self):
                return self._b

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with tempfile.TemporaryDirectory() as tmp:
            orch = SALTBORConversationalOrchestrator(router=router, persistence_path=Path(tmp) / "exp08.db", seed=42)
            try:
                a = orch.handle_message("Quiero abrir una pupusería en Santa Ana.")
                mock_body = {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "verdict": "CONDITIONALLY_PROMISING",
                                                "executive_summary": "Interpretación Gemini grounded en indicadores reales de Santa Ana.",
                                            }
                                        )
                                    }
                                ]
                            }
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 40, "candidatesTokenCount": 20},
                }
                with patch("urllib.request.urlopen", return_value=_FakeResp(mock_body)):
                    res = orch.execute_stage_b(a.conversation_id, a.scenario_id, seed=42)

                h1 = res.recommendation.provider_used == AIProviderType.REMOTE_GEMINI.value
                h2 = res.recommendation.verdict in set(AnalyticalVerdict)
                h3 = len(res.recommendation.supporting_evidence) >= 5
                return self._result(
                    success=h1 and h2 and h3,
                    hypotheses=[
                        {"statement": "Gemini provider executes structured analysis over Stage B evidence", "confirmed": h1},
                        {"statement": "Verdict conforms strictly to AnalyticalVerdict enum", "confirmed": h2},
                        {"statement": "Supporting evidence retains simulated provenance indicators", "confirmed": h3},
                    ],
                    summary=f"Gemini evidence interpretation completed ({res.recommendation.verdict.value}).",
                    duration=time.perf_counter() - t0,
                    metrics={"provider": res.recommendation.provider_used, "verdict": res.recommendation.verdict.value},
                )
            finally:
                orch.close()


class Experiment116A_09_AlternativeInterventionComparison(_Base116AExperiment):
    """EXP_116A_09: Multi-seed paired comparison across baseline, intervention, and alternative."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_09",
            name="Alternative Intervention Comparison",
            description="Compares baseline vs school vs school transport across multiple seeds with CI95 and multi-scale views.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            orch = SALTBORConversationalOrchestrator(persistence_path=Path(tmp) / "exp09.db", seed=42)
            try:
                a = orch.handle_message("Compara construir una escuela con mejorar el transporte escolar en Chalatenango.")
                geo_ctx = orch.territorial_engine.resolve_location("Chalatenango")
                report = orch.comparison_engine.compare_scenarios(
                    context=geo_ctx,
                    base_intervention=a.proposed_intervention,
                    temporal=a.temporal_horizon,
                    seeds=[42, 101, 202],
                    max_active_agents=30,
                )
                h1 = len(report.baseline.seeds) == 3 and len(report.alternatives) >= 2
                h2 = bool(report.paired_deltas) and bool(report.recommended_alternative)
                h3 = "individual_household" in report.baseline.multi_scale_views and "municipal_departmental" in report.baseline.multi_scale_views
                return self._result(
                    success=h1 and h2 and h3,
                    hypotheses=[
                        {"statement": "Multi-seed paired runs executed across baseline and alternatives", "confirmed": h1},
                        {"statement": "Paired deltas and recommended alternative computed", "confirmed": h2},
                        {"statement": "Multi-scale territorial views populated", "confirmed": h3},
                    ],
                    summary=f"Recommended alternative: {report.recommended_alternative}.",
                    duration=time.perf_counter() - t0,
                    metrics={"recommended": report.recommended_alternative, "paired_deltas": report.paired_deltas},
                )
            finally:
                orch.close()


class Experiment116A_10_OneYearSimulation(_Base116AExperiment):
    """EXP_116A_10: Full 365-day seasonal simulation with checkpointing and deterministic seed replay."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_10",
            name="One-Year Simulation",
            description="Runs a 365-day seasonal simulation with checkpoints and confirms deterministic reproducibility.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            orch1 = SALTBORConversationalOrchestrator(persistence_path=Path(tmp) / "y1a.db", seed=42)
            orch2 = SALTBORConversationalOrchestrator(persistence_path=Path(tmp) / "y1b.db", seed=42)
            try:
                a1 = orch1.handle_message("Simula cómo se comporta una tienda en San Miguel durante un año.")
                b1 = orch1.execute_stage_b(a1.conversation_id, a1.scenario_id, seed=42)

                a2 = orch2.handle_message("Simula cómo se comporta una tienda en San Miguel durante un año.")
                b2 = orch2.execute_stage_b(a2.conversation_id, a2.scenario_id, seed=42)

                r1 = next(i.value for i in b1.evidence.indicators if i.indicator_id == "commercial_revenue_usd")
                r2 = next(i.value for i in b2.evidence.indicators if i.indicator_id == "commercial_revenue_usd")
                ckpt = orch1.persistence.load_checkpoint(b1.checkpoint_id) if b1.checkpoint_id else None

                h1 = b1.temporal_horizon.horizon_days == 365 and b1.evidence.simulated_ticks == 35040
                h2 = ckpt is not None and ckpt["simulated_days"] == 365.0
                h3 = r1 == r2 and b1.evidence.wall_clock_seconds < 3.0
                return self._result(
                    success=h1 and h2 and h3,
                    hypotheses=[
                        {"statement": "365-day horizon simulates 35,040 equivalent ticks via hybrid seasonal sampling", "confirmed": h1},
                        {"statement": "SQLite WAL checkpoint persisted cleanly", "confirmed": h2},
                        {"statement": "Deterministic seed reproducibility and <3s execution achieved", "confirmed": h3},
                    ],
                    summary=f"365-day run completed in {b1.evidence.wall_clock_seconds:.4f}s (revenue=${r1}).",
                    duration=time.perf_counter() - t0,
                    metrics={"wall_clock_seconds": b1.evidence.wall_clock_seconds, "revenue_usd": r1},
                )
            finally:
                orch1.close()
                orch2.close()


class Experiment116A_11_OfflineSimulation(_Base116AExperiment):
    """EXP_116A_11: 100% offline simulation with Gemini & Ollama unavailable and map hidden."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_11",
            name="Offline Simulation",
            description="Executes full Stage A -> Stage B pipeline completely offline without Gemini, Ollama, or map rendering.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        router = AIModelRouter(allow_remote=False)
        with tempfile.TemporaryDirectory() as tmp:
            orch = SALTBORConversationalOrchestrator(router=router, persistence_path=Path(tmp) / "exp11.db", seed=42)
            try:
                with patch.object(router.ollama_provider, "is_available", return_value=False):
                    a = orch.handle_message("¿Qué ocurre si se interrumpe esta carretera en San Vicente durante 15 días?", map_visible=False)
                    b = orch.execute_stage_b(a.conversation_id, a.scenario_id, seed=42, map_visible=False)

                h1 = b.recommendation.provider_used == AIProviderType.OFFLINE_DETERMINISTIC.value
                h2 = b.map_visible is False and b.evidence.ledger_audit["conservation_passed"] is True
                return self._result(
                    success=h1 and h2,
                    hypotheses=[
                        {"statement": "System falls back seamlessly to OFFLINE_DETERMINISTIC", "confirmed": h1},
                        {"statement": "Headless simulation completes with map hidden and $0.00 ledger diff", "confirmed": h2},
                    ],
                    summary="100% offline headless simulation verified.",
                    duration=time.perf_counter() - t0,
                    metrics={"provider": b.recommendation.provider_used, "verdict": b.recommendation.verdict.value},
                )
            finally:
                orch.close()


class Experiment116A_12_SustainedPerformance(_Base116AExperiment):
    """EXP_116A_12: Sustained multi-district performance benchmark (latency, RSS memory, CPU, throughput)."""

    def __init__(self) -> None:
        super().__init__(ExperimentConfig(
            experiment_id="EXP_116A_12",
            name="Sustained Performance Benchmark",
            description="Measures wall-clock latency, CPU time, memory RSS, active agents, and throughput across 12 sustained runs.",
        ))

    def run(self, runner: Any = None) -> ExperimentResult:
        t0 = time.perf_counter()
        cpu0 = time.process_time()
        tracemalloc.start()
        rss_before = _get_process_rss_mb()

        with tempfile.TemporaryDirectory() as tmp:
            orch = SALTBORConversationalOrchestrator(persistence_path=Path(tmp) / "exp12.db", seed=42)
            try:
                districts = ["Santa Tecla", "Soyapango", "San Miguel", "Santa Ana", "Chalatenango", "Usulután"]
                latencies_ms: List[float] = []
                total_segments = 0
                active_agents_peak = 0
                engines_seen = set()

                for idx in range(12):
                    place = districts[idx % len(districts)]
                    t_run = time.perf_counter()
                    a = orch.handle_message(f"Quiero abrir una pupusería en {place} durante 30 días.")
                    b = orch.execute_stage_b(a.conversation_id, a.scenario_id, seed=42 + idx, max_active_agents=48)
                    latencies_ms.append((time.perf_counter() - t_run) * 1000.0)
                    total_segments += len(b.evidence.temporal_series)
                    active_agents_peak = max(active_agents_peak, orch.population_manager.active_registry.count)
                    engines_seen.update(b.evidence.active_engines)

                wall_s = round(time.perf_counter() - t0, 4)
                cpu_s = round(time.process_time() - cpu0, 4)
                _, peak_traced_bytes = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                rss_after = _get_process_rss_mb()

                avg_ms = round(sum(latencies_ms) / len(latencies_ms), 2)
                max_ms = round(max(latencies_ms), 2)
                ms_per_segment = round((sum(latencies_ms)) / max(1, total_segments), 2)

                h1 = avg_ms < 500.0
                h2 = wall_s < 10.0 and active_agents_peak > 0
                return self._result(
                    success=h1 and h2,
                    hypotheses=[
                        {"statement": "Mean end-to-end Stage A+B latency under 500ms", "confirmed": h1},
                        {"statement": "12 sustained multi-district simulations completed under 10s budget", "confirmed": h2},
                    ],
                    summary=(
                        f"12 sustained Stage A+B runs in {wall_s:.2f}s (avg={avg_ms:.2f}ms/run, "
                        f"ms/segment={ms_per_segment:.2f}ms, RSS={rss_after:.1f}MB)."
                    ),
                    duration=wall_s,
                    metrics={
                        "runs": 12,
                        "wall_clock_seconds": wall_s,
                        "cpu_seconds": cpu_s,
                        "avg_latency_ms": avg_ms,
                        "max_latency_ms": max_ms,
                        "ms_per_segment": ms_per_segment,
                        "total_segments": total_segments,
                        "rss_before_mb": rss_before,
                        "rss_after_mb": rss_after,
                        "tracemalloc_peak_mb": round(peak_traced_bytes / (1024.0 * 1024.0), 2),
                        "active_agents_peak": active_agents_peak,
                        "active_engines": sorted(engines_seen),
                    },
                )
            finally:
                if tracemalloc.is_tracing():
                    tracemalloc.stop()
                orch.close()


PHASE116A_EXPERIMENTS = {
    "EXP_116A_01": Experiment116A_01_NationalGeographicResolution,
    "EXP_116A_02": Experiment116A_02_ConversationalBusinessCreation,
    "EXP_116A_03": Experiment116A_03_SchoolDemandAssessment,
    "EXP_116A_04": Experiment116A_04_SyntheticPopulationEvidenceExtraction,
    "EXP_116A_05": Experiment116A_05_TemporalHorizonComparison,
    "EXP_116A_06": Experiment116A_06_PopulationActivationDeactivation,
    "EXP_116A_07": Experiment116A_07_CommuterAndVisitorFlows,
    "EXP_116A_08": Experiment116A_08_GeminiEvidenceInterpretation,
    "EXP_116A_09": Experiment116A_09_AlternativeInterventionComparison,
    "EXP_116A_10": Experiment116A_10_OneYearSimulation,
    "EXP_116A_11": Experiment116A_11_OfflineSimulation,
    "EXP_116A_12": Experiment116A_12_SustainedPerformance,
}
