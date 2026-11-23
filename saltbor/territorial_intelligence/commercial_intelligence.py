"""Commercial Activity, Business Distribution & Economic Context Engines (Phase 1.17 Section 4).

Identifies real OSM & curated commercial establishments around any Salvadoran location,
separates unverified commercial buildings from confirmed operating businesses, computes
concentration/diversity/accessibility metrics, and represents Salvadoran informal-commerce
uncertainty explicitly without ever fabricating businesses.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from saltbor.conversational.schemas import TerritorialContext
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.datasets.salvadoran.establishments_data import SALVADORAN_ESTABLISHMENTS_P8
from saltbor.world.geographic.spatial_index import haversine_distance_km

from saltbor.territorial_intelligence.schemas import (
    BuildingIntelligenceReport,
    BuildingUseCategory,
    CommercialCategory,
    CommercialConcentrationMetrics,
    CommercialContextReport,
    CommercialEstablishmentRecord,
    UnverifiedCommercialBuilding,
)


def _bbox_for_radius(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float, float]:
    d_lat = radius_km / 111.0
    d_lon = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)


def _classify_osm_commercial(
    name: str,
    feature_class: str,
    source_class: str,
) -> Optional[CommercialCategory]:
    """Map an OSM POI/facility strictly from observed tags and name without inventing activity."""
    n_low = (name or "").lower()
    src = (source_class or "").lower()
    fc = (feature_class or "").lower()

    if "pupus" in n_low or "comedor" in n_low:
        return CommercialCategory.PUPUSERIA
    if src == "pharmacy" or "farmacia" in n_low:
        return CommercialCategory.PHARMACY
    if src == "supermarket" or "supermercado" in n_low or "selectos" in n_low or "despensa" in n_low:
        return CommercialCategory.SUPERMARKET
    if src == "mall" or "centro comercial" in n_low or "multiplaza" in n_low or "metrocentro" in n_low or "plaza mundo" in n_low:
        return CommercialCategory.COMMERCIAL_CENTER
    if fc == "market" or src == "marketplace" or "mercado" in n_low or "tiangue" in n_low:
        if "calle" in n_low or "ambulante" in n_low or "tiangue" in n_low:
            return CommercialCategory.STREET_MARKET
        return CommercialCategory.MARKET
    if fc == "food_service" or src in ("restaurant", "fast_food", "cafe", "bar", "pub", "bakery", "beverages", "food_court"):
        return CommercialCategory.RESTAURANT
    if src in ("car_repair", "workshop") or "taller" in n_low:
        return CommercialCategory.WORKSHOP
    if src in ("factory", "manufacture", "industrial") or "fabrica" in n_low or "fábrica" in n_low or "maquila" in n_low:
        return CommercialCategory.FACTORY
    if src in ("warehouse",) or "bodega" in n_low:
        return CommercialCategory.WAREHOUSE
    if "agroservicio" in n_low or "beneficio" in n_low or "cooperativa" in n_low:
        return CommercialCategory.AGRICULTURAL_BUSINESS
    if fc in ("fuel", "transport") or src in ("fuel", "bus_station", "taxi"):
        return CommercialCategory.TRANSPORT_COMMERCE
    if src in ("office", "bank", "atm") or fc == "finance" or "oficina" in n_low:
        return CommercialCategory.OFFICE
    if fc == "service_business" or src in ("hairdresser", "beauty_shop", "laundry", "travel_agent", "veterinary", "car_wash", "car_rental", "computer_shop") or fc == "hospitality":
        return CommercialCategory.SERVICE_BUSINESS
    if fc == "retail_commercial" or src in ("convenience", "clothes", "butcher", "greengrocer", "kiosk", "shoe_shop", "hardware", "doityourself", "electronics", "furniture_shop", "bookshop", "stationery", "gift_shop", "jeweller", "mobile_phone_shop", "optician", "sports_shop", "toy_shop", "bicycle_shop", "car_dealership", "general", "florist"):
        return CommercialCategory.SHOP
    return None


def _map_p8_category(cat_val: str, name: str) -> Optional[CommercialCategory]:
    c = (cat_val or "").lower()
    n = (name or "").lower()
    if "pupus" in n or "comedor" in n:
        return CommercialCategory.PUPUSERIA
    if "farmac" in n:
        return CommercialCategory.PHARMACY
    if "mercado" in c or "market" in c:
        return CommercialCategory.MARKET
    if "super" in n:
        return CommercialCategory.SUPERMARKET
    if "agro" in c or "agric" in c:
        return CommercialCategory.AGRICULTURAL_BUSINESS
    if "taller" in n or "work" in c:
        return CommercialCategory.WORKSHOP
    if "commerc" in c or "store" in c or "retail" in c or "food" in c:
        return CommercialCategory.SHOP
    if "financ" in c or "bank" in c:
        return CommercialCategory.OFFICE
    if "transport" in c:
        return CommercialCategory.TRANSPORT_COMMERCE
    return None


class CommercialActivityIntelligenceEngine:
    """Identifies confirmed real commercial establishments & separates unverified buildings."""

    def __init__(self, geography: Optional[IngestedGeography] = None) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def discover_commercial_activity(
        self,
        lat: float,
        lon: float,
        radius_km: float = 1.5,
        building_report: Optional[BuildingIntelligenceReport] = None,
        category_filter: Optional[CommercialCategory] = None,
        limit: int = 400,
    ) -> Tuple[List[CommercialEstablishmentRecord], List[UnverifiedCommercialBuilding]]:
        """Return confirmed establishments from OSM + P8 and unverified commercial buildings."""
        bbox = _bbox_for_radius(lat, lon, radius_km)
        establishments: List[CommercialEstablishmentRecord] = []
        seen_keys: set[str] = set()

        if self.geography.available:
            poi_rows = (
                self.geography.features_in_bbox(bbox, layer="pois", limit=limit)
                + self.geography.features_in_bbox(bbox, layer="pois_a", limit=limit)
                + self.geography.features_in_bbox(bbox, layer="buildings", feature_class="industrial", limit=120)
            )
            for row in poi_rows:
                elat = float(row["centroid"]["lat"])
                elon = float(row["centroid"]["lon"])
                dist_m = haversine_distance_km(lat, lon, elat, elon) * 1000.0
                if dist_m > radius_km * 1000.0:
                    continue
                cat = _classify_osm_commercial(
                    row.get("name", ""),
                    row.get("feature_class", ""),
                    row.get("source_class", ""),
                )
                if cat is None:
                    continue
                if category_filter is not None and cat != category_filter:
                    continue

                osm_id = str(row.get("osm_id") or row["feature_id"])
                dedup_key = f"osm:{osm_id}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                raw_name = (row.get("name") or "").strip()
                display_name = raw_name if raw_name else f"{row.get('source_class') or cat.value} (OSM sin nombre)"
                establishments.append(
                    CommercialEstablishmentRecord(
                        establishment_id=row["feature_id"],
                        name=display_name,
                        category=cat,
                        raw_source_class=row.get("source_class", ""),
                        lat=round(elat, 6),
                        lon=round(elon, 6),
                        distance_m=round(dist_m, 1),
                        geographic_coverage_note="osm_polygon_centroid" if row["layer"].endswith("_a") or row["layer"] == "buildings" else "osm_point",
                        source="OpenStreetMap contributors (Geofabrik)",
                        verification_status=row.get("validation_state", "VERIFIED_REAL"),
                        is_formal_status_known=False,
                        formal_status="unknown",
                        is_synthetic=False,
                        opening_hours=None,  # Not in Geofabrik shapefile; never fabricated
                        known_activity=row.get("source_class") or cat.value,
                        available_products_or_services=[],
                        known_employment=None,  # Not in OSM; never fabricated
                        last_verified_date=row.get("acquired_at", "2026-11-23"),
                    )
                )

        # Include curated P8 establishments within radius
        p8_items = (
            SALVADORAN_ESTABLISHMENTS_P8.values()
            if isinstance(SALVADORAN_ESTABLISHMENTS_P8, dict)
            else SALVADORAN_ESTABLISHMENTS_P8
        )
        seen_names = {e.name.lower().strip() for e in establishments}
        for rec in p8_items:
            dist_m = haversine_distance_km(lat, lon, rec.latitude, rec.longitude) * 1000.0
            if dist_m > radius_km * 1000.0:
                continue
            cat = _map_p8_category(
                rec.category.value if hasattr(rec.category, "value") else str(rec.category),
                rec.name,
            )
            if cat is None:
                continue
            if category_filter is not None and cat != category_filter:
                continue
            dedup_name = rec.name.lower().strip()
            if dedup_name in seen_names:
                continue
            seen_names.add(dedup_name)
            establishments.append(
                CommercialEstablishmentRecord(
                    establishment_id=rec.establishment_id,
                    name=rec.name,
                    category=cat,
                    raw_source_class=rec.sub_category,
                    lat=round(rec.latitude, 6),
                    lon=round(rec.longitude, 6),
                    distance_m=round(dist_m, 1),
                    geographic_coverage_note="curated_salvadoran_p8_record",
                    source=rec.source_name,
                    verification_status=rec.validation_status.value if hasattr(rec.validation_status, "value") else str(rec.validation_status),
                    is_formal_status_known=True,
                    formal_status="formal",
                    is_synthetic=False,
                    opening_hours=rec.opening_hours,
                    known_activity=rec.sub_category,
                    available_products_or_services=[],
                    known_employment=None,
                    last_verified_date=rec.saltbor_fetch_date,
                )
            )

        establishments.sort(key=lambda e: e.distance_m)

        # Identify unverified commercial buildings (commercial footprint with no confirmed establishment within 40m)
        unverified: List[UnverifiedCommercialBuilding] = []
        if building_report is not None:
            for b in building_report.sample_buildings:
                if b.building_use not in (BuildingUseCategory.COMMERCIAL, BuildingUseCategory.MIXED_USE):
                    continue
                has_match = any(
                    haversine_distance_km(b.lat, b.lon, e.lat, e.lon) * 1000.0 <= 40.0
                    for e in establishments
                )
                if not has_match:
                    unverified.append(
                        UnverifiedCommercialBuilding(
                            building_feature_id=b.feature_id,
                            lat=b.lat,
                            lon=b.lon,
                            surface_area_m2=b.surface_area_m2,
                            source_classification=b.source_classification,
                        )
                    )

        return establishments, unverified


class BusinessDistributionEngine:
    """Computes commercial density, Shannon diversity, competitors & service proximity."""

    def __init__(self, geography: Optional[IngestedGeography] = None) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def compute_concentration_metrics(
        self,
        context: TerritorialContext,
        establishments: List[CommercialEstablishmentRecord],
        unverified_buildings: List[UnverifiedCommercialBuilding],
        area_km2: float,
    ) -> CommercialConcentrationMetrics:
        safe_area = max(0.05, float(area_km2))
        n_est = len(establishments)
        density = round(n_est / safe_area, 2)

        cat_counts: Dict[str, int] = {}
        for e in establishments:
            cat_counts[e.category.value] = cat_counts.get(e.category.value, 0) + 1

        # Normalized Shannon diversity index H' / ln(K)
        shannon_norm = 0.0
        if n_est > 0 and len(cat_counts) > 1:
            entropy = -sum((cnt / n_est) * math.log(cnt / n_est) for cnt in cat_counts.values() if cnt > 0)
            shannon_norm = round(min(1.0, entropy / math.log(len(cat_counts))), 3)

        # Nearest transport, education & health facilities from real OSM
        nearest_tr_m = self._nearest_distance_m(context.lat, context.lon, "transport")
        nearest_edu_m = self._nearest_class_distance_m(context.lat, context.lon, ("pois", "pois_a"), "education")
        nearest_hlt_m = self._nearest_class_distance_m(context.lat, context.lon, ("pois", "pois_a"), "health")

        # Residential demand potential combining district population & urban income priors
        pop_factor = min(1.0, context.approx_population / 120000.0)
        income_factor = 0.72 if context.is_urban else 0.45
        demand_potential = round(min(1.0, 0.65 * pop_factor + 0.35 * income_factor), 3)

        # Employment center proximity proxy from industrial/office/commercial hubs
        emp_nodes = cat_counts.get("office", 0) + cat_counts.get("factory", 0) + cat_counts.get("commercial_center", 0) + cat_counts.get("supermarket", 0)
        emp_prox = round(min(1.0, 0.15 + emp_nodes * 0.06), 3)

        return CommercialConcentrationMetrics(
            analysis_area_km2=round(safe_area, 3),
            confirmed_establishments_count=n_est,
            unverified_commercial_buildings_count=len(unverified_buildings),
            business_density_per_km2=density,
            commercial_diversity_shannon_norm=shannon_norm,
            competitor_concentration_by_category=cat_counts,
            commercial_accessibility_score=round(float(context.accessibility_index), 3),
            residential_demand_potential_index=demand_potential,
            proximity_to_nearest_transport_m=nearest_tr_m,
            proximity_to_nearest_education_m=nearest_edu_m,
            proximity_to_nearest_health_m=nearest_hlt_m,
            employment_center_proximity_score=emp_prox,
        )

    def _nearest_distance_m(self, lat: float, lon: float, layer: str) -> Optional[float]:
        if not self.geography.available:
            return None
        hits = self.geography.nearest_features(lat, lon, layer=layer, limit=1, radius_deg=0.05)
        if not hits:
            return None
        c = hits[0]["centroid"]
        return round(haversine_distance_km(lat, lon, c["lat"], c["lon"]) * 1000.0, 1)

    def _nearest_class_distance_m(
        self,
        lat: float,
        lon: float,
        layers: Tuple[str, ...],
        feature_class: str,
    ) -> Optional[float]:
        if not self.geography.available:
            return None
        bbox = _bbox_for_radius(lat, lon, 3.0)
        best_m: Optional[float] = None
        for lyr in layers:
            for feat in self.geography.features_in_bbox(bbox, layer=lyr, feature_class=feature_class, limit=80):
                d_m = haversine_distance_km(lat, lon, feat["centroid"]["lat"], feat["centroid"]["lon"]) * 1000.0
                if best_m is None or d_m < best_m:
                    best_m = d_m
        return round(best_m, 1) if best_m is not None else None


class TerritorialEconomicContextEngine:
    """Master coordinator for commercial intelligence, concentration, and informal economy framing."""

    def __init__(self, geography: Optional[IngestedGeography] = None) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self.activity_engine = CommercialActivityIntelligenceEngine(geography=self.geography)
        self.distribution_engine = BusinessDistributionEngine(geography=self.geography)

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def build_economic_context(
        self,
        context: TerritorialContext,
        radius_km: Optional[float] = None,
        area_km2: Optional[float] = None,
        building_report: Optional[BuildingIntelligenceReport] = None,
        category_filter: Optional[CommercialCategory] = None,
    ) -> CommercialContextReport:
        r_km = radius_km or context.radius_km or 1.5
        eff_area = area_km2 if area_km2 is not None else (math.pi * r_km * r_km)

        establishments, unverified = self.activity_engine.discover_commercial_activity(
            lat=context.lat,
            lon=context.lon,
            radius_km=r_km,
            building_report=building_report,
            category_filter=category_filter,
        )
        metrics = self.distribution_engine.compute_concentration_metrics(
            context=context,
            establishments=establishments,
            unverified_buildings=unverified,
            area_km2=eff_area,
        )

        informal_share = 0.62 if context.is_urban else 0.78
        limitations = [
            "OSM registra establecimientos mapeados por contribuyentes; negocios pequeños e informales suelen estar subrepresentados.",
            "Los edificios marcados como 'unverified_commercial_building' tienen uso edilicio comercial sin comercio confirmado.",
        ]
        if not establishments:
            limitations.append(
                "No se encontraron establecimientos comerciales confirmados en OSM dentro del radio analizado; no se fabrican negocios."
            )

        return CommercialContextReport(
            district_id=context.district_id,
            district_name=context.district_name,
            establishments=establishments,
            unverified_commercial_buildings=unverified,
            simulated_informal_entities=[],
            category_counts=metrics.competitor_concentration_by_category,
            concentration_metrics=metrics,
            informal_economy_prior_share=informal_share,
            economic_context_summary={
                "is_urban": context.is_urban,
                "estimated_daily_household_income_usd": 24.0 if context.is_urban else 14.5,
                "remittance_household_share_prior": 0.26 if context.is_urban else 0.34,
                "confirmed_establishments": len(establishments),
                "unverified_commercial_buildings": len(unverified),
            },
            limitations=limitations,
        )
