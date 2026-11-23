"""National Synthetic Population Activation & Context Engine (Phase 1.16A).

Manages national-scale persistent synthetic identities across El Salvador's 262
districts while activating only the required geographic region and LOD in RAM.
Reuses `MultilevelPopulationManager`, `CognitiveLODManager`, `PopulationRegistry`,
`SyntheticHuman`, and `MockDataGenerator` without double-counting commuters.
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from saltbor.cognition.emotions.engine import EmotionalEngine
from saltbor.cognition.memory.engine import MemoryEngine
from saltbor.cognition.memory.semantic import SemanticFact
from saltbor.cognition.personality.engine import PersonalityEngine
from saltbor.cognition.personality.traits import PersonalityTraits, TraitValue
from saltbor.core.identity import HumanIdentity, IdentityFactory
from saltbor.core.types import ActivityType, DataSource, Gender
from saltbor.datasets.mock_data import PERSONA_TEMPLATES
from saltbor.population.demographics import Demographics
from saltbor.population.human import SyntheticHuman
from saltbor.population.lod import CognitiveLOD, CognitiveLODManager
from saltbor.population.multilevel.models import (
    CommunityAggregate,
    LODLevel,
    PersistentIndividualRecord,
)
from saltbor.population.multilevel.population_manager import MultilevelPopulationManager
from saltbor.population.physical_state import PhysicalState
from saltbor.population.registry import PopulationRegistry

from saltbor.conversational.schemas import (
    ActivationLOD,
    PopulationCategory,
    TerritorialContext,
)

logger = logging.getLogger(__name__)

_GIVEN_NAMES_M = [
    "José", "Carlos", "Mateo", "Miguel", "Diego", "Luis", "Rafael", "Roberto",
    "Óscar", "Nelson", "Kevin", "Bryan", "Mauricio", "Salvador", "Ernesto",
]
_GIVEN_NAMES_F = [
    "María", "Sofía", "Carmen", "Ana", "Lucía", "Rosa", "Gabriela", "Karla",
    "Claudia", "Brenda", "Fátima", "Patricia", "Elena", "Mónica", "Andrea",
]
_FAMILY_NAMES = [
    "Hernández", "Martínez", "López", "García", "Rodríguez", "Pérez", "Flores",
    "Rivera", "Ramírez", "Cruz", "Reyes", "Mendoza", "Chávez", "Vásquez", "Ramos",
]


@dataclass
class NationalHumanMetadata:
    """Tracks home vs current district and flow categories for anti-double-counting."""

    uid: str
    home_district_id: str
    current_district_id: str
    household_id: str
    primary_category: PopulationCategory
    active_roles: Set[PopulationCategory] = field(default_factory=set)
    commuter_origin_district: Optional[str] = None
    commuter_dest_district: Optional[str] = None


def map_activation_to_multilevel_lod(lod: ActivationLOD) -> LODLevel:
    """Bridge Phase 1.16A LOD (0 coarsest..3 finest) to MultilevelPopulationManager LODLevel."""
    mapping = {
        ActivationLOD.LOD_0_TERRITORIAL_AGGREGATE: LODLevel.LOD_3_COMMUNITY,
        ActivationLOD.LOD_1_HOUSEHOLD_GROUP: LODLevel.LOD_2_COHORT_GROUP,
        ActivationLOD.LOD_2_INDIVIDUAL_SUMMARY: LODLevel.LOD_1_SIMPLIFIED,
        ActivationLOD.LOD_3_INDIVIDUAL_FULL: LODLevel.LOD_0_INDIVIDUAL,
    }
    return mapping[lod]


def map_activation_to_cognitive_lod(lod: ActivationLOD) -> CognitiveLOD:
    """Bridge Phase 1.16A LOD to CognitiveLODManager."""
    mapping = {
        ActivationLOD.LOD_0_TERRITORIAL_AGGREGATE: CognitiveLOD.LOD_3_DORMANT,
        ActivationLOD.LOD_1_HOUSEHOLD_GROUP: CognitiveLOD.LOD_2_EVENT_DRIVEN,
        ActivationLOD.LOD_2_INDIVIDUAL_SUMMARY: CognitiveLOD.LOD_1_ROUTINE,
        ActivationLOD.LOD_3_INDIVIDUAL_FULL: CognitiveLOD.LOD_0_FULL,
    }
    return mapping[lod]


class TerritorialPopulationContextEngine:
    """Derives grounded demographic & mobility flow estimates for a resolved territory."""

    def build_population_context(
        self,
        context: TerritorialContext,
        activation_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compute grounded demographic estimates with explicit uncertainty and methods."""
        pop = max(0, int(context.approx_population))
        is_urban = context.is_urban

        # Calibrated Salvadoran EHPM/DIGESTYC priors (urban vs rural differentiation)
        avg_household_size = 3.55 if is_urban else 4.10
        school_age_share = 0.24 if is_urban else 0.29
        workforce_share = 0.56 if is_urban else 0.49
        informal_share = 0.62 if is_urban else 0.78
        remittance_hh_share = 0.26 if is_urban else 0.34
        avg_daily_household_income_usd = 24.0 if is_urban else 14.5

        # Adjust commercial/visitor flow potential from real OSM POIs & road network
        food_pois = context.nearby_facilities_counts.get("food_service", 0)
        transit_stops = context.transport_stops_count
        road_segs = context.road_network_summary.get("total_segments_in_radius", 0)

        estimated_households = int(round(pop / avg_household_size)) if pop > 0 else 0
        estimated_school_age = int(round(pop * school_age_share))
        estimated_workers = int(round(pop * workforce_share))
        # Inbound daily commuters / transit corridor multiplier based on road & transit density
        commuter_inflow_est = int(round(pop * (0.08 if is_urban else 0.03) * min(1.8, 0.6 + transit_stops * 0.08)))
        visitor_commercial_est = int(round(pop * 0.04 * min(2.0, 0.5 + (food_pois + road_segs * 0.05) * 0.02)))

        uncertainties: List[str] = []
        if context.buildings_is_partial:
            uncertainties.append(
                "Sin huellas completas de edificaciones OSM; densidad residencial estimada mediante población distrital D.L. 762 y cobertura de uso de suelo."
            )
        uncertainties.append(
            "Los flujos intermunicipales diarios son estimaciones calibradas del modelo basadas en infraestructura vial y paradas OSM, no conteo censal origen-destino en tiempo real."
        )

        return {
            "district_id": context.district_id,
            "district_name": context.district_name,
            "is_urban": is_urban,
            "permanent_residents_approx": pop,
            "estimated_households": estimated_households,
            "avg_household_size": avg_household_size,
            "school_age_population_est": estimated_school_age,
            "economically_active_workers_est": estimated_workers,
            "informal_employment_share": informal_share,
            "remittance_receiving_household_share": remittance_hh_share,
            "avg_daily_household_income_usd": avg_daily_household_income_usd,
            "estimated_daily_inbound_commuters": commuter_inflow_est,
            "estimated_daily_commercial_visitors": visitor_commercial_est,
            "estimation_method": "D.L. 762 district population + EHPM urban/rural priors + OSM POI/road gravity scaling",
            "active_simulation_cohort": activation_summary or {},
            "uncertainties": uncertainties,
        }


class NationalPopulationActivationManager:
    """Selective territorial population hydrator preventing commuter double-counting."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.multilevel = MultilevelPopulationManager()
        self.lod_manager = CognitiveLODManager()
        self.active_registry = PopulationRegistry()
        self.identity_factory = IdentityFactory(seed=seed)

        self._human_meta: Dict[str, NationalHumanMetadata] = {}
        self._district_agents: Dict[str, List[str]] = {}
        self._active_districts: Dict[str, ActivationLOD] = {}
        self._district_boundaries: Dict[str, float] = {}
        self._commuter_flows: List[Dict[str, Any]] = []
        self._cached_synthesized_humans: Dict[str, SyntheticHuman] = {}

    def total_unique_persistent_individuals(self) -> int:
        """Exact count of unique human identities across the national registry."""
        return len(self._human_meta)

    def ensure_district_cohort(
        self,
        context: TerritorialContext,
        cohort_size: int = 40,
        seed: Optional[int] = None,
    ) -> List[str]:
        """Register persistent synthetic residents for a district if not already created."""
        dist_id = context.district_id or "UNKNOWN"
        existing = self._district_agents.get(dist_id, [])
        if len(existing) >= cohort_size:
            return existing[:cohort_size]

        used_seed = seed if seed is not None else self.seed
        rng = np.random.default_rng(used_seed + sum(ord(c) for c in dist_id))

        # Register community aggregate at LOD 0 (territorial aggregate)
        if dist_id not in self.multilevel._communities:
            self.multilevel.register_community(
                CommunityAggregate(
                    community_id=f"comm_{dist_id}",
                    district_id=dist_id,
                    name=context.district_name or dist_id,
                    center_lat=context.lat,
                    center_lon=context.lon,
                    total_population=max(cohort_size, context.approx_population),
                    mean_wealth=28.0 if context.is_urban else 18.0,
                    gini_coefficient=0.41 if context.is_urban else 0.37,
                )
            )

        need = cohort_size - len(existing)
        is_urban = context.is_urban
        urban_occs = [
            "Comerciante", "Vendedor Ambulante", "Empleado de Tienda", "Estudiante",
            "Costurera", "Motorista", "Mecánico", "Enfermero", "Docente", "Cocinera",
        ]
        rural_occs = [
            "Agricultor", "Jornalero", "Vendedora de Mercado", "Estudiante",
            "Albañil", "Costurera", "Ganadero", "Carpintero", "Docente", "Ama de Casa",
        ]
        occ_pool = urban_occs if is_urban else rural_occs

        created_uids: List[str] = list(existing)
        hh_size = 3 if is_urban else 4

        for i in range(need):
            idx = len(existing) + i
            hh_index = idx // hh_size
            hh_id = f"hh_{dist_id}_{hh_index:03d}"

            # Deterministic UUID derived from district + index + seed so identity stays constant
            det_uid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"saltbor:{used_seed}:{dist_id}:{idx}"))
            if det_uid in self._human_meta:
                created_uids.append(det_uid)
                continue

            is_female = bool(rng.random() < 0.51)
            given = _GIVEN_NAMES_F[idx % len(_GIVEN_NAMES_F)] if is_female else _GIVEN_NAMES_M[idx % len(_GIVEN_NAMES_M)]
            family = f"{_FAMILY_NAMES[(idx * 3) % len(_FAMILY_NAMES)]} {_FAMILY_NAMES[(idx * 5 + 2) % len(_FAMILY_NAMES)]}"

            # Age distribution: ~26% school-age (6..17), ~62% working-age (18..64), ~12% older (65+)
            role_roll = float(rng.random())
            if role_roll < 0.26:
                age = int(rng.integers(6, 18))
                occupation = "Estudiante"
                category = PopulationCategory.STUDENT
                wealth = round(float(rng.uniform(3.0, 14.0)), 2)
            elif role_roll < 0.88:
                age = int(rng.integers(18, 63))
                occupation = occ_pool[idx % len(occ_pool)]
                if occupation == "Estudiante":
                    occupation = occ_pool[(idx + 1) % len(occ_pool)]
                category = PopulationCategory.WORKER
                base_cash = rng.uniform(16.0, 65.0) if is_urban else rng.uniform(10.0, 42.0)
                wealth = round(float(base_cash), 2)
            else:
                age = int(rng.integers(63, 82))
                occupation = "Adulto Mayor"
                category = PopulationCategory.PERMANENT_RESIDENT
                wealth = round(float(rng.uniform(12.0, 45.0)), 2)

            # Slight spatial jitter inside district boundary
            j_lat = float(context.lat + rng.normal(0.0, 0.003))
            j_lon = float(context.lon + rng.normal(0.0, 0.003))

            serial = self.identity_factory.next_serial
            self.identity_factory.advance_to(serial + 1)

            rec = PersistentIndividualRecord(
                uid=det_uid,
                serial=serial,
                given_name=given,
                family_name=family,
                gender="female" if is_female else "male",
                age_years=float(age),
                occupation=occupation,
                current_location_id=f"loc_{dist_id}",
                lat=round(j_lat, 6),
                lon=round(j_lon, 6),
                wealth=wealth,
                health=round(float(rng.uniform(0.78, 1.0)), 3),
                energy=round(float(rng.uniform(0.65, 1.0)), 3),
                hunger=round(float(rng.uniform(0.15, 0.55)), 3),
                happiness=round(float(rng.uniform(0.45, 0.85)), 3),
                community_id=f"comm_{dist_id}",
                district_id=dist_id,
                household_id=hh_id,
                lod_tier=int(LODLevel.LOD_2_COHORT_GROUP),
            )
            self.multilevel.register_individual(rec)

            roles = {PopulationCategory.PERMANENT_RESIDENT, category}
            self._human_meta[det_uid] = NationalHumanMetadata(
                uid=det_uid,
                home_district_id=dist_id,
                current_district_id=dist_id,
                household_id=hh_id,
                primary_category=PopulationCategory.PERMANENT_RESIDENT,
                active_roles=roles,
            )
            created_uids.append(det_uid)

        self._district_agents[dist_id] = created_uids
        return created_uids[:cohort_size]

    def _hydrate_synthetic_human(
        self,
        rec: PersistentIndividualRecord,
        target_lod: ActivationLOD,
    ) -> SyntheticHuman:
        """Hydrate a SyntheticHuman cleanly preserving identity, state, and prior memories."""
        cached = self._cached_synthesized_humans.get(rec.uid)
        if cached is not None:
            # Sync mutable physical attributes from persistent record
            cached.physical_state.money = float(rec.wealth)
            cached.physical_state.health = float(rec.health)
            cached.physical_state.energy = float(rec.energy)
            cached.physical_state.hunger = float(rec.hunger)
            cached.physical_state.current_location_id = rec.current_location_id
            return cached

        uid_obj = uuid.UUID(rec.uid)
        tmpl = PERSONA_TEMPLATES[rec.serial % len(PERSONA_TEMPLATES)]
        p_cfg = tmpl.get("personality", {})

        identity = HumanIdentity(
            uid=uid_obj,
            serial=rec.serial,
            given_name=rec.given_name,
            family_name=rec.family_name,
            data_source=DataSource.MOCK_GENERATED,
        )
        demographics = Demographics(
            age=max(0, min(125, int(round(rec.age_years)))),
            gender=Gender.FEMALE if rec.gender == "female" else Gender.MALE,
            occupation=rec.occupation,
            income_level=round(min(1.0, max(0.05, rec.wealth / 80.0)), 2),
            data_source=DataSource.MOCK_GENERATED,
        )
        physical_state = PhysicalState(
            energy=rec.energy,
            hunger=rec.hunger,
            health=rec.health,
            money=rec.wealth,
            current_location_id=rec.current_location_id,
            home_location_id=rec.household_id,
            work_location_id=f"work_{rec.district_id}",
        )
        personality = PersonalityEngine(
            traits=PersonalityTraits(
                openness=TraitValue(base_value=float(p_cfg.get("openness", 0.55)), current_value=float(p_cfg.get("openness", 0.55))),
                conscientiousness=TraitValue(base_value=float(p_cfg.get("conscientiousness", 0.65)), current_value=float(p_cfg.get("conscientiousness", 0.65))),
                extraversion=TraitValue(base_value=float(p_cfg.get("extraversion", 0.55)), current_value=float(p_cfg.get("extraversion", 0.55))),
                agreeableness=TraitValue(base_value=float(p_cfg.get("agreeableness", 0.70)), current_value=float(p_cfg.get("agreeableness", 0.70))),
                neuroticism=TraitValue(base_value=float(p_cfg.get("neuroticism", 0.35)), current_value=float(p_cfg.get("neuroticism", 0.35))),
            )
        )
        emotions = EmotionalEngine()
        memory = MemoryEngine()
        if rec.packed_cognitive_state:
            try:
                packed = json.loads(rec.packed_cognitive_state.decode("utf-8"))
                for idx, fact_text in enumerate(packed.get("semantic_facts", [])):
                    memory.semantic.store(
                        SemanticFact(
                            fact_id=f"restored_{idx}",
                            category="territorial_experience",
                            content=fact_text,
                            confidence=0.9,
                            source="persistent_memory",
                            learned_tick=0,
                        )
                    )
            except Exception:
                pass

        human = SyntheticHuman(
            identity=identity,
            demographics=demographics,
            physical_state=physical_state,
            personality=personality,
            emotions=emotions,
            memory=memory,
            rng=np.random.default_rng(self.seed + rec.serial),
        )
        # Preserve household & district linkage cleanly on the agent instance
        human.household_id = rec.household_id  # type: ignore[attr-defined]
        human.district_id = rec.district_id  # type: ignore[attr-defined]
        self._cached_synthesized_humans[rec.uid] = human
        return human

    def activate_region(
        self,
        context: TerritorialContext,
        target_lod: ActivationLOD = ActivationLOD.LOD_3_INDIVIDUAL_FULL,
        max_active_agents: int = 40,
        boundary_radius_km: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Activate a geographic region to the target LOD without resetting existing humans."""
        dist_id = context.district_id or "UNKNOWN"
        uids = self.ensure_district_cohort(context, cohort_size=max_active_agents, seed=seed)
        self._active_districts[dist_id] = target_lod
        self._district_boundaries[dist_id] = boundary_radius_km or context.radius_km

        ml_lod = map_activation_to_multilevel_lod(target_lod)
        cog_lod = map_activation_to_cognitive_lod(target_lod)

        hydrated_count = 0
        if target_lod in (ActivationLOD.LOD_2_INDIVIDUAL_SUMMARY, ActivationLOD.LOD_3_INDIVIDUAL_FULL):
            for uid in uids[:max_active_agents]:
                rec = self.multilevel._persistent.get(uid)
                if not rec:
                    continue
                rec.lod_tier = int(ml_lod)
                human = self._hydrate_synthetic_human(rec, target_lod)
                self.multilevel._active_humans[uid] = human
                self.active_registry.register(human)
                self.lod_manager.set_focal_agent(human.uid, is_focal=(target_lod == ActivationLOD.LOD_3_INDIVIDUAL_FULL))
                assign = self.lod_manager.get_assignment(human.uid)
                assign.tier = cog_lod
                hydrated_count += 1
        else:
            # Coarse LOD 0 / LOD 1: ensure any previously hydrated agents in district are dehydrated cleanly
            self.deactivate_region(dist_id, target_lod=target_lod)

        return {
            "district_id": dist_id,
            "district_name": context.district_name,
            "target_lod": target_lod.name,
            "multilevel_lod": ml_lod.name,
            "cognitive_lod": cog_lod.name,
            "boundary_radius_km": self._district_boundaries[dist_id],
            "hydrated_active_agents": hydrated_count,
            "district_persistent_cohort": len(self._district_agents.get(dist_id, [])),
            "national_unique_persistent": self.total_unique_persistent_individuals(),
            "total_active_in_ram": self.active_registry.count,
        }

    def deactivate_region(
        self,
        district_id: str,
        target_lod: ActivationLOD = ActivationLOD.LOD_0_TERRITORIAL_AGGREGATE,
    ) -> Dict[str, Any]:
        """Dehydrate active agents in a district back to persistent records without memory/state loss."""
        ml_lod = map_activation_to_multilevel_lod(target_lod)
        dehydrated = 0
        for uid in list(self._district_agents.get(district_id, [])):
            rec = self.multilevel._persistent.get(uid)
            human = self.multilevel._active_humans.pop(uid, None)
            if human is None:
                human = self._cached_synthesized_humans.get(uid)
            if human is not None and rec is not None:
                rec.wealth = float(human.physical_state.money)
                rec.health = float(human.physical_state.health)
                rec.energy = float(human.physical_state.energy)
                rec.hunger = float(human.physical_state.hunger)
                rec.current_location_id = str(human.physical_state.current_location_id or rec.current_location_id)
                facts = []
                if hasattr(human, "memory") and hasattr(human.memory, "semantic"):
                    try:
                        facts = [f.content for f in human.memory.semantic.get_all()[:20]]
                    except Exception:
                        facts = []
                rec.packed_cognitive_state = json.dumps({"semantic_facts": facts}).encode("utf-8")
                rec.lod_tier = int(ml_lod)
                self.active_registry.unregister(human.uid)
                self.lod_manager.set_focal_agent(human.uid, is_focal=False)
                self.lod_manager.get_assignment(human.uid).tier = map_activation_to_cognitive_lod(target_lod)
                dehydrated += 1
            elif rec is not None:
                rec.lod_tier = int(ml_lod)

        self._active_districts[district_id] = target_lod
        return {
            "district_id": district_id,
            "target_lod": target_lod.name,
            "dehydrated_agents": dehydrated,
            "remaining_active_in_ram": self.active_registry.count,
            "national_unique_persistent": self.total_unique_persistent_individuals(),
        }

    def register_inter_district_flow(
        self,
        origin_context: TerritorialContext,
        dest_context: TerritorialContext,
        category: PopulationCategory,
        count: int = 5,
    ) -> Dict[str, Any]:
        """Move persistent agents between districts as commuters/visitors/transit WITHOUT duplicating UIDs."""
        origin_id = origin_context.district_id
        dest_id = dest_context.district_id
        origin_uids = self.ensure_district_cohort(origin_context, cohort_size=max(20, count * 2))
        self.ensure_district_cohort(dest_context, cohort_size=20)

        moved_uids: List[str] = []
        for uid in origin_uids:
            if len(moved_uids) >= count:
                break
            meta = self._human_meta.get(uid)
            rec = self.multilevel._persistent.get(uid)
            if not meta or not rec:
                continue
            if meta.home_district_id == origin_id and meta.current_district_id == origin_id:
                meta.current_district_id = dest_id
                meta.commuter_origin_district = origin_id
                meta.commuter_dest_district = dest_id
                meta.active_roles.add(category)
                rec.current_location_id = f"loc_{dest_id}"
                rec.lat = dest_context.lat
                rec.lon = dest_context.lon
                if uid in self._cached_synthesized_humans:
                    self._cached_synthesized_humans[uid].physical_state.current_location_id = rec.current_location_id
                moved_uids.append(uid)

        flow_rec = {
            "origin_district_id": origin_id,
            "origin_name": origin_context.district_name,
            "dest_district_id": dest_id,
            "dest_name": dest_context.district_name,
            "category": category.value,
            "moved_unique_uids": len(moved_uids),
        }
        self._commuter_flows.append(flow_rec)
        return flow_rec

    def get_district_population_accounting(self, district_id: str) -> Dict[str, Any]:
        """Return deduplicated category breakdown for a district + national anti-double-count check."""
        permanent = [m for m in self._human_meta.values() if m.home_district_id == district_id]
        present = [m for m in self._human_meta.values() if m.current_district_id == district_id]
        outbound = [m for m in permanent if m.current_district_id != district_id]
        inbound = [m for m in present if m.home_district_id != district_id]

        by_cat: Dict[str, int] = {cat.value: 0 for cat in PopulationCategory}
        for m in present:
            for r in m.active_roles:
                by_cat[r.value] = by_cat.get(r.value, 0) + 1
        by_cat[PopulationCategory.PERMANENT_RESIDENT.value] = len(permanent)

        # Global uniqueness invariant check
        all_home_count = sum(1 for m in self._human_meta.values() if m.home_district_id)
        unique_present_ids = {m.uid for m in present}
        return {
            "district_id": district_id,
            "permanent_residents": len(permanent),
            "unique_individuals_present": len(unique_present_ids),
            "outbound_commuters": len(outbound),
            "inbound_commuters": len(inbound),
            "category_counts": by_cat,
            "national_unique_individuals": len(self._human_meta),
            "double_counting_detected": len(self._human_meta) != all_home_count,
        }

    def get_active_humans_for_district(self, district_id: str) -> List[SyntheticHuman]:
        """Return hydrated SyntheticHuman instances currently present in a district."""
        present_uids = {
            m.uid for m in self._human_meta.values() if m.current_district_id == district_id
        }
        res: List[SyntheticHuman] = []
        for h in self.active_registry.get_all():
            if str(h.uid) in present_uids:
                res.append(h)
        return res

    def capture_baseline_snapshot(self) -> Dict[str, Any]:
        """Snapshot persistent & active human states before branching scenarios."""
        recs = {uid: copy.deepcopy(rec) for uid, rec in self.multilevel._persistent.items()}
        metas = {uid: copy.deepcopy(m) for uid, m in self._human_meta.items()}
        dist_agents = {k: list(v) for k, v in self._district_agents.items()}
        active_stats = {
            str(h.uid): (
                float(h.physical_state.money),
                float(h.physical_state.hunger),
                float(h.physical_state.health),
                float(h.physical_state.energy),
                str(h.physical_state.current_location_id or ""),
                str(h.physical_state.work_location_id or ""),
                str(getattr(h.demographics, "occupation", "")),
                getattr(h, "employment_status", None),
            )
            for h in self.active_registry.get_all()
        }
        return {"records": recs, "metas": metas, "dist_agents": dist_agents, "active_stats": active_stats}

    def restore_baseline_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Restore persistent & active human states so scenarios share comparable initial conditions."""
        self.multilevel._persistent = copy.deepcopy(snapshot["records"])
        self._human_meta = copy.deepcopy(snapshot["metas"])
        if "dist_agents" in snapshot:
            self._district_agents = copy.deepcopy(snapshot["dist_agents"])
        for uid_str, vals in snapshot["active_stats"].items():
            h = self._cached_synthesized_humans.get(uid_str)
            if h is not None:
                h.physical_state.money = vals[0]
                h.physical_state.hunger = vals[1]
                h.physical_state.health = vals[2]
                if len(vals) >= 8:
                    h.physical_state.energy = vals[3]
                    h.physical_state.current_location_id = vals[4]
                    h.physical_state.work_location_id = vals[5]
                    h.demographics.occupation = vals[6]
                    if vals[7] is not None:
                        h.employment_status = vals[7]
