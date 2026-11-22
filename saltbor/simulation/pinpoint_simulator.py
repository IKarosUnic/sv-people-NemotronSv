"""Ultra-Precise Pinpoint Map Placement & Micro-Spatial Simulator (Phase 1.18+).

Allows any user to click an exact WGS84 coordinate `(lat, lon)` on the map of
El Salvador and place a custom, highly specific entity (business, pupusería,
store, pharmacy, clinic, school, transit stop, or street blockage/construction)
with custom name, prices, capacity, hours, capital, and radius.

Automatically:
1. Queries real OpenStreetMap features (`geography.sqlite`) around `(lat, lon)`
   to identify the exact street corner, nearby POIs, and local competitors.
2. Injects the entity into the live `SimulationRunner` (`WorldHumanInteractionEngine`,
   `CommercialEngine`, `EditableWorldEngine` Layer D, or `TransportationEngine`).
3. Simulates micro-catchment demand, price competition, and double-entry
   conserved cash flows (`VerifiableEconomicLedger`, $0.00 discrepancy).
"""

from __future__ import annotations

import math
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from saltbor.domain.models import FeatureGeometryType, WorldLayerType
from saltbor.economy.commerce.commercial_engine import (
    CommercialEstablishment,
    CommercialProduct,
    EstablishmentType,
)
from saltbor.territory.economic_ledger import (
    AccountType,
    TransactionConcept,
    TransactionEntry,
    VerifiableEconomicLedger,
)
from saltbor.territory.territory_catalog import TerritoryCatalogService
from saltbor.world.locations.capabilities import (
    PlaceCapability,
    PlaceCategory,
    PlaceProfile,
    PlaceService,
)


CATEGORY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "pupuseria": {
        "icon": "🫓",
        "label": "Pupusería y Comedor",
        "place_category": PlaceCategory.PUPUSERIA,
        "est_type": EstablishmentType.COMEDOR_PUPUSERIA,
        "default_name": "Pupusería El Comal",
        "default_price_usd": 0.90,
        "reference_market_price_usd": 0.95,
        "unit_cost_ratio": 0.52,
        "default_capacity": 24,
        "default_capital_usd": 150.0,
        "daily_fixed_cost_usd": 6.0,
        "opening_hour": 6,
        "closing_hour": 21,
        "product_id": "pupusa_revuelta",
        "product_name": "Orden de Pupusas / Comida",
    },
    "tienda_pulperia": {
        "icon": "🏪",
        "label": "Tienda / Pulpería de Barrio",
        "place_category": PlaceCategory.STORE,
        "est_type": EstablishmentType.PULPERIA,
        "default_name": "Tienda y Abarrotería La Bendición",
        "default_price_usd": 1.10,
        "reference_market_price_usd": 1.15,
        "unit_cost_ratio": 0.68,
        "default_capacity": 12,
        "default_capital_usd": 200.0,
        "daily_fixed_cost_usd": 4.0,
        "opening_hour": 6,
        "closing_hour": 21,
        "product_id": "canasta_basica_diaria",
        "product_name": "Víveres y Granos Básicos (lb)",
    },
    "farmacia": {
        "icon": "💊",
        "label": "Farmacia / Botiquín Comunitario",
        "place_category": PlaceCategory.PHARMACY,
        "est_type": EstablishmentType.HEALTH_CLINIC,
        "default_name": "Farmacia San Rafael",
        "default_price_usd": 3.50,
        "reference_market_price_usd": 4.00,
        "unit_cost_ratio": 0.60,
        "default_capacity": 15,
        "default_capital_usd": 350.0,
        "daily_fixed_cost_usd": 8.0,
        "opening_hour": 7,
        "closing_hour": 20,
        "product_id": "medicamento_esencial",
        "product_name": "Medicamento Básico / Analgésico",
    },
    "taller": {
        "icon": "🔧",
        "label": "Taller Artesanal / Mecánico",
        "place_category": PlaceCategory.WORKSHOP,
        "est_type": EstablishmentType.ARTISAN_WORKSHOP,
        "default_name": "Taller El Maestro",
        "default_price_usd": 5.00,
        "reference_market_price_usd": 5.50,
        "unit_cost_ratio": 0.45,
        "default_capacity": 10,
        "default_capital_usd": 250.0,
        "daily_fixed_cost_usd": 5.5,
        "opening_hour": 7,
        "closing_hour": 18,
        "product_id": "servicio_reparacion",
        "product_name": "Reparación / Obra Artesanal",
    },
    "clinica": {
        "icon": "🏥",
        "label": "Puesto / Unidad de Salud",
        "place_category": PlaceCategory.CLINIC,
        "est_type": EstablishmentType.HEALTH_CLINIC,
        "default_name": "Puesto Comunitario de Salud",
        "default_price_usd": 2.00,
        "reference_market_price_usd": 3.00,
        "unit_cost_ratio": 0.40,
        "default_capacity": 35,
        "default_capital_usd": 500.0,
        "daily_fixed_cost_usd": 12.0,
        "opening_hour": 7,
        "closing_hour": 17,
        "product_id": "consulta_medica",
        "product_name": "Consulta y Atención Primaria",
    },
    "escuela": {
        "icon": "🎓",
        "label": "Centro Escolar / Aula Técnica",
        "place_category": PlaceCategory.SCHOOL,
        "est_type": EstablishmentType.PULPERIA,
        "default_name": "Centro Escolar Comunitario",
        "default_price_usd": 0.50,
        "reference_market_price_usd": 1.00,
        "unit_cost_ratio": 0.50,
        "default_capacity": 60,
        "default_capital_usd": 400.0,
        "daily_fixed_cost_usd": 10.0,
        "opening_hour": 7,
        "closing_hour": 16,
        "product_id": "capacitacion_escolar",
        "product_name": "Matrícula / Refrigerio Escolar",
    },
    "bloqueo_obra_vial": {
        "icon": "🚧",
        "label": "Bloqueo / Obra Vial en Calle Exacta",
        "place_category": PlaceCategory.STREET,
        "est_type": EstablishmentType.PULPERIA,
        "default_name": "Cierre Vial / Reparación de Calle",
        "default_price_usd": 0.0,
        "reference_market_price_usd": 1.0,
        "unit_cost_ratio": 0.0,
        "default_capacity": 0,
        "default_capital_usd": 120.0,
        "daily_fixed_cost_usd": 15.0,
        "opening_hour": 0,
        "closing_hour": 24,
        "product_id": "obra_vial",
        "product_name": "Tramo Vial Intervenido",
    },
}


class PinpointPlacementSimulator:
    """Handles exact coordinate `(lat, lon)` inspection, entity placement, and micro-simulation."""

    def __init__(self, geography_db_path: str = "saltbor/datasets/gis/ingested/geography.sqlite") -> None:
        self.catalog = TerritoryCatalogService()
        self.geography_db_path = geography_db_path

    @staticmethod
    def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Compute exact spherical Haversine distance in meters between two WGS84 coordinates."""
        r_m = 6371000.0
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
        return round(2.0 * r_m * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a))), 1)

    def _find_nearest_district(self, lat: float, lon: float) -> Tuple[Any, float]:
        best_dist = None
        best_km = 999999.0
        for d in self.catalog.districts.values():
            km = self.catalog.haversine_km(lat, lon, d.latitude, d.longitude)
            if km < best_km:
                best_km = km
                best_dist = d
        return best_dist, round(best_km, 2)

    def _query_nearby_osm_features(self, lat: float, lon: float, radius_m: float = 400.0) -> Dict[str, Any]:
        """Query real OpenStreetMap features in `geography.sqlite` around `(lat, lon)`."""
        delta_deg = max(0.002, (radius_m / 111000.0) * 1.35)
        min_lat, max_lat = lat - delta_deg, lat + delta_deg
        min_lon, max_lon = lon - delta_deg, lon + delta_deg

        nearest_road = None
        nearest_road_dist_m = 999999.0
        nearby_pois: List[Dict[str, Any]] = []
        roads_count = 0

        try:
            conn = sqlite3.connect(self.geography_db_path)
            conn.row_factory = sqlite3.Row
            road_rows = conn.execute(
                """
                SELECT feature_id, layer, name, feature_class, lat, lon
                FROM geographic_features
                WHERE layer = 'roads' AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
                LIMIT 150
                """,
                (min_lat, max_lat, min_lon, max_lon),
            ).fetchall()
            poi_rows = conn.execute(
                """
                SELECT feature_id, layer, name, feature_class, lat, lon
                FROM geographic_features
                WHERE layer IN ('pois', 'places', 'buildings') AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
                LIMIT 100
                """,
                (min_lat, max_lat, min_lon, max_lon),
            ).fetchall()
            conn.close()

            nearest_named_road = None
            nearest_named_dist_m = 999999.0

            for r in road_rows:
                d_m = self.haversine_m(lat, lon, float(r["lat"]), float(r["lon"]))
                if d_m > radius_m * 1.5:
                    continue
                roads_count += 1
                fname = str(r["name"] or "").strip()
                fclass = str(r["feature_class"] or "")
                if fname and d_m < nearest_named_dist_m:
                    nearest_named_dist_m = d_m
                    nearest_named_road = fname
                if d_m < nearest_road_dist_m:
                    nearest_road_dist_m = d_m
                    nearest_road = fname or f"Vía OSM ({fclass})"

            if nearest_named_road:
                nearest_road = nearest_named_road
                nearest_road_dist_m = nearest_named_dist_m

            for r in poi_rows:
                d_m = self.haversine_m(lat, lon, float(r["lat"]), float(r["lon"]))
                if d_m > radius_m * 1.5:
                    continue
                fname = str(r["name"] or "").strip()
                fclass = str(r["feature_class"] or "")
                if fname:
                    nearby_pois.append({
                        "name": fname,
                        "class": fclass,
                        "distance_m": d_m,
                    })
        except Exception:
            pass

        nearby_pois.sort(key=lambda x: x["distance_m"])
        return {
            "nearest_street": nearest_road or "Calle / Camino Vecinal OSM",
            "nearest_street_distance_m": round(nearest_road_dist_m, 1) if nearest_road else 15.0,
            "osm_road_segments_in_radius": roads_count,
            "nearby_osm_pois": nearby_pois[:6],
        }

    def inspect_point(
        self,
        lat: float,
        lon: float,
        radius_m: float = 400.0,
        live_runner: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Return micro-spatial context at exact `(lat, lon)` coordinate."""
        district, dist_km = self._find_nearest_district(lat, lon)
        muni = self.catalog.municipalities.get(district.municipality_id) if district else None
        dept = self.catalog.departments.get(district.department_code) if district else None
        osm_ctx = self._query_nearby_osm_features(lat, lon, radius_m=radius_m)
        hazard = self.catalog.get_topographic_hazard_profile(district.name if district else "San Salvador")

        nearby_places: List[Dict[str, Any]] = []
        nearby_agents_count = 0
        avg_agent_cash = 25.0

        if live_runner is not None:
            wi = getattr(live_runner, "world_interaction", None)
            if wi and hasattr(wi, "places"):
                for p in wi.places.values():
                    plat, plon = p.wgs84_coords
                    dm = self.haversine_m(lat, lon, plat, plon)
                    if dm <= radius_m * 2.0:
                        nearby_places.append({
                            "place_id": p.place_id,
                            "name": p.name,
                            "category": p.category.value,
                            "distance_m": dm,
                            "occupants": len(p.current_occupants),
                        })
            nearby_places.sort(key=lambda x: x["distance_m"])

            humans = live_runner.population.get_all()
            if humans:
                avg_agent_cash = round(
                    sum(float(h.physical_state.money) for h in humans) / len(humans),
                    2,
                )
                nearby_agents_count = len(humans)

        return {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "radius_m": radius_m,
            "district_id": district.district_id if district else "SS",
            "district_name": district.name if district else "San Salvador",
            "municipality_name": muni.name if muni else "San Salvador Centro",
            "department_name": dept.name if dept else "San Salvador",
            "distance_to_district_center_km": dist_km,
            "nearest_street_osm": osm_ctx["nearest_street"],
            "nearest_street_distance_m": osm_ctx["nearest_street_distance_m"],
            "osm_road_segments_in_radius": osm_ctx["osm_road_segments_in_radius"],
            "nearby_osm_pois": osm_ctx["nearby_osm_pois"],
            "nearby_simulation_places": nearby_places[:6],
            "active_population_sample": nearby_agents_count,
            "average_local_purchasing_power_usd": avg_agent_cash,
            "relief_class": hazard["relief_class"],
            "elevation_m": hazard["elevation_m"],
            "tobler_walking_factor": hazard["tobler_walking_speed_factor"],
        }

    def _parse_specific_description(
        self,
        description: str,
        category_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Extract ultra-specific parameters (category, name, price, capital, capacity, hours) from Spanish text."""
        low = description.lower()

        if category_hint and category_hint in CATEGORY_DEFAULTS:
            cat_key = category_hint
        elif any(w in low for w in ["pupus", "comedor", "cafet", "restaurante", "merendero"]):
            cat_key = "pupuseria"
        elif any(w in low for w in ["farmacia", "botiquin", "botiquín", "medicina"]):
            cat_key = "farmacia"
        elif any(w in low for w in ["clinica", "clínica", "unidad de salud", "hospital", "consultorio"]):
            cat_key = "clinica"
        elif any(w in low for w in ["escuela", "colegio", "aula", "kinder", "institut"]):
            cat_key = "escuela"
        elif any(w in low for w in ["taller", "carpinter", "mecanic", "mecánic", "artesan", "panader"]):
            cat_key = "taller"
        elif any(w in low for w in ["bloqueo", "cerrar calle", "derrumbe", "reparacion vial", "obra vial", "bacheo"]):
            cat_key = "bloqueo_obra_vial"
        else:
            cat_key = "tienda_pulperia"

        defaults = CATEGORY_DEFAULTS[cat_key]

        # Extract custom quoted name if present: e.g. llamada "El Comalito" or 'La Bendición'
        name_match = re.search(r"['\"]([^'\"]{2,40})['\"]", description)
        custom_name = name_match.group(1).strip() if name_match else None

        # Extract dollar amounts: price vs capital
        dollar_matches = [float(x) for x in re.findall(r"\$\s*(\d+(?:\.\d+)?)", description)]
        price_val = None
        capital_val = None
        for val in dollar_matches:
            if val <= 25.0 and price_val is None:
                price_val = val
            elif val > 25.0 and capital_val is None:
                capital_val = val

        # Extract capacity (e.g. "25 personas", "aforo 30")
        cap_match = re.search(r"(\d+)\s*(?:personas|clientes|lugares|asientos|estudiantes|pacientes)", low)
        capacity_val = int(cap_match.group(1)) if cap_match else None

        return {
            "category_key": cat_key,
            "parsed_name": custom_name,
            "parsed_price_usd": price_val,
            "parsed_capital_usd": capital_val,
            "parsed_capacity": capacity_val,
            "defaults": defaults,
        }

    def place_and_simulate(
        self,
        lat: float,
        lon: float,
        description: str = "Abrir una pupusería llamada 'El Comal de Oro' con pupusas a $0.85",
        category: Optional[str] = None,
        custom_name: Optional[str] = None,
        unit_price_usd: Optional[float] = None,
        initial_capital_usd: Optional[float] = None,
        capacity: Optional[int] = None,
        opening_hour: Optional[int] = None,
        closing_hour: Optional[int] = None,
        catchment_radius_m: float = 400.0,
        days: int = 7,
        live_runner: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Place a specific entity at exact `(lat, lon)`, inject into live runner, and simulate micro-outcomes."""
        parsed = self._parse_specific_description(description, category_hint=category)
        cat_key = parsed["category_key"]
        defs = parsed["defaults"]

        point_ctx = self.inspect_point(lat, lon, radius_m=catchment_radius_m, live_runner=live_runner)
        street_label = point_ctx["nearest_street_osm"]

        final_name = (
            custom_name
            or parsed["parsed_name"]
            or f"{defs['default_name']} ({street_label})"
        )
        final_price = (
            float(unit_price_usd)
            if unit_price_usd is not None
            else (parsed["parsed_price_usd"] if parsed["parsed_price_usd"] is not None else float(defs["default_price_usd"]))
        )
        final_capital = (
            float(initial_capital_usd)
            if initial_capital_usd is not None
            else (parsed["parsed_capital_usd"] if parsed["parsed_capital_usd"] is not None else float(defs["default_capital_usd"]))
        )
        final_capacity = (
            int(capacity)
            if capacity is not None
            else (parsed["parsed_capacity"] if parsed["parsed_capacity"] is not None else int(defs["default_capacity"]))
        )
        final_open = int(opening_hour) if opening_hour is not None else int(defs["opening_hour"])
        final_close = int(closing_hour) if closing_hour is not None else int(defs["closing_hour"])
        sim_days = max(1, min(60, int(days)))

        entity_id = f"pin_{cat_key}_{uuid4().hex[:8]}"

        # ---------------------------------------------------------------------
        # 1. Inject into Live SimulationRunner (Layer D + World Places + Commerce / Traffic)
        # ---------------------------------------------------------------------
        injected_into_runner = False
        if live_runner is not None:
            injected_into_runner = True
            # Layer D non-destructive feature
            de = getattr(live_runner, "domain_engine", None)
            if de and hasattr(de, "world_engine"):
                de.world_engine.create_feature(
                    layer=WorldLayerType.LAYER_D_INTERVENTIONS,
                    geometry_type=FeatureGeometryType.POINT,
                    coordinates=[round(lon, 6), round(lat, 6)],
                    name=final_name,
                    category=cat_key,
                    properties={
                        "unit_price_usd": final_price,
                        "initial_capital_usd": final_capital,
                        "capacity": final_capacity,
                        "opening_hour": final_open,
                        "closing_hour": final_close,
                        "catchment_radius_m": catchment_radius_m,
                        "street": street_label,
                        "district": point_ctx["district_name"],
                    },
                    feature_id=entity_id,
                )

            if cat_key == "bloqueo_obra_vial":
                iw = getattr(live_runner, "integrated_world", None)
                if iw and hasattr(iw, "transportation"):
                    iw.transportation.register_blockage(
                        cause=final_name,
                        location_name=f"{street_label} ({point_ctx['district_name']})",
                        lat=lat,
                        lon=lon,
                        start_tick=int(live_runner.clock.current_tick),
                        duration_ticks=sim_days * 96,
                        radius_m=min(300.0, max(30.0, catchment_radius_m * 0.35)),
                    )
            else:
                # Register PlaceProfile in WorldHumanInteractionEngine
                wi = getattr(live_runner, "world_interaction", None)
                if wi and hasattr(wi, "register_place"):
                    place_prof = PlaceProfile(
                        place_id=entity_id,
                        name=final_name,
                        category=defs["place_category"],
                        capabilities=(
                            PlaceCapability.IDENTIFIABLE
                            | PlaceCapability.NAVIGABLE
                            | PlaceCapability.VISITABLE
                            | PlaceCapability.SCHEDULED
                            | PlaceCapability.SERVICE_PROVIDER
                            | PlaceCapability.INVENTORY_STORAGE
                            | PlaceCapability.SOCIAL_INTERACTION
                            | PlaceCapability.ECONOMIC_CONSEQUENCES
                        ),
                        wgs84_coords=(round(lat, 6), round(lon, 6)),
                        capacity=final_capacity,
                        opening_hour=final_open,
                        closing_hour=final_close,
                        operating_cost_per_day=float(defs["daily_fixed_cost_usd"]),
                        cash_box_usd=final_capital,
                        inventory={defs["product_id"]: max(50, final_capacity * 6)},
                        price_catalog={defs["product_id"]: final_price},
                        services={
                            defs["product_id"]: PlaceService(
                                service_id=defs["product_id"],
                                name=defs["product_name"],
                                cost_usd=final_price,
                                duration_ticks=2,
                                hunger_reduction=0.45 if cat_key in ("pupuseria", "tienda_pulperia") else 0.0,
                                health_recovery=0.35 if cat_key in ("farmacia", "clinica") else 0.0,
                                max_simultaneous_clients=max(2, final_capacity // 2),
                            )
                        },
                    )
                    wi.register_place(place_prof)

                # Register CommercialEstablishment in CommercialEngine
                ce = getattr(live_runner, "commerce_engine", None)
                if ce and hasattr(ce, "register_establishment"):
                    ce.register_establishment(
                        CommercialEstablishment(
                            establishment_id=entity_id,
                            name=final_name,
                            establishment_type=defs["est_type"],
                            location_id=entity_id,
                            is_verified_real=False,
                            opening_hours=(final_open, final_close),
                            operating_cost_per_day=float(defs["daily_fixed_cost_usd"]),
                            cash_box_usd=final_capital,
                            catalog={
                                defs["product_id"]: CommercialProduct(
                                    product_id=defs["product_id"],
                                    name=defs["product_name"],
                                    category="custom_pinpoint",
                                    unit_price_usd=final_price,
                                    current_stock=float(max(80, final_capacity * 8)),
                                    unit_label="unidad",
                                )
                            },
                        )
                    )

        # ---------------------------------------------------------------------
        # 2. Micro-Catchment Demand, Competition & Conserved Ledger Simulation
        # ---------------------------------------------------------------------
        ledger = VerifiableEconomicLedger()
        # Record initial capital
        ledger.initial_currency_pool = final_capital + 5000.0  # Local neighborhood consumer pool + business capital

        ref_price = max(0.25, float(defs["reference_market_price_usd"]))
        price_ratio = final_price / ref_price if final_price > 0 else 1.0
        # Price elasticity: lower price attracts more customers; excessive price loses customers
        price_attraction_factor = max(0.25, min(1.85, 1.0 + 0.75 * (1.0 - price_ratio)))

        # Street connectivity & POI density bonus
        road_bonus = min(1.35, 0.85 + 0.08 * min(6, point_ctx["osm_road_segments_in_radius"]))
        hours_open = max(1, final_close - final_open)
        hours_factor = min(1.25, hours_open / 12.0)

        # Competition penalty from nearby places of same category within catchment radius
        same_cat_competitors = [
            p for p in point_ctx["nearby_simulation_places"]
            if p["category"] == defs["place_category"].value and p["place_id"] != entity_id
        ]
        competition_factor = max(0.50, 1.0 - 0.15 * len(same_cat_competitors))

        base_daily_visitors = max(8.0, min(120.0, (catchment_radius_m / 20.0) * point_ctx["tobler_walking_factor"]))
        daily_customers = int(
            round(
                min(
                    final_capacity * max(1, hours_open // 2),
                    base_daily_visitors * price_attraction_factor * road_bonus * hours_factor * competition_factor,
                )
            )
        ) if cat_key != "bloqueo_obra_vial" else 0

        unit_cost = round(final_price * float(defs["unit_cost_ratio"]), 2)
        daily_fixed_cost = float(defs["daily_fixed_cost_usd"])

        cash_box = final_capital
        total_revenue = 0.0
        total_cogs = 0.0
        total_fixed = 0.0

        for day_idx in range(1, sim_days + 1):
            tick = day_idx * 96
            day_rev = round(daily_customers * final_price, 2)
            day_cogs = round(daily_customers * unit_cost, 2)
            day_fix = round(daily_fixed_cost, 2)

            if day_rev > 0:
                ledger.record_retail_food_purchase_cash(
                    buyer_id="vecinos_radio_peatonal",
                    tiendita_id=entity_id,
                    amount_usd=day_rev,
                    cost_of_goods_usd=day_cogs,
                    commodity=defs["product_id"],
                    quantity_lb=float(daily_customers),
                    tick=tick,
                )
                cash_box = round(cash_box + day_rev, 2)
                total_revenue = round(total_revenue + day_rev, 2)

            # Replenish stock from wholesale hub & pay daily operating cost
            day_outflow = round(day_cogs + day_fix, 2)
            if day_outflow > 0:
                paid_outflow = min(cash_box, day_outflow)
                if paid_outflow > 0:
                    ledger.record_transaction(
                        concept=TransactionConcept.WHOLESALE_PURCHASE,
                        originating_domain="pinpoint_micro_commerce",
                        description=f"Reposición de insumos y operación día {day_idx} en {final_name}",
                        tick=tick,
                        entries=[
                            TransactionEntry(f"{entity_id}_cash", entity_id, AccountType.ASSET_CASH, debit=0.0, credit=paid_outflow),
                            TransactionEntry(f"{entity_id}_op_expense", entity_id, AccountType.EXPENSE, debit=paid_outflow, credit=0.0),
                            TransactionEntry("proveedor_mayorista_cash", "proveedor_mayorista", AccountType.ASSET_CASH, debit=paid_outflow, credit=0.0),
                            TransactionEntry("proveedor_mayorista_rev", "proveedor_mayorista", AccountType.REVENUE, debit=0.0, credit=paid_outflow),
                        ],
                    )
                    cash_box = round(cash_box - paid_outflow, 2)
                total_cogs = round(total_cogs + day_cogs, 2)
                total_fixed = round(total_fixed + day_fix, 2)

        net_profit = round(total_revenue - (total_cogs + total_fixed), 2)
        roi_pct = round((net_profit / max(1.0, final_capital)) * 100.0, 1)
        all_balanced = all(tx.is_balanced for tx in ledger.transactions)

        if cat_key == "bloqueo_obra_vial":
            semaforo = "🟡 OBRA / BLOQUEO ACTIVO EN VÍA"
            resumen = (
                f"🚧 {final_name} colocado en coordenadas exactas ({lat:.6f}, {lon:.6f}) sobre "
                f"{street_label} ({point_ctx['district_name']}, {point_ctx['municipality_name']}) "
                f"durante {sim_days} días. Radio afectado: {catchment_radius_m:.0f}m. "
                f"Los transeúntes y vehículos en esa vía recalculan desvío automáticamente."
            )
        else:
            if net_profit > 0 and cash_box >= final_capital:
                semaforo = "🟢 UBICACIÓN RENTABLE Y SOLVENTE"
            elif cash_box > 20.0:
                semaforo = "🟡 PUNTO DE EQUILIBRIO / MARGEN AJUSTADO"
            else:
                semaforo = "🔴 RIESGO DE LIQUIDEZ EN ESTA UBICACIÓN"

            resumen = (
                f"{defs['icon']} '{final_name}' colocado en el punto exacto ({lat:.6f}, {lon:.6f}) — "
                f"frente a {street_label} ({point_ctx['district_name']}, {point_ctx['municipality_name']}) → {semaforo}. "
                f"En {sim_days} días a un precio de ${final_price:.2f} (horario {final_open:02d}:00–{final_close:02d}:00, "
                f"radio {catchment_radius_m:.0f}m): atrae ~{daily_customers} clientes/día, "
                f"vende ${total_revenue:.2f}, gasta ${total_cogs + total_fixed:.2f} en insumos/operación y "
                f"deja una ganancia neta de ${net_profit:+.2f} (Caja final: ${cash_box:.2f}, ROI: {roi_pct:+.1f}%)."
            )

        tarjetas = [
            {
                "icono": "📍",
                "titulo": "Punto Exacto y Calle OSM",
                "valor": f"{street_label}",
                "explicacion": f"WGS84 ({lat:.5f}, {lon:.5f}) · {point_ctx['district_name']} ({point_ctx['municipality_name']}).",
            },
            {
                "icono": "👥",
                "titulo": "Clientela y Competencia",
                "valor": f"{daily_customers} clientes/día",
                "explicacion": (
                    f"Radio {catchment_radius_m:.0f}m · {len(same_cat_competitors)} competidores directos · "
                    f"Precio ${final_price:.2f} (mercado ${ref_price:.2f})."
                ),
            },
            {
                "icono": "💵",
                "titulo": f"Resultado en {sim_days} Días",
                "valor": f"Ganancia ${net_profit:+.2f} | Caja ${cash_box:.2f}",
                "explicacion": f"Ventas: ${total_revenue:.2f} · Costos: ${total_cogs + total_fixed:.2f} (ROI {roi_pct:+.1f}%).",
            },
            {
                "icono": "⚖️",
                "titulo": "Auditoría Contable",
                "valor": "$0.00 discrepancia" if all_balanced else "Revisar",
                "explicacion": f"{len(ledger.transactions)} asientos de doble partida verificados e inyectado en Capa D.",
            },
        ]

        return {
            "status": "ok",
            "entity_id": entity_id,
            "injected_into_live_map": injected_into_runner,
            "titulo": f"{defs['icon']} {final_name}",
            "categoria": cat_key,
            "categoria_label": defs["label"],
            "coordenadas": {"lat": round(lat, 6), "lon": round(lon, 6)},
            "ubicacion_exacta": point_ctx,
            "parametros_especificos": {
                "nombre": final_name,
                "precio_unitario_usd": final_price,
                "precio_referencia_zona_usd": ref_price,
                "capital_inicial_usd": final_capital,
                "capacidad_aforo": final_capacity,
                "horario": f"{final_open:02d}:00 - {final_close:02d}:00",
                "radio_influencia_m": catchment_radius_m,
                "dias_simulados": sim_days,
            },
            "metricas_negocio": {
                "clientes_estimados_por_dia": daily_customers,
                "competidores_cercanos": len(same_cat_competitors),
                "ingresos_totales_usd": total_revenue,
                "costos_totales_usd": round(total_cogs + total_fixed, 2),
                "ganancia_neta_usd": net_profit,
                "caja_final_usd": cash_box,
                "roi_pct": roi_pct,
                "ledger_balanced": all_balanced,
            },
            "semaforo": semaforo,
            "resumen_sencillo": resumen,
            "tarjetas_impacto": tarjetas,
        }
