"""Semantic search API over conversation transcripts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.api import SearchResponse
from app.services import audit
from app.services.search import search_transcripts

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    request: Request,
    q: str = Query(..., min_length=2, description="Natural-language query"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> SearchResponse:
    """Find conversations semantically similar to ``q`` (e.g. 'angry about billing')."""
    hits = search_transcripts(q, limit=limit)
    audit.record(
        db,
        actor=request.headers.get("x-actor", "anonymous"),
        action="search",
        resource_type="dashboard",
        detail={"query": q, "hits": len(hits)},
        ip_address=request.client.host if request.client else None,
    )
    return SearchResponse(query=q, hits=hits)
