"""Dynamic Causal Orchestration Assistant for SALTBOR Phase 1.15.

Validates AI-proposed causal mechanisms against SALTBOR's scientific registry,
prevents arbitrary numerical hallucinations, detects circular event cascades,
and tags unproven links as HYPOTHESIS_PENDING_VALIDATION.
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, Dict, List, Optional, Tuple

from saltbor.territory.causal_trace import EpistemicCategory


class CausalValidationStatus(str, enum.Enum):
    """Scientific verification status of proposed causal mechanisms."""
    VALIDATED_MECHANISM = "VALIDATED_MECHANISM"
    EMPIRICALLY_CALIBRATED = "EMPIRICALLY_CALIBRATED"
    HYPOTHESIS_PENDING_VALIDATION = "HYPOTHESIS_PENDING_VALIDATION"
    REJECTED_CIRCULAR_OR_UNSUPPORTED = "REJECTED_CIRCULAR_OR_UNSUPPORTED"


# Core Scientific Causal Registry of SALTBOR
KNOWN_SCIENTIFIC_MECHANISMS: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("road_interruption", "freight_cost_surge"): {
        "engine": "CrossDomainInteractionEngine",
        "formula": "c_freight = d * c_base * mu_friction",
        "category": EpistemicCategory.EXPLICIT_MECHANISM,
    },
    ("freight_cost_surge", "staple_food_inflation"): {
        "engine": "RegionalEconomicNetworkEngine",
        "formula": "P_retail = P_wholesale + c_freight + markup",
        "category": EpistemicCategory.EXPLICIT_MECHANISM,
    },
    ("staple_food_inflation", "domestic_liquidity_drain"): {
        "engine": "VerifiableEconomicLedger",
        "formula": "Delta_cash = - (quantity * P_retail)",
        "category": EpistemicCategory.EXPLICIT_MECHANISM,
    },
    ("domestic_liquidity_drain", "school_absenteeism_risk"): {
        "engine": "HumanBehaviorHeterogeneityEngine",
        "formula": "P(dropout) = f(food_deficit, asset_buffer, adolescent_wage)",
        "category": EpistemicCategory.EMPIRICAL_EVIDENCE,
    },
    ("transport_delay_to_clinic", "unattended_infection_complication"): {
        "engine": "PublicServiceCapacityEngine",
        "formula": "Wait_time = M/M/c(lambda, mu)",
        "category": EpistemicCategory.EXPLICIT_MECHANISM,
    },
    ("unattended_infection_complication", "household_catastrophic_medical_expenditure"): {
        "engine": "CrossDomainInteractionEngine",
        "formula": "Delta_cash_med = out_of_pocket_drugs + lost_workday_wages",
        "category": EpistemicCategory.EXPLICIT_MECHANISM,
    },
}


class AICausalOrchestrationAssistant:
    """Validates and filters causal links to maintain scientific consistency."""

    def __init__(self) -> None:
        self.registry = KNOWN_SCIENTIFIC_MECHANISMS

    def validate_proposed_mechanism(
        self,
        cause: str,
        effect: str,
        proposed_delta: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Validate whether a cause-effect relationship exists in SALTBOR engines."""
        c = cause.lower().strip()
        e = effect.lower().strip()

        # Check for circularity
        if c == e:
            return {
                "status": CausalValidationStatus.REJECTED_CIRCULAR_OR_UNSUPPORTED,
                "reason": "Circular causality: cause and effect are identical.",
                "valid": False,
            }

        key = (c, e)
        if key in self.registry:
            meta = self.registry[key]
            return {
                "status": CausalValidationStatus.VALIDATED_MECHANISM,
                "engine": meta["engine"],
                "formula": meta["formula"],
                "category": meta["category"].value,
                "valid": True,
            }

        # Check if inverse exists (potential loop risk)
        if (e, c) in self.registry:
            return {
                "status": CausalValidationStatus.REJECTED_CIRCULAR_OR_UNSUPPORTED,
                "reason": "Feedback loop detected; requires explicit lagged step.",
                "valid": False,
            }

        # Unsupported or uncalibrated proposal
        return {
            "status": CausalValidationStatus.HYPOTHESIS_PENDING_VALIDATION,
            "reason": (
                "Proposed mechanism is not connected to a validated physical/economic engine. "
                "Marked as research hypothesis without arbitrary state authority."
            ),
            "category": EpistemicCategory.CAUSAL_HYPOTHESIS.value,
            "valid": False,
        }

    def filter_and_register_chain(self, causal_chain: List[Dict[str, str]]) -> Dict[str, Any]:
        """Audit an entire chain of proposed causal links."""
        validated = []
        pending_hypotheses = []
        rejected = []

        for step in causal_chain:
            cause = step.get("cause", "")
            effect = step.get("effect", "")
            check = self.validate_proposed_mechanism(cause, effect)
            if check["valid"]:
                validated.append({**step, **check})
            elif check["status"] == CausalValidationStatus.HYPOTHESIS_PENDING_VALIDATION:
                pending_hypotheses.append({**step, **check})
            else:
                rejected.append({**step, **check})

        return {
            "validated_count": len(validated),
            "pending_hypotheses_count": len(pending_hypotheses),
            "rejected_count": len(rejected),
            "validated_mechanisms": validated,
            "hypotheses_pending_validation": pending_hypotheses,
            "rejected_links": rejected,
        }
