"""Conversational Temporal Simulation Controller (Phase 1.16A).

Parses natural-language Spanish temporal horizons, proposes domain-appropriate
defaults, confirms high-cost/long horizons, and executes deterministic multi-resolution
simulations (Fine Tick, Hybrid Representative Seasonal, Long-Term Aggregated)
with checkpoints, resumability, and cancellation.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import threading
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from saltbor.conversational.schemas import (
    ConversationIntent,
    TemporalHorizonSpec,
)

logger = logging.getLogger(__name__)

_SPANISH_NUMBER_WORDS: Dict[str, int] = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40, "sesenta": 60, "noventa": 90,
}

# Monthly rainfall & school-calendar seasonality multipliers for El Salvador
_EL_SALVADOR_SEASONALITY: List[Dict[str, Any]] = [
    {"month": 1, "name": "Enero", "season": "DRY", "rain_factor": 0.1, "mobility_friction": 1.00, "school_active": False, "agri_demand": 0.75},
    {"month": 2, "name": "Febrero", "season": "DRY", "rain_factor": 0.1, "mobility_friction": 1.00, "school_active": True, "agri_demand": 0.70},
    {"month": 3, "name": "Marzo", "season": "DRY", "rain_factor": 0.15, "mobility_friction": 1.00, "school_active": True, "agri_demand": 0.70},
    {"month": 4, "name": "Abril", "season": "TRANSITION", "rain_factor": 0.35, "mobility_friction": 1.03, "school_active": True, "agri_demand": 0.85},
    {"month": 5, "name": "Mayo", "season": "RAINY", "rain_factor": 0.85, "mobility_friction": 1.15, "school_active": True, "agri_demand": 1.15},
    {"month": 6, "name": "Junio", "season": "RAINY", "rain_factor": 0.95, "mobility_friction": 1.20, "school_active": True, "agri_demand": 1.10},
    {"month": 7, "name": "Julio", "season": "CANICULA", "rain_factor": 0.60, "mobility_friction": 1.08, "school_active": True, "agri_demand": 1.00},
    {"month": 8, "name": "Agosto", "season": "RAINY", "rain_factor": 0.85, "mobility_friction": 1.15, "school_active": True, "agri_demand": 1.10},
    {"month": 9, "name": "Septiembre", "season": "RAINY", "rain_factor": 1.00, "mobility_friction": 1.25, "school_active": True, "agri_demand": 1.15},
    {"month": 10, "name": "Octubre", "season": "RAINY", "rain_factor": 0.95, "mobility_friction": 1.22, "school_active": True, "agri_demand": 1.10},
    {"month": 11, "name": "Noviembre", "season": "POSTRERA", "rain_factor": 0.35, "mobility_friction": 1.04, "school_active": False, "agri_demand": 0.95},
    {"month": 12, "name": "Diciembre", "season": "DRY", "rain_factor": 0.15, "mobility_friction": 1.02, "school_active": False, "agri_demand": 1.20},
]


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclasses.dataclass
class TemporalCheckpoint:
    """Resumable checkpoint for temporal simulation loops."""

    scenario_id: str
    seed: int
    completed_steps: int
    total_steps: int
    simulated_days_elapsed: float
    step_history: List[Dict[str, Any]]
    state_summary: Dict[str, Any]


class ConversationalTemporalController:
    """Parses temporal intent and drives multi-resolution simulation schedules."""

    def parse_temporal_horizon(
        self,
        text: Optional[str],
        intent: ConversationIntent = ConversationIntent.GENERAL_SCENARIO,
        seed: int = 42,
        explicit_days: Optional[int] = None,
    ) -> TemporalHorizonSpec:
        """Infer TemporalHorizonSpec from Spanish text or domain-calibrated defaults."""
        raw = (text or "").strip()
        norm = _norm(raw)

        days: Optional[int] = explicit_days
        seasonal_profile = "STANDARD"
        calendar_alignment = "standard_calendar"
        inferred_default = explicit_days is None

        if days is None and norm:
            # Explicit phrases
            if "esta semana" in norm or "una semana" in norm or "7 dias" in norm:
                days = 7
                inferred_default = False
            elif "quincena" in norm or "15 dias" in norm or "quince dias" in norm:
                days = 15
                inferred_default = False
            elif "epoca lluviosa" in norm or "temporada lluviosa" in norm or "invierno" in norm:
                days = 180
                seasonal_profile = "RAINY_SEASON"
                calendar_alignment = "may_to_october_rainy"
                inferred_default = False
            elif "epoca seca" in norm or "temporada seca" in norm or "verano" in norm:
                days = 180
                seasonal_profile = "DRY_SEASON"
                calendar_alignment = "november_to_april_dry"
                inferred_default = False
            elif "ano escolar" in norm or "ciclo escolar" in norm or "calendario escolar" in norm:
                days = 200
                seasonal_profile = "SCHOOL_CALENDAR"
                calendar_alignment = "mined_academic_calendar"
                inferred_default = False
            else:
                # Regex for numeric or word multipliers + unit
                m_num = re.search(
                    r"(?:durante|por|en\s+los\s+proximos|en\s+un|para)?\s*"
                    r"(\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|quince|veinte|treinta)\s+"
                    r"(dia|dias|semana|semanas|mes|meses|ano|anos)\b",
                    norm,
                )
                if m_num:
                    qty_raw, unit = m_num.group(1), m_num.group(2)
                    qty = int(qty_raw) if qty_raw.isdigit() else _SPANISH_NUMBER_WORDS.get(qty_raw, 1)
                    if unit.startswith("dia"):
                        days = qty
                    elif unit.startswith("semana"):
                        days = qty * 7
                    elif unit.startswith("mes"):
                        days = qty * 30
                    elif unit.startswith("ano"):
                        days = qty * 365
                        seasonal_profile = "ANNUAL_CYCLE"
                    inferred_default = False

        # Domain-calibrated defaults when user did not specify duration
        if days is None:
            inferred_default = True
            if intent == ConversationIntent.BUSINESS_PLACEMENT:
                days = 30
                calendar_alignment = "commercial_30d_plus_annual_option"
            elif intent == ConversationIntent.TRANSPORT_INFRASTRUCTURE:
                days = 7
                calendar_alignment = "representative_peak_mobility_days"
            elif intent == ConversationIntent.EDUCATIONAL_INFRASTRUCTURE:
                days = 365
                seasonal_profile = "SCHOOL_CALENDAR"
                calendar_alignment = "mined_academic_calendar"
            elif intent == ConversationIntent.AGRICULTURAL_INTERVENTION:
                days = 180
                seasonal_profile = "RAINY_SEASON"
                calendar_alignment = "crop_cycle_primera_postrera"
            elif intent in (ConversationIntent.HEALTH_INFRASTRUCTURE, ConversationIntent.PUBLIC_SERVICES):
                days = 180
                calendar_alignment = "medium_term_public_service"
            elif intent == ConversationIntent.ENVIRONMENTAL_SCENARIO:
                days = 90
                seasonal_profile = "RAINY_SEASON"
                calendar_alignment = "seasonal_hazard_window"
            else:
                days = 30

        days = max(1, min(3650, int(days)))

        if days >= 365 and seasonal_profile == "STANDARD":
            seasonal_profile = "ANNUAL_CYCLE"

        # Choose multi-resolution mode so long runs never brute-force full minute-level cognition
        ticks_per_day = 96
        total_simulated_ticks = days * ticks_per_day

        if days <= 14:
            resolution_mode = "FINE_TICK"
            representative_days = days
            effective_engine_ticks = min(240, days * 12)
        elif days <= 365:
            resolution_mode = "HYBRID_REPRESENTATIVE"
            # Representative slices: up to 12 seasonal/monthly representative blocks (each 4-8 real ticks)
            representative_days = min(24, max(4, round(days / 15)))
            effective_engine_ticks = representative_days * 6
        else:
            resolution_mode = "LONG_TERM_AGGREGATED"
            years = max(1, round(days / 365))
            representative_days = min(30, years * 6)
            effective_engine_ticks = representative_days * 4

        est_runtime = round(0.05 + effective_engine_ticks * 0.004, 3)
        requires_conf = days > 90 and inferred_default is False and days >= 365
        conf_reason = (
            f"El horizonte de {days} días usa muestreo estacional híbrido ({effective_engine_ticks} pasos de motor representando {days} días). Confirme si prefiere un análisis preliminar de 30 días."
            if requires_conf
            else None
        )

        return TemporalHorizonSpec(
            raw_expression=raw or None,
            horizon_days=days,
            resolution_mode=resolution_mode,
            ticks_per_day=ticks_per_day,
            total_simulated_ticks=total_simulated_ticks,
            effective_engine_ticks=effective_engine_ticks,
            representative_days=representative_days,
            seasonal_profile=seasonal_profile,
            calendar_alignment=calendar_alignment,
            inferred_default=inferred_default,
            requires_confirmation=requires_conf,
            confirmation_reason=conf_reason,
            estimated_runtime_seconds=est_runtime,
            seed=seed,
        )

    def build_seasonal_schedule(self, spec: TemporalHorizonSpec) -> List[Dict[str, Any]]:
        """Build ordered list of simulation segments representing the temporal horizon."""
        steps = max(1, spec.representative_days)
        days_per_step = spec.horizon_days / float(steps)

        if spec.seasonal_profile == "RAINY_SEASON":
            start_month_idx = 4  # May
        elif spec.seasonal_profile == "DRY_SEASON":
            start_month_idx = 10  # Nov
        elif spec.seasonal_profile == "SCHOOL_CALENDAR":
            start_month_idx = 1  # Feb
        else:
            start_month_idx = 0  # Jan

        schedule: List[Dict[str, Any]] = []
        ticks_per_step = max(2, spec.effective_engine_ticks // steps)

        for idx in range(steps):
            elapsed_days = idx * days_per_step
            month_idx = (start_month_idx + int(elapsed_days / 30.0)) % 12
            season_meta = _EL_SALVADOR_SEASONALITY[month_idx]
            schedule.append(
                {
                    "segment_index": idx,
                    "simulated_day_start": round(elapsed_days, 2),
                    "simulated_day_end": round(elapsed_days + days_per_step, 2),
                    "days_weight": round(days_per_step, 3),
                    "engine_ticks": ticks_per_step,
                    "month_name": season_meta["name"],
                    "season": season_meta["season"],
                    "rain_factor": season_meta["rain_factor"],
                    "mobility_friction": season_meta["mobility_friction"],
                    "school_active": season_meta["school_active"],
                    "agri_demand": season_meta["agri_demand"],
                }
            )
        return schedule

    def execute_with_checkpoints(
        self,
        scenario_id: str,
        spec: TemporalHorizonSpec,
        step_fn: Callable[[Dict[str, Any], int], Dict[str, Any]],
        cancel_event: Optional[threading.Event] = None,
        checkpoint: Optional[TemporalCheckpoint] = None,
    ) -> Dict[str, Any]:
        """Execute a scheduled temporal simulation with checkpointing and cancellation support."""
        t0 = time.perf_counter()
        schedule = self.build_seasonal_schedule(spec)

        start_idx = checkpoint.completed_steps if checkpoint else 0
        history: List[Dict[str, Any]] = list(checkpoint.step_history) if checkpoint else []
        last_checkpoint: Optional[TemporalCheckpoint] = checkpoint
        cancelled = False

        for idx in range(start_idx, len(schedule)):
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

            seg = schedule[idx]
            seg_result = step_fn(seg, idx)
            record = {**seg, **seg_result}
            history.append(record)

            # Save periodic checkpoint every 2 segments or at completion
            if (idx + 1) % 2 == 0 or (idx + 1) == len(schedule):
                last_checkpoint = TemporalCheckpoint(
                    scenario_id=scenario_id,
                    seed=spec.seed,
                    completed_steps=idx + 1,
                    total_steps=len(schedule),
                    simulated_days_elapsed=seg["simulated_day_end"],
                    step_history=list(history),
                    state_summary=dict(seg_result),
                )

        wall_sec = round(time.perf_counter() - t0, 4)
        sim_days_done = history[-1]["simulated_day_end"] if history else 0.0
        return {
            "scenario_id": scenario_id,
            "completed": not cancelled and len(history) == len(schedule),
            "cancelled": cancelled,
            "segments_completed": len(history),
            "segments_total": len(schedule),
            "simulated_days_elapsed": round(sim_days_done, 2),
            "simulated_ticks_equivalent": int(round(sim_days_done * spec.ticks_per_day)),
            "engine_ticks_executed": sum(h.get("engine_ticks", 0) for h in history),
            "wall_clock_seconds": wall_sec,
            "history": history,
            "checkpoint": last_checkpoint,
        }
