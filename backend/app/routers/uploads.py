from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pathlib import Path
from app.database import get_db
from app import models
from app.services.youtube import youtube_service
from app.config import settings

router = APIRouter(prefix="/uploads", tags=["uploads"])

@router.get("/", response_model=list)
def list_uploads(status: str = None, db: Session = Depends(get_db)):
    query = db.query(models.Upload)
    if status:
        query = query.filter(models.Upload.status == status)
    uploads = query.order_by(models.Upload.scheduled_for.desc()).all()
    return [
        {
            "id": u.id,
            "project_id": u.project_id,
            "script_id": u.script_id,
            "video_path": u.video_path,
            "scheduled_for": u.scheduled_for.isoformat() if u.scheduled_for else None,
            "youtube_video_id": u.youtube_video_id,
            "status": u.status,
            "title": u.title,
            "description": u.description,
            "tags": u.tags,
            "thumbnail_path": u.thumbnail_path
        }
        for u in uploads
    ]

@router.post("/{upload_id}/now", response_model=dict)
def upload_now(upload_id: int, db: Session = Depends(get_db)):
    upload = db.query(models.Upload).filter(models.Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    result = youtube_service.upload_video(
        video_path=upload.video_path,
        title=upload.title or "Untitled Short",
        description=upload.description or "",
        tags=upload.tags.split(",") if upload.tags else [],
        privacy_status="private",
        publish_at=None,
        thumbnail_path=upload.thumbnail_path
    )
    
    if result["status"] == "success":
        upload.status = "done"
        upload.youtube_video_id = result["video_id"]
        db.commit()
    else:
        upload.status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=result.get("message", "Upload failed"))
    
    return result

@router.put("/{upload_id}/schedule", response_model=dict)
def update_schedule(upload_id: int, data: dict, db: Session = Depends(get_db)):
    upload = db.query(models.Upload).filter(models.Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    from datetime import datetime
    if "scheduled_for" in data:
        upload.scheduled_for = datetime.fromisoformat(data["scheduled_for"])
    if "title" in data:
        upload.title = data["title"]
    if "description" in data:
        upload.description = data["description"]
    if "tags" in data:
        upload.tags = data["tags"]
    
    upload.status = "queued"
    db.commit()
    return {"status": "updated", "upload_id": upload_id}

@router.post("/{upload_id}/thumbnail", response_model=dict)
def upload_thumbnail(upload_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    upload = db.query(models.Upload).filter(models.Upload.id == upload_id).first()
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    # Save thumbnail
    thumb_dir = settings.PROJECTS_DIR / str(upload.project_id) / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = thumb_dir / f"thumb_{upload_id}.png"
    
    with open(thumb_path, "wb") as f:
        f.write(file.file.read())
    
    upload.thumbnail_path = str(thumb_path)
    db.commit()
    return {"status": "success", "thumbnail_path": str(thumb_path)}
