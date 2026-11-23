# NATIONAL POPULATION & TERRITORIAL COVERAGE REPORT (EL SALVADOR)

**Framework**: Decree Law 762 (Reorganización Político-Administrativa de El Salvador) + OpenStreetMap Geofabrik Extract (`2026-11-13`)  
**Scope**: Full national territory (`13.0°N–14.5°N`, `-90.2°W–-87.6°W`)

---

## 1. Administrative Hierarchy Coverage (`saltbor/datasets/salvadoran/territory_data.py`)

Verified directly from runtime dataset inspection:
- **Departments**: **14** (`SALVADORAN_DEPARTMENTS_P8`, zones: Occidental, Central, Paracentral, Oriental).
- **Municipalities**: **44** (`SALVADORAN_MUNICIPALITIES_P8`, D.L. 762 consolidated municipalities).
- **Districts**: **262** (`SALVADORAN_DISTRICTS_P8`, all former municipalities converted to districts under D.L. 762).
- **Known Cantones**: **474** indexed across districts (`district.known_cantones`).
- **Registered Approximate National Population**: **6,578,000** residents across the 262 districts.
- **Pre-curated P8 Establishments**: **41** (`SALVADORAN_ESTABLISHMENTS_P8`).

---

## 2. OpenStreetMap Spatial Coverage (`saltbor/datasets/gis/ingested/geography.sqlite`)

Verified directly from `dataset_provenance` and `layer_provenance`:
- **Total Ingested Features**: **151,227** rows in `geographic_features` (manifest records `151,251` total processed; `ODbL-1.0`, `EPSG:4326`).

| Layer | Geometry | Feature Count | Partial? | Coverage & Limitations |
| :--- | :--- | :---: | :---: | :--- |
| `roads` | `line` | 121,344 | No (National) | Geometric connectivity only; OSM turn restrictions absent |
| `landuse` | `polygon` | 10,887 | No (National) | Coarse OSM polygons (residential, commercial, agricultural, forest), not cadastral parcels |
| `pois` | `point` | 8,011 | No (National) | Presence of `food_service` (1,942), `health` (673), `education` (422), `finance` (332), `public_safety` (144), `government` (58), `market` (39), `public_service` (38), `other` (4,363). Capacity/hours modeled separately |
| `waterways` | `line` | 4,433 | No (National) | Rivers (1,437), streams (2,548), drains (402), canals (46); discharge volume absent |
| `places` | `point` | 2,657 | No (National) | Hamlets (1,368), villages (485), towns (259), localities (246), farms (153), suburbs (129), cities (15), island (1), capital (1) |
| `water` | `polygon` | 1,437 | No (National) | Water bodies and reservoirs |
| `buildings` | `polygon` | 989 | **YES (`is_partial=1`)** | **Restricted to San Salvador Centro bbox `[-89.202, 13.693, -89.186, 13.704]`**. Outside this bbox, building footprints are unavailable in `geography.sqlite` and must be reported as missing/partial |
| `transport` | `point` | 897 | No (National) | Bus stops (775), bus stations (89), taxi ranks (9), railway stations (3), airports (3), ferry terminals (2); schedules absent |
| `adminareas` | `polygon` | 474 | No (National) | Historical OSM boundary relations; D.L. 762 hierarchy in `territory_data.py` is authoritative |
| `natural` | `polygon` | 122 | No (National) | Coastline and terrain polygons |

---

## 3. Synthetic Population Categories & Anti-Double-Counting Architecture

`NationalPopulationActivationManager` and `TerritorialPopulationContextEngine` support national simulation without instantiating 6.58M full-cognition agents simultaneously, strictly classifying and deduplicating across the **8 required population categories**:

1. `PERMANENT_RESIDENT` — Registered in `home_district_id`.
2. `TEMPORARY_POPULATION` — Seasonal agricultural/short-term residents temporarily present in `current_district_id`.
3. `DAILY_COMMUTER` — Persistent `home_district_id != work_or_study_district_id`; counted **once** in national `unique_uid` registry, accounted separately as `outbound_commuters` in origin and `inbound_commuters` in destination.
4. `STUDENT` — School-age cohort (`age 5–22`) attending educational facilities locally or across district lines.
5. `WORKER` — Economically active cohort (`age 18–65`) in formal, informal, agricultural, or commercial labor.
6. `VISITOR` — Non-resident periodic visitors drawn to commercial centers/markets.
7. `COMMERCIAL_FLOW` — Directed purchasing/supply trips visiting commercial corridors.
8. `TRANSIT_POPULATION` — Pass-through highway/bus-corridor travelers along trunk/primary/secondary roads.

### Double-Counting Invariant

$$\text{National Unique Individuals} = \left|\bigcup_{d \in \text{Districts}} \{\text{uid} \mid \text{home\_district}(\text{uid}) = d\}\right|$$

A commuter residing in Santa Tecla (`0511` / La Libertad Sur) and working in San Salvador Centro (`0614`) keeps one unique `uid` and one `PersistentIndividualRecord`; both districts track her role (`outbound_commuter` vs `inbound_worker`) without inflating total national population or duplicating household income.

### Demographic Grounding & Uncertainty Exposure

Where block-level census microdata or building footprints (`buildings` outside San Salvador Centro) are unavailable, population synthesis explicitly records:
- **Basis**: D.L. 762 district population (`approx_population`), urban/rural core flag (`is_urban_core`), OSM residential/commercial/agricultural landuse shares, and POI density.
- **Method**: Calibrated Salvadoran demographic priors (household size, age pyramid, informal employment share, remittance prevalence).
- **Explicit Uncertainty**: Exposed in `TerritorialPopulationContextEngine` output and `EvidenceBundle.missing_indicators` whenever local survey/census/building geometry is missing.
