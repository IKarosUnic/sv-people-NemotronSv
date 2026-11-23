"""Territorial Intervention Designer & Live Simulation Executor (Phase 1.16A).

Translates natural-language user specifications and follow-up modifications into
validated `InterventionSpec` entities across all 18 intervention categories,
materializes them inside SALTBOR's real engines (`CommercialEngine`, `BusinessRegistry`,
`LaborMarketEngine`, `PublicServiceCapacityEngine`, `HousingEngine`, `LiveScenarioBridge`,
`VerifiableEconomicLedger`), and simulates bounded-rationality human responses.
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np

from saltbor.conversational.schemas import (
    ConversationIntent,
    InterventionCategory,
    InterventionSpec,
    ParsedUserRequest,
    TerritorialContext,
    TemporalHorizonSpec,
)
from saltbor.core.types import ContractType, EmploymentStatus
from saltbor.domain.models import DataProvenanceTier
from saltbor.economy.business.enterprise import BusinessEnterprise, BusinessStatus, BusinessType
from saltbor.economy.commerce.commercial_engine import (
    CommercialEngine,
    CommercialEstablishment,
    CommercialProduct,
    EstablishmentType,
    VisitIntent,
)
from saltbor.economy.labor.market import LaborMarketEngine
from saltbor.population.human import SyntheticHuman
from saltbor.territory.economic_ledger import (
    AccountType,
    TransactionConcept,
    TransactionEntry,
    VerifiableEconomicLedger,
)
from saltbor.territory.models import (
    PublicServiceFacility,
    ServiceCapacityStatus,
    ServiceCategory,
)
from saltbor.territory.public_services import PublicServiceCapacityEngine

logger = logging.getLogger(__name__)


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


INTERVENTION_TEMPLATES: Dict[InterventionCategory, Dict[str, Any]] = {
    InterventionCategory.PUPUSERIA: {
        "default_name": "Pupusería Comunitaria",
        "est_type": EstablishmentType.COMEDOR_PUPUSERIA,
        "biz_type": BusinessType.DINING_COMEDOR,
        "capacity": 24,
        "opening_hour": 6,
        "closing_hour": 21,
        "workforce_count": 2,
        "daily_wage_usd": 12.0,
        "unit_price_usd": 0.90,
        "unit_cost_ratio": 0.50,
        "daily_fixed_cost_usd": 7.0,
        "initial_capital_usd": 220.0,
        "products": ["pupusa_revuelta", "pupusa_queso", "cafe_de_olla"],
        "product_category": "prepared_meal",
        "service_category": None,
    },
    InterventionCategory.RESTAURANT: {
        "default_name": "Comedor y Restaurante Local",
        "est_type": EstablishmentType.COMEDOR_PUPUSERIA,
        "biz_type": BusinessType.DINING_COMEDOR,
        "capacity": 32,
        "opening_hour": 7,
        "closing_hour": 21,
        "workforce_count": 3,
        "daily_wage_usd": 13.0,
        "unit_price_usd": 2.75,
        "unit_cost_ratio": 0.52,
        "daily_fixed_cost_usd": 11.0,
        "initial_capital_usd": 380.0,
        "products": ["almuerzo_ejecutivo", "plato_tipico"],
        "product_category": "prepared_meal",
        "service_category": None,
    },
    InterventionCategory.PHARMACY: {
        "default_name": "Farmacia Comunitaria",
        "est_type": EstablishmentType.HEALTH_CLINIC,
        "biz_type": BusinessType.MARKET_STALL,
        "capacity": 18,
        "opening_hour": 7,
        "closing_hour": 20,
        "workforce_count": 2,
        "daily_wage_usd": 15.0,
        "unit_price_usd": 3.50,
        "unit_cost_ratio": 0.62,
        "daily_fixed_cost_usd": 9.0,
        "initial_capital_usd": 450.0,
        "products": ["analgesico_basico", "suero_oral", "antibiotico_basico"],
        "product_category": "household",
        "service_category": ServiceCategory.HEALTHCARE,
    },
    InterventionCategory.SHOP: {
        "default_name": "Tienda y Pulpería Local",
        "est_type": EstablishmentType.PULPERIA,
        "biz_type": BusinessType.MARKET_STALL,
        "capacity": 16,
        "opening_hour": 6,
        "closing_hour": 21,
        "workforce_count": 1,
        "daily_wage_usd": 11.0,
        "unit_price_usd": 1.15,
        "unit_cost_ratio": 0.68,
        "daily_fixed_cost_usd": 5.0,
        "initial_capital_usd": 240.0,
        "products": ["frijol_rojo", "maiz_blanco", "pan_frances", "huevos"],
        "product_category": "staple_food",
        "service_category": None,
    },
    InterventionCategory.MARKET: {
        "default_name": "Mercado Municipal / Distrital",
        "est_type": EstablishmentType.MERCADO_STALL,
        "biz_type": BusinessType.MARKET_STALL,
        "capacity": 120,
        "opening_hour": 5,
        "closing_hour": 18,
        "workforce_count": 8,
        "daily_wage_usd": 12.0,
        "unit_price_usd": 1.05,
        "unit_cost_ratio": 0.65,
        "daily_fixed_cost_usd": 28.0,
        "initial_capital_usd": 1200.0,
        "products": ["granos_basicos", "verduras_frescas", "lacteos"],
        "product_category": "staple_food",
        "service_category": ServiceCategory.PUBLIC_MARKET,
    },
    InterventionCategory.COMMERCIAL_ESTABLISHMENT: {
        "default_name": "Establecimiento Comercial",
        "est_type": EstablishmentType.PULPERIA,
        "biz_type": BusinessType.MARKET_STALL,
        "capacity": 20,
        "opening_hour": 8,
        "closing_hour": 19,
        "workforce_count": 2,
        "daily_wage_usd": 12.5,
        "unit_price_usd": 2.25,
        "unit_cost_ratio": 0.60,
        "daily_fixed_cost_usd": 8.0,
        "initial_capital_usd": 320.0,
        "products": ["bien_comercial_general"],
        "product_category": "household",
        "service_category": None,
    },
    InterventionCategory.AGRICULTURAL_BUSINESS: {
        "default_name": "Cooperativa y Agroservicio Local",
        "est_type": EstablishmentType.MERCADO_STALL,
        "biz_type": BusinessType.AGRICULTURAL_FARM,
        "capacity": 40,
        "opening_hour": 6,
        "closing_hour": 17,
        "workforce_count": 4,
        "daily_wage_usd": 11.5,
        "unit_price_usd": 1.60,
        "unit_cost_ratio": 0.58,
        "daily_fixed_cost_usd": 10.0,
        "initial_capital_usd": 500.0,
        "products": ["maiz_blanco", "frijol_rojo", "abono_organico"],
        "product_category": "staple_food",
        "service_category": None,
    },
    InterventionCategory.SCHOOL: {
        "default_name": "Centro Escolar Comunitario",
        "est_type": None,
        "biz_type": None,
        "capacity": 180,
        "opening_hour": 7,
        "closing_hour": 16,
        "workforce_count": 6,
        "daily_wage_usd": 24.0,
        "unit_price_usd": 0.0,
        "unit_cost_ratio": 0.0,
        "daily_fixed_cost_usd": 45.0,
        "initial_capital_usd": 2500.0,
        "products": ["educacion_basica", "educacion_media"],
        "product_category": "service",
        "service_category": ServiceCategory.EDUCATION,
    },
    InterventionCategory.TRAINING_CENTER: {
        "default_name": "Centro de Formación Técnica",
        "est_type": None,
        "biz_type": None,
        "capacity": 80,
        "opening_hour": 8,
        "closing_hour": 18,
        "workforce_count": 4,
        "daily_wage_usd": 22.0,
        "unit_price_usd": 0.0,
        "unit_cost_ratio": 0.0,
        "daily_fixed_cost_usd": 25.0,
        "initial_capital_usd": 1200.0,
        "products": ["capacitacion_vocacional"],
        "product_category": "service",
        "service_category": ServiceCategory.EDUCATION,
    },
    InterventionCategory.CLINIC: {
        "default_name": "Unidad Comunitaria de Salud Familiar (UCSF)",
        "est_type": EstablishmentType.HEALTH_CLINIC,
        "biz_type": None,
        "capacity": 65,
        "opening_hour": 7,
        "closing_hour": 17,
        "workforce_count": 5,
        "daily_wage_usd": 28.0,
        "unit_price_usd": 0.0,
        "unit_cost_ratio": 0.0,
        "daily_fixed_cost_usd": 40.0,
        "initial_capital_usd": 2000.0,
        "products": ["consulta_primaria", "control_preventivo"],
        "product_category": "service",
        "service_category": ServiceCategory.HEALTHCARE,
    },
    InterventionCategory.HOSPITAL: {
        "default_name": "Centro Hospitalario Regional",
        "est_type": EstablishmentType.HEALTH_CLINIC,
        "biz_type": None,
        "capacity": 240,
        "opening_hour": 0,
        "closing_hour": 24,
        "workforce_count": 20,
        "daily_wage_usd": 35.0,
        "unit_price_usd": 0.0,
        "unit_cost_ratio": 0.0,
        "daily_fixed_cost_usd": 180.0,
        "initial_capital_usd": 9000.0,
        "products": ["emergencias", "hospitalizacion"],
        "product_category": "service",
        "service_category": ServiceCategory.HEALTHCARE,
    },
    InterventionCategory.ROAD: {
        "default_name": "Intervención Vial / Carretera",
        "est_type": None,
        "biz_type": None,
        "capacity": 500,
        "opening_hour": 0,
        "closing_hour": 24,
        "workforce_count": 6,
        "daily_wage_usd": 16.0,
        "unit_price_usd": 0.0,
        "unit_cost_ratio": 0.0,
        "daily_fixed_cost_usd": 30.0,
        "initial_capital_usd": 1500.0,
        "products": ["conectividad_vial"],
        "product_category": "service",
        "service_category": ServiceCategory.PUBLIC_TRANSIT,
    },
    InterventionCategory.PUBLIC_TRANSPORT: {
        "default_name": "Ruta de Transporte Público / Escolar",
        "est_type": None,
        "biz_type": None,
        "capacity": 160,
        "opening_hour": 5,
        "closing_hour": 20,
        "workforce_count": 3,
        "daily_wage_usd": 18.0,
        "unit_price_usd": 0.35,
        "unit_cost_ratio": 0.45,
        "daily_fixed_cost_usd": 24.0,
        "initial_capital_usd": 900.0,
        "products": ["pasaje_ruta_local"],
        "product_category": "service",
        "service_category": ServiceCategory.PUBLIC_TRANSIT,
    },
    InterventionCategory.WATER_INFRASTRUCTURE: {
        "default_name": "Sistema Comunitario de Agua Potable",
        "est_type": None,
        "biz_type": None,
        "capacity": 300,
        "opening_hour": 0,
        "closing_hour": 24,
        "workforce_count": 2,
        "daily_wage_usd": 16.0,
        "unit_price_usd": 0.25,
        "unit_cost_ratio": 0.30,
        "daily_fixed_cost_usd": 18.0,
        "initial_capital_usd": 1600.0,
        "products": ["abastecimiento_agua_potable"],
        "product_category": "service",
        "service_category": ServiceCategory.WATER_ACCESS,
    },
    InterventionCategory.ELECTRICITY_INFRASTRUCTURE: {
        "default_name": "Red de Electrificación Local",
        "est_type": None,
        "biz_type": None,
        "capacity": 350,
        "opening_hour": 0,
        "closing_hour": 24,
        "workforce_count": 2,
        "daily_wage_usd": 18.0,
        "unit_price_usd": 0.40,
        "unit_cost_ratio": 0.35,
        "daily_fixed_cost_usd": 22.0,
        "initial_capital_usd": 1800.0,
        "products": ["suministro_electrico"],
        "product_category": "service",
        "service_category": ServiceCategory.COMMUNITY_SPACE,
    },
    InterventionCategory.RECREATIONAL_FACILITY: {
        "default_name": "Parque y Espacio Recreativo Comunitario",
        "est_type": EstablishmentType.ENTERTAINMENT_VENUE,
        "biz_type": None,
        "capacity": 120,
        "opening_hour": 6,
        "closing_hour": 21,
        "workforce_count": 2,
        "daily_wage_usd": 12.0,
        "unit_price_usd": 0.0,
        "unit_cost_ratio": 0.0,
        "daily_fixed_cost_usd": 10.0,
        "initial_capital_usd": 600.0,
        "products": ["recreacion_deporte"],
        "product_category": "service",
        "service_category": ServiceCategory.COMMUNITY_SPACE,
    },
    InterventionCategory.HOUSING: {
        "default_name": "Proyecto Habitacional Comunitario",
        "est_type": None,
        "biz_type": BusinessType.CONSTRUCTION_MASONRY,
        "capacity": 40,
        "opening_hour": 0,
        "closing_hour": 24,
        "workforce_count": 5,
        "daily_wage_usd": 15.0,
        "unit_price_usd": 3.0,
        "unit_cost_ratio": 0.40,
        "daily_fixed_cost_usd": 15.0,
        "initial_capital_usd": 2000.0,
        "products": ["vivienda_asequible"],
        "product_category": "service",
        "service_category": ServiceCategory.COMMUNITY_SPACE,
    },
    InterventionCategory.ENVIRONMENTAL_PROJECT: {
        "default_name": "Proyecto de Resiliencia Ambiental / Reforestación",
        "est_type": None,
        "biz_type": None,
        "capacity": 200,
        "opening_hour": 6,
        "closing_hour": 17,
        "workforce_count": 4,
        "daily_wage_usd": 13.0,
        "unit_price_usd": 0.0,
        "unit_cost_ratio": 0.0,
        "daily_fixed_cost_usd": 12.0,
        "initial_capital_usd": 800.0,
        "products": ["mitigacion_deslave_inundacion"],
        "product_category": "service",
        "service_category": ServiceCategory.SANITATION,
    },
}


class TerritorialInterventionDesigner:
    """Designs, modifies, and executes conversational interventions inside SALTBOR engines."""

    def design_intervention(
        self,
        parsed: ParsedUserRequest,
        context: TerritorialContext,
        temporal: TemporalHorizonSpec,
        existing_spec: Optional[InterventionSpec] = None,
    ) -> InterventionSpec:
        """Build or update an InterventionSpec from parsed Spanish text and territorial context."""
        if parsed.is_follow_up and existing_spec is not None:
            return self.apply_follow_up_modification(existing_spec, parsed, temporal)

        category = parsed.intervention_type or self._infer_category_from_intent(parsed.intent, parsed.raw_message)
        tmpl = INTERVENTION_TEMPLATES[category]
        norm_msg = _norm(parsed.raw_message)

        # Extract optional price / staff / capacity overrides directly from text
        price = float(tmpl["unit_price_usd"])
        m_price = re.search(r"\$\s*(\d+(?:\.\d+)?)", parsed.raw_message)
        if m_price:
            price = float(m_price.group(1))

        workforce = int(tmpl["workforce_count"])
        m_staff = re.search(r"(\d+|dos|tres|cuatro|cinco|seis)\s+(?:empleados|trabajadores|docentes|maestros|medicos)", norm_msg)
        if m_staff:
            w_raw = m_staff.group(1)
            w_map = {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6}
            workforce = int(w_raw) if w_raw.isdigit() else w_map.get(w_raw, workforce)

        is_shock = any(w in norm_msg for w in ("interrumpe", "bloqueo", "corte", "deslave", "sequia", "inundacion", "cierre"))
        shock_type = None
        if is_shock:
            if any(w in norm_msg for w in ("carretera", "calle", "camino", "vial", "deslave")):
                shock_type = "ROAD_BLOCKAGE_LANDSLIDE"
            elif "sequia" in norm_msg:
                shock_type = "DROUGHT_CROP_LOSS"
            elif "inundacion" in norm_msg:
                shock_type = "FLOODING_AGRICULTURE"
            else:
                shock_type = "PUBLIC_SERVICE_CUT"

        place_suffix = context.canton_name or context.district_name or "El Salvador"
        name = f"{tmpl['default_name']} ({place_suffix})"

        compare_alts: List[str] = []
        if parsed.intent == ConversationIntent.TERRITORIAL_COMPARISON or "compara" in norm_msg:
            if category == InterventionCategory.SCHOOL or "escuela" in norm_msg:
                compare_alts = ["CONSTRUIR_ESCUELA", "MEJORAR_TRANSPORTE_ESCOLAR"]

        return InterventionSpec(
            intervention_id=f"INT_{category.value}_{uuid4().hex[:6]}",
            category=category,
            name=name,
            location_query=context.query,
            lat=context.lat,
            lon=context.lon,
            district_id=context.district_id,
            capacity=int(tmpl["capacity"]),
            opening_hour=int(tmpl["opening_hour"]),
            closing_hour=int(tmpl["closing_hour"]),
            resources={"osm_nearest_road": (context.nearest_road or {}).get("name", "Vía local")},
            workforce_count=workforce,
            daily_wage_usd=float(tmpl["daily_wage_usd"]),
            products_or_services=list(tmpl["products"]),
            unit_price_usd=price,
            unit_cost_ratio=float(tmpl["unit_cost_ratio"]),
            daily_fixed_cost_usd=float(tmpl["daily_fixed_cost_usd"]),
            initial_capital_usd=float(tmpl["initial_capital_usd"]),
            conditions=list(parsed.constraints),
            opening_day=1,
            duration_days=temporal.horizon_days,
            is_shock_scenario=is_shock,
            shock_type=shock_type,
            compare_alternatives=compare_alts,
        )

    def apply_follow_up_modification(
        self,
        base_spec: InterventionSpec,
        parsed: ParsedUserRequest,
        temporal: TemporalHorizonSpec,
    ) -> InterventionSpec:
        """Apply conversational follow-up modifications without losing location or entity identity."""
        updated = base_spec.model_copy(deep=True)
        updated.intervention_id = f"{base_spec.intervention_id}_v{uuid4().hex[:4]}"
        updated.duration_days = temporal.horizon_days
        mods = dict(parsed.follow_up_modifications)
        norm_msg = _norm(parsed.raw_message)

        if "add_employees" in mods:
            added = int(mods["add_employees"])
            updated.workforce_count = max(0, updated.workforce_count + added)
            updated.capacity = int(round(updated.capacity * (1.0 + 0.18 * added)))
            updated.custom_modifications["added_employees"] = added
        elif "set_employees" in mods:
            updated.workforce_count = max(0, int(mods["set_employees"]))
            updated.custom_modifications["set_employees"] = updated.workforce_count

        if "set_price_usd" in mods:
            updated.unit_price_usd = max(0.05, float(mods["set_price_usd"]))
            updated.custom_modifications["set_price_usd"] = updated.unit_price_usd
        elif "price_delta_pct" in mods:
            updated.unit_price_usd = round(
                max(0.05, updated.unit_price_usd * (1.0 + float(mods["price_delta_pct"]))), 2
            )
            updated.custom_modifications["price_delta_pct"] = mods["price_delta_pct"]

        if "horario" in norm_msg or "tarde" in norm_msg or "noche" in norm_msg or "hasta las" in norm_msg:
            if "solo" in norm_msg and "tarde" in norm_msg:
                updated.opening_hour = 13
                updated.closing_hour = 21
                updated.custom_modifications["schedule"] = "afternoon_only"
            m_close = re.search(
                r"hasta\s+las\s+(\d+|ocho|nueve|diez|once|doce)(?:\s*(?:pm|de\s+la\s+noche))?",
                norm_msg,
            )
            if m_close:
                hr_map = {"ocho": 20, "nueve": 21, "diez": 22, "once": 23, "doce": 24}
                raw_h = m_close.group(1)
                h_val = int(raw_h) if raw_h.isdigit() else hr_map.get(raw_h, 22)
                if h_val <= 11 and ("noche" in norm_msg or "pm" in norm_msg):
                    h_val += 12
                updated.closing_hour = max(updated.opening_hour + 1, min(24, h_val))
                updated.custom_modifications["closing_hour"] = updated.closing_hour

        if "capacidad" in norm_msg:
            m_cap = re.search(r"(\d+)", norm_msg)
            if m_cap:
                updated.capacity = max(4, int(m_cap.group(1)))
                updated.custom_modifications["capacity"] = updated.capacity

        return updated

    @staticmethod
    def _infer_category_from_intent(intent: ConversationIntent, msg: str) -> InterventionCategory:
        norm = _norm(msg)
        keyword_map = [
            ("pupuser", InterventionCategory.PUPUSERIA),
            ("farmacia", InterventionCategory.PHARMACY),
            ("botiquin", InterventionCategory.PHARMACY),
            ("escuela", InterventionCategory.SCHOOL),
            ("colegio", InterventionCategory.SCHOOL),
            ("instituto", InterventionCategory.SCHOOL),
            ("capacitacion", InterventionCategory.TRAINING_CENTER),
            ("clinica", InterventionCategory.CLINIC),
            ("unidad de salud", InterventionCategory.CLINIC),
            ("hospital", InterventionCategory.HOSPITAL),
            ("restaurante", InterventionCategory.RESTAURANT),
            ("comedor", InterventionCategory.RESTAURANT),
            ("mercado", InterventionCategory.MARKET),
            ("tienda", InterventionCategory.SHOP),
            ("pulperia", InterventionCategory.SHOP),
            ("carretera", InterventionCategory.ROAD),
            ("calle", InterventionCategory.ROAD),
            ("camino", InterventionCategory.ROAD),
            ("transporte", InterventionCategory.PUBLIC_TRANSPORT),
            ("bus", InterventionCategory.PUBLIC_TRANSPORT),
            ("agua", InterventionCategory.WATER_INFRASTRUCTURE),
            ("electric", InterventionCategory.ELECTRICITY_INFRASTRUCTURE),
            ("parque", InterventionCategory.RECREATIONAL_FACILITY),
            ("vivienda", InterventionCategory.HOUSING),
            ("agric", InterventionCategory.AGRICULTURAL_BUSINESS),
            ("cultivo", InterventionCategory.AGRICULTURAL_BUSINESS),
            ("ambiental", InterventionCategory.ENVIRONMENTAL_PROJECT),
        ]
        for kw, cat in keyword_map:
            if kw in norm:
                return cat

        intent_defaults = {
            ConversationIntent.BUSINESS_PLACEMENT: InterventionCategory.COMMERCIAL_ESTABLISHMENT,
            ConversationIntent.EDUCATIONAL_INFRASTRUCTURE: InterventionCategory.SCHOOL,
            ConversationIntent.HEALTH_INFRASTRUCTURE: InterventionCategory.CLINIC,
            ConversationIntent.TRANSPORT_INFRASTRUCTURE: InterventionCategory.ROAD,
            ConversationIntent.PUBLIC_SERVICES: InterventionCategory.WATER_INFRASTRUCTURE,
            ConversationIntent.AGRICULTURAL_INTERVENTION: InterventionCategory.AGRICULTURAL_BUSINESS,
            ConversationIntent.ENVIRONMENTAL_SCENARIO: InterventionCategory.ENVIRONMENTAL_PROJECT,
        }
        return intent_defaults.get(intent, InterventionCategory.COMMERCIAL_ESTABLISHMENT)

    def execute_intervention_simulation(
        self,
        spec: InterventionSpec,
        context: TerritorialContext,
        humans: List[SyntheticHuman],
        temporal: TemporalHorizonSpec,
        temporal_controller: Any,
        seed: int = 42,
        include_intervention: bool = True,
        cancel_event: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute a grounded simulation with real CommercialEngine, LaborMarket, PublicServices & Double-Entry Ledger."""
        rng = np.random.default_rng(seed)
        ledger = VerifiableEconomicLedger()
        commerce = CommercialEngine()
        labor = LaborMarketEngine()
        public_services = PublicServiceCapacityEngine()
        active_engines: List[str] = ["VerifiableEconomicLedger", "PopulationRegistry"]

        def _seed_initial_cash(entity_id: str, amount_usd: float) -> None:
            amt = round(float(amount_usd), 2)
            if amt <= 0:
                return
            ledger.initial_currency_pool = round(ledger.initial_currency_pool + amt, 2)
            ledger.record_transaction(
                concept=TransactionConcept.INITIAL_CAPITAL,
                originating_domain="initialization",
                description=f"Capital inicial de {entity_id}",
                tick=0,
                entries=[
                    TransactionEntry(f"cash_{entity_id}", entity_id, AccountType.ASSET_CASH, debit=amt, credit=0.0),
                    TransactionEntry(f"equity_{entity_id}", entity_id, AccountType.EQUITY, debit=0.0, credit=amt),
                ],
            )

        # 1. Seed initial monetary pool strictly inside VerifiableEconomicLedger
        for h in humans:
            _seed_initial_cash(str(h.uid), float(h.physical_state.money))
        _seed_initial_cash("external_employer_pool", 50000.0)
        _seed_initial_cash("local_utility_and_landlord", 500.0)

        tmpl = INTERVENTION_TEMPLATES[spec.category]
        is_commercial = tmpl["est_type"] is not None and not spec.is_shock_scenario

        # Seed existing competitor establishments grounded in real OSM POI counts
        comp_count = max(
            1,
            min(
                5,
                context.nearby_facilities_counts.get("food_service", 0)
                or context.nearby_facilities_counts.get("retail_commercial", 1),
            ),
        )
        comp_prices: List[float] = []
        for c_idx in range(comp_count):
            comp_id = f"osm_comp_{c_idx}"
            comp_price = round(max(0.45, spec.unit_price_usd * float(rng.uniform(0.95, 1.15))), 2)
            comp_prices.append(comp_price)
            commerce.register_establishment(
                CommercialEstablishment(
                    establishment_id=comp_id,
                    name=f"Comercio Existente #{c_idx + 1}",
                    establishment_type=EstablishmentType.COMEDOR_PUPUSERIA,
                    location_id=f"loc_{context.district_id}",
                    is_verified_real=True,
                    opening_hours=(6, 20),
                    capacity=20,
                    cash_box_usd=100.0,
                    catalog={
                        "comp_item": CommercialProduct(
                            product_id="comp_item",
                            name="Oferta Local Existente",
                            category=tmpl["product_category"],
                            unit_price_usd=comp_price,
                            current_stock=500.0,
                        )
                    },
                )
            )
            _seed_initial_cash(comp_id, 100.0)
        avg_comp_price = float(np.mean(comp_prices)) if comp_prices else spec.unit_price_usd

        target_est_id = spec.intervention_id
        enterprise: Optional[BusinessEnterprise] = None
        hired_workers: List[SyntheticHuman] = []

        if include_intervention and is_commercial:
            active_engines.extend(["CommercialEngine", "BusinessEnterprise", "LaborMarketEngine"])
            products_catalog = {
                pid: CommercialProduct(
                    product_id=pid,
                    name=pid.replace("_", " ").title(),
                    category=tmpl["product_category"],
                    unit_price_usd=round(spec.unit_price_usd, 2),
                    current_stock=5000.0,
                )
                for pid in (spec.products_or_services or ["producto_principal"])
            }
            est = CommercialEstablishment(
                establishment_id=target_est_id,
                name=spec.name,
                establishment_type=tmpl["est_type"],
                location_id=f"loc_{context.district_id}",
                is_verified_real=False,
                opening_hours=(spec.opening_hour, spec.closing_hour),
                capacity=spec.capacity,
                cash_box_usd=round(spec.initial_capital_usd, 2),
                operating_cost_per_day=spec.daily_fixed_cost_usd,
                catalog=products_catalog,
            )
            commerce.register_establishment(est)
            _seed_initial_cash(target_est_id, spec.initial_capital_usd)

            biz_type = tmpl["biz_type"] or BusinessType.MARKET_STALL
            owner_uid = humans[0].uid if humans else uuid4()
            enterprise = BusinessEnterprise(
                business_id=target_est_id,
                name=spec.name,
                business_type=biz_type,
                owner_uid=owner_uid,
                location_id=f"loc_{context.district_id}",
                cash_reserve=round(spec.initial_capital_usd, 2),
                max_employees=max(1, spec.workforce_count + 2),
                operating_cost_per_day=spec.daily_fixed_cost_usd,
            )

            # Hire eligible adult workers via LaborMarketEngine vacancies
            adult_candidates = [
                h for h in humans
                if 18 <= getattr(h.demographics, "age", 30) <= 64 and str(h.uid) != str(owner_uid)
            ]
            for w_idx in range(min(spec.workforce_count, len(adult_candidates))):
                vac = labor.post_vacancy(
                    business_id=target_est_id,
                    employer_uid=str(owner_uid),
                    title=f"Personal en {spec.name}",
                    required_skill="comercio",
                    min_skill_level=0.1,
                    offered_daily_wage=spec.daily_wage_usd,
                    contract_type=ContractType.INFORMAL_WAGE,
                    location_id=f"loc_{context.district_id}",
                )
                worker = adult_candidates[w_idx]
                vac.applicants.append(str(worker.uid))
                vac.is_filled = True
                worker.employment_status = EmploymentStatus.EMPLOYED_INFORMAL
                enterprise.hire_worker(worker, daily_wage=spec.daily_wage_usd)
                hired_workers.append(worker)

        # Register Public Service facility when relevant (school, clinic, hospital, transport, water)
        target_facility_id = f"fac_{spec.intervention_id}"
        service_cat = tmpl.get("service_category")
        if service_cat is not None:
            active_engines.append("PublicServiceCapacityEngine")
            if include_intervention:
                public_services.register_facility(
                    PublicServiceFacility(
                        facility_id=target_facility_id,
                        category=service_cat,
                        name=spec.name,
                        department_code=context.department_code or "06",
                        municipality_id=context.municipality_id or "0614",
                        latitude=context.lat,
                        longitude=context.lon,
                        coverage_radius_km=3.5 if context.is_urban else 7.0,
                        status=ServiceCapacityStatus.OPERATIONAL,
                        configured_capacity_per_day=max(20, spec.capacity),
                        staff_count=max(1, spec.workforce_count),
                        available_equipment_score=0.90,
                        geographic_accessibility_index=context.accessibility_index,
                        provenance_tier=DataProvenanceTier.SIMULATED,
                    )
                )

        # Baseline existing school/health service capacity grounded in OSM POI count (points + polygons)
        osm_edu_count = context.nearby_facilities_counts.get("education", 0)
        osm_hlt_count = context.nearby_facilities_counts.get("health", 0)
        existing_edu_capacity = max(120, osm_edu_count * 180)
        existing_hlt_capacity = max(40, osm_hlt_count * 50)
        public_services.register_facility(
            PublicServiceFacility(
                facility_id="existing_district_edu",
                category=ServiceCategory.EDUCATION,
                name=f"Oferta Escolar Existente ({context.district_name})",
                department_code=context.department_code or "06",
                municipality_id=context.municipality_id or "0614",
                latitude=context.lat,
                longitude=context.lon,
                configured_capacity_per_day=existing_edu_capacity,
                staff_count=max(2, osm_edu_count * 4),
                geographic_accessibility_index=context.accessibility_index,
            )
        )
        public_services.register_facility(
            PublicServiceFacility(
                facility_id="existing_district_hlt",
                category=ServiceCategory.HEALTHCARE,
                name=f"Oferta de Salud Existente ({context.district_name})",
                department_code=context.department_code or "06",
                municipality_id=context.municipality_id or "0614",
                latitude=context.lat,
                longitude=context.lon,
                configured_capacity_per_day=existing_hlt_capacity,
                staff_count=max(2, osm_hlt_count * 3),
                geographic_accessibility_index=context.accessibility_index,
            )
        )

        # Accumulators across simulated horizon (explicit separation: raw cohort events vs extrapolated scale)
        totals: Dict[str, Any] = {
            "total_visitors": 0.0,
            "total_browsers_without_purchase": 0.0,
            "total_purchasers": 0.0,
            "raw_cohort_visitors": 0,
            "raw_cohort_browsers": 0,
            "raw_cohort_purchasers": 0,
            "raw_cohort_revenue_usd": 0.0,
            "closed_hour_passersby": 0,
            "capacity_rejected_visits": 0,
            "total_revenue_usd": 0.0,
            "total_cogs_usd": 0.0,
            "total_wages_paid_usd": 0.0,
            "obligated_wages_usd": 0.0,
            "unpaid_wages_usd": 0.0,
            "total_fixed_costs_usd": 0.0,
            "obligated_fixed_costs_usd": 0.0,
            "unpaid_fixed_costs_usd": 0.0,
            "competitor_sales_usd": 0.0,
            "edu_served": 0.0,
            "edu_unmet": 0.0,
            "hlt_served": 0.0,
            "hlt_unmet": 0.0,
            "school_dropout_risk_events": 0.0,
            "school_eval_segments": 0,
            "household_income_earned_usd": 0.0,
            "shock_mobility_penalty": 0.0,
            "agent_experience_log": {},
        }
        unique_visitor_uids: set[str] = set()
        unique_buyer_uids: set[str] = set()

        # District population scale factor (maps sample cohort visits to catchment scale conservatively)
        pop_scale = max(1.0, min(15.0, context.approx_population / max(1, len(humans) * 400)))
        if not context.is_urban:
            pop_scale *= 0.65

        def _simulate_segment(seg: Dict[str, Any], seg_idx: int) -> Dict[str, Any]:
            days_w = float(seg["days_weight"])
            friction = float(seg["mobility_friction"])
            if spec.is_shock_scenario and include_intervention:
                friction *= (1.0 + 0.85 * spec.shock_severity)
            totals["shock_mobility_penalty"] = max(totals["shock_mobility_penalty"], friction)

            tick_base = int((seg_idx + 1) * 96)
            seg_visitors = 0
            seg_browsers = 0
            seg_purchasers = 0
            seg_rev = 0.0
            seg_comp_rev = 0.0
            seg_wages = 0.0
            hourly_occ: Dict[int, int] = {}

            # 1. Daily worker incomes & business payroll inside double-entry ledger (accrue obligated vs paid honestly)
            if include_intervention and enterprise is not None:
                for w in hired_workers:
                    obligated_wage = round(spec.daily_wage_usd * min(days_w, 30.0), 2)
                    totals["obligated_wages_usd"] += obligated_wage
                    if enterprise.cash_reserve >= obligated_wage and obligated_wage > 0:
                        enterprise.cash_reserve = round(enterprise.cash_reserve - obligated_wage, 2)
                        w.physical_state.money = round(w.physical_state.money + obligated_wage, 2)
                        seg_wages += obligated_wage
                        totals["household_income_earned_usd"] += obligated_wage
                        ledger.record_transaction(
                            concept=TransactionConcept.WAGE_PAYMENT,
                            originating_domain="labor_market",
                            description=f"Salario {spec.name}",
                            tick=tick_base,
                            entries=[
                                TransactionEntry(f"cash_{target_est_id}", target_est_id, AccountType.ASSET_CASH, 0.0, obligated_wage),
                                TransactionEntry(f"exp_wage_{target_est_id}", target_est_id, AccountType.EXPENSE, obligated_wage, 0.0),
                                TransactionEntry(f"cash_{w.uid}", str(w.uid), AccountType.ASSET_CASH, obligated_wage, 0.0),
                                TransactionEntry(f"rev_wage_{w.uid}", str(w.uid), AccountType.REVENUE, 0.0, obligated_wage),
                            ],
                        )
                    else:
                        # Record unpaid wage obligation rather than silently omitting it from P&L
                        totals["unpaid_wages_usd"] += obligated_wage

                obligated_fixed = round(spec.daily_fixed_cost_usd * days_w, 2)
                totals["obligated_fixed_costs_usd"] += obligated_fixed
                fixed_cost = round(min(max(0.0, enterprise.cash_reserve), obligated_fixed), 2)
                if obligated_fixed > fixed_cost:
                    totals["unpaid_fixed_costs_usd"] += round(obligated_fixed - fixed_cost, 2)
                if fixed_cost > 0:
                    enterprise.cash_reserve = round(enterprise.cash_reserve - fixed_cost, 2)
                    totals["total_fixed_costs_usd"] += fixed_cost
                    ledger.record_transaction(
                        concept=TransactionConcept.BUSINESS_OVERHEAD,
                        originating_domain="commercial",
                        description=f"Costo fijo operativo {spec.name}",
                        tick=tick_base,
                        entries=[
                            TransactionEntry(f"cash_{target_est_id}", target_est_id, AccountType.ASSET_CASH, 0.0, fixed_cost),
                            TransactionEntry(f"exp_overhead_{target_est_id}", target_est_id, AccountType.EXPENSE, fixed_cost, 0.0),
                            TransactionEntry("cash_local_utility", "local_utility_and_landlord", AccountType.ASSET_CASH, fixed_cost, 0.0),
                            TransactionEntry("rev_local_utility", "local_utility_and_landlord", AccountType.REVENUE, 0.0, fixed_cost),
                        ],
                    )
            else:
                # Baseline external informal daily income for non-intervention workers
                for h in humans:
                    if 18 <= getattr(h.demographics, "age", 30) <= 64 and rng.random() < 0.45:
                        earn = round(float(rng.uniform(4.0, 9.0)), 2)
                        h.physical_state.money = round(h.physical_state.money + earn, 2)
                        totals["household_income_earned_usd"] += earn
                        ledger.record_transaction(
                            concept=TransactionConcept.WAGE_PAYMENT,
                            originating_domain="labor_market",
                            description="Jornal/ingreso diario de base",
                            tick=tick_base,
                            entries=[
                                TransactionEntry("external_employer_pool", "external_employer_pool", AccountType.EXPENSE, earn, 0.0),
                                TransactionEntry("external_employer_pool_cash", "external_employer_pool", AccountType.ASSET_CASH, 0.0, earn),
                                TransactionEntry(f"cash_{h.uid}", str(h.uid), AccountType.ASSET_CASH, earn, 0.0),
                                TransactionEntry(f"rev_{h.uid}", str(h.uid), AccountType.REVENUE, 0.0, earn),
                            ],
                        )

            # 2. Agent independent commercial visit decisions (CommercialEngine.execute_visit)
            target_est = commerce.get_establishment(target_est_id) if include_intervention and is_commercial else None
            price_premium = max(0.0, (spec.unit_price_usd - avg_comp_price) / max(0.5, avg_comp_price))
            comp_divert_prob = min(0.45, 0.12 + 0.04 * comp_count + 0.10 * price_premium)
            for h in humans:
                # Decide hour and whether agent passes by / visits a business
                visit_hour = int(rng.integers(6, 21))
                # Friction and hunger affect visit probability; passersby are NOT guaranteed buyers
                pass_prob = min(0.85, (0.35 + 0.35 * context.accessibility_index) / max(1.0, friction * 0.85))
                if rng.random() > pass_prob:
                    continue

                if target_est is not None:
                    # Closed hours must NOT be counted as active establishment visits
                    if not target_est.is_open_at_hour(visit_hour):
                        totals["closed_hour_passersby"] += 1
                        continue

                    # Competitive market diversion: some passersby choose existing OSM/local competitors
                    if comp_count > 0 and rng.random() < comp_divert_prob:
                        comp_id = f"osm_comp_{int(rng.integers(0, comp_count))}"
                        comp_intent = VisitIntent.DINE if float(h.physical_state.money) >= 2.0 else VisitIntent.COMPARE_PRICES
                        comp_out = commerce.execute_visit(
                            agent=h,
                            establishment_id=comp_id,
                            intent=comp_intent,
                            current_hour=visit_hour,
                        )
                        if comp_out.purchased and comp_out.total_spent_usd > 0:
                            c_spent = round(comp_out.total_spent_usd, 2)
                            seg_comp_rev += c_spent
                            ledger.record_transaction(
                                concept=TransactionConcept.FOOD_PURCHASE_CASH,
                                originating_domain="commercial",
                                description=f"Consumo en competidor {comp_id}",
                                tick=tick_base,
                                entries=[
                                    TransactionEntry(f"cash_{h.uid}", str(h.uid), AccountType.ASSET_CASH, 0.0, c_spent),
                                    TransactionEntry(f"exp_{h.uid}", str(h.uid), AccountType.EXPENSE, c_spent, 0.0),
                                    TransactionEntry(f"cash_{comp_id}", comp_id, AccountType.ASSET_CASH, c_spent, 0.0),
                                    TransactionEntry(f"rev_{comp_id}", comp_id, AccountType.REVENUE, 0.0, c_spent),
                                ],
                            )
                        continue

                    # Bounded rationality + hourly capacity check
                    h_money = float(h.physical_state.money)
                    h_hunger = float(h.physical_state.hunger)
                    cur_occ = hourly_occ.get(visit_hour, 0)
                    if cur_occ >= target_est.capacity:
                        totals["capacity_rejected_visits"] += 1
                        intent = VisitIntent.BROWSE
                    elif h_money < spec.unit_price_usd * 1.1:
                        intent = VisitIntent.COMPARE_PRICES
                    elif spec.category in (InterventionCategory.PUPUSERIA, InterventionCategory.RESTAURANT):
                        if h_hunger >= 0.28 and h_money >= spec.unit_price_usd + 1.5 and rng.random() < 0.68:
                            intent = VisitIntent.DINE
                        else:
                            intent = VisitIntent.BROWSE if rng.random() < 0.6 else VisitIntent.COMPARE_PRICES
                    else:
                        intent = VisitIntent.PURCHASE if rng.random() < 0.58 else VisitIntent.BROWSE

                    if cur_occ < target_est.capacity:
                        hourly_occ[visit_hour] = cur_occ + 1

                    outcome = commerce.execute_visit(
                        agent=h,
                        establishment_id=target_est_id,
                        intent=intent,
                        current_hour=visit_hour,
                    )
                    seg_visitors += 1
                    unique_visitor_uids.add(str(h.uid))
                    if outcome.purchased and outcome.total_spent_usd > 0:
                        seg_purchasers += 1
                        unique_buyer_uids.add(str(h.uid))
                        spent = round(outcome.total_spent_usd, 2)
                        if enterprise is not None:
                            enterprise.cash_reserve = round(enterprise.cash_reserve + spent, 2)
                        seg_rev += spent
                        ledger.record_transaction(
                            concept=TransactionConcept.FOOD_PURCHASE_CASH,
                            originating_domain="commercial",
                            description=f"Consumo en {spec.name}",
                            tick=tick_base,
                            entries=[
                                TransactionEntry(f"cash_{h.uid}", str(h.uid), AccountType.ASSET_CASH, 0.0, spent),
                                TransactionEntry(f"exp_{h.uid}", str(h.uid), AccountType.EXPENSE, spent, 0.0),
                                TransactionEntry(f"cash_{target_est_id}", target_est_id, AccountType.ASSET_CASH, spent, 0.0),
                                TransactionEntry(f"rev_{target_est_id}", target_est_id, AccountType.REVENUE, 0.0, spent),
                            ],
                        )
                        totals["agent_experience_log"][str(h.uid)] = (
                            f"Compré en {spec.name} por ${spent:.2f} (saldo restante ${h.physical_state.money:.2f})."
                        )
                    else:
                        seg_browsers += 1
                        totals["agent_experience_log"][str(h.uid)] = (
                            f"Visité o observé {spec.name} sin comprar ({outcome.reasoning})."
                        )

                    # Replenish hunger partially across multi-day segment cycle
                    h.physical_state.hunger = min(0.95, float(h.physical_state.hunger) + 0.15)
                else:
                    # Competitors serve demand when target business isn't active
                    comp_out = commerce.execute_visit(
                        agent=h,
                        establishment_id="osm_comp_0",
                        intent=VisitIntent.DINE if h.physical_state.money >= 2.0 else VisitIntent.COMPARE_PRICES,
                        current_hour=visit_hour,
                    )
                    if comp_out.purchased:
                        seg_comp_rev += comp_out.total_spent_usd

            # Scale commercial flows over days_w & catchment scale while keeping raw cohort figures explicit
            scale_mult = round(days_w * pop_scale, 2)
            scaled_rev = round(seg_rev * scale_mult, 2)
            scaled_cogs = round(scaled_rev * spec.unit_cost_ratio, 2)
            totals["raw_cohort_visitors"] += seg_visitors
            totals["raw_cohort_browsers"] += seg_browsers
            totals["raw_cohort_purchasers"] += seg_purchasers
            totals["raw_cohort_revenue_usd"] += round(seg_rev, 2)
            totals["total_visitors"] += round(seg_visitors * scale_mult, 1)
            totals["total_browsers_without_purchase"] += round(seg_browsers * scale_mult, 1)
            totals["total_purchasers"] += round(seg_purchasers * scale_mult, 1)
            totals["total_revenue_usd"] += scaled_rev
            totals["total_cogs_usd"] += scaled_cogs
            totals["total_wages_paid_usd"] += seg_wages
            totals["competitor_sales_usd"] += round(seg_comp_rev * scale_mult, 2)

            # 3. Educational & Healthcare demand evaluation via PublicServiceCapacityEngine
            public_services.reset_daily_queues()
            is_edu_focus = (
                spec.category in (InterventionCategory.SCHOOL, InterventionCategory.TRAINING_CENTER, InterventionCategory.PUBLIC_TRANSPORT)
                or temporal.seasonal_profile == "SCHOOL_CALENDAR"
            )
            school_active_now = bool(seg.get("school_active", True))
            if school_active_now or is_edu_focus:
                school_age = [h for h in humans if 5 <= getattr(h.demographics, "age", 30) <= 18]
                school_demand_total = max(1, int(round((len(school_age) or 4) * pop_scale * 1.5)))
                if include_intervention and service_cat == ServiceCategory.EDUCATION:
                    _, srv_new, rem_dem = public_services.submit_service_demand(target_facility_id, school_demand_total)
                    _, srv_old, unmet_edu = public_services.submit_service_demand("existing_district_edu", rem_dem)
                    srv_edu = srv_new + srv_old
                else:
                    _, srv_edu, unmet_edu = public_services.submit_service_demand("existing_district_edu", school_demand_total)

                low_cash_households = sum(1 for h in humans if h.physical_state.money < 12.0)
                agri_pull = float(seg["agri_demand"]) if not context.is_urban else 0.75
                transport_boost = 0.35 if (include_intervention and spec.category == InterventionCategory.PUBLIC_TRANSPORT) else 0.0
                dropout_risk = max(
                    0.02,
                    min(
                        0.65,
                        (low_cash_households / max(1, len(humans))) * 0.35 * friction * agri_pull
                        + (unmet_edu / max(1, school_demand_total)) * 0.30
                        - transport_boost,
                    ),
                )
                totals["edu_served"] += srv_edu * days_w
                totals["edu_unmet"] += unmet_edu * days_w
                totals["school_dropout_risk_events"] += dropout_risk
                totals["school_eval_segments"] += 1
            else:
                # Non-educational simulation during academic vacation month (e.g. January): do not fabricate school overflow
                unmet_edu = 0
                dropout_risk = 0.0

            hlt_demand = max(1, int(round(len(humans) * 0.25 * pop_scale * friction)))
            if include_intervention and service_cat == ServiceCategory.HEALTHCARE:
                _, srv_h1, rem_h = public_services.submit_service_demand(target_facility_id, hlt_demand)
                _, srv_h2, unmet_hlt = public_services.submit_service_demand("existing_district_hlt", rem_h)
                srv_hlt = srv_h1 + srv_h2
            else:
                _, srv_hlt, unmet_hlt = public_services.submit_service_demand("existing_district_hlt", hlt_demand)

            totals["hlt_served"] += srv_hlt * days_w
            totals["hlt_unmet"] += unmet_hlt * days_w

            return {
                "visitors": seg_visitors,
                "purchasers": seg_purchasers,
                "browsers_no_buy": seg_browsers,
                "segment_revenue_usd": round(scaled_rev, 2),
                "segment_wages_usd": round(seg_wages, 2),
                "edu_unmet_daily": unmet_edu,
                "hlt_unmet_daily": unmet_hlt,
                "dropout_risk_score": round(dropout_risk, 3),
            }

        exec_meta = temporal_controller.execute_with_checkpoints(
            scenario_id=spec.intervention_id,
            spec=temporal,
            step_fn=_simulate_segment,
            cancel_event=cancel_event,
        )

        # Ledger conservation verification ($0.0000 discrepancy)
        cons_ok, cons_msg, cons_metrics = ledger.verify_accounting_conservation()
        cons = {
            "conservation_passed": cons_ok,
            "message": cons_msg,
            "total_transactions": len(ledger.transactions),
            **cons_metrics,
        }

        # Update enterprise solvency status honestly if obligated payroll or fixed costs went unpaid
        total_unpaid = round(totals["unpaid_wages_usd"] + totals["unpaid_fixed_costs_usd"], 2)
        if enterprise is not None:
            if total_unpaid > 50.0 or enterprise.cash_reserve < -50.0:
                enterprise.status = BusinessStatus.INSOLVENT
            elif total_unpaid > 0.0 or enterprise.cash_reserve < 20.0:
                enterprise.status = BusinessStatus.DISTRESSED

        # Honest operating P&L deducts ALL obligated payroll & fixed overhead (never omitting unpaid defaults)
        net_profit = round(
            totals["total_revenue_usd"]
            - totals["total_cogs_usd"]
            - totals["obligated_wages_usd"]
            - totals["obligated_fixed_costs_usd"],
            2,
        )
        edu_segs = max(1, int(totals["school_eval_segments"]))
        avg_dropout_risk = (
            round(totals["school_dropout_risk_events"] / edu_segs, 4)
            if totals["school_eval_segments"] > 0
            else None
        )
        total_edu_demand = totals["edu_served"] + totals["edu_unmet"]
        school_att = round(totals["edu_served"] / total_edu_demand, 4) if total_edu_demand > 0 else None

        return {
            "spec": spec,
            "include_intervention": include_intervention,
            "active_engines": active_engines,
            "temporal_execution": exec_meta,
            "totals": {
                "total_visitors": round(totals["total_visitors"], 1),
                "total_browsers_without_purchase": round(totals["total_browsers_without_purchase"], 1),
                "total_purchasers": round(totals["total_purchasers"], 1),
                "raw_cohort_visitors": int(totals["raw_cohort_visitors"]),
                "raw_cohort_unique_visitors": len(unique_visitor_uids),
                "raw_cohort_browsers": int(totals["raw_cohort_browsers"]),
                "raw_cohort_purchasers": int(totals["raw_cohort_purchasers"]),
                "raw_cohort_unique_buyers": len(unique_buyer_uids),
                "raw_cohort_repeat_visits": max(0, int(totals["raw_cohort_visitors"]) - len(unique_visitor_uids)),
                "raw_cohort_revenue_usd": round(totals["raw_cohort_revenue_usd"], 2),
                "closed_hour_passersby": int(totals["closed_hour_passersby"]),
                "capacity_rejected_visits": int(totals["capacity_rejected_visits"]),
                "expansion_pop_scale": round(pop_scale, 4),
                "conversion_rate": round(
                    totals["total_purchasers"] / max(1.0, totals["total_visitors"]), 4
                ),
                "total_revenue_usd": round(totals["total_revenue_usd"], 2),
                "total_cogs_usd": round(totals["total_cogs_usd"], 2),
                "total_wages_paid_usd": round(totals["total_wages_paid_usd"], 2),
                "obligated_wages_usd": round(totals["obligated_wages_usd"], 2),
                "unpaid_wages_usd": round(totals["unpaid_wages_usd"], 2),
                "total_fixed_costs_usd": round(totals["total_fixed_costs_usd"], 2),
                "obligated_fixed_costs_usd": round(totals["obligated_fixed_costs_usd"], 2),
                "unpaid_fixed_costs_usd": round(totals["unpaid_fixed_costs_usd"], 2),
                "net_operating_profit_usd": net_profit,
                "enterprise_closing_cash_usd": round(enterprise.cash_reserve, 2) if enterprise else 0.0,
                "enterprise_status": enterprise.status.value if enterprise else "not_applicable",
                "competitor_sales_usd": round(totals["competitor_sales_usd"], 2),
                "edu_served_person_days": round(totals["edu_served"], 1),
                "edu_unmet_person_days": round(totals["edu_unmet"], 1),
                "school_attendance_rate": school_att,
                "avg_school_dropout_risk": avg_dropout_risk,
                "hlt_served_person_days": round(totals["hlt_served"], 1),
                "hlt_unmet_person_days": round(totals["hlt_unmet"], 1),
                "household_income_earned_usd": round(totals["household_income_earned_usd"], 2),
                "mobility_friction_peak": round(totals["shock_mobility_penalty"], 3),
                "hired_workers_count": len(hired_workers),
            },
            "agent_experience_log": totals["agent_experience_log"],
            "ledger_conservation": cons,
            "commerce_engine": commerce,
            "labor_engine": labor,
            "public_services_engine": public_services,
        }
