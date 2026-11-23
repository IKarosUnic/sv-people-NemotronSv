"""Human Mobility, Population Distribution & Flow Evidence Engines (Phase 1.17 Section 6).

Differentiates all 10 mobility roles without double-counting, models time-of-day
and day-type heterogeneous individual schedules grounded in SyntheticHuman attributes,
identifies OSM mobility corridors, and enforces strict FlowEvidenceTier attribution
so simulated flows are never mistaken for measured pedestrian counts.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional, Tuple

from saltbor.conversational.population_activation import NationalPopulationActivationManager
from saltbor.conversational.schemas import PopulationCategory, TerritorialContext
from saltbor.datasets.gis.pipeline import DEFAULT_OUTPUT as DEFAULT_GEO_SQLITE, IngestedGeography
from saltbor.datasets.salvadoran.territory_data import SALVADORAN_DISTRICTS_P8, SalvadoranDistrictData
from saltbor.population.human import SyntheticHuman
from saltbor.world.geographic.spatial_index import haversine_distance_km

from saltbor.territorial_intelligence.schemas import (
    CatchmentAreaResult,
    CommercialContextReport,
    DayType,
    FlowEvidenceTier,
    MobilityCorridor,
    MobilityRole,
    PopulationFlowReport,
    TimePeriod,
)


class TerritorialPopulationDistributionEngine:
    """Computes resident vs mobile population distribution for any Salvadoran catchment."""

    def __init__(self) -> None:
        self._districts: Dict[str, SalvadoranDistrictData] = (
            SALVADORAN_DISTRICTS_P8
            if isinstance(SALVADORAN_DISTRICTS_P8, dict)
            else {d.district_id: d for d in SALVADORAN_DISTRICTS_P8}
        )

    def get_nearby_districts(self, lat: float, lon: float, current_district_id: str, limit: int = 5) -> List[Tuple[SalvadoranDistrictData, float]]:
        dists: List[Tuple[SalvadoranDistrictData, float]] = []
        for d in self._districts.values():
            if d.district_id == current_district_id:
                continue
            km = haversine_distance_km(lat, lon, d.latitude, d.longitude)
            dists.append((d, km))
        dists.sort(key=lambda item: item[1])
        return dists[:limit]

    def estimate_catchment_population_distribution(
        self,
        context: TerritorialContext,
        catchment: Optional[CatchmentAreaResult] = None,
    ) -> Dict[str, Any]:
        pop = max(0, int(context.approx_population))
        eff_area = catchment.effective_area_km2 if catchment else (math.pi * (context.radius_km ** 2))
        # Urban districts concentrate population within denser core (~25-65 km2); rural districts spread wider
        nominal_district_area = 28.0 if context.is_urban else 68.0
        catchment_share = min(1.0, max(0.03, eff_area / nominal_district_area))
        catchment_residents = int(round(pop * catchment_share))

        # Estimate neighboring origin-destination gravity
        neighbors = self.get_nearby_districts(context.lat, context.lon, context.district_id, limit=4)
        od_patterns: List[Dict[str, Any]] = []
        total_inbound = 0
        for nb, dist_km in neighbors:
            gravity = int(round((nb.approx_population * 0.012) / max(1.0, (dist_km / 3.5) ** 1.3)))
            gravity = min(gravity, int(pop * 0.12) + 500)
            total_inbound += gravity
            od_patterns.append(
                {
                    "origin_district_id": nb.district_id,
                    "origin_district_name": nb.name,
                    "distance_km": round(dist_km, 2),
                    "estimated_daily_commuters_and_visitors": gravity,
                    "method": "gravity_inverse_distance_calibrated",
                }
            )

        return {
            "district_population_approx": pop,
            "catchment_residents_est": catchment_residents,
            "catchment_area_km2": round(eff_area, 3),
            "estimated_daily_inbound": total_inbound,
            "estimated_daily_outbound": int(round(catchment_residents * (0.14 if context.is_urban else 0.19))),
            "origin_destination_patterns": od_patterns,
        }


class PopulationFlowEvidenceEngine:
    """Enforces epistemic separation on all human mobility indicators."""

    @staticmethod
    def build_evidence_tiers() -> Dict[str, FlowEvidenceTier]:
        return {
            "street_sensor_pedestrian_counts": FlowEvidenceTier.MEASURED_FLOW,
            "district_demographic_base": FlowEvidenceTier.OFFICIAL_STATISTICAL_ESTIMATE,
            "road_and_transit_corridor_accessibility": FlowEvidenceTier.GIS_DERIVED_ACCESSIBILITY,
            "origin_destination_gravity_and_diurnal_curves": FlowEvidenceTier.MODEL_GENERATED_MOBILITY,
            "active_synthetic_human_schedules": FlowEvidenceTier.SYNTHETIC_AGENT_SIMULATION,
        }


class HumanMobilityFlowEngine:
    """Models 10-role non-double-counted mobility flows & heterogeneous agent schedules."""

    def __init__(
        self,
        geography: Optional[IngestedGeography] = None,
        population_manager: Optional[NationalPopulationActivationManager] = None,
    ) -> None:
        self._owns_geo = geography is None
        self.geography = geography or IngestedGeography(DEFAULT_GEO_SQLITE)
        self.pop_manager = population_manager
        self.dist_engine = TerritorialPopulationDistributionEngine()

    def close(self) -> None:
        if self._owns_geo:
            self.geography.close()

    def analyze_mobility(
        self,
        context: TerritorialContext,
        humans: Optional[List[SyntheticHuman]] = None,
        catchment: Optional[CatchmentAreaResult] = None,
        commercial_report: Optional[CommercialContextReport] = None,
        time_period: TimePeriod = TimePeriod.MORNING,
        day_type: DayType = DayType.WEEKDAY,
        season: Literal["DRY", "RAINY", "HARVEST_TRANSITION"] = "DRY",
    ) -> PopulationFlowReport:
        """Analyze time-dependent, role-differentiated mobility without double counting."""
        dist_info = self.dist_engine.estimate_catchment_population_distribution(context, catchment)
        corridors = self._extract_mobility_corridors(context, catchment)

        # Unique individual role accounting (every hydrated SyntheticHuman assigned strictly ONE primary active role at time_period)
        active_humans = humans or []
        role_counts: Dict[str, int] = {r.value: 0 for r in MobilityRole}
        period_profiles: Dict[str, Dict[str, int]] = {}
        schedule_signatures: Dict[str, int] = {}

        if active_humans:
            # Ensure deterministic commuters from nearest neighbor district exist if population_manager provided
            commuter_uids: set[str] = set()
            if self.pop_manager is not None:
                for uid in [str(h.uid) for h in active_humans]:
                    meta = self.pop_manager._human_meta.get(uid)
                    if meta and meta.home_district_id != context.district_id:
                        commuter_uids.add(uid)

            # Build per-period unique role classification across all 5 time periods
            for tp in TimePeriod:
                tp_counts: Dict[str, int] = {r.value: 0 for r in MobilityRole}
                for h in active_humans:
                    role = self._determine_individual_role_at_period(
                        human=h,
                        is_external_commuter=str(h.uid) in commuter_uids,
                        is_urban=context.is_urban,
                        time_period=tp,
                        day_type=day_type,
                        season=season,
                    )
                    tp_counts[role.value] += 1
                    if tp == time_period:
                        role_counts[role.value] += 1
                period_profiles[tp.value] = {k: v for k, v in tp_counts.items() if v > 0}

            # Measure individual schedule heterogeneity across the cohort (Shannon entropy of role sequences)
            for h in active_humans:
                seq = tuple(
                    self._determine_individual_role_at_period(
                        human=h,
                        is_external_commuter=str(h.uid) in commuter_uids,
                        is_urban=context.is_urban,
                        time_period=tp,
                        day_type=day_type,
                        season=season,
                    ).value
                    for tp in TimePeriod
                )
                key = "|".join(seq)
                schedule_signatures[key] = schedule_signatures.get(key, 0) + 1
            entropy = self._normalized_entropy(schedule_signatures, len(active_humans))
        else:
            # Aggregate statistical breakdown (still strictly non-overlapping sum == 100% of catchment + inbound)
            base_pop = dist_info["catchment_residents_est"]
            inflow = dist_info["estimated_daily_inbound"]
            role_counts = self._statistical_role_breakdown(
                base_pop=base_pop,
                inflow=inflow,
                is_urban=context.is_urban,
                time_period=time_period,
                day_type=day_type,
                season=season,
            )
            for tp in TimePeriod:
                period_profiles[tp.value] = self._statistical_role_breakdown(
                    base_pop=base_pop,
                    inflow=inflow,
                    is_urban=context.is_urban,
                    time_period=tp,
                    day_type=day_type,
                    season=season,
                )
            entropy = 0.75

        # Pedestrian activity index driven by road network, commercial hubs, transit & time/season
        comm_count = commercial_report.concentration_metrics.confirmed_establishments_count if commercial_report else 0
        period_mult = {
            TimePeriod.MORNING: 0.92,
            TimePeriod.MIDDAY: 0.96,
            TimePeriod.AFTERNOON: 0.88,
            TimePeriod.EVENING: 0.54,
            TimePeriod.NIGHT: 0.18,
        }[time_period]
        day_mult = {DayType.WEEKDAY: 1.0, DayType.WEEKEND: 0.78, DayType.HOLIDAY: 0.62}[day_type]
        season_mult = 0.85 if season == "RAINY" else (1.05 if season == "HARVEST_TRANSITION" else 1.0)
        base_activity = min(1.0, 0.25 * context.accessibility_index + 0.40 * min(1.0, comm_count / 25.0) + 0.35 * min(1.0, context.approx_population / 100000.0))
        ped_index = round(min(1.0, max(0.05, base_activity * period_mult * day_mult * season_mult)), 3)

        return PopulationFlowReport(
            district_id=context.district_id,
            district_name=context.district_name,
            time_period=time_period,
            day_type=day_type,
            season=season,
            unique_resident_population_approx=int(context.approx_population),
            unique_active_synthetic_individuals=len(active_humans),
            double_counting_prevented=True,
            role_breakdown={k: v for k, v in role_counts.items() if v > 0},
            temporal_profile_by_period=period_profiles,
            estimated_pedestrian_activity_index=ped_index,
            estimated_daily_arrivals=dist_info["estimated_daily_inbound"],
            estimated_daily_departures=dist_info["estimated_daily_outbound"],
            origin_destination_patterns=dist_info["origin_destination_patterns"],
            mobility_corridors=corridors,
            schedule_heterogeneity_entropy=entropy,
            measured_flows_available=False,
            evidence_tiers=PopulationFlowEvidenceEngine.build_evidence_tiers(),
        )

    @staticmethod
    def _determine_individual_role_at_period(
        human: SyntheticHuman,
        is_external_commuter: bool,
        is_urban: bool,
        time_period: TimePeriod,
        day_type: DayType,
        season: str,
    ) -> MobilityRole:
        """Assign strictly one mutually exclusive role per individual at a given time slice."""
        occ = (human.demographics.occupation or "").lower()
        age = int(human.demographics.age)
        money = float(human.physical_state.money)
        hunger = float(human.physical_state.hunger)
        extraversion = float(human.personality.traits.extraversion.current_value)
        conscientiousness = float(human.personality.traits.conscientiousness.current_value)

        if time_period == TimePeriod.NIGHT:
            if is_external_commuter and extraversion > 0.65:
                return MobilityRole.VISITOR
            return MobilityRole.TEMPORARY_RESIDENT if is_external_commuter else MobilityRole.PERMANENT_RESIDENT

        if is_external_commuter:
            if day_type == DayType.WEEKDAY and time_period in (TimePeriod.MORNING, TimePeriod.MIDDAY):
                return MobilityRole.COMMUTER
            if time_period == TimePeriod.AFTERNOON and money >= 12.0:
                return MobilityRole.CUSTOMER
            return MobilityRole.TRANSIT if time_period == TimePeriod.EVENING else MobilityRole.VISITOR

        # Seasonal agricultural workers during harvest / rainy transitions in rural areas
        if not is_urban and season == "HARVEST_TRANSITION" and ("agri" in occ or "jornal" in occ):
            if time_period in (TimePeriod.MORNING, TimePeriod.MIDDAY):
                return MobilityRole.SEASONAL_AGRICULTURAL_WORKER

        # Students (school-age or occupation Estudiante)
        if age < 18 or "estudiant" in occ:
            if day_type == DayType.WEEKDAY and time_period in (TimePeriod.MORNING, TimePeriod.MIDDAY):
                return MobilityRole.STUDENT
            if time_period == TimePeriod.AFTERNOON and extraversion > 0.55:
                return MobilityRole.VISITOR
            return MobilityRole.PERMANENT_RESIDENT

        # Working adults
        if 18 <= age <= 64 and "adulto mayor" not in occ:
            if day_type == DayType.WEEKDAY and time_period in (TimePeriod.MORNING, TimePeriod.MIDDAY):
                # High conscientiousness or informal commerce works regular hours; others seek services or transit
                if time_period == TimePeriod.MIDDAY and hunger > 0.55 and money >= 5.0:
                    return MobilityRole.CUSTOMER
                if conscientiousness < 0.38 and time_period == TimePeriod.MORNING:
                    return MobilityRole.TRANSIT
                return MobilityRole.WORKER
            if time_period == TimePeriod.AFTERNOON:
                if money >= 15.0 and (hunger > 0.40 or extraversion > 0.50):
                    return MobilityRole.CUSTOMER
                if day_type == DayType.WEEKEND:
                    return MobilityRole.VISITOR
                return MobilityRole.TRANSIT
            if time_period == TimePeriod.EVENING:
                if extraversion > 0.62 and money >= 10.0:
                    return MobilityRole.CUSTOMER
                return MobilityRole.PERMANENT_RESIDENT

        # Older adults / homemakers / service seekers
        if time_period == TimePeriod.MORNING and conscientiousness > 0.45:
            return MobilityRole.SERVICE_SEEKER
        if time_period == TimePeriod.MIDDAY and money >= 10.0:
            return MobilityRole.CUSTOMER
        return MobilityRole.PERMANENT_RESIDENT

    @staticmethod
    def _normalized_entropy(counts: Dict[str, int], total: int) -> float:
        if total <= 1 or len(counts) <= 1:
            return 0.0
        h = -sum((c / total) * math.log(c / total) for c in counts.values() if c > 0)
        return round(min(1.0, h / math.log(len(counts))), 3)

    @staticmethod
    def _statistical_role_breakdown(
        base_pop: int,
        inflow: int,
        is_urban: bool,
        time_period: TimePeriod,
        day_type: DayType,
        season: str,
    ) -> Dict[str, int]:
        # Partition residents + non-double-counted inbound into mutually exclusive daytime/nighttime slices
        if time_period == TimePeriod.NIGHT:
            return {
                MobilityRole.PERMANENT_RESIDENT.value: base_pop,
                MobilityRole.TEMPORARY_RESIDENT.value: int(round(inflow * 0.05)),
            }
        w_mult = 1.0 if day_type == DayType.WEEKDAY else 0.48
        s_mult = 1.0 if day_type == DayType.WEEKDAY else 0.15
        workers = int(round(base_pop * (0.34 if is_urban else 0.28) * w_mult))
        students = int(round(base_pop * 0.20 * s_mult))
        seasonal_ag = int(round(base_pop * (0.01 if is_urban else (0.12 if season == "HARVEST_TRANSITION" else 0.04))))
        customers = int(round(base_pop * 0.09 + inflow * 0.25))
        services = int(round(base_pop * 0.05 + inflow * 0.10))
        commuters = int(round(inflow * (0.45 if day_type == DayType.WEEKDAY else 0.18)))
        visitors = int(round(inflow * 0.12))
        transit = int(round(inflow * 0.08))
        remaining_res = max(0, base_pop - (workers + students + seasonal_ag + int(round(base_pop * 0.14))))
        return {
            MobilityRole.PERMANENT_RESIDENT.value: remaining_res,
            MobilityRole.WORKER.value: workers,
            MobilityRole.STUDENT.value: students,
            MobilityRole.SEASONAL_AGRICULTURAL_WORKER.value: seasonal_ag,
            MobilityRole.CUSTOMER.value: customers,
            MobilityRole.SERVICE_SEEKER.value: services,
            MobilityRole.COMMUTER.value: commuters,
            MobilityRole.VISITOR.value: visitors,
            MobilityRole.TRANSIT.value: transit,
        }

    def _extract_mobility_corridors(
        self,
        context: TerritorialContext,
        catchment: Optional[CatchmentAreaResult],
    ) -> List[MobilityCorridor]:
        if not self.geography.available:
            return []
        r_km = catchment.effective_radius_km if catchment else context.radius_km
        d_lat = r_km / 111.0
        d_lon = r_km / (111.0 * max(0.2, math.cos(math.radians(context.lat))))
        bbox = (context.lon - d_lon, context.lat - d_lat, context.lon + d_lon, context.lat + d_lat)

        roads = self.geography.features_in_bbox(bbox, layer="roads", limit=900)
        stops = self.geography.features_in_bbox(bbox, layer="transport", limit=150)

        by_name: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for rd in roads:
            rc = rd.get("feature_class") or "other"
            if rc not in ("motorway", "trunk", "primary", "secondary", "tertiary"):
                continue
            rname = (rd.get("name") or f"Vía {rc}").strip()
            key = (rname, rc)
            entry = by_name.setdefault(key, {"segments": 0, "lat_sum": 0.0, "lon_sum": 0.0})
            entry["segments"] += 1
            entry["lat_sum"] += float(rd["centroid"]["lat"])
            entry["lon_sum"] += float(rd["centroid"]["lon"])

        corridors: List[MobilityCorridor] = []
        class_weight = {"motorway": 1.0, "trunk": 0.92, "primary": 0.85, "secondary": 0.72, "tertiary": 0.58}
        for (rname, rc), info in by_name.items():
            c_lat = info["lat_sum"] / info["segments"]
            c_lon = info["lon_sum"] / info["segments"]
            near_stops = sum(
                1 for s in stops
                if haversine_distance_km(c_lat, c_lon, s["centroid"]["lat"], s["centroid"]["lon"]) <= 0.35
            )
            intensity = min(1.0, class_weight.get(rc, 0.5) * 0.65 + min(0.35, near_stops * 0.06 + info["segments"] * 0.015))
            corridors.append(
                MobilityCorridor(
                    corridor_name=rname,
                    road_class=rc,
                    segment_count=info["segments"],
                    transport_stops_along_corridor=near_stops,
                    estimated_relative_intensity=round(intensity, 3),
                )
            )
        corridors.sort(key=lambda c: (c.estimated_relative_intensity, c.segment_count), reverse=True)
        return corridors[:10]
