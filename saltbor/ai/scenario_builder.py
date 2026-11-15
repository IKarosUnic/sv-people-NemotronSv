"""Natural Language Scenario Builder for SALTBOR Phase 1.15.

Translates unconstrained user text into validated, executable multidomain territorial
scenario configurations without requiring dedicated Python classes.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, Dict, List, Optional

from saltbor.ai.budget import AIComputeBudgetManager
from saltbor.ai.providers.base import (
    AIRequest,
    AIResponse,
    AITaskCategory,
)
from saltbor.ai.router import AIModelRouter
from saltbor.territory.generalized_scenarios import (
    TerritorialScenarioDefinition,
    ShockType,
    InterventionType,
)
from saltbor.territory.territory_catalog import TerritoryCatalogService, TerritoryDataCoverageReport

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ScenarioBuildResult:
    """Outcome container of natural language scenario compilation."""
    scenario_definition: TerritorialScenarioDefinition
    coverage_report: TerritoryDataCoverageReport
    raw_interpretation: str
    user_provided_info: Dict[str, Any]
    verified_geographic_info: Dict[str, Any]
    model_assumptions: List[str]
    missing_information: List[str]
    uncertainties: List[str]
    is_ready_for_execution: bool = True


class NaturalLanguageScenarioBuilder:
    """Compiler that converts natural language prompts to structured simulation scenarios."""

    def __init__(
        self,
        router: Optional[AIModelRouter] = None,
        budget_manager: Optional[AIComputeBudgetManager] = None,
        catalog: Optional[TerritoryCatalogService] = None,
    ) -> None:
        self.router = router or AIModelRouter()
        self.budget_manager = budget_manager or AIComputeBudgetManager()
        self.catalog = catalog or TerritoryCatalogService()

    def build_scenario_from_text(
        self,
        prompt: str,
        preferred_canton_override: Optional[str] = None,
    ) -> ScenarioBuildResult:
        """Parse natural language instruction and synthesize complete scenario definition."""
        req = AIRequest(
            task_category=AITaskCategory.SCENARIO_EXTRACTION,
            prompt=prompt,
            system_instruction=(
                "Eres el asistente científico de SALTBOR. Traduce el texto del usuario "
                "en un escenario territorial estructurado para El Salvador. "
                "No inventes datos que no existan."
            ),
        )

        # 1. Check budget & execute through router
        if self.budget_manager.is_budget_exceeded():
            # Force deterministic offline execution
            resp = self.router.deterministic_provider.execute(req)
        else:
            cached = self.budget_manager.get_cached_response(req)
            if cached:
                resp = cached
            else:
                resp = self.router.route_request(req)
                self.budget_manager.record_execution(req, resp)

        extracted = resp.structured_data or {}

        # 2. Resolve geography and evaluate data coverage
        territory_query = preferred_canton_override or extracted.get("canton_name") or "San José Las Flores"
        coverage = self.catalog.evaluate_data_coverage(territory_query)

        dept_code = coverage.department_code
        mun_id = coverage.municipality_id
        community_id = f"canton_{coverage.name.lower().replace(' ', '_')}"

        # 3. Assemble validated TerritorialScenarioDefinition
        scen_id = extracted.get("scenario_id", f"SCEN_NL_{coverage.territory_id.lower()}")
        name = extracted.get("name", f"Escenario Territorial en {coverage.name}")
        description = prompt
        duration_ticks = extracted.get("duration_ticks", 96)

        shocks = extracted.get("shocks", [])
        interventions = extracted.get("interventions", [])
        hypotheses = [
            f"El shock vial en {coverage.name} incrementará los costos de transporte y la inflación de alimentos.",
            f"La falta de liquidez obligará a los hogares vulnerables a activar estrategias de contención.",
        ]

        model_assumptions = extracted.get("assumptions", [])
        missing_info = list(set(extracted.get("missing_information", []) + coverage.missing_variables))
        uncertainties = list(set(extracted.get("uncertainties", []) + coverage.uncertainties))

        scenario_def = TerritorialScenarioDefinition(
            scenario_id=scen_id,
            name=name,
            description=description,
            department_code=dept_code,
            municipality_id=mun_id,
            community_id=community_id,
            duration_ticks=duration_ticks,
            shocks=shocks,
            interventions=interventions,
            hypotheses=hypotheses,
            uncertainties=uncertainties,
            is_rural=True,
        )

        user_info = {
            "prompt": prompt,
            "detected_duration_days": extracted.get("duration_days", 15),
            "target_domains": extracted.get("affected_domains", []),
        }

        verified_geo = {
            "department_code": dept_code,
            "municipality_id": mun_id,
            "district_id": coverage.territory_id,
            "name": coverage.name,
            "data_quality_score": coverage.data_quality_score,
            "facilities_count": len(coverage.known_facilities),
        }

        return ScenarioBuildResult(
            scenario_definition=scenario_def,
            coverage_report=coverage,
            raw_interpretation=resp.raw_text,
            user_provided_info=user_info,
            verified_geographic_info=verified_geo,
            model_assumptions=model_assumptions,
            missing_information=missing_info,
            uncertainties=uncertainties,
            is_ready_for_execution=True,
        )
