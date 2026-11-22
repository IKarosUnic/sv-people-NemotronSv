"""Live Scenario Bridge — Unifying Declarative AI Scenarios with Live Tick Execution (Phase 1.16).

Allows any `TerritorialScenarioDefinition` (including those generated from
natural language via `NaturalLanguageScenarioBuilder`) to be injected into and
stepped tick-by-tick inside the live `SimulationRunner` visual engine while
maintaining strict double-entry accounting conservation (sum(debits) == sum(credits)).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set

from saltbor.core.types import Tick
from saltbor.events.types import EventType, SimulationEvent
from saltbor.social.resources.cpr_manager import CPRHealthStatus
from saltbor.territory.economic_ledger import (
    AccountType,
    TransactionConcept,
    TransactionEntry,
    VerifiableEconomicLedger,
)
from saltbor.territory.generalized_scenarios import (
    InterventionType,
    ShockType,
    TerritorialScenarioDefinition,
)

logger = logging.getLogger(__name__)


@dataclass
class ActiveLiveScenarioSession:
    """Tracks an active declarative scenario injected into a live SimulationRunner."""

    scenario_def: TerritorialScenarioDefinition
    start_tick: int
    end_tick: int
    applied_shocks: Set[int] = field(default_factory=set)
    expired_shocks: Set[int] = field(default_factory=set)
    applied_interventions: Set[int] = field(default_factory=set)
    baseline_prices: Dict[str, Dict[str, float]] = field(default_factory=dict)
    audit_events: List[Dict[str, Any]] = field(default_factory=list)
    is_completed: bool = False


class LiveScenarioBridge:
    """Bridges declarative TerritorialScenarioDefinitions into the live SimulationRunner loop."""

    def __init__(self, runner: Any) -> None:
        self.runner = runner
        self.active_sessions: Dict[str, ActiveLiveScenarioSession] = {}
        self.ledger = VerifiableEconomicLedger()

    def inject_scenario(
        self,
        scenario_def: TerritorialScenarioDefinition,
        start_tick: Optional[int] = None,
    ) -> ActiveLiveScenarioSession:
        """Bind a declarative scenario to the live SimulationRunner starting at start_tick."""
        curr_tick = int(self.runner.clock.current_tick) if start_tick is None else int(start_tick)
        duration = max(1, int(scenario_def.duration_ticks))
        session = ActiveLiveScenarioSession(
            scenario_def=scenario_def,
            start_tick=curr_tick,
            end_tick=curr_tick + duration,
        )
        self.active_sessions[scenario_def.scenario_id] = session
        session.audit_events.append({
            "tick": curr_tick,
            "action": "SCENARIO_INJECTED",
            "scenario_id": scenario_def.scenario_id,
            "community_id": scenario_def.community_id,
            "duration_ticks": duration,
        })
        return session

    def step(self, current_tick: Tick) -> None:
        """Advance all active live scenarios for the current simulation tick."""
        if not self.active_sessions:
            return

        tick_int = int(current_tick)
        for scenario_id, session in list(self.active_sessions.items()):
            if session.is_completed:
                continue

            rel_tick = tick_int - session.start_tick
            if rel_tick < 0:
                continue

            # 1. Process scheduled shocks
            for idx, shock in enumerate(session.scenario_def.shocks):
                s_start = int(shock.get("start_tick", 0))
                s_dur = int(shock.get("duration_ticks", session.scenario_def.duration_ticks))
                s_end = s_start + s_dur

                if rel_tick >= s_start and idx not in session.applied_shocks:
                    self._apply_live_shock(session, idx, shock, tick_int)
                    session.applied_shocks.add(idx)

                if rel_tick >= s_end and idx in session.applied_shocks and idx not in session.expired_shocks:
                    self._expire_live_shock(session, idx, shock, tick_int)
                    session.expired_shocks.add(idx)

            # 2. Process scheduled policy interventions
            for idx, intervention in enumerate(session.scenario_def.interventions):
                i_start = int(intervention.get("start_tick", 0))
                if rel_tick >= i_start and idx not in session.applied_interventions:
                    self._apply_live_intervention(session, idx, intervention, tick_int)
                    session.applied_interventions.add(idx)

            # 3. Check completion
            if tick_int >= session.end_tick:
                # Ensure all price shocks are restored
                for idx, shock in enumerate(session.scenario_def.shocks):
                    if idx in session.applied_shocks and idx not in session.expired_shocks:
                        self._expire_live_shock(session, idx, shock, tick_int)
                        session.expired_shocks.add(idx)
                session.is_completed = True
                session.audit_events.append({
                    "tick": tick_int,
                    "action": "SCENARIO_COMPLETED",
                    "scenario_id": scenario_id,
                })

    def _apply_live_shock(
        self,
        session: ActiveLiveScenarioSession,
        shock_idx: int,
        shock: Dict[str, Any],
        current_tick: int,
    ) -> None:
        raw_type = str(shock.get("type", shock.get("shock_type", ShockType.ROAD_BLOCKAGE_LANDSLIDE.value))).upper()
        severity = float(shock.get("severity", shock.get("magnitude", 0.5)))
        duration = int(shock.get("duration_ticks", 48))

        if "ROAD" in raw_type or "LANDSLIDE" in raw_type or "FLOOD" in raw_type:
            # Register live road blockage on IntegratedWorldSimulationEngine
            iw = getattr(self.runner, "integrated_world", None)
            loc_name = f"Acceso {session.scenario_def.community_id}"
            if iw and hasattr(iw, "transportation"):
                iw.transportation.register_blockage(
                    cause=f"Shock de Escenario ({raw_type})",
                    location_name=loc_name,
                    lat=13.7010,
                    lon=-89.1920,
                    start_tick=current_tick,
                    duration_ticks=duration,
                    radius_m=150.0,
                )

            # Degrade communal road CPR
            cpr_mgr = getattr(self.runner, "cpr_manager", None)
            if cpr_mgr:
                road_cpr = cpr_mgr.get_resource("camino_el_calvario")
                if road_cpr:
                    road_cpr.current_stock = max(10.0, road_cpr.current_stock - 30.0 * severity)
                    if road_cpr.stock_ratio < 0.35:
                        road_cpr.status = CPRHealthStatus.STRESSED

            if getattr(self.runner, "event_bus", None):
                evt = SimulationEvent(
                    event_type=EventType.ROAD_BLOCKED,
                    tick=current_tick,
                    location_id=session.scenario_def.community_id,
                    data={
                        "scenario_id": session.scenario_def.scenario_id,
                        "shock_type": raw_type,
                        "severity": severity,
                        "duration_ticks": duration,
                    },
                    importance=0.80,
                )
                self.runner.event_bus.emit(evt)
                if getattr(self.runner, "causal_graph", None):
                    self.runner.causal_graph.add_event(
                        evt,
                        description=f"Bloqueo vial en vivo ({raw_type}) en {session.scenario_def.community_id}",
                    )

        if "PRICE" in raw_type or "DROUGHT" in raw_type or "FOOD" in raw_type or "LANDSLIDE" in raw_type:
            # Apply reversible price spike to staple food products in CommercialEngine
            multiplier = 1.0 + min(0.80, max(0.10, severity * 0.45))
            ce = getattr(self.runner, "commerce_engine", None)
            if ce:
                for est in ce.get_all_establishments():
                    est_prices = session.baseline_prices.setdefault(est.establishment_id, {})
                    for prod_id, prod in est.catalog.items():
                        if prod_id not in est_prices:
                            est_prices[prod_id] = float(prod.unit_price)
                        prod.unit_price = round(est_prices[prod_id] * multiplier, 2)

        session.audit_events.append({
            "tick": current_tick,
            "action": "SHOCK_APPLIED",
            "shock_index": shock_idx,
            "shock_type": raw_type,
            "severity": severity,
        })

    def _expire_live_shock(
        self,
        session: ActiveLiveScenarioSession,
        shock_idx: int,
        shock: Dict[str, Any],
        current_tick: int,
    ) -> None:
        raw_type = str(shock.get("type", shock.get("shock_type", ""))).upper()
        ce = getattr(self.runner, "commerce_engine", None)
        if ce and session.baseline_prices:
            for est in ce.get_all_establishments():
                saved = session.baseline_prices.get(est.establishment_id, {})
                for prod_id, base_price in saved.items():
                    if prod_id in est.catalog:
                        est.catalog[prod_id].unit_price = base_price

        session.audit_events.append({
            "tick": current_tick,
            "action": "SHOCK_EXPIRED",
            "shock_index": shock_idx,
            "shock_type": raw_type,
        })

    def _apply_live_intervention(
        self,
        session: ActiveLiveScenarioSession,
        intervention_idx: int,
        intervention: Dict[str, Any],
        current_tick: int,
    ) -> None:
        raw_type = str(
            intervention.get("type", intervention.get("intervention_type", InterventionType.COMBINED_TERRITORIAL_PACKAGE.value))
        ).upper()

        # 1. Road Rehabilitation
        if "ROAD" in raw_type or "COMBINED" in raw_type:
            cpr_mgr = getattr(self.runner, "cpr_manager", None)
            if cpr_mgr:
                road_cpr = cpr_mgr.get_resource("camino_el_calvario")
                if road_cpr:
                    road_cpr.current_stock = min(road_cpr.max_capacity, road_cpr.current_stock + 40.0)
                    road_cpr.status = CPRHealthStatus.SUSTAINABLE

        # 2. Focused Cash Transfer (Strictly Conserved Double-Entry Accounting!)
        if "CASH" in raw_type or "TRANSFER" in raw_type or "COMBINED" in raw_type:
            transfer_per_agent = float(intervention.get("transfer_amount_usd", 5.0))
            treasury_dict = getattr(self.runner, "community_utility_treasury", {"balance": 0.0})
            available_treasury = float(treasury_dict.get("balance", 0.0))

            # Locate vulnerable individuals (lowest cash first)
            living_humans = sorted(
                self.runner.population.get_all(),
                key=lambda h: float(h.physical_state.money),
            )
            recipients = [h for h in living_humans if h.physical_state.money < 25.0][:5]
            if not recipients and living_humans:
                recipients = living_humans[:2]

            total_disbursed = 0.0
            for human in recipients:
                if available_treasury < transfer_per_agent or transfer_per_agent <= 0.0:
                    break
                available_treasury -= transfer_per_agent
                treasury_dict["balance"] = round(available_treasury, 4)
                human.physical_state.money = round(float(human.physical_state.money) + transfer_per_agent, 4)
                total_disbursed += transfer_per_agent

                # Record double-entry transaction in VerifiableEconomicLedger
                self.ledger.record_transaction(
                    concept=TransactionConcept.MUNICIPAL_EMERGENCY_GRANT,
                    originating_domain="governance_social_protection",
                    description=f"Transferencia solidaria conservada a {human.uid}",
                    tick=current_tick,
                    entries=[
                        TransactionEntry(
                            account_id=f"cash_{human.uid}",
                            entity_id=str(human.uid),
                            account_type=AccountType.ASSET_CASH,
                            debit=transfer_per_agent,
                            credit=0.0,
                        ),
                        TransactionEntry(
                            account_id="community_utility_treasury",
                            entity_id="municipal_treasury",
                            account_type=AccountType.ASSET_CASH,
                            debit=0.0,
                            credit=transfer_per_agent,
                        ),
                    ],
                )

        # 3. Mobile Health Brigade
        if "HEALTH" in raw_type or "BRIGADE" in raw_type or "COMBINED" in raw_type:
            for human in self.runner.population.get_all():
                if human.physical_state.health < 0.85:
                    human.physical_state.health = min(1.0, float(human.physical_state.health) + 0.15)

        session.audit_events.append({
            "tick": current_tick,
            "action": "INTERVENTION_APPLIED",
            "intervention_index": intervention_idx,
            "intervention_type": raw_type,
        })

    def get_status_summary(self) -> Dict[str, Any]:
        """Return diagnostic summary of all injected live scenarios and ledger balance."""
        all_balanced = all(tx.is_balanced for tx in self.ledger.transactions)
        max_discrepancy = max(
            (abs(tx.total_debit - tx.total_credit) for tx in self.ledger.transactions),
            default=0.0,
        )
        return {
            "active_scenarios_count": sum(1 for s in self.active_sessions.values() if not s.is_completed),
            "completed_scenarios_count": sum(1 for s in self.active_sessions.values() if s.is_completed),
            "ledger_transactions_count": len(self.ledger.transactions),
            "ledger_is_balanced": all_balanced,
            "net_accounting_discrepancy_usd": round(max_discrepancy, 6),
            "scenarios": {
                sid: {
                    "name": sess.scenario_def.name,
                    "community_id": sess.scenario_def.community_id,
                    "start_tick": sess.start_tick,
                    "end_tick": sess.end_tick,
                    "is_completed": sess.is_completed,
                    "applied_shocks": len(sess.applied_shocks),
                    "applied_interventions": len(sess.applied_interventions),
                    "audit_events": sess.audit_events,
                }
                for sid, sess in self.active_sessions.items()
            },
        }
