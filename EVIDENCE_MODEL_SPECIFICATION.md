# EVIDENCE MODEL SPECIFICATION (PHASE 1.16A)

**Module**: [schemas.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/schemas.py), [evidence_engine.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/evidence_engine.py), [decision_analyst.py](file:///c:/GIT%20HUB/sv%20people/saltbor/conversational/decision_analyst.py)

---

## 1. Core Epistemic Rules

1. **Zero Fabricated Metrics**: Every indicator inside `EvidenceBundle` MUST originate from actual simulation state, double-entry ledger entries (`VerifiableEconomicLedger`), event logs, or verified territorial datasets. Missing or inactive domain indicators are emitted with `available=False` and recorded in `missing_indicators`.
2. **Mandatory Provenance**: Every indicator carries an `EvidenceProvenance` block identifying:
   - `source_engine` (e.g., `"CommercialEngine"`, `"VerifiableEconomicLedger"`, `"PublicServiceCapacityEngine"`, `"PopulationRegistry"`)
   - `source_entity`
   - `calculation_method`
   - `time_interval` (e.g., `"ticks 0..720 (30 simulated days)"`)
   - `population_scope` (e.g., `"48 hydrated agents / 206,500 district population"`)
   - `geographic_scope` (e.g., `"Santa Tecla (0511), La Libertad Sur"`)
   - `seed`
   - `data_quality` (`0.0–1.0`)
   - `confidence` (`0.0–1.0`)
   - `limitations`
3. **Non-Independent Synthetic Opinions**: Querying synthetic humans grounds responses in their `identity`, `memory`, `personality`, `autonomy` goals, `physical_state.money`/`hunger`/`health`, `social` relationships, and simulated commercial/service experiences. Because agents share environment, prices, households, and social networks, `is_independent_sample` is ALWAYS `False` and `correlation_warning` explicitly forbids treating repeated or clustered agent responses as independent real-world survey statistics.
4. **Analytical Verdicts (No Simplistic YES/NO)**: `GeminiDecisionAnalyst` classifies decisions into one of 5 calibrated categories:
   - `PROMISING`
   - `CONDITIONALLY_PROMISING`
   - `INSUFFICIENT_EVIDENCE`
   - `HIGH_RISK`
   - `NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS`

---

## 2. Pydantic v2 Schema Specification

```python
class EvidenceProvenance(BaseModel):
    source_engine: str
    source_entity: str
    calculation_method: str
    time_interval: str
    population_scope: str
    geographic_scope: str
    seed: int
    data_quality: float  # [0.0, 1.0]
    confidence: float    # [0.0, 1.0]
    limitations: str

class EvidenceIndicator(BaseModel):
    indicator_id: str
    domain: str
    name: str
    value: Optional[float | int | str | bool] = None
    unit: str = ""
    available: bool = True
    provenance: EvidenceProvenance

class SyntheticOpinionRecord(BaseModel):
    opinion_id: str
    agent_uids: List[str]
    group_label: str
    query_method: str
    context_summary: str
    response_text: str
    stance: str
    simulated_tick: int
    seed: int
    confidence: float
    is_independent_sample: Literal[False] = False
    correlation_warning: str
    limitations: str

class EvidenceBundle(BaseModel):
    scenario_id: str
    seed: int
    horizon_days: int
    simulated_ticks: int
    geographic_scope: str
    district_id: str
    data_classification: Literal["SYNTHETIC_SIMULATED"] = "SYNTHETIC_SIMULATED"
    active_engines: List[str]
    population_summary: Dict[str, Any]
    indicators: List[EvidenceIndicator]
    group_breakdowns: Dict[str, Dict[str, Any]]
    temporal_series: List[Dict[str, Any]]
    synthetic_opinions: List[SyntheticOpinionRecord]
    ledger_audit: Dict[str, Any]
    missing_indicators: List[str]
    limitations: List[str]
```

---

## 3. Verdict Decision Rubric (Deterministic + LLM-Assisted)

- **`INSUFFICIENT_EVIDENCE`**: Data quality `< 0.45`, zero active simulated agents, or critical missing indicators preventing evaluation (e.g., unknown unmapped locality without baseline demographic/POI data).
- **`HIGH_RISK`**: Severe negative net cash flow / business insolvency risk, high household liquidity distress, or ledger conservation failure.
- **`NOT_RECOMMENDED_UNDER_CURRENT_ASSUMPTIONS`**: Sustained net loss or negative service/accessibility impact under baseline operating assumptions when viable alternatives outperform it.
- **`CONDITIONALLY_PROMISING`**: Positive expected demand or social benefit, conditioned on key constraints (e.g., keeping prices competitive, staffing within margin, transport subsidy, rainy-season mitigation, or unresolved data gaps).
- **`PROMISING`**: Positive demand/access outcome across indicators, sustainable solvency, zero ledger discrepancy, and coherent supporting evidence across simulated groups.
