"""Modular FastAPI sub-routers for SALTBOR Visualization & Observability API (Phase 1.16+)."""

from saltbor.visualization.routers.conversational_studio_router import router as conversational_studio_router
from saltbor.visualization.routers.national_validation_router import router as national_validation_router
from saltbor.visualization.routers.pipeline_router import router as pipeline_router
from saltbor.visualization.routers.territorial_intelligence_router import router as territorial_intelligence_router

__all__ = [
    "conversational_studio_router",
    "national_validation_router",
    "pipeline_router",
    "territorial_intelligence_router",
]
