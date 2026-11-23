# PHASE 1.17 — MANDATORY ADDENDUM: REAL-WORLD TERRITORIAL EVIDENCE AUDIT

**Audit Date**: 2026-11-23  
**Audited Database**: [`saltbor_studio.db`](file:///c:/GIT%20HUB/sv%20people/saltbor_studio.db) (Conversation `CONV_26f0f3d832`, preserved unmodified)  
**Audited Runs**:  
1. **General Commercial Establishment in Santa Tecla** (`SCEN_9393e2f8` / `EXEC_89a6765e8c`, `seed=42`, `30` days)  
2. **Community Pupusería in Santa Tecla** (`SCEN_96f14a52` / `EXEC_41fad3fac1`, `seed=42`, `30` days)  

**Honesty Rule**: Archived values in `saltbor_studio.db` are preserved untouched. Every finding is classified strictly as `CONFIRMED`, `SUSPECTED`, `NOT_REPRODUCIBLE`, or `UNVERIFIED`.

---

## 1. Reproduction Report (Section A)

### 1.1 Exact Parameters Recovered from `saltbor_studio.db`

| Field | Scenario 1 — General Commercial | Scenario 2 — Community Pupusería |
| :--- | :--- | :--- |
| `conversation_id` | `CONV_26f0f3d832` | `CONV_26f0f3d832` |
| `scenario_id` / `execution_id` | `SCEN_9393e2f8` / `EXEC_89a6765e8c` | `SCEN_96f14a52` / `EXEC_41fad3fac1` |
| User Turn Text | `"Quiero abrir un negocio en Santa Tecla."` | Turn 3: `"SERA UNA PUPUSERIA Y ESTARA CERCA DEL PASEO TECLEÑO"` → unresolved (`SCEN_fbf73699`); Turn 5 + Map Pin: `"NEGOCIO DE PUPUSERIA"` |
| `category` / `intervention_id` | `COMMERCIAL_ESTABLISHMENT` / `INT_COMMERCIAL_ESTABLISHMENT_385079` | `PUPUSERIA` / `INT_PUPUSERIA_81b9c2` |
| `location_query` & Coordinates | `"Santa Tecla"`, `(13.676, -89.28)` | `"(13.67529, -89.28761)"`, `(13.67529, -89.28761)` |
| Nearest OSM Road | `"Avenida Robert Baden Powell"` | `"1a Avenida Norte"` |
| `district_id` / `seed` / `horizon` | `dist_santa_tecla` / `42` / `30` days (`4` × `7.5` d/seg) | `dist_santa_tecla` / `42` / `30` days (`4` × `7.5` d/seg) |
| `unit_price_usd` / `unit_cost_ratio` | `$2.25` / `0.60` | `$0.90` / `0.50` |
| `capacity` / `opening_hours` | `20` / `(8, 19)` | `24` / `(6, 21)` |
| `workforce_count` / `daily_wage_usd` | `2` / `$12.50` | `2` / `$12.00` |
| `daily_fixed_cost_usd` / `initial_capital` | `$8.00` / `$320.00` | `$7.00` / `$220.00` |
| `map_visible` | `false` | `true` |

### 1.2 Bit-for-Bit Reproduction Comparison (Pre-1.17 `pois`-only vs Post-1.17 GIS)

Both runs occurred **before** Phase 1.17 re-ingested OSM polygon POIs (`pois_a`) and nationwide buildings (`buildings`). Replaying the exact parameters with pre-1.17 point-only `pois` (`emulate_pre117_pois_only=True`) reproduces **100% of all archived indicators bit-for-bit**:

| Indicator | SCEN 1 Archived (`saltbor_studio.db`) | SCEN 1 Replay (Pre-1.17) | SCEN 2 Archived (`saltbor_studio.db`) | SCEN 2 Replay (Pre-1.17) | SCEN 2 Replay (Current `pois_a`) |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `resident_population_approx` | `150,000` | `150,000` | `150,000` | `150,000` | `150,000` |
| `unique_active_cohort` | `40` | `40` | `40` | `40` | `40` |
| `inbound_commuters` | `0` | `0` | `0` | `0` | `0` |
| `household_avg_cash_usd` | `$34.56` | `$34.56` | `$34.95` | `$34.95` | `$34.95` |
| `commercial_visitors` | `7,593.6` | `7,593.6` | `7,945.1` | `7,945.1` | `7,945.1` |
| `commercial_browsers_without_purchase` | `5,413.9` | `5,413.9` | `4,289.0` | `4,289.0` | `4,289.0` |
| `commercial_purchasers` | `2,179.7` | `2,179.7` | `3,656.2` | `3,656.2` | `3,656.2` |
| `commercial_conversion_rate` | `0.2870` (`28.7%`) | `0.2870` | `0.4602` (`46.02%`) | `0.4602` | `0.4602` |
| `commercial_revenue_usd` | `$4,904.13` | `$4,904.13` | `$3,290.50` | `$3,290.50` | `$3,290.50` |
| `commercial_net_profit_usd` | `$1,596.66` | `$1,596.66` | `$1,386.56` | `$1,386.56` | `$1,386.56` |
| `school_attendance_rate` | `1.0000` (`100%`) | `1.0000` | `0.3543` (`35.43%`) | `0.3543` | `1.0000` |
| `edu_unmet_person_days` | `0.0` | `0.0` | `2,460.0` | `2,460.0` | `0.0` |
| `mobility_accessibility_index` | `0.989` | `0.989` | `0.989` | `0.989` | `0.989` |
| `household_income_earned_usd` | `$187.50` | `$187.50` | `$180.00` | `$180.00` | `$180.00` |
| `total_transactions` / `diff` | `85` / `$0.00` | `85` / `$0.00` | `106` / `$0.00` | `106` / `$0.00` | `106` / `$0.00` |
| `data_quality_score` | `1.00` | `1.00` | `1.00` | `1.00` | `1.00` |

**Result**: Both historical runs are **100% deterministically reproducible**.

---

## 2. Metric Provenance Matrix (Pupusería Scenario `EXEC_41fad3fac1`)

Every requested metric is classified using strict provenance origins:

| Metric & Reported Value | Exact Calculation Formula | Code Location | Provenance Origin Classification |
| :--- | :--- | :--- | :--- |
| **150,000 estimated residents** | Lookup of `dist_santa_tecla.approx_population` | `territory_data.py`; [`territorial_context.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/territorial_context.py#L717) | `GEOGRAPHIC_DATASET` (approx. municipal/district prior, not block census) |
| **40 activated synthetic agents** | `len(humans)` from `max_active_agents=40` (`ensure_district_cohort`) | [`population_activation.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/population_activation.py#L180-L303) | `AGGREGATED_SYNTHETIC_AGENTS` (capped sample cohort) |
| **0 incoming commuters** | Count where `m.home_district_id != m.current_district_id`; `register_inter_district_flow()` was not invoked | [`population_activation.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/population_activation.py#L531) | `AGGREGATED_SYNTHETIC_AGENTS` (zero because flow engine not wired into Stage B) |
| **$34.95 average liquidity** | Post-run `mean(h.physical_state.money)` = initial mean `$31.62` + `($180.00 wages - $46.80 unscaled purchases) / 40` = `$34.95` | [`evidence_engine.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/evidence_engine.py#L110-L122) | `AGGREGATED_SYNTHETIC_AGENTS` (**Unit mismatch**: unscaled wages & unscaled spend divided across 40 agents) |
| **7,945.1 total visits** | `(29 + 27 + 31 + 26 = 113 raw cohort visits) * scale_mult`, where `pop_scale = min(15.0, 150000 / (40*400)) = 9.375` and `scale_mult = round(7.5 * 9.375, 2) = 70.31` | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L773-L932) | `EXTRAPOLATED_COHORT` (`DETERMINISTIC_MULTIPLIER` `70.31x` applied to `113` visits) |
| **4,289.0 visitors without purchases** | `(12 + 17 + 15 + 17 = 61 non-buying visits) * 70.31` (`843.7 + 1195.3 + 1054.7 + 1195.3 = 4289.0`) | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L910-L933) | `EXTRAPOLATED_COHORT` |
| **3,656.2 purchases** | `(17 + 10 + 16 + 9 = 52 DINE purchases) * 70.31` (`1195.3 + 703.1 + 1125.0 + 632.8 = 3656.2`). Note rounding drift: `4289.0 + 3656.2 = 7945.2 != 7945.1` | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L887-L934) | `EXTRAPOLATED_COHORT` (`52` ledger buys × `70.31`) |
| **46.02% conversion** | `round(3656.2 / 7945.1, 4) = 0.4602` (`52 / 113 = 0.460177`) | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L1024-L1026) | `DIRECT_SIMULATION_EVENT` / ratio of extrapolated visits |
| **$3,290.50 gross commercial revenue** | `(52 purchases * $0.90 = $46.80 unscaled ledger sales) * 70.31` (`1075.74 + 632.79 + 1012.46 + 569.51 = $3,290.50`) | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L892-L935) | `EXTRAPOLATED_COHORT` (**Unscaled ledger cash** = `$46.80`, extrapolated `70.31x` = `$3,290.50`) |
| **$1,386.56 operating net result** | `$3,290.50` scaled revenue − `$1,645.24` scaled COGS (`0.50x`, unledgered) − `$180.00` unscaled Seg-0 payroll − `$78.70` cash-capped unscaled fixed costs | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L1005-L1031) | `DETERMINISTIC_MULTIPLIER` + mixed-scale accounting defect (`$540` wages & `$131.30` fixed costs silently skipped!) |
| **35.43% educational attendance** | `srv_edu / school_demand_total` = `(45 * 30 = 1,350) / (127 * 30 = 3,810) = 0.35433`, from `1` point-only school POI (`1 * 45 = 45/day`) vs `round(9 * 9.375 * 1.5) = 127/day` | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L719-L966) | `DETERMINISTIC_MULTIPLIER` (`45 seats/OSM point POI`) + omitted `pois_a` polygons + ignored `school_active=False` |
| **2,460.0 unmet education person-days** | `(127 - 45 = 82 unmet/day) * 4 segs * 7.5 days/seg = 2,460.0` | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L949-L965) | `DETERMINISTIC_MULTIPLIER` (artifact of missing `pois_a` + `45/POI` proxy) |
| **0.989 accessibility index** | `0.55 * min(1, 600/40) + 0.25 * min(1, 78/6) + 0.20 * 0.946 = 0.55 + 0.25 + 0.1892 = 0.989` | [`territorial_context.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/territorial_context.py#L669-L675) | `GEOGRAPHIC_DATASET` + `DETERMINISTIC_MULTIPLIER` (`tobler=0.946` from cordillera slope) |

---

## 3. Population Representativeness Audit (Section B)

Inspecting the exact 40-agent cohort generated for `dist_santa_tecla` (`seed=42`):

- **Sampling Ratio & Expansion Factor**: `40` agents represent `150,000` residents (`0.0267%`, expansion `3,750` residents/agent), yet `intervention_designer.py` scales behavior using an unvalidated formula `pop_scale = min(15.0, 150000 / (40 * 400)) = 9.375` (`70.31x` per 7.5-day segment) without variance or confidence intervals.
- **Household Linkage**: Grouped sequentially into `14` household IDs (`hh_dist_santa_tecla_000..013`: thirteen households of 3 agents, one of 1 agent).
- **Spatial Distribution**: Agents received isotropic centroid jitter `rng.normal(0.0, 0.003°)` (`lat: 13.6658..13.6811`, `lon: -89.2930..-89.2824`). In Phase 1.16A they were **not** placed onto OSM residential building footprints or residential land-use polygons, nor did distance from the pin `(13.67529, -89.28761)` attenuate visit probability.
- **Demographic & Economic Structure**:
  - Ages `10..78` (mean `37.42`): `9` under 18 (`22.5%`), `27` working-age 18–64 (`67.5%`), `4` elderly 65+ (`10.0%`). Gender: `24` female (`60%`), `16` male (`40%`).
  - Occupations reflect EHPM urban mix (`Estudiante: 9`, `Adulto Mayor: 6`, `Costurera: 4`, `Comerciante: 3`, `Motorista: 3`, `Docente: 3`, `Vendedor Ambulante: 3`, etc.) minus `2` hired by the simulated business (`Empleado en Pupusería Comunitaria`).
  - Initial liquidity: mean `$31.62`, sampled uniformly per age band (students `$3–14`, workers `$16–65`, elderly `$12–45`), omitted: top wealth tail / formal salaried deciles above `$65`.
- **Commuters & Mobility**: `0` inbound and `0` outbound commuters because `NationalPopulationActivationManager.register_inter_district_flow()` is never called in `execute_stage_b()`.
- **Persistence & Isolation Defect**: Identities are deterministically reproducible via `uuid5("saltbor:42:dist_santa_tecla:idx")`, **but** [`capture_baseline_snapshot()`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/population_activation.py#L564-L586) only restored `money`, `hunger`, `health` — leaving `demographics.occupation`, `employment_status`, `work_location_id`, `energy`, and `current_location_id` mutated across consecutive runs on the same orchestrator instance (**CONFIRMED**).

---

## 4. Commercial Calculation Trace (Section C)

Exact stage-by-stage trace of `SCEN_96f14a52` (`Pupusería Comunitaria`, `price=$0.90`, `COGS=50%`, `cap=24`, `hours=6..21`, `staff=2`, `wage=$12/d`, `fixed=$7/d`, `init_cash=$220.00`, `4 segs × 7.5d`):

1. **Passing Probability**: Per segment (`friction = 1.0`), `pass_prob = min(0.85, (0.35 + 0.35 * 0.989) / 1.0) = 0.69615` for all `40` agents regardless of distance to store.
2. **Visits & Closed Hours Defect**:
   - In `SCEN_96f14a52` (`6..21`), `rng.integers(6, 21)` yields `6..20` (all open): `29 + 27 + 31 + 26 = 113` visits across `40` unique visitors (`73` repeat visits across segments).
   - **Defect Confirmed in SCEN_9393e2f8 (`hours 8..19`)**: `visit_hour` (`6..20`) hit closed hours `6, 7, 19, 20` on `24` visits (`108` total vs `84` open visits in `CommercialEngine.visit_history`). Closed-hour visits returned `"Establishment is closed"` inside `execute_visit()` without incrementing `est.daily_visitors`, yet line `885` in [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L885-L910) still incremented `seg_visitors` and `seg_browsers`, inflating total visits by `+28.6%` (`7,593.6` vs `5,906.0`).
3. **Capacity Check Dead Code (`CONFIRMED`)**: Line `865` checks `len(target_est.current_occupants) >= target_est.capacity`, but `current_occupants` is never populated anywhere in `execute_visit()` or `intervention_designer.py`, so capacity is never binding.
4. **Inventory Bypass for `VisitIntent.DINE` (`CONFIRMED`)**: While `VisitIntent.PURCHASE` decrements `prod.current_stock`, `VisitIntent.DINE` in [`commercial_engine.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/economy/commerce/commercial_engine.py#L257-L300) never checks or decrements `meal_product.current_stock`.
5. **Competition Ignored (`CONFIRMED`)**: Lines `599–625` register `5` `osm_comp_*` competitors, but lines `859–926` put `else:` after `if target_est is not None:`, meaning `0` visits go to competitors whenever the simulated business exists (`competitor_sales_usd = $0.00`).
6. **Purchases & Direct Ledger Revenue**: `17 + 10 + 16 + 9 = 52` `DINE` purchases × `$0.90` = **`$46.80`** raw ledger sales (`38` unique buyers, `61` non-purchase `BROWSE`/`COMPARE_PRICES` visits, `$0.00` accounting diff across `106` ledger entries).
7. **Extrapolation & Broken Mixed-Scale P&L (`CONFIRMED CRITICAL DEFECT`)**:
   - Segment multiplier `scale_mult = round(7.5 * 9.375, 2) = 70.31`:
     - Seg 0: `17 * $0.90 * 70.31 = $1,075.74`
     - Seg 1: `10 * $0.90 * 70.31 = $632.79`
     - Seg 2: `16 * $0.90 * 70.31 = $1,012.46`
     - Seg 3: `9 * $0.90 * 70.31 = $569.51`
     - Sum = **`$3,290.50`**; COGS = `0.50 * $3,290.50 = $1,645.24` (unledgered).
   - **Payroll & Overhead Silent Default + Scale Mismatch**:
     - Seg 0 paid `2 * $12.00 * 7.5 = $180.00` from `$220.00` capital -> `$40.00` left -> paid `min($40.00, $52.50) = $40.00` fixed cost (`$12.50` unpaid!) -> `$0.00` + `$15.30` sales = `$15.30`.
     - Segs 1, 2, 3 each owed `$180.00` payroll and `$52.50` fixed cost, **but** `15.30 >= 180.0` failed silently -> **`$0.00` wages paid in Segs 1–3 (`$540.00` unpaid!)**, while fixed costs took whatever sales trickled in (`$15.30 + $9.00 + $14.40 = $38.70`; **`$118.80` more unpaid!**), ending with `enterprise_closing_cash_usd = $8.10` (`status = 'active'`!).
     - True obligated opex was `$720.00 wages + $210.00 fixed = $930.00`, yet only `$258.70` (`$180.00 + $78.70`) was deducted against **catchment-scaled** gross margin (`$1,645.26`), manufacturing `$1,386.56` net profit from an enterprise that missed 75% of its payroll on unscaled cashflow!

---

## 5. Scenario Isolation Report: Why Educational Attendance Dropped `100% -> 35.43%` (Section D)

**Confirmed Root Cause (Three Compounding Model & Coverage Artifacts — NOT Pupusería Causality):**

1. **Primary Cause (`-64.57 percentage points`): Pre-1.17 `pois`-only query missed polygon schools (`pois_a`) across an 820m pin shift.**
   - `SCEN_9393e2f8` used Santa Tecla centroid `(13.676, -89.28)`: its 1.5 km bbox contained **`3`** point-only `education` POIs in pre-1.17 `geography.sqlite` → `existing_edu_capacity = 3 * 45 = 135 seats/day` ≥ `school_demand_total = 127` → `0` unmet → **`100.0%` attendance**.
   - `SCEN_96f14a52` moved `820m` west to map pin `(13.67529, -89.28761)`: its 1.5 km bbox contained only **`1`** point `education` POI (`2` points near Merliot/East edge fell just outside `-89.28761 + dlon`), while **`21` real school polygons inside that exact bbox sat uningested in `pois_a`**! Capacity collapsed from `135` to `1 * 45 = 45 seats/day` (`45 / 127 = 0.35433` = **`35.43%`**, unmet = `(127 - 45) * 30 = 2,460.0 person-days`).
   - Replaying the exact same pin with Phase 1.17's ingested `pois_a` layer (`22` total schools) immediately restores `100%` attendance (`0.0` unmet).
2. **Calender Logic Defect**: Temporal segments for January all carried `"school_active": False` (holiday), yet `execute_intervention_simulation()` simulated daily school overflow anyway.
3. **Mutable State Leakage Across Sequential Scenarios (`CONFIRMED`)**: As verified directly on `pm.restore_baseline_snapshot(snap)`, `2` hired employees from Run 1 retained `demographics.occupation = 'Empleado en Establecimiento Comercial (Santa Tecla)'` and `work_location_id = 'loc_dist_santa_tecla'` instead of original occupations (`Vendedor Ambulante`, `Empleado de Tienda`) and `work_dist_santa_tecla`. While this did not alter `SCEN 2`'s `school_attendance_rate` (driven by age `<= 18`), it violated clean isolation between sequential scenarios on the same orchestrator instance.

---

## 6. Geographic Coverage & Data-Quality Audit (Section E)

Why did Santa Tecla report **`1.00 / 1.00`** data quality while simultaneously warning `buildings_is_partial = True` and `"edificio OSM fuera de San Salvador Centro no mapeado"`?
- In [`territorial_context.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/territorial_context.py#L684-L694):
  `quality = 0.40 + (0.15 if pop > 0) + (0.20 if roads > 0) + (0.15 if any_pois > 0) + (0.10 if landuse or buildings > 0) = 1.00`.
- Having **`0` building polygons** + `buildings_is_partial == True` + zero floor/occupancy/vacancy/flow data yielded `0` penalty because `landuse` polygons satisfied `if landuse_summary or buildings_count > 0`!
- **Replacement Required**: Never award `1.00` without empirical field/sensor/occupancy verification, explicitly penalize partial/missing buildings, and replace the single misleading global scalar with question-specific **`QuestionDataQualityAssessment`** (`required_datasets`, `available_datasets`, `coverage_by_dataset`, `freshness`, `provenance`, `missing_fields`, `confidence_score`).

---

## 7. Classified Defects & Unresolved Hypotheses (Section G)

| ID | Classification | Component | Finding Summary |
| :--- | :--- | :--- | :--- |
| `DEF-01` | **CONFIRMED** | [`population_activation.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/population_activation.py#L564-L586) | Incomplete state restore (`occupation`, `employment_status`, `work_location_id`, `energy`, `current_location_id` leak across runs). |
| `DEF-02` | **CONFIRMED** | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L863-L913) | Closed-hour visits in SCEN 1 counted in `seg_visitors`/`seg_browsers` (`108` vs `84` open `visit_history`), inflating traffic `+28.6%`. |
| `DEF-03` | **CONFIRMED** | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L793-L828) | Mixed-scale P&L (`70.31x` revenue/COGS vs `1x` payroll/fixed) + silent payroll/overhead default (`$540` unpaid wages, `$131.30` unpaid overhead) while reporting `active` and `+$1,386.56` profit. |
| `DEF-04` | **CONFIRMED** | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L859-L926) | Registered `5` `osm_comp_*` competitors receive `0` visits (`competitor_sales_usd = $0.00`) whenever `target_est` exists. |
| `DEF-05` | **CONFIRMED** | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L865) & [`commercial_engine.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/economy/commerce/commercial_engine.py#L257-L300) | Dead capacity guard (`current_occupants` never populated) + `VisitIntent.DINE` never decrements or checks `current_stock`. |
| `DEF-06` | **CONFIRMED** | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L719-L966) | Education capacity drop (`100% -> 35.43%`) caused by uningested `pois_a` polygons + brittle `45 seats/point` proxy across 820m pin move + ignoring `school_active=False` in January. |
| `DEF-07` | **CONFIRMED** | [`territorial_context.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/territorial_context.py#L684-L694) | Global `data_quality_score` hit `1.00/1.00` despite `buildings_is_partial=True` and missing empirical datasets. |
| `DEF-08` | **CONFIRMED** | [`evidence_engine.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/evidence_engine.py) | Indicators lacked explicit `definition`, `data_origin` (`EXTRAPOLATED_COHORT` vs `DIRECT_SIMULATION_EVENT`), `uncertainty`, and `is_synthetic` separation on scaled commercial KPIs. |
| `DEF-09` | **CONFIRMED** | [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py#L855) | Spatial friction & distance decay absent in `pass_prob`; `register_inter_district_flow()` not connected to Stage B (`0` commuters). |
| `HYP-01` | **NOT_REPRODUCIBLE** | Scenario State | Initial hypothesis that Pupusería entity directly caused the `100% -> 35.43%` school attendance drop was **refuted** by pinpointing the 820m bounding-box school count change (`3 -> 1` points). |
| `HYP-02` | **UNVERIFIED** | Empirical Validation | Real-world commercial conversion rates and unit footfall in Santa Tecla cannot be empirically calibrated without field point-of-sale / sensor count ground truth (`measured_flows_available=False`). |

---

## 8. Post-Fix Verification (Mandatory Gate Completed)

Archived historical rows in [`saltbor_studio.db`](file:///c:/GIT%20HUB/sv%20people/saltbor_studio.db) remain unmodified (`test_archived_studio_db_santa_tecla_records_untouched` passes). All confirmed structural defects (`DEF-01..DEF-09`) were remediated across [`population_activation.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/population_activation.py), [`commercial_engine.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/economy/commerce/commercial_engine.py), [`intervention_designer.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/intervention_designer.py), [`schemas.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/schemas.py), [`territorial_context.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/territorial_context.py), [`evidence_engine.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/evidence_engine.py), [`orchestrator.py`](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/orchestrator.py), and [`territorial_studio.js`](file:///c:/GIT%20HUB/sv%20people/saltbor/visualization/web/modules/territorial_studio.js).

### 8.1 Post-Fix Santa Tecla Runs (`seed=42`, `30` days, `40` agents)

| Metric | Post-Fix SCEN 1 (General Commercial) | Post-Fix SCEN 2 (Pupusería) | Change / Explanation |
| :--- | ---: | ---: | :--- |
| `data_quality_score` / `question_data_quality` | `0.85` / `0.60` | `0.85` / `0.60` | Removed false `1.00/1.00`; penalizes missing empirical field/occupancy/spend datasets |
| `raw_cohort_visitors` / `raw_cohort_revenue_usd` | `57` / `$42.75` | `78` / `$21.60` | Excludes closed hours; reports raw ledger figures directly (`DIRECT_SIMULATION_EVENT`) |
| `commercial_visitors` / `commercial_purchasers` | `4,007.7` / `1,335.8` | `5,484.2` / `1,687.4` | Tagged `EXTRAPOLATED_COHORT`; reflects competitor diversion (`comp_count = 5`) |
| `commercial_competitor_sales_usd` | `$4,077.98` | `$2,169.77` | Competitors now capture realistic market share |
| `commercial_revenue_usd` (extrapolated) | `$3,005.75` | `$1,518.70` | Realistic competitive revenue |
| `commercial_obligated_wages_usd` | `$750.00` | `$720.00` | Full 30-day obligated payroll accrued |
| `commercial_net_profit_usd` | `+$212.31` | `-$170.66` | Deducts full obligated payroll & fixed overhead without hiding unpaid defaults |
| Analytical Verdict | `PROMISING` | `NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS` | `$0.90` pupusería with 2 staff (`$930/mo` opex) cannot break even once competition & full opex apply |
| `school_attendance_rate` / `edu_unmet_person_days` | `None` (`avail=False`) / `0.0` | `None` (`avail=False`) / `0.0` | Stops fabricating January vacation school deficits in commercial scenarios |
| `ledger_audit` (`diff` / `txns`) | `$0.00` / `102` | `$0.00` / `110` | Strict double-entry conservation maintained |

### 8.2 Regression Suites & Knowledge Graph Verification

- **Phase 1.17 Full Suite + Evidence Audit Regression Tests** (`python -m pytest tests/test_territorial_intelligence/ tests/test_experiments/test_phase117_territorial_experiments.py -v`): **16 passed in 21.17s** (`0` failures, `0` skipped), including all **5** new audit tests in [`test_phase117_evidence_audit.py`](file:///c:/GIT%20HUB/sv%20people/tests/test_territorial_intelligence/test_phase117_evidence_audit.py) (`2.18s` standalone) and **20/20** validation experiments (`EXP_117_A..EXP_117_T`).
- **Cross-Phase Regression Suite** (`tests/test_conversational/`, `tests/test_gis/`, `tests/test_visualization/test_studio_frontend_e2e.py`, `tests/test_visualization/test_api_endpoints.py`, `tests/test_territory/`, `tests/test_experiments/test_phase114_territorial_experiments.py`, `test_phase115_ai_experiments.py`, `test_phase116a_conversational_experiments.py`): **162 passed in 34.59s** (`0` failures, `0` skipped).
- **Graphify Knowledge Graph** (`python -m graphify update .`): Rebuilt cleanly with `16,137` nodes, `44,046` edges, and `442` communities.
