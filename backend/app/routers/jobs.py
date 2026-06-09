from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.services.youtube import youtube_service
from app.services.scheduler import scheduler_service

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/", response_model=list)
def list_jobs(status: str = None, db: Session = Depends(get_db)):
    query = db.query(models.Job)
    if status:
        query = query.filter(models.Job.status == status)
    jobs = query.order_by(models.Job.created_at.desc()).all()
    return [
        {
            "id": j.id,
            "project_id": j.project_id,
            "job_type": j.job_type,
            "status": j.status,
            "progress": j.progress,
            "logs": j.logs,
            "current_stage": j.current_stage,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None
        }
        for j in jobs
    ]

@router.get("/{job_id}", response_model=dict)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "project_id": job.project_id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "logs": job.logs,
        "current_stage": job.current_stage,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None
    }

@router.post("/{job_id}/cancel", response_model=dict)
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in ["queued", "running"]:
        # 1. Mark cancelled in the running scheduler pipeline (so the loop bails)
        try:
            scheduler_service.mark_cancelled(job_id)
        except Exception as e:
            print(f"mark_cancelled failed: {e}")
        # 2. Interrupt ComfyUI directly as a belt-and-braces measure
        try:
            import asyncio as aio
            try:
                loop = aio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        pool.submit(aio.run, scheduler_service_comfyui_interrupt()).result(timeout=10)
                else:
                    loop.run_until_complete(scheduler_service_comfyui_interrupt())
            except RuntimeError:
                aio.run(scheduler_service_comfyui_interrupt())
        except Exception as e:
            print(f"ComfyUI interrupt on cancel failed: {e}")
        # 3. Update DB status
        job.status = "cancelled"
        job.logs = (job.logs or "") + "\nCancelled by user"
        db.commit()
    return {"status": "cancelled", "job_id": job_id}

async def scheduler_service_comfyui_interrupt():
    """Helper to interrupt ComfyUI from the cancel route."""
    from app.services.visuals import visuals_service
    return await visuals_service.comfyui.interrupt()

@router.post("/clear-finished", response_model=dict)
def clear_finished_jobs(db: Session = Depends(get_db)):
    ids = [row[0] for row in db.query(models.Job.id).filter(
        models.Job.status.in_(["completed", "failed", "cancelled"])
    ).all()]
    if ids:
        db.query(models.PromptLog).filter(models.PromptLog.job_id.in_(ids)).update(
            {models.PromptLog.job_id: None}, synchronize_session=False
        )
        db.query(models.ResearchLog).filter(models.ResearchLog.job_id.in_(ids)).update(
            {models.ResearchLog.job_id: None}, synchronize_session=False
        )
        deleted = db.query(models.Job).filter(models.Job.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        return {"deleted": deleted}
    db.commit()
    return {"deleted": 0}

@router.post("/clear-all", response_model=dict)
def clear_all_jobs(db: Session = Depends(get_db)):
    db.query(models.PromptLog).update(
        {models.PromptLog.job_id: None}, synchronize_session=False
    )
    db.query(models.ResearchLog).update(
        {models.ResearchLog.job_id: None}, synchronize_session=False
    )
    deleted = db.query(models.Job).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}
