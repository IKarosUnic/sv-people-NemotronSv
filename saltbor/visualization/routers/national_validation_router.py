"""Modular FastAPI Router for 262-District National Coverage & Tier-5 External Validation (Phase 1.17)."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from saltbor.scientific.external_validation import ExternalHistoricalValidator
from saltbor.territory.territory_catalog import TerritoryCatalogService

router = APIRouter()

_catalog = TerritoryCatalogService()
_validator = ExternalHistoricalValidator()


class CustomSeriesBacktestRequest(BaseModel):
    series_id: str
    simulated_values: List[float]


@router.get("/territory/national_audit")
def get_national_262_districts_audit() -> Dict[str, Any]:
    """Audit administrative and infrastructural resolution across all 14 departments, 44 municipalities, and 262 districts."""
    return _catalog.get_national_coverage_audit()


@router.get("/territory/hazard_profile")
def get_territory_topographic_hazard_profile(territory: str = "Cantón El Rosario") -> Dict[str, Any]:
    """Return relief classification, Tobler slope penalty, and landslide/flood/drought hazard profile."""
    return _catalog.get_topographic_hazard_profile(territory)


@router.get("/territory/supply_chain")
def get_territory_hierarchical_supply_chain(territory: str = "Cantón El Rosario") -> Dict[str, Any]:
    """Resolve hierarchical wholesale supply chain and MINSAL/MINED public service links for any district."""
    return _catalog.resolve_supply_chain_and_services(territory)


@router.get("/scientific/external_validation/series")
def list_historical_benchmark_series() -> List[Dict[str, Any]]:
    """List official out-of-sample Salvadoran historical time-series benchmarks (BCR, ONEC/EHPM, MINED)."""
    return [
        {
            "series_id": bm.series_id,
            "title": bm.title,
            "source_agency": bm.source_agency,
            "citation": bm.citation,
            "unit": bm.unit,
            "time_points": list(bm.time_points),
            "observed_values": list(bm.observed_values),
            "observed_ci_halfwidth": bm.observed_ci_halfwidth,
            "tolerance_nrmse": bm.tolerance_nrmse,
        }
        for bm in _validator.series_catalog.values()
    ]


@router.get("/scientific/external_validation/backtest")
def run_canonical_external_backtest(seed: int = 42) -> Dict[str, Any]:
    """Run out-of-sample historical backtesting suite to verify Tier-5 EXTERNALLY_VALIDATED status."""
    return _validator.run_canonical_salvadoran_backtest_suite(seed=seed)


@router.post("/scientific/external_validation/evaluate")
def evaluate_custom_series_backtest(req: CustomSeriesBacktestRequest) -> Dict[str, Any]:
    """Evaluate a custom simulated series against an official historical benchmark series."""
    if req.series_id not in _validator.series_catalog:
        raise HTTPException(status_code=404, detail=f"Benchmark series '{req.series_id}' not found.")
    res = _validator.validate_series(req.series_id, req.simulated_values)
    return {
        "series_id": res.series_id,
        "title": res.title,
        "source_agency": res.source_agency,
        "rmse": res.rmse,
        "mae": res.mae,
        "nrmse": res.nrmse,
        "wasserstein_distance": res.wasserstein_distance,
        "pearson_r": res.pearson_r,
        "interval_coverage_rate": res.interval_coverage_rate,
        "assigned_tier": res.assigned_tier.value,
        "passed_external_validation": res.passed_external_validation,
        "epistemic_note": res.epistemic_note,
    }
