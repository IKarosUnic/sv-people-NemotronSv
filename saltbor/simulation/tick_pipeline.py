"""Modular Tick Stage Pipeline and Adaptive LOD Time-Budget Controller (Phase 1.16).

Decouples SimulationRunner.step() stage telemetry and implements dynamic
time-budget-aware Level of Detail (LOD) throttling for large populations
while keeping small-N deterministic simulations 100% bit-for-bit identical.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import time
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from saltbor.core.types import HumanID, Tick
from saltbor.population.human import SyntheticHuman
from saltbor.population.lod import CognitiveLOD, CognitiveLODManager


@dataclass
class TickStageRecord:
    """Latency breakdown for a single simulation tick across architectural layers."""

    tick: int
    environment_ms: float = 0.0
    orchestrator_ms: float = 0.0
    daily_rollover_ms: float = 0.0
    live_scenario_ms: float = 0.0
    population_update_ms: float = 0.0
    world_transit_ms: float = 0.0
    psychology_ms: float = 0.0
    checkpoint_ms: float = 0.0
    total_ms: float = 0.0
    active_agents_updated: int = 0
    deferred_lod_agents: int = 0


class AdaptiveLODBudgetController:
    """Dynamically modulates population LOD tiers to meet a target ms/tick budget.

    Invariants:
    - For populations <= auto_activate_population_threshold (default 100) unless
      explicitly forced (`force_adaptive=True`), 100% of living agents execute
      every tick to preserve bit-for-bit seed determinism with existing tests.
    - Focal agents and agents in acute physiological or economic distress
      (hunger >= 0.80, health <= 0.25, money < 1.0) are NEVER throttled.
    """

    def __init__(
        self,
        target_budget_ms: float = 50.0,
        auto_activate_population_threshold: int = 100,
        force_adaptive: bool = False,
    ) -> None:
        self.target_budget_ms = max(1.0, target_budget_ms)
        self.auto_activate_population_threshold = auto_activate_population_threshold
        self.force_adaptive = force_adaptive
        self._recent_tick_ms: deque[float] = deque(maxlen=32)
        self._throttle_level: int = 0  # 0 = none, 1 = moderate (stride 2), 2 = aggressive (stride 4)

    @property
    def throttle_level(self) -> int:
        return self._throttle_level

    @property
    def rolling_mean_ms(self) -> float:
        if not self._recent_tick_ms:
            return 0.0
        return float(sum(self._recent_tick_ms) / len(self._recent_tick_ms))

    def record_tick_duration(self, duration_ms: float, population_size: int) -> None:
        """Update rolling latency window and adjust LOD throttle level."""
        self._recent_tick_ms.append(duration_ms)
        if not self.force_adaptive and population_size <= self.auto_activate_population_threshold:
            self._throttle_level = 0
            return

        mean_ms = self.rolling_mean_ms
        if mean_ms > self.target_budget_ms * 1.5:
            self._throttle_level = 2
        elif mean_ms > self.target_budget_ms:
            self._throttle_level = max(1, self._throttle_level)
        elif mean_ms < self.target_budget_ms * 0.55 and self._throttle_level > 0:
            self._throttle_level -= 1

    def is_exceptional_or_in_crisis(
        self,
        human: SyntheticHuman,
        lod_manager: CognitiveLODManager,
    ) -> bool:
        """Determine if an agent must remain in LOD 0 full fidelity regardless of budget."""
        if human.uid in lod_manager.focal_uids:
            return True
        ps = human.physical_state
        if not getattr(human, "is_alive", ps.health > 0.0):
            return False
        if ps.hunger >= 0.80 or ps.health <= 0.25 or ps.energy <= 0.15 or ps.money < 1.0:
            return True
        if getattr(human, "active_evacuation_alert", False):
            return True
        return False

    def select_humans_for_tick(
        self,
        execution_order: List[SyntheticHuman],
        current_tick: Tick,
        lod_manager: CognitiveLODManager,
    ) -> tuple[List[SyntheticHuman], int]:
        """Partition execution_order into active agents for this tick and count of deferred agents."""
        pop_size = len(execution_order)
        if not self.force_adaptive and pop_size <= self.auto_activate_population_threshold:
            return execution_order, 0

        effective_level = self._throttle_level
        if self.force_adaptive and effective_level == 0:
            effective_level = 1

        if effective_level == 0:
            return execution_order, 0

        stride = 2 if effective_level == 1 else 4
        active: List[SyntheticHuman] = []
        deferred = 0

        for idx, human in enumerate(execution_order):
            if not getattr(human, "is_alive", human.physical_state.health > 0.0):
                lod_manager.get_assignment(human.uid).tier = CognitiveLOD.LOD_3_DORMANT
                deferred += 1
                continue

            if self.is_exceptional_or_in_crisis(human, lod_manager):
                lod_manager.get_assignment(human.uid).tier = CognitiveLOD.LOD_0_FULL
                active.append(human)
                continue

            # Deterministic staggering based on agent serial and current tick
            serial_num = int(getattr(human.identity, "serial", idx))
            if (serial_num + int(current_tick)) % stride == 0:
                lod_manager.get_assignment(human.uid).tier = CognitiveLOD.LOD_1_ROUTINE
                active.append(human)
            else:
                lod_manager.get_assignment(human.uid).tier = CognitiveLOD.LOD_2_EVENT_DRIVEN
                deferred += 1

        return active, deferred

    def get_status(self) -> Dict[str, Any]:
        return {
            "target_budget_ms": self.target_budget_ms,
            "auto_activate_population_threshold": self.auto_activate_population_threshold,
            "force_adaptive": self.force_adaptive,
            "throttle_level": self._throttle_level,
            "rolling_mean_ms": round(self.rolling_mean_ms, 3),
            "samples": len(self._recent_tick_ms),
        }


class TickStagePipeline:
    """Tracks per-stage execution timings and diagnostics for SimulationRunner.step()."""

    def __init__(self, history_limit: int = 256) -> None:
        self.history: deque[TickStageRecord] = deque(maxlen=history_limit)

    def record(self, stage_record: TickStageRecord) -> None:
        self.history.append(stage_record)

    def get_telemetry_summary(self) -> Dict[str, Any]:
        """Compute mean and p95 latency per stage across recent ticks."""
        if not self.history:
            return {
                "ticks_sampled": 0,
                "mean_total_ms": 0.0,
                "p95_total_ms": 0.0,
                "stages_mean_ms": {},
            }

        records = list(self.history)
        totals = [r.total_ms for r in records]
        p95_total = float(np.percentile(totals, 95)) if totals else 0.0

        def _mean(attr: str) -> float:
            return round(float(sum(getattr(r, attr) for r in records) / len(records)), 4)

        return {
            "ticks_sampled": len(records),
            "mean_total_ms": round(float(sum(totals) / len(totals)), 4),
            "p95_total_ms": round(p95_total, 4),
            "last_tick": records[-1].tick,
            "last_active_agents": records[-1].active_agents_updated,
            "last_deferred_agents": records[-1].deferred_lod_agents,
            "stages_mean_ms": {
                "environment_ms": _mean("environment_ms"),
                "orchestrator_ms": _mean("orchestrator_ms"),
                "daily_rollover_ms": _mean("daily_rollover_ms"),
                "live_scenario_ms": _mean("live_scenario_ms"),
                "population_update_ms": _mean("population_update_ms"),
                "world_transit_ms": _mean("world_transit_ms"),
                "psychology_ms": _mean("psychology_ms"),
                "checkpoint_ms": _mean("checkpoint_ms"),
            },
        }
