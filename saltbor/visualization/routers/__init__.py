"""Modular FastAPI sub-routers for SALTBOR Visualization & Observability API (Phase 1.16+)."""

from saltbor.visualization.routers.pipeline_router import router as pipeline_router
from saltbor.visualization.routers.national_validation_router import router as national_validation_router

__all__ = [
    "pipeline_router",
    "national_validation_router",
]
