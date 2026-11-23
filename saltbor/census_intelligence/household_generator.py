"""Synthetic Household & Population Generation Engine (Phase 1.18 Section 7).

Builds households FIRST grounded on allocated residential anchors, then
generates internally consistent household members (age, sex, family relations,
education level/attendance/lag, labor activity/occupation/income intervals,
spatial mobility destinations, and behavioral constraints).
Supports scalable hybrid simulation (exact 1:1 households at community scale,
stratified weighted cohorts at district/department/national scale) and hydrates
into SALTBOR's `SyntheticHuman` + `NationalPopulationActivationManager`.
"""

from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from shapely.geometry import Point, shape

from saltbor.conversational.population_activation import (
    NationalHumanMetadata,
    NationalPopulationActivationManager,
)
from saltbor.conversational.schemas import ActivationLOD, PopulationCategory, TerritorialContext
from saltbor.population.human import SyntheticHuman
from saltbor.population.multilevel.models import LODLevel, PersistentIndividualRecord

from saltbor.census_intelligence.schemas import (
    CensusQueryResult,
    DiscoveredTerritorialContext,
    PopulationAllocationResult,
    SyntheticHousehold,
    SyntheticPerson,
    SyntheticPopulationBatch,
)

_AGE_GROUPS: List[Tuple[str, int, int]] = [
    ("0-4", 0, 4),
    ("5-9", 5, 9),
    ("10-14", 10, 14),
    ("15-19", 15, 19),
    ("20-24", 20, 24),
    ("25-29", 25, 29),
    ("30-34", 30, 34),
    ("35-39", 35, 39),
    ("40-44", 40, 44),
    ("45-49", 45, 49),
    ("50-54", 50, 54),
    ("55-59", 55, 59),
    ("60-64", 60, 64),
    ("65+", 65, 86),
]

_URBAN_OCCUPATIONS = [
    ("Comerciante", "informal"),
    ("Empleado de Comercio/Servicios", "formal"),
    ("Vendedor por Cuenta Propia", "informal"),
    ("Operario/Técnico", "formal"),
    ("Docente/Profesional", "formal"),
    ("Motorista/Transporte", "informal"),
    ("Trabajador Administrativo", "formal"),
    ("Servicios Personales/Hogar", "informal"),
]

_RURAL_OCCUPATIONS = [
    ("Agricultor/Productor", "informal"),
    ("Jornalero Agrícola", "informal"),
    ("Comerciante Local", "informal"),
    ("Albañil/Construcción", "informal"),
    ("Docente/Servicio Público", "formal"),
    ("Costurera/Artesano", "informal"),
    ("Empleado Agroindustrial", "formal"),
    ("Transporte Rural", "informal"),
]


def _age_to_group(age: int) -> str:
    for lbl, lo, hi in _AGE_GROUPS:
        if lo <= age <= hi:
            return lbl
    return "65+"


def _sample_key(rng: np.random.Generator, dist: Dict[str, float]) -> str:
    keys = list(dist.keys())
    probs = np.array([max(0.0, float(dist[k])) for k in keys], dtype=float)
    s = probs.sum()
    probs = (probs / s) if s > 0 else np.ones(len(keys)) / len(keys)
    idx = int(rng.choice(len(keys), p=probs))
    return keys[idx]


def _bracket_to_midpoint(bracket: str, rng: np.random.Generator) -> float:
    ranges = {
        "0_365": (180.0, 365.0),
        "365_600": (365.0, 600.0),
        "600_1000": (600.0, 1000.0),
        "1000_1800": (1000.0, 1800.0),
        "1800_plus": (1800.0, 3100.0),
    }
    lo, hi = ranges.get(bracket, (365.0, 800.0))
    return round(float(rng.uniform(lo, hi)), 2)


def _stratum_from_income(income_usd: float) -> str:
    if income_usd < 420.0:
        return "low"
    if income_usd < 800.0:
        return "medium_low"
    if income_usd < 1450.0:
        return "medium"
    return "medium_high"


class SyntheticHouseholdGenerationEngine:
    """Generates calibrated households-first synthetic populations linked to residential geometry."""

    def generate_population(
        self,
        discovery: DiscoveredTerritorialContext,
        census: CensusQueryResult,
        allocation: PopulationAllocationResult,
        seed: int = 42,
        max_sample_households: int = 450,
    ) -> SyntheticPopulationBatch:
        """Build households first, then coherent family members grounded in residential anchors."""
        rng = np.random.default_rng(seed + sum(ord(c) for c in discovery.primary_district_id))
        target_pop = max(10, int(allocation.allocated_population_target))
        target_hh = max(3, int(allocation.allocated_households_target))

        is_weighted = target_hh > max_sample_households
        n_hh_to_build = max_sample_households if is_weighted else target_hh
        hh_weight = round(target_hh / max(1, n_hh_to_build), 4) if is_weighted else 1.0

        # Collect valid residential building anchors; fall back strictly inside primary_geom
        primary_geom = shape(discovery.expansion.primary_area.geometry_geojson)
        res_anchors = [a for a in allocation.building_anchors if a.allocated_residential]
        if not res_anchors:
            c = primary_geom.centroid
            res_anchors = []
            fallback_coords: List[Tuple[float, float, Optional[str]]] = [(float(c.y), float(c.x), None)]
        else:
            fallback_coords = [(a.lat, a.lon, a.feature_id) for a in res_anchors]

        hh_size_dist = census.household_size_distribution or {
            "1": 0.145, "2": 0.22, "3": 0.265, "4": 0.205, "5": 0.10, "6": 0.045, "7+": 0.02,
        }
        ehpm = census.ehpm_priors or {}
        income_brackets = ehpm.get(
            "household_income_brackets_monthly_usd",
            {"0_365": 0.24, "365_600": 0.28, "600_1000": 0.25, "1000_1800": 0.15, "1800_plus": 0.08},
        )
        attendance_rates = ehpm.get(
            "school_attendance_rates_by_level",
            {
                "parvularia_4_6": 0.65,
                "basica_ciclo_1_7_9": 0.95,
                "basica_ciclo_2_10_12": 0.94,
                "basica_ciclo_3_13_15": 0.87,
                "bachillerato_16_18": 0.69,
                "superior_19_24": 0.22,
            },
        )
        lag_rate = float(ehpm.get("educational_lag_rate_school_age", 0.12))
        informal_share = float(ehpm.get("informal_employment_share", 0.62 if discovery.is_urban else 0.78))
        female_head_share = float(census.female_headed_household_share or 0.45)

        households: List[SyntheticHousehold] = []
        persons: List[SyntheticPerson] = []

        # Step 1: Build Households First
        anchor_cursor = 0
        minx, miny, maxx, maxy = primary_geom.bounds
        for hh_idx in range(n_hh_to_build):
            hh_id = f"HH_{discovery.primary_district_id}_{seed}_{hh_idx:05d}"

            # Choose spatial anchor strictly inside residential footprint / primary polygon
            if fallback_coords:
                base_lat, base_lon, b_id = fallback_coords[anchor_cursor % len(fallback_coords)]
                anchor_cursor += 1
                # Tiny sub-parcel offset (~4-8m) while staying inside primary_geom
                cand_lat = round(base_lat + float(rng.normal(0.0, 0.00005)), 6)
                cand_lon = round(base_lon + float(rng.normal(0.0, 0.00005)), 6)
                if not primary_geom.contains(Point(cand_lon, cand_lat)):
                    cand_lat, cand_lon = round(base_lat, 6), round(base_lon, 6)
            else:
                b_id = None
                cand_lat, cand_lon = discovery.center_lat, discovery.center_lon
                for _ in range(12):
                    rx = float(rng.uniform(minx, maxx))
                    ry = float(rng.uniform(miny, maxy))
                    if primary_geom.contains(Point(rx, ry)):
                        cand_lat, cand_lon = round(ry, 6), round(rx, 6)
                        break

            sz_key = _sample_key(rng, hh_size_dist)
            hh_size = 7 if sz_key == "7+" else int(sz_key)
            if hh_size == 1:
                comp = "unipersonal"
            elif hh_size >= 5 and rng.random() < 0.48:
                comp = "extended"
            elif rng.random() < 0.24:
                comp = "single_parent"
            else:
                comp = "nuclear"

            head_sex = "F" if rng.random() < female_head_share else "M"
            bracket = _sample_key(rng, income_brackets)
            hh_income = _bracket_to_midpoint(bracket, rng)
            stratum = _stratum_from_income(hh_income)
            tenure = "owned" if rng.random() < 0.654 else "rented_or_other"

            # Step 2: Generate Members inside this Household respecting family roles & ages
            head_age = int(rng.integers(24, 72))
            member_specs: List[Tuple[str, int, str]] = [("head", head_age, head_sex)]

            remaining = hh_size - 1
            if remaining > 0 and comp in ("nuclear", "extended"):
                sp_age = max(18, min(85, head_age + int(rng.integers(-6, 7))))
                sp_sex = "M" if head_sex == "F" else "F"
                member_specs.append(("spouse", sp_age, sp_sex))
                remaining -= 1

            if remaining > 0 and comp == "extended":
                el_age = max(65, min(86, head_age + int(rng.integers(22, 34))))
                el_sex = "F" if rng.random() < 0.54 else "M"
                member_specs.append(("elder_relative", el_age, el_sex))
                remaining -= 1

            # Children (respect parent-child age difference >= 15 yrs)
            max_child_age = max(1, min(22, head_age - 16))
            for _ in range(remaining):
                if rng.random() < 0.82 or max_child_age >= 18:
                    c_age = int(rng.integers(0, max_child_age + 1))
                    rel = "child"
                else:
                    c_age = int(rng.integers(18, 48))
                    rel = "other_relative"
                c_sex = "F" if rng.random() < 0.52 else "M"
                member_specs.append((rel, c_age, c_sex))

            member_ids: List[str] = []
            dep_cnt = 0
            kids_cnt = 0
            adults_cnt = 0
            elders_cnt = 0

            for m_idx, (rel, age, sex) in enumerate(member_specs):
                pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"saltbor:118:{hh_id}:{m_idx}"))
                member_ids.append(pid)

                if age < 18:
                    kids_cnt += 1
                    dep_cnt += 1
                elif age >= 65:
                    elders_cnt += 1
                    dep_cnt += 1
                else:
                    adults_cnt += 1

                # Education attributes calibrated to EHPM attendance & schooling years
                enrolled_lvl: Optional[str] = None
                attending: Optional[bool] = None
                lag_yrs = 0

                if age <= 3:
                    ed_level = "primera_infancia"
                    sch_years = 0
                    act = "child_under_5"
                    occ = "Menor en Hogar"
                    formality = "not_applicable"
                    p_income_interval = None
                    p_income_usd = 0.0
                    dest = "home"
                    mob_need = "caregiver_accompanied"
                elif 4 <= age <= 6:
                    attending = bool(rng.random() < float(attendance_rates.get("parvularia_4_6", 0.65)))
                    enrolled_lvl = "parvularia" if attending else None
                    ed_level = "parvularia" if attending else "sin_educacion_inicial"
                    sch_years = max(0, age - 4) if attending else 0
                    act = "student" if attending else "inactive_home"
                    occ = "Estudiante Parvularia" if attending else "Menor en Hogar"
                    formality = "not_applicable"
                    p_income_interval = None
                    p_income_usd = 0.0
                    dest = "school" if attending else "home"
                    mob_need = "escorted_walk_short"
                elif 7 <= age <= 18:
                    if age <= 9:
                        lvl_key, att_key = "basica_ciclo_1", "basica_ciclo_1_7_9"
                    elif age <= 12:
                        lvl_key, att_key = "basica_ciclo_2", "basica_ciclo_2_10_12"
                    elif age <= 15:
                        lvl_key, att_key = "basica_ciclo_3", "basica_ciclo_3_13_15"
                    else:
                        lvl_key, att_key = "bachillerato", "bachillerato_16_18"

                    attending = bool(rng.random() < float(attendance_rates.get(att_key, 0.85)))
                    if attending and rng.random() < lag_rate:
                        lag_yrs = int(rng.integers(1, 3))
                    enrolled_lvl = lvl_key if attending else None
                    expected_yrs = max(1, age - 6 - lag_yrs)
                    sch_years = expected_yrs if attending else max(0, expected_yrs - int(rng.integers(1, 4)))
                    ed_level = lvl_key if attending else "escolaridad_incompleta"
                    if attending:
                        act = "student"
                        occ = f"Estudiante ({lvl_key})"
                        formality = "not_applicable"
                        p_income_interval = None
                        p_income_usd = 0.0
                        dest = "school"
                    else:
                        act = "employed" if age >= 16 and rng.random() < 0.45 else "inactive_home"
                        occ = "Trabajador Joven" if act == "employed" else "Sin Asistencia Escolar"
                        formality = "informal" if act == "employed" else "not_applicable"
                        p_income_interval = "0_365" if act == "employed" else None
                        p_income_usd = round(float(rng.uniform(120.0, 290.0)), 2) if act == "employed" else 0.0
                        dest = "workplace" if act == "employed" else "neighborhood"
                    mob_need = "school_commute" if attending else "local_errands"
                else:
                    # Adults 19+
                    base_sch = 8.4 if discovery.is_urban else 5.6
                    sch_years = int(max(0, min(18, round(rng.normal(base_sch, 3.2)))))
                    if sch_years == 0:
                        ed_level = "sin_escolaridad"
                    elif sch_years <= 6:
                        ed_level = "basica_primaria"
                    elif sch_years <= 9:
                        ed_level = "basica_tercer_ciclo"
                    elif sch_years <= 12:
                        ed_level = "bachillerato"
                    else:
                        ed_level = "educacion_superior"

                    if age <= 24 and rng.random() < float(attendance_rates.get("superior_19_24", 0.22)):
                        attending = True
                        enrolled_lvl = "superior"
                        act = "student"
                        occ = "Estudiante Universitario/Técnico"
                        formality = "not_applicable"
                        p_income_interval = None
                        p_income_usd = 0.0
                        dest = "university_or_training"
                        mob_need = "transit_commute"
                    elif age >= 65 and rng.random() < 0.72:
                        attending = False
                        act = "retired"
                        occ = "Adulto Mayor"
                        formality = "not_applicable"
                        p_income_interval = "0_365"
                        p_income_usd = round(float(rng.uniform(100.0, 350.0)), 2)
                        dest = "health_and_market"
                        mob_need = "accessible_local"
                    else:
                        attending = False
                        emp_prob = 0.76 if sex == "M" else 0.52
                        if rng.random() < emp_prob:
                            act = "employed"
                            occ_pool = _URBAN_OCCUPATIONS if discovery.is_urban else _RURAL_OCCUPATIONS
                            occ, def_form = occ_pool[(hh_idx + m_idx) % len(occ_pool)]
                            formality = "informal" if rng.random() < informal_share else def_form
                            p_income_usd = round(max(180.0, hh_income / max(1, adults_cnt) * float(rng.uniform(0.75, 1.15))), 2)
                            p_income_interval = (
                                "0_365" if p_income_usd < 365 else ("365_600" if p_income_usd < 600 else "600_1000")
                            )
                            dest = "workplace_and_commerce"
                            mob_need = "daily_commute"
                        else:
                            act = "unemployed" if rng.random() < 0.14 else "inactive_home"
                            occ = "Buscando Empleo" if act == "unemployed" else "Quehaceres del Hogar"
                            formality = "not_applicable"
                            p_income_interval = None
                            p_income_usd = 0.0
                            dest = "market_and_services"
                            mob_need = "local_services"

                persons.append(
                    SyntheticPerson(
                        person_id=pid,
                        household_id=hh_id,
                        age=age,
                        age_group=_age_to_group(age),
                        sex=sex,  # type: ignore[arg-type]
                        relationship_to_head=rel,  # type: ignore[arg-type]
                        education_level=ed_level,
                        schooling_years=sch_years,
                        enrolled_level=enrolled_lvl,
                        attending_school=attending,
                        educational_lag_years=lag_yrs,
                        activity_condition=act,  # type: ignore[arg-type]
                        occupation=occ,
                        employment_formality=formality,  # type: ignore[arg-type]
                        monthly_income_interval_usd=p_income_interval,
                        estimated_monthly_income_usd=p_income_usd,
                        socioeconomic_stratum=stratum,
                        home_lat=cand_lat,
                        home_lon=cand_lon,
                        habitual_destination_type=dest,
                        mobility_need_category=mob_need,
                        cost_sensitivity=round(0.85 if stratum == "low" else (0.60 if stratum == "medium_low" else 0.35), 2),
                        expansion_weight=hh_weight,
                        unavailable_attributes=["exact_household_survey_microdata"],
                    )
                )

            households.append(
                SyntheticHousehold(
                    household_id=hh_id,
                    building_feature_id=b_id,
                    home_lat=cand_lat,
                    home_lon=cand_lon,
                    district_id=discovery.primary_district_id,
                    household_size=len(member_specs),
                    family_composition=comp,  # type: ignore[arg-type]
                    head_sex=head_sex,  # type: ignore[arg-type]
                    dependents_count=dep_cnt,
                    children_adolescents_count=kids_cnt,
                    adults_count=adults_cnt,
                    elderly_count=elders_cnt,
                    monthly_income_bracket_usd=bracket,
                    estimated_monthly_income_usd=hh_income,
                    socioeconomic_stratum=stratum,  # type: ignore[arg-type]
                    housing_tenure=tenure,  # type: ignore[arg-type]
                    expansion_weight=hh_weight,
                    member_ids=member_ids,
                )
            )

        scale_label = "COMMUNITY" if target_pop < 5000 else ("ZONE" if target_pop < 25000 else "DISTRICT")
        return SyntheticPopulationBatch(
            batch_id=f"POP_{discovery.primary_district_id}_{seed}_{len(households)}",
            seed=seed,
            district_id=discovery.primary_district_id,
            area_label=discovery.expansion.primary_area.label,
            generation_scale=scale_label,  # type: ignore[arg-type]
            represented_population_total=int(round(len(persons) * hh_weight)),
            represented_households_total=target_hh,
            simulated_sample_persons=len(persons),
            simulated_sample_households=len(households),
            is_weighted_cohort=is_weighted,
            households=households,
            persons=persons,
        )

    @staticmethod
    def hydrate_to_synthetic_humans(
        batch: SyntheticPopulationBatch,
        population_manager: NationalPopulationActivationManager,
        context: TerritorialContext,
        max_active: int = 40,
    ) -> List[SyntheticHuman]:
        """Bridge grounded Phase 1.18 households/persons cleanly into NationalPopulationActivationManager."""
        dist_id = context.district_id or batch.district_id
        selected = batch.persons[:max_active] if len(batch.persons) <= max_active else [
            batch.persons[int(i * len(batch.persons) / max_active)] for i in range(max_active)
        ]

        uids: List[str] = []
        for idx, p in enumerate(selected):
            uid = p.person_id
            if uid not in population_manager.multilevel._persistent:
                serial = population_manager.identity_factory.next_serial
                population_manager.identity_factory.advance_to(serial + 1)
                daily_cash = max(4.0, round((p.estimated_monthly_income_usd or 220.0) / 14.0, 2))
                rec = PersistentIndividualRecord(
                    uid=uid,
                    serial=serial,
                    given_name="Residente",
                    family_name=f"Sintético {idx + 1}",
                    gender="female" if p.sex == "F" else "male",
                    age_years=float(p.age),
                    occupation=p.occupation,
                    current_location_id=f"loc_{dist_id}",
                    lat=p.home_lat,
                    lon=p.home_lon,
                    wealth=daily_cash,
                    health=0.90,
                    energy=0.85,
                    hunger=0.25,
                    happiness=0.65,
                    community_id=f"comm_{dist_id}",
                    district_id=dist_id,
                    household_id=p.household_id,
                    lod_tier=int(LODLevel.LOD_0_INDIVIDUAL),
                )
                population_manager.multilevel.register_individual(rec)
                cat = PopulationCategory.STUDENT if p.activity_condition == "student" else (
                    PopulationCategory.WORKER if p.activity_condition == "employed" else PopulationCategory.PERMANENT_RESIDENT
                )
                population_manager._human_meta[uid] = NationalHumanMetadata(
                    uid=uid,
                    home_district_id=dist_id,
                    current_district_id=dist_id,
                    household_id=p.household_id,
                    primary_category=PopulationCategory.PERMANENT_RESIDENT,
                    active_roles={PopulationCategory.PERMANENT_RESIDENT, cat},
                )
            uids.append(uid)

        # Merge into district list without resetting or erasing existing identities
        existing = population_manager._district_agents.setdefault(dist_id, [])
        for uid in uids:
            if uid not in existing:
                existing.append(uid)

        hydrated: List[SyntheticHuman] = []
        for uid in uids:
            rec = population_manager.multilevel._persistent.get(uid)
            if rec:
                h = population_manager._hydrate_synthetic_human(rec, ActivationLOD.LOD_3_INDIVIDUAL_FULL)
                population_manager.multilevel._active_humans[uid] = h
                population_manager.active_registry.register(h)
                population_manager.lod_manager.set_focal_agent(h.uid, is_focal=True)
                hydrated.append(h)
        return hydrated
