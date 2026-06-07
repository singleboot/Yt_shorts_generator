from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from app.database import get_db
from app.models import ResearchLog

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/")
def list_research(
    project_id: Optional[int] = None,
    job_id: Optional[int] = None,
    source_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(ResearchLog)
    if project_id is not None:
        q = q.filter(ResearchLog.project_id == project_id)
    if job_id is not None:
        q = q.filter(ResearchLog.job_id == job_id)
    if source_type:
        q = q.filter(ResearchLog.source_type == source_type)
    q = q.order_by(ResearchLog.created_at.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_serialize(r) for r in rows],
    }


@router.get("/stats/summary")
def research_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    total = db.query(func.count(ResearchLog.id)).scalar() or 0
    completed = db.query(func.count(ResearchLog.id)).filter(ResearchLog.status == "completed").scalar() or 0
    failed = db.query(func.count(ResearchLog.id)).filter(ResearchLog.status == "failed").scalar() or 0
    total_results = db.query(func.coalesce(func.sum(ResearchLog.result_count), 0)).scalar() or 0
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "total_search_results": int(total_results),
    }


@router.get("/{research_id}")
def get_research(research_id: int, db: Session = Depends(get_db)):
    row = db.query(ResearchLog).filter(ResearchLog.id == research_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Research log not found")
    return _serialize(row, full=True)


@router.delete("/")
def clear_research(
    project_id: Optional[int] = None,
    before: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    q = db.query(ResearchLog)
    if project_id is not None:
        q = q.filter(ResearchLog.project_id == project_id)
    if before is not None:
        q = q.filter(ResearchLog.created_at < before)
    deleted = q.delete()
    db.commit()
    return {"deleted": deleted}


def _serialize(r: ResearchLog, full: bool = False) -> dict:
    out = {
        "id": r.id,
        "project_id": r.project_id,
        "job_id": r.job_id,
        "video_index": r.video_index,
        "source_type": r.source_type,
        "query": r.query,
        "topic_used": r.topic_used,
        "source_url": r.source_url,
        "result_count": r.result_count,
        "status": r.status,
        "error": r.error,
        "duration_ms": r.duration_ms,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
    if full:
        out["search_results"] = r.search_results or []
        out["context_text"] = r.context_text or ""
        out["web_content"] = r.web_content or ""
    else:
        # Truncated preview for list view
        out["search_results_preview"] = (r.search_results or [])[:3]
        out["context_preview"] = (r.context_text or "")[:400]
    return out
