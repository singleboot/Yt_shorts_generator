from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime
from app.database import get_db
from app import models

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _serialize(p: models.PromptLog) -> dict:
    return {
        "id": p.id,
        "project_id": p.project_id,
        "job_id": p.job_id,
        "video_index": p.video_index,
        "scene_index": p.scene_index,
        "scene_number": p.scene_number,
        "raw_visual_description": p.raw_visual_description,
        "sanitized_visual_description": p.sanitized_visual_description,
        "trigger_words": p.trigger_words,
        "suffix": p.suffix,
        "final_prompt": p.final_prompt,
        "lora_name": p.lora_name,
        "lora_strength_model": p.lora_strength_model,
        "lora_strength_clip": p.lora_strength_clip,
        "seed": p.seed,
        "width": p.width,
        "height": p.height,
        "frame_count": p.frame_count,
        "duration_seconds": p.duration_seconds,
        "status": p.status,
        "comfyui_prompt_id": p.comfyui_prompt_id,
        "error": p.error,
        "output_path": p.output_path,
        "narration_text": p.narration_text,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "completed_at": p.completed_at.isoformat() if p.completed_at else None,
    }


@router.get("/", response_model=list)
def list_prompts(
    project_id: Optional[int] = None,
    job_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List prompt log rows, newest first. Filters: project_id, job_id, status."""
    query = db.query(models.PromptLog)
    if project_id is not None:
        query = query.filter(models.PromptLog.project_id == project_id)
    if job_id is not None:
        query = query.filter(models.PromptLog.job_id == job_id)
    if status:
        query = query.filter(models.PromptLog.status == status)
    rows = query.order_by(desc(models.PromptLog.created_at)).limit(limit).offset(offset).all()
    return [_serialize(p) for p in rows]


@router.get("/{prompt_id}", response_model=dict)
def get_prompt(prompt_id: int, db: Session = Depends(get_db)):
    """Get full detail for one prompt log row."""
    row = db.query(models.PromptLog).filter(models.PromptLog.id == prompt_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt log not found")
    return _serialize(row)


@router.get("/comfyui/{comfyui_prompt_id}", response_model=dict)
def get_prompt_by_comfyui_id(comfyui_prompt_id: str, db: Session = Depends(get_db)):
    """Look up a prompt log by ComfyUI's prompt_id (useful when matching ComfyUI history)."""
    row = (
        db.query(models.PromptLog)
        .filter(models.PromptLog.comfyui_prompt_id == comfyui_prompt_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Prompt log not found for comfyui_prompt_id")
    return _serialize(row)


@router.delete("/", response_model=dict)
def delete_prompts(
    project_id: Optional[int] = None,
    before: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Bulk delete prompt log rows. Use ?project_id=X to scope to one project, or ?before=ISO to purge old ones."""
    query = db.query(models.PromptLog)
    if project_id is not None:
        query = query.filter(models.PromptLog.project_id == project_id)
    if before:
        try:
            before_dt = datetime.fromisoformat(before)
            query = query.filter(models.PromptLog.created_at < before_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid 'before' datetime format. Use ISO 8601.")
    count = query.count()
    query.delete(synchronize_session=False)
    db.commit()
    return {"deleted": count}


@router.get("/stats/summary", response_model=dict)
def get_prompt_stats(db: Session = Depends(get_db)):
    """Aggregate counts for the Prompt Console header summary."""
    total = db.query(models.PromptLog).count()
    running = db.query(models.PromptLog).filter(models.PromptLog.status == "running").count()
    completed = db.query(models.PromptLog).filter(models.PromptLog.status == "completed").count()
    failed = db.query(models.PromptLog).filter(models.PromptLog.status == "failed").count()
    queued = db.query(models.PromptLog).filter(models.PromptLog.status == "queued").count()
    last_run = (
        db.query(models.PromptLog)
        .order_by(desc(models.PromptLog.created_at))
        .first()
    )
    return {
        "total": total,
        "running": running,
        "completed": completed,
        "failed": failed,
        "queued": queued,
        "last_run_at": last_run.created_at.isoformat() if last_run and last_run.created_at else None,
    }
