"""AI Scenario Planning Assistant for SALTBOR Phase 1.15.

Assists researchers in formulating actionable territorial research questions,
discovering relevant domains, comparing policy alternatives, detecting missing variables,
and clearly distinguishing empirical facts from exploratory recommendations.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

from saltbor.ai.budget import AIComputeBudgetManager
from saltbor.ai.providers.base import (
    AIRequest,
    AITaskCategory,
)
from saltbor.ai.router import AIModelRouter


@dataclasses.dataclass
class PolicyAlternative:
    """Alternative intervention candidate formulated by the assistant."""
    alternative_id: str
    name: str
    category: str
    rationale: str
    target_domains: List[str]
    estimated_cost_usd: float
    implementation_complexity: str  # low, medium, high
    trade_offs: List[str]


class ScenarioPlanningAssistant:
    """Intelligent guide for scenario formulation and policy alternative discovery."""

    def __init__(
        self,
        router: Optional[AIModelRouter] = None,
        budget_manager: Optional[AIComputeBudgetManager] = None,
    ) -> None:
        self.router = router or AIModelRouter()
        self.budget_manager = budget_manager or AIComputeBudgetManager()

    def generate_planning_recommendations(
        self,
        research_objective: str,
        territory_name: str = "Cantón El Rosario",
    ) -> Dict[str, Any]:
        """Generate structured alternatives and recommendations for a policy question."""
        req = AIRequest(
            task_category=AITaskCategory.POLICY_PLANNING,
            prompt=f"Territorio: {territory_name}. Objetivo de política: {research_objective}",
            system_instruction=(
                "Formula alternativas comparables de política territorial. "
                "Distingue claramente una recomendación exploratoria de un hecho probado."
            ),
        )

        resp = self.router.route_request(req)
        structured = resp.structured_data or {}

        # Default structured alternatives
        alternatives = [
            PolicyAlternative(
                alternative_id="POL_ALT_1_INFRASTRUCTURE",
                name="Inversión en Resiliencia Vial Directa",
                category="Infraestructura",
                rationale="Mitigación física en puntos críticos de ladera para evitar cortes de paso.",
                target_domains=["transportation", "commerce"],
                estimated_cost_usd=150.0,
                implementation_complexity="medium",
                trade_offs=[
                    "Alto costo de capital inicial.",
                    "Requiere adjudicación y tiempo de obra.",
                ],
            ),
            PolicyAlternative(
                alternative_id="POL_ALT_2_LOCAL_MARKET",
                name="Soporte y Crédito Rotativo a Tienditas Locales",
                category="Comercio y Seguridad Alimentaria",
                rationale="Línea de crédito para sostener inventarios de granos básicos sin colapsar el fiado.",
                target_domains=["commerce", "household_economy"],
                estimated_cost_usd=80.0,
                implementation_complexity="low",
                trade_offs=[
                    "No resuelve el problema de transporte si el corte es muy prolongado.",
                    "Riesgo de insolvencia si los salarios locales no se recuperan.",
                ],
            ),
            PolicyAlternative(
                alternative_id="POL_ALT_3_TARGETED_SUBSIDIES",
                name="Transferencia Monetaria de Emergencia para Salud y Educación",
                category="Protección Social",
                rationale="Bono directo a familias con estudiantes en riesgo de deserción o enfermos crónicos.",
                target_domains=["education", "healthcare", "household_economy"],
                estimated_cost_usd=100.0,
                implementation_complexity="low",
                trade_offs=[
                    "Alivio temporal sin mejora en activos comunitarios permanentes.",
                ],
            ),
        ]

        return {
            "research_objective": research_objective,
            "target_territory": territory_name,
            "recommended_observation_period_ticks": 96,
            "key_indicators_to_monitor": [
                "Gasto promedio de bolsillo en salud (USD)",
                "Tasa de asistencia escolar en tercer ciclo (%)",
                "Volumen acumulado de crédito informal / fiado (USD)",
                "Saldo de liquidez neta en tienditas de abarrotes (USD)",
            ],
            "alternatives": [dataclasses.asdict(alt) for alt in alternatives],
            "disclaimer": (
                "Las sugerencias anteriores son opciones analíticas para la formulación de hipótesis "
                "y no constituyen garantías de viabilidad financiera o rentabilidad social."
            ),
        }
