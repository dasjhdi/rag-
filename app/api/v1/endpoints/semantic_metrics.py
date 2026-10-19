"""Read-only semantic metrics endpoint (SU-10)."""

from fastapi import APIRouter

from app.observability import semantic_metrics

router = APIRouter(prefix="/semantic-metrics", tags=["Semantic Metrics"])


@router.get("/summary")
async def get_semantic_metrics_summary():
    """Return the current in-process semantic metrics snapshot."""
    return semantic_metrics.snapshot()
