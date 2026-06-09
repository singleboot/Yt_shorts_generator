from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.database import get_db
from app import models
from app.services.scheduler import scheduler_service
from app.config import settings

router = APIRouter(prefix="/projects", tags=["projects"])

class GenerateScriptsRequest(BaseModel):
    video_count: int = None
    duration: int = None
    source_type: str = None
    category: str = None
    topic: str = None
    url: str = None

class AddVideosRequest(BaseModel):
    count: int = 1
    duration: int = None
    source_type: str = None
    category: str = None
    topic: str = None
    url: str = None

@router.get("/", response_model=list)
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(models.Project).all()
    return [_project_to_dict(p) for p in projects]

@router.post("/", response_model=dict)
def create_project(project_data: dict, db: Session = Depends(get_db)):
    project = models.Project(
        name=project_data.get("name", "New Project"),
        source_type=project_data.get("source_type", "auto_research"),
        source_value=project_data.get("source_value", ""),
        category=project_data.get("category", "tech"),
        subcategory=project_data.get("subcategory", ""),
        visual_type=project_data.get("visual_type", "stock_footage"),
        visual_settings=project_data.get("visual_settings", {}),
        audio_settings=project_data.get("audio_settings", {}),
        caption_settings=project_data.get("caption_settings", {}),
        schedule_settings=project_data.get("schedule_settings", {}),
        seo_settings=project_data.get("seo_settings", {}),
        youtube_channel_id=project_data.get("youtube_channel_id"),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_to_dict(project)

@router.get("/{project_id}", response_model=dict)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_to_dict(project)

@router.put("/{project_id}", response_model=dict)
def update_project(project_id: int, project_data: dict, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for key, value in project_data.items():
        if hasattr(project, key):
            setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return _project_to_dict(project)

@router.delete("/{project_id}", response_model=dict)
def delete_project(project_id: int, action: str = "delete", db: Session = Depends(get_db)):
    from app.config import settings
    from pathlib import Path
    import shutil, zipfile
    from datetime import datetime

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = settings.PROJECTS_DIR / str(project.id)

    if action == "archive":
        archives_dir = settings.STORAGE_DIR / "archives"
        archives_dir.mkdir(parents=True, exist_ok=True)

        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in project.name)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        zip_path = archives_dir / f"{safe_name}_{project.id}_{timestamp}.zip"

        if project_dir.exists():
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in project_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(project_dir.parent)
                        zf.write(file_path, arcname)
            shutil.rmtree(project_dir)

        project.status = "archived"
        project.archive_path = str(zip_path)
        project.archived_at = datetime.utcnow()
        db.commit()

        return {"status": "archived", "message": f"Project archived to {zip_path.name}"}

    # Permanent delete
    if project_dir.exists():
        shutil.rmtree(project_dir)
    # Manually clear FK-referenced logs before cascading (ordering issues with
    # prompt_logs/research_logs referencing both project and jobs)
    db.query(models.PromptLog).filter(models.PromptLog.project_id == project_id).delete()
    db.query(models.ResearchLog).filter(models.ResearchLog.project_id == project_id).delete()
    db.delete(project)
    db.commit()

    archive_path = Path(project.archive_path) if project.archive_path else None
    if archive_path and archive_path.exists():
        try:
            archive_path.unlink()
        except Exception:
            pass

    return {"status": "deleted"}

@router.post("/{project_id}/restore", response_model=dict)
def restore_project(project_id: int, db: Session = Depends(get_db)):
    from app.config import settings
    from pathlib import Path
    import zipfile, shutil

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status != "archived" or not project.archive_path:
        raise HTTPException(status_code=400, detail="Project is not archived")

    zip_path = Path(project.archive_path)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Archive file not found")

    project_dir = settings.PROJECTS_DIR / str(project.id)
    if project_dir.exists():
        shutil.rmtree(project_dir)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(project_dir.parent)

    project.status = "active"
    project.archive_path = None
    project.archived_at = None
    db.commit()

    try:
        zip_path.unlink()
    except Exception:
        pass

    return {"status": "restored", "message": "Project restored"}

@router.post("/{project_id}/batch", response_model=dict)
def trigger_batch(project_id: int, body: dict = {}, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    import json
    # Update project from body
    if body.get("category"):
        project.category = body["category"]
    if body.get("topic"):
        project.source_value = body["topic"]
        project.source_type = "auto_research"
    if body.get("url"):
        project.source_value = body["url"]
        project.source_type = "url"
    if body.get("source_type"):
        project.source_type = body["source_type"]
    if body.get("duration"):
        vs = project.visual_settings
        if isinstance(vs, str):
            vs = json.loads(vs) if vs else {}
        elif vs is None:
            vs = {}
        elif isinstance(vs, dict):
            vs = dict(vs)
        vs["total_duration"] = body["duration"]
        project.visual_settings = vs
    if body.get("video_count"):
        ss = project.schedule_settings
        if isinstance(ss, str):
            ss = json.loads(ss) if ss else {}
        elif ss is None:
            ss = {}
        elif isinstance(ss, dict):
            ss = dict(ss)
        ss["video_count"] = body["video_count"]
        project.schedule_settings = ss
    db.commit()
    return scheduler_service.trigger_batch_now(project_id)

@router.post("/{project_id}/save", response_model=dict)
def save_project(project_id: int, body: dict, db: Session = Depends(get_db)):
    """Save project settings and create folder structure on disk."""
    from app.config import settings
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for key in ("source_type", "source_value", "category", "subcategory"):
        if key in body:
            setattr(project, key, body[key])
    if "visual_settings" in body:
        project.visual_settings = body["visual_settings"]
    if "audio_settings" in body:
        project.audio_settings = body["audio_settings"]
    if "caption_settings" in body:
        project.caption_settings = body["caption_settings"]
    if "schedule_settings" in body:
        project.schedule_settings = body["schedule_settings"]
    if "youtube_channel_id" in body:
        project.youtube_channel_id = body["youtube_channel_id"]

    db.commit()

    base = settings.PROJECTS_DIR / str(project.id)
    for sub in ("scripts", "videos", "audio", "final", "thumbnails"):
        (base / sub).mkdir(parents=True, exist_ok=True)

    return {"status": "success", "message": "Project saved"}

@router.post("/{project_id}/post", response_model=dict)
def post_project(project_id: int, db: Session = Depends(get_db)):
    """Schedule all queued uploads for this project using global settings."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return scheduler_service.schedule_uploads_for_project(project_id)

@router.get("/{project_id}/videos", response_model=dict)
def list_project_videos(project_id: int, db: Session = Depends(get_db)):
    """List all videos for a project with their script, upload, job status, and overrides."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    schedule_settings = project.schedule_settings
    if isinstance(schedule_settings, str):
        import json; schedule_settings = json.loads(schedule_settings)
    # video_count is computed AFTER we know the actual video indices (below).
    # Don't trust schedule_settings.video_count - it can be stale (was set by an
    # earlier batch to a value the user no longer wants).

    # Check pending overrides
    pending_overrides = {}
    if isinstance(schedule_settings, dict):
        pending_overrides = schedule_settings.get("pending_overrides", {})

    scripts = db.query(models.Script).filter(models.Script.project_id == project_id).order_by(models.Script.video_index, models.Script.id.desc()).all()
    uploads = db.query(models.Upload).filter(models.Upload.project_id == project_id).all()
    jobs = db.query(models.Job).filter(models.Job.project_id == project_id, models.Job.job_type == "video").order_by(models.Job.created_at.desc()).all()
    
    # Map uploads to script ids
    upload_by_script = {u.script_id: u for u in uploads}
    job_by_index = {}
    for j in jobs:
        try:
            idx = int(j.logs.split("/")[0].replace("Video ", "")) - 1
            if idx not in job_by_index:
                job_by_index[idx] = j
        except:
            pass
    
    videos = []
    # Only show indices that have actual content (script, upload, or job).
    # Empty slots (where video_count is set but no script exists) are not padded
    # as cards - the frontend creates placeholders when the user clicks Generate.
    all_indices = set()
    for s in scripts:
        all_indices.add(s.video_index)
    for j in jobs:
        try:
            all_indices.add(int(j.logs.split("/")[0].replace("Video ", "")) - 1)
        except:
            pass
    for i in sorted(all_indices):
        # Pick the newest script per index that has an upload; fall back to newest overall
        idx_scripts = [s for s in scripts if s.video_index == i]
        script = None
        if idx_scripts:
            # Prefer script with upload, else take the newest (first since sorted id.desc)
            for s in idx_scripts:
                if s.id in upload_by_script:
                    script = s
                    break
            if not script:
                script = idx_scripts[0]
        upload = upload_by_script.get(script.id) if script else None
        job = job_by_index.get(i)
        
        # Check overrides from pending or from script
        overrides = None
        idx_str = str(i)
        merged_vo = {}
        if script and script.video_overrides:
            existing = script.video_overrides
            if isinstance(existing, str):
                existing = __import__("json").loads(existing)
            merged_vo.update(existing or {})
        if idx_str in pending_overrides:
            merged_vo.update(pending_overrides[idx_str] or {})
        overrides = merged_vo if merged_vo else None
        
        video_url = None
        if upload and upload.video_path:
            from pathlib import Path
            from app.config import settings
            video_path = Path(upload.video_path).resolve()
            storage = Path(settings.STORAGE_DIR).resolve()
            try:
                rel = video_path.relative_to(storage)
                video_url = f"/storage/{rel.as_posix()}"
            except ValueError:
                video_url = None
        
        videos.append({
            "index": i,
            "script": {
                "id": script.id if script else None,
                "title": script.title if script else None,
                "content": script.content[:500] if script and script.content else None,
                "scenes": (script.scenes if not isinstance(script.scenes, str) else (__import__("json").loads(script.scenes) if script.scenes else [])) if script and script.scenes else [],
                "hashtags": script.hashtags if script else None,
                "global_serial": script.global_serial if script else None,
                "created_at": script.created_at.isoformat() if script and script.created_at else None,
            } if script else None,
            "upload": {
                "id": upload.id,
                "status": upload.status,
                "scheduled_for": upload.scheduled_for.isoformat() if upload.scheduled_for else None,
                "title": upload.title,
                "youtube_video_id": upload.youtube_video_id,
                "archived_at": upload.archived_at.isoformat() if upload.archived_at else None,
                "video_url": video_url,
                "video_path": upload.video_path,
            } if upload else None,
            "job": {
                "id": job.id,
                "status": job.status,
                "progress": job.progress,
                "logs": job.logs,
                "current_stage": job.current_stage,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.created_at.isoformat() if job.created_at else None,
            } if job else None,
            "overrides": overrides,
        })
    
    return {"status": "success", "videos": videos, "video_count": len(videos)}

@router.delete("/{project_id}/videos/{video_index}", response_model=dict)
def delete_video(project_id: int, video_index: int, db: Session = Depends(get_db)):
    """Delete a video (script, assets, upload, files on disk) by index.

    For empty slots (no script) the endpoint still cleans up any orphan jobs
    and folder for that index, so it acts as a true 'remove this card' op.
    """
    import json as _json
    from pathlib import Path as _Path
    from app.config import settings
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    script = db.query(models.Script).filter(
        models.Script.project_id == project_id,
        models.Script.video_index == video_index
    ).first()

    if not script:
        # No script - still clean up orphan jobs and the folder for this slot
        orphan_jobs = db.query(models.Job).filter(
            models.Job.project_id == project_id,
            models.Job.logs.like(f"Video {video_index + 1}/%")
        ).all()
        for job in orphan_jobs:
            # Clean up prompt_logs and research_logs that FK-reference this job
            try:
                db.query(models.PromptLog).filter(models.PromptLog.job_id == job.id).delete()
            except Exception:
                pass
            try:
                db.query(models.ResearchLog).filter(models.ResearchLog.job_id == job.id).delete()
            except Exception:
                pass
            db.delete(job)
        # Clean up the on-disk folder for this video slot if it exists
        try:
            video_dir = _Path(settings.PROJECTS_DIR) / str(project_id) / "videos" / str(video_index)
            if video_dir.exists():
                import shutil
                shutil.rmtree(video_dir, ignore_errors=True)
            audio_dir = _Path(settings.PROJECTS_DIR) / str(project_id) / "audio" / str(video_index)
            if audio_dir.exists():
                import shutil
                shutil.rmtree(audio_dir, ignore_errors=True)
            final_dir = _Path(settings.PROJECTS_DIR) / str(project_id) / "final" / str(video_index)
            if final_dir.exists():
                import shutil
                shutil.rmtree(final_dir, ignore_errors=True)
        except Exception:
            pass
        # Lower schedule_settings.video_count if it was set above this index
        try:
            ss = project.schedule_settings
            if isinstance(ss, str):
                ss = _json.loads(ss) if ss else {}
            if isinstance(ss, dict) and ss.get("video_count", 1) > video_index + 1:
                ss["video_count"] = video_index  # truncate to this index
                project.schedule_settings = ss
        except Exception:
            pass
        db.commit()
        return {"status": "success", "message": f"Empty slot {video_index + 1} cleared"}

    # Delete associated assets on disk then from DB
    assets = db.query(models.Asset).filter(models.Asset.script_id == script.id).all()
    for asset in assets:
        if asset.local_path:
            try:
                p = __import__("pathlib").Path(asset.local_path)
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        db.delete(asset)

    # Delete upload file on disk then from DB
    uploads = db.query(models.Upload).filter(models.Upload.script_id == script.id).all()
    for upload in uploads:
        if upload.video_path:
            try:
                p = __import__("pathlib").Path(upload.video_path)
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        db.delete(upload)

    # Delete the script itself (cascade handles remaining relations)
    # Also clean up any jobs associated with this script's video_index
    jobs = db.query(models.Job).filter(
        models.Job.project_id == project_id,
        models.Job.logs.like(f"Video {video_index + 1}/%")
    ).all()
    for job in jobs:
        # Clean up prompt_logs and research_logs that FK-reference this job
        # (otherwise SQLite blocks the delete with FOREIGN KEY constraint failed)
        try:
            db.query(models.PromptLog).filter(models.PromptLog.job_id == job.id).delete()
        except Exception:
            pass
        try:
            db.query(models.ResearchLog).filter(models.ResearchLog.job_id == job.id).delete()
        except Exception:
            pass
        db.delete(job)

    if script.video_overrides:
        ss = project.schedule_settings
        if isinstance(ss, str):
            ss = __import__("json").loads(ss) if ss else {}
        pending = ss.get("pending_overrides", {}) if isinstance(ss, dict) else {}
        pending.pop(str(video_index), None)
        if isinstance(ss, dict):
            ss["pending_overrides"] = pending
            project.schedule_settings = ss

    db.delete(script)
    db.commit()

    # Clean up project video folder
    try:
        video_dir = __import__("pathlib").Path(project.video_path) if hasattr(project, "video_path") and project.video_path else None
        if not video_dir:
            from app.core.config import settings
            video_dir = __import__("pathlib").Path(settings.STORAGE_DIR) / str(project_id) / str(video_index)
        if video_dir and video_dir.exists():
            import shutil
            shutil.rmtree(str(video_dir), ignore_errors=True)
    except Exception:
        pass

    return {"status": "success", "message": f"Video {video_index + 1} deleted"}

@router.post("/{project_id}/videos/{video_index}/post", response_model=dict)
def post_single_video(project_id: int, video_index: int, db: Session = Depends(get_db)):
    """Schedule a single video for upload using global settings."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return scheduler_service.schedule_single_upload(project_id, video_index)

@router.put("/{project_id}/videos/{video_index}/settings", response_model=dict)
def update_video_settings(project_id: int, video_index: int, data: dict, db: Session = Depends(get_db)):
    """Update per-video style/voice/music overrides and regenerate."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    overrides = {
        "ai_style": data.get("ai_style"),
        "voice_id": data.get("voice_id"),
        "music_genre": data.get("music_genre"),
        "lora_strength": data.get("lora_strength"),
    }
    overrides = {k: v for k, v in overrides.items() if v is not None}
    return scheduler_service.regenerate_video(project_id, video_index, overrides)

@router.post("/suggest-topics", response_model=dict)
def suggest_topics(body: dict = {}, db: Session = Depends(get_db)):
    """Generate topic ideas for a category using Ollama."""
    import asyncio as _aio
    from app.services.research import research_service
    category = body.get("category", "tech")
    seed = body.get("seed", "")
    project_id = body.get("project_id", 0)
    try:
        topics = _aio.run(research_service.suggest_topics(
            category=category,
            seed=seed,
            project_id=project_id,
        ))
    except Exception:
        topics = _aio.run(research_service.suggest_topics(category, seed))
    return {"status": "success", "topics": topics}

@router.post("/trending-topics", response_model=dict)
def trending_topics(body: dict = {}, db: Session = Depends(get_db)):
    """Search web for trending topics in a category."""
    import asyncio as _aio
    from app.services.research import research_service
    category = body.get("category", "tech")
    project_id = body.get("project_id", 0)
    # Run the async coroutine. asyncio.run is the cleanest entry point and
    # works correctly with thread-locals (the service opens its own session
    # to avoid SQLAlchemy session-in-thread issues).
    try:
        topics = _aio.run(research_service.trending_topics(
            category=category,
            project_id=project_id,
        ))
    except Exception:
        topics = _aio.run(research_service.trending_topics(category))
    return {"status": "success", "topics": topics}

@router.post("/{project_id}/trending-now", response_model=dict)
def trending_now(project_id: int, body: dict = {}, db: Session = Depends(get_db)):
    """One-click trending: scrape → scripts → videos. No review phase."""
    import json as _json
    import asyncio as _aio
    from app.services.research import research_service
    from app.services.script import script_service

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    category = body.get("category", project.category)

    def run_async(coro):
        try:
            loop = _aio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(_aio.run, coro).result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return _aio.run(coro)

    # Don't pass db: the asyncio coroutine runs in a worker thread and a
    # SQLAlchemy session is not safe to share across threads. The service
    # opens its own session.
    trending = run_async(research_service.trending_topics(category, project_id=project_id))
    if not trending:
        trending = run_async(research_service.suggest_topics(
            category, "trending viral topics right now", project_id=project_id
        ))
    if not trending:
        return {"status": "error", "message": "Could not find trending topics"}

    trending_topic = trending[0]

    project.category = category
    project.source_value = trending_topic
    project.source_type = "auto_research"

    if body.get("duration"):
        vs = project.visual_settings
        if isinstance(vs, str): vs = _json.loads(vs) if vs else {}
        elif vs is None: vs = {}
        elif isinstance(vs, dict): vs = dict(vs)
        vs["total_duration"] = body["duration"]
        project.visual_settings = vs

    video_count = body.get("video_count", 1)
    ss = project.schedule_settings
    if isinstance(ss, str): ss = _json.loads(ss) if ss else {}
    elif ss is None: ss = {}
    elif isinstance(ss, dict): ss = dict(ss)
    ss["video_count"] = video_count
    project.schedule_settings = ss
    db.commit()

    schedule_settings = project.schedule_settings
    if isinstance(schedule_settings, str): schedule_settings = _json.loads(schedule_settings) if schedule_settings else {}
    visual_settings = project.visual_settings
    if isinstance(visual_settings, str): visual_settings = _json.loads(visual_settings) if visual_settings else {}
    duration = max(visual_settings.get("total_duration", 45) - (settings.OUTRO_DURATION_SECONDS or 0), 6)
    video_count = schedule_settings.get("video_count", 1) if isinstance(schedule_settings, dict) else 1

    results = []
    for i in range(video_count):
        existing = db.query(models.Script).filter(
            models.Script.project_id == project_id,
            models.Script.video_index == i
        ).first()
        if existing:
            results.append({
                "index": i, "id": existing.id, "title": existing.title,
                "status": "existing", "global_serial": existing.global_serial,
            })
            continue

        research = run_async(research_service.research_topic(
            f"{trending_topic} part {i + 1}", category
        ))
        script_data = run_async(script_service.generate_script(
            topic=research["topic"], category=category,
            context=research["context"], duration=duration
        ))
        max_serial = db.query(func.max(models.Script.global_serial)).scalar() or 0
        script = models.Script(
            project_id=project_id,
            title=script_data.get("title", research["topic"]),
            content=script_data.get("hook", "") + "\n\n" + "\n".join([s["narration_text"] for s in script_data.get("scenes", [])]),
            scenes=script_data.get("scenes", []),
            hashtags=",".join(script_data.get("hashtags", [])),
            status="approved",
            video_index=i,
            global_serial=max_serial + 1,
        )
        db.add(script)
        db.commit()
        db.refresh(script)
        results.append({
            "index": i, "id": script.id, "title": script.title,
            "status": "new", "global_serial": script.global_serial,
        })

    job_ids = []
    for i in range(video_count):
        job = models.Job(
            project_id=project_id,
            job_type="video",
            status="queued",
            logs=f"Video {i+1}/{video_count}",
            progress=0
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_ids.append(job.id)

    scheduler_service.scheduler.add_job(
        scheduler_service._process_job_queue,
        "date",
        run_date=datetime.utcnow() + timedelta(seconds=2),
        id=f"trending_now_{project_id}",
        replace_existing=True
    )

    return {
        "status": "success",
        "trending_topic": trending_topic,
        "trending_topics": trending,
        "scripts": results,
        "video_count": video_count,
        "job_ids": job_ids,
    }

@router.post("/{project_id}/cancel-all", response_model=dict)
def cancel_all_project_jobs(project_id: int, db: Session = Depends(get_db)):
    """Cancel all queued/running jobs for a project."""
    jobs = db.query(models.Job).filter(
        models.Job.project_id == project_id,
        models.Job.status.in_(["queued", "running"])
    ).all()
    count = 0
    for job in jobs:
        job.status = "cancelled"
        count += 1
    db.commit()
    return {"status": "success", "cancelled": count}

@router.post("/{project_id}/archive", response_model=dict)
def archive_project(project_id: int, db: Session = Depends(get_db)):
    """Manually archive all posted videos for this project."""
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    from app.services.archive import archive_service
    count = archive_service.archive_project(project_id)
    return {"status": "success", "archived": count}

@router.post("/{project_id}/generate-scripts", response_model=dict)
def generate_scripts(project_id: int, body: GenerateScriptsRequest = Body(GenerateScriptsRequest()), db: Session = Depends(get_db)):
    """Generate ONLY scripts (no t2v) for a batch. Synchronous — all Ollama calls."""
    import json as _json
    import asyncio as _aio
    from app.services.research import research_service
    from app.services.script import script_service

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.category:
        project.category = body.category
    if body.topic:
        project.source_value = body.topic
        project.source_type = "auto_research"
    if body.url:
        project.source_value = body.url
        project.source_type = "url"
    if body.source_type:
        project.source_type = body.source_type
    if body.duration:
        vs = project.visual_settings
        if isinstance(vs, str):
            vs = _json.loads(vs) if vs else {}
        elif vs is None:
            vs = {}
        elif isinstance(vs, dict):
            vs = dict(vs)
        vs["total_duration"] = body.duration
        project.visual_settings = vs
    if body.video_count:
        ss = project.schedule_settings
        if isinstance(ss, str):
            ss = _json.loads(ss) if ss else {}
        elif ss is None:
            ss = {}
        elif isinstance(ss, dict):
            ss = dict(ss)
        ss["video_count"] = body.video_count
        project.schedule_settings = ss
    db.commit()

    schedule_settings = project.schedule_settings
    if isinstance(schedule_settings, str):
        schedule_settings = _json.loads(schedule_settings) if schedule_settings else {}
    visual_settings = project.visual_settings
    if isinstance(visual_settings, str):
        visual_settings = _json.loads(visual_settings) if visual_settings else {}
    duration = max(visual_settings.get("total_duration", 45) - (settings.OUTRO_DURATION_SECONDS or 0), 6)
    video_count = schedule_settings.get("video_count", 1) if isinstance(schedule_settings, dict) else 1
    audio_settings = project.audio_settings
    if isinstance(audio_settings, str):
        audio_settings = _json.loads(audio_settings) if audio_settings else {}
    elif not isinstance(audio_settings, dict):
        audio_settings = {}
    voice_id = audio_settings.get("voice_id", "en-US-AriaNeural")
    voice_custom = audio_settings.get("voice_custom", "")
    music_genre = audio_settings.get("music_genre", "ambient")
    music_custom = audio_settings.get("music_custom", "")

    def run_async(coro):
        try:
            loop = _aio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(_aio.run, coro).result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return _aio.run(coro)

    # Find next available index for appending
    max_index = db.query(func.max(models.Script.video_index)).filter(
        models.Script.project_id == project_id
    ).scalar() or -1
    start_index = max_index + 1

    results = []
    for offset in range(video_count):
        i = start_index + offset

        if project.source_type == "url" and project.source_value:
            web_content = run_async(research_service.summarize_webpage(project.source_value))
            topic = f"{project.source_value} part {i + 1}"
            context = web_content
        else:
            research = run_async(research_service.research_topic(
                f"{project.source_value} part {i + 1}",
                project.category
            ))
            topic = research["topic"]
            context = research["context"]

        script_data = run_async(script_service.generate_script(
            topic=topic,
            category=project.category,
            context=context,
            duration=duration,
            voice_id=voice_id,
            voice_custom=voice_custom,
            music_genre=music_genre,
            music_custom=music_custom
        ))

        max_serial = db.query(func.max(models.Script.global_serial)).scalar() or 0
        music_prompt = script_data.get("music_prompt", "")
        # Merge any pending per-video overrides (set before script existed) with music_prompt
        pending = schedule_settings.get("pending_overrides", {}) if isinstance(schedule_settings, dict) else {}
        pending_for_idx = pending.get(str(i), {}) or {}
        merged_overrides = dict(pending_for_idx)
        if music_prompt:
            merged_overrides["music_prompt"] = music_prompt
        video_overrides = merged_overrides if merged_overrides else None
        script = models.Script(
            project_id=project_id,
            title=script_data.get("title", topic),
            content=script_data.get("hook", "") + "\n\n" + "\n".join([s["narration_text"] for s in script_data.get("scenes", [])]),
            scenes=script_data.get("scenes", []),
            hashtags=",".join(script_data.get("hashtags", [])),
            status="approved",
            video_index=i,
            global_serial=max_serial + 1,
            video_overrides=video_overrides,
        )
        db.add(script)
        db.commit()
        db.refresh(script)
        # Clear consumed pending overrides for this index
        if str(i) in pending:
            pending.pop(str(i), None)
            schedule_settings["pending_overrides"] = pending
            project.schedule_settings = schedule_settings
            db.commit()

        results.append({
            "index": i,
            "id": script.id,
            "title": script.title,
            "content": script.content[:500],
            "scenes": script.scenes if not isinstance(script.scenes, str) else (_json.loads(script.scenes) if script.scenes else []),
            "global_serial": script.global_serial,
            "created_at": script.created_at.isoformat() if script.created_at else None,
            "status": "new",
        })

    return {"status": "success", "scripts": results, "video_count": start_index + len(results)}


@router.post("/{project_id}/add-videos", response_model=dict)
def add_new_videos(project_id: int, body: AddVideosRequest = Body(AddVideosRequest()), db: Session = Depends(get_db)):
    """Append N new scripts at max(video_index)+1..+N and queue video jobs for them.

    Used by the "+ Add N New Videos" button when a project already has scripts/videos.
    Does NOT touch existing scripts or jobs - safe to call when a pipeline is mid-run.
    """
    import json as _json
    import asyncio as _aio
    from datetime import datetime, timedelta
    from app.services.research import research_service
    from app.services.script import script_service
    from app.services.scheduler import scheduler_service

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    count = max(1, min(32, body.count))
    if body.category:
        project.category = body.category
    if body.topic:
        project.source_value = body.topic
        project.source_type = "auto_research"
    if body.url:
        project.source_value = body.url
        project.source_type = "url"
    if body.source_type:
        project.source_type = body.source_type
    if body.duration:
        vs = project.visual_settings
        if isinstance(vs, str):
            vs = _json.loads(vs) if vs else {}
        elif vs is None:
            vs = {}
        elif isinstance(vs, dict):
            vs = dict(vs)
        vs["total_duration"] = body.duration
        project.visual_settings = vs
    db.commit()

    schedule_settings = project.schedule_settings
    if isinstance(schedule_settings, str):
        schedule_settings = _json.loads(schedule_settings) if schedule_settings else {}
    visual_settings = project.visual_settings
    if isinstance(visual_settings, str):
        visual_settings = _json.loads(visual_settings) if visual_settings else {}
    duration = max(visual_settings.get("total_duration", 45) - (settings.OUTRO_DURATION_SECONDS or 0), 6)
    audio_settings = project.audio_settings
    if isinstance(audio_settings, str):
        audio_settings = _json.loads(audio_settings) if audio_settings else {}
    elif not isinstance(audio_settings, dict):
        audio_settings = {}
    voice_id = audio_settings.get("voice_id", "en-US-AriaNeural")
    voice_custom = audio_settings.get("voice_custom", "")
    music_genre = audio_settings.get("music_genre", "ambient")
    music_custom = audio_settings.get("music_custom", "")

    def run_async(coro):
        try:
            loop = _aio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(_aio.run, coro).result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return _aio.run(coro)

    # Find next available index for appending
    max_index = db.query(func.max(models.Script.video_index)).filter(
        models.Project.id == project_id
    ).scalar() or -1
    start_index = max_index + 1

    new_scripts = []
    new_indices = []
    for offset in range(count):
        i = start_index + offset
        new_indices.append(i)

        if project.source_type == "url" and project.source_value:
            web_content = run_async(research_service.summarize_webpage(project.source_value))
            topic = f"{project.source_value} part {i + 1}"
            context = web_content
        else:
            research = run_async(research_service.research_topic(
                f"{project.source_value} part {i + 1}",
                project.category
            ))
            topic = research["topic"]
            context = research["context"]

        script_data = run_async(script_service.generate_script(
            topic=topic,
            category=project.category,
            context=context,
            duration=duration,
            voice_id=voice_id,
            voice_custom=voice_custom,
            music_genre=music_genre,
            music_custom=music_custom
        ))

        max_serial = db.query(func.max(models.Script.global_serial)).scalar() or 0
        music_prompt = script_data.get("music_prompt", "")
        pending = schedule_settings.get("pending_overrides", {}) if isinstance(schedule_settings, dict) else {}
        pending_for_idx = pending.get(str(i), {}) or {}
        merged_overrides = dict(pending_for_idx)
        if music_prompt:
            merged_overrides["music_prompt"] = music_prompt
        video_overrides = merged_overrides if merged_overrides else None
        script = models.Script(
            project_id=project_id,
            title=script_data.get("title", topic),
            content=script_data.get("hook", "") + "\n\n" + "\n".join([s["narration_text"] for s in script_data.get("scenes", [])]),
            scenes=script_data.get("scenes", []),
            hashtags=",".join(script_data.get("hashtags", [])),
            status="approved",
            video_index=i,
            global_serial=max_serial + 1,
            video_overrides=video_overrides,
        )
        db.add(script)
        db.commit()
        db.refresh(script)
        if str(i) in pending:
            pending.pop(str(i), None)
            schedule_settings["pending_overrides"] = pending
            project.schedule_settings = schedule_settings
            db.commit()
        new_scripts.append({"index": i, "id": script.id, "title": script.title})

    # Bump schedule_settings.video_count so the new indices are inside the planned range
    new_video_count = start_index + count
    if isinstance(schedule_settings, dict):
        schedule_settings["video_count"] = new_video_count
        project.schedule_settings = schedule_settings
        db.commit()

    # Queue a video job for EACH new index, tagged with the actual video_num so the
    # scheduler hits the right video_index (not 0)
    job_ids = []
    for i in new_indices:
        job = models.Job(
            project_id=project_id,
            job_type="video",
            status="queued",
            logs=f"Video {i + 1}/{new_video_count}",
            progress=0,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_ids.append(job.id)
        scheduler_service.scheduler.add_job(
            scheduler_service._run_single_video_job_by_id,
            "date",
            run_date=datetime.now() + timedelta(seconds=2),
            args=[job.id],
            id=f"add_video_{project_id}_{i}",
            replace_existing=True,
        )

    return {
        "status": "success",
        "added": count,
        "start_index": start_index,
        "scripts": new_scripts,
        "job_ids": job_ids,
    }


@router.post("/{project_id}/videos/{video_index}/regenerate-script", response_model=dict)
def regenerate_script(project_id: int, video_index: int, db: Session = Depends(get_db)):
    """Regenerate a single script for a video (no t2v)."""
    import json as _json
    import asyncio as _aio
    from app.services.research import research_service
    from app.services.script import script_service

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete existing script + assets for this video_index
    existing = db.query(models.Script).filter(
        models.Script.project_id == project_id,
        models.Script.video_index == video_index
    ).first()
    if existing:
        db.query(models.Asset).filter(models.Asset.script_id == existing.id).delete()
        db.delete(existing)
        db.commit()

    schedule_settings = project.schedule_settings
    if isinstance(schedule_settings, str):
        schedule_settings = _json.loads(schedule_settings) if schedule_settings else {}
    visual_settings = project.visual_settings
    if isinstance(visual_settings, str):
        visual_settings = _json.loads(visual_settings) if visual_settings else {}
    duration = max(visual_settings.get("total_duration", 45) - (settings.OUTRO_DURATION_SECONDS or 0), 6)
    video_count = schedule_settings.get("video_count", 1) if isinstance(schedule_settings, dict) else 1
    audio_settings = project.audio_settings
    if isinstance(audio_settings, str):
        audio_settings = _json.loads(audio_settings) if audio_settings else {}
    elif not isinstance(audio_settings, dict):
        audio_settings = {}
    voice_id = audio_settings.get("voice_id", "en-US-AriaNeural")
    voice_custom = audio_settings.get("voice_custom", "")
    music_genre = audio_settings.get("music_genre", "ambient")
    music_custom = audio_settings.get("music_custom", "")

    def run_async(coro):
        try:
            loop = _aio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(_aio.run, coro).result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return _aio.run(coro)

    if project.source_type == "url" and project.source_value:
        web_content = run_async(research_service.summarize_webpage(project.source_value))
        topic = f"{project.source_value} part {video_index + 1}"
        context = web_content
    else:
        research = run_async(research_service.research_topic(
            f"{project.source_value} part {video_index + 1}",
            project.category
        ))
        topic = research["topic"]
        context = research["context"]

        script_data = run_async(script_service.generate_script(
            topic=topic,
            category=project.category,
            context=context,
            duration=duration,
            voice_id=voice_id,
            voice_custom=voice_custom,
            music_genre=music_genre,
            music_custom=music_custom
        ))

        max_serial = db.query(func.max(models.Script.global_serial)).scalar() or 0
        music_prompt = script_data.get("music_prompt", "")
    # Merge any pending per-video overrides (set before script existed) with music_prompt
    pending = schedule_settings.get("pending_overrides", {}) if isinstance(schedule_settings, dict) else {}
    pending_for_idx = pending.get(str(video_index), {}) or {}
    merged_overrides = dict(pending_for_idx)
    if music_prompt:
        merged_overrides["music_prompt"] = music_prompt
    video_overrides = merged_overrides if merged_overrides else None
    script = models.Script(
        project_id=project_id,
        title=script_data.get("title", topic),
        content=script_data.get("hook", "") + "\n\n" + "\n".join([s["narration_text"] for s in script_data.get("scenes", [])]),
        scenes=script_data.get("scenes", []),
        hashtags=",".join(script_data.get("hashtags", [])),
        status="approved",
        video_index=video_index,
        global_serial=max_serial + 1,
        video_overrides=video_overrides,
    )
    db.add(script)
    db.commit()
    db.refresh(script)
    # Clear consumed pending overrides for this index
    if str(video_index) in pending:
        pending.pop(str(video_index), None)
        schedule_settings["pending_overrides"] = pending
        project.schedule_settings = schedule_settings
        db.commit()

    return {
        "status": "success",
        "script": {
            "id": script.id,
            "title": script.title,
            "content": script.content[:500],
            "scenes": script.scenes if not isinstance(script.scenes, str) else (_json.loads(script.scenes) if script.scenes else []),
            "global_serial": script.global_serial,
            "created_at": script.created_at.isoformat() if script.created_at else None,
        }
    }

@router.post("/{project_id}/videos/{video_index}/generate", response_model=dict)
def generate_single_video(project_id: int, video_index: int, db: Session = Depends(get_db)):
    """Queue a video job for a specific script index.

    The user has already approved/reviewed the script. The scheduler reuses
    the existing script as-is (does NOT regenerate it) and runs the rest of
    the pipeline (t2v, voice, music, assembly).
    """
    import json as _json
    from datetime import datetime, timedelta

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Sanity: there should be a script for this index. If not, refuse - the
    # caller should use the scripts-generation path first.
    existing = db.query(models.Script).filter(
        models.Script.project_id == project_id,
        models.Script.video_index == video_index
    ).first()
    if not existing:
        raise HTTPException(
            status_code=400,
            detail=f"No script at index {video_index}. Generate scripts first.",
        )

    # Clear stale batch/generate jobs for this project to prevent extra processing
    db.query(models.Job).filter(
        models.Job.project_id == project_id,
        models.Job.job_type.in_(["batch", "generate"]),
        models.Job.status == "queued"
    ).delete()
    db.commit()

    schedule_settings = _json.loads(project.schedule_settings) if isinstance(project.schedule_settings, str) else project.schedule_settings
    # Use actual script count, not schedule_settings.video_count (which is the last batch size)
    video_count = db.query(func.count(models.Script.id)).filter(
        models.Script.project_id == project_id
    ).scalar() or 1

    # Resume-from-checkpoint: if a previous video job for this same
    # (project, video_index) ended in cancelled/failed and recorded a
    # current_stage, inherit that stage so the scheduler skips already-
    # completed work. Files persist on disk between runs, so the per-stage
    # "skip if file exists" guards handle the actual resume.
    resume_stage = None
    last_video_job = (
        db.query(models.Job)
        .filter(
            models.Job.project_id == project_id,
            models.Job.job_type == "video",
            models.Job.status.in_(["cancelled", "failed"]),
        )
        .order_by(models.Job.id.desc())
        .first()
    )
    # Match the last job to this specific video by parsing its logs. The
    # scheduler always prefixes with "Video N/..." on the first log line.
    if last_video_job and last_video_job.logs:
        try:
            first_line = last_video_job.logs.split("\n", 1)[0]
            n_part = first_line.split("/")[0].replace("Video ", "").strip()
            if int(n_part) == video_index + 1 and last_video_job.current_stage:
                if last_video_job.current_stage != "completed":
                    resume_stage = last_video_job.current_stage
        except Exception:
            pass

    job = models.Job(
        project_id=project_id,
        job_type="video",
        status="queued",
        logs=f"Video {video_index + 1}/{video_count}" + (
            f" — resuming from {resume_stage}" if resume_stage else ""
        ),
        progress=0,
        current_stage=resume_stage,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    scheduler_service.scheduler.add_job(
        scheduler_service._run_single_video_job_by_id,
        "date",
        run_date=datetime.now() + timedelta(seconds=2),
        args=[job.id],
        id=f"single_video_{project_id}_{video_index}",
        replace_existing=True
    )

    return {"status": "success", "job_id": job.id, "video_index": video_index}

@router.get("/{project_id}/scripts", response_model=list)
def list_project_scripts(project_id: int, db: Session = Depends(get_db)):
    scripts = db.query(models.Script).filter(models.Script.project_id == project_id).all()
    return [
        {
            "id": s.id,
            "project_id": s.project_id,
            "title": s.title,
            "content": s.content,
            "scenes": s.scenes if not isinstance(s.scenes, str) else __import__("json").loads(s.scenes),
            "hashtags": s.hashtags,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None
        }
        for s in scripts
    ]

@router.get("/{project_id}/jobs", response_model=list)
def list_project_jobs(project_id: int, db: Session = Depends(get_db)):
    jobs = db.query(models.Job).filter(models.Job.project_id == project_id).order_by(models.Job.created_at.desc()).all()
    return [
        {
            "id": j.id,
            "project_id": j.project_id,
            "job_type": j.job_type,
            "status": j.status,
            "progress": j.progress,
            "logs": j.logs,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None
        }
        for j in jobs
    ]

@router.get("/{project_id}/uploads", response_model=list)
def list_project_uploads(project_id: int, db: Session = Depends(get_db)):
    uploads = db.query(models.Upload).filter(models.Upload.project_id == project_id).order_by(models.Upload.scheduled_for.desc()).all()
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
            "tags": u.tags
        }
        for u in uploads
    ]


@router.post("/{project_id}/videos/{video_index}/scenes/{scene_index}/regenerate", response_model=dict)
def regenerate_scene(project_id: int, video_index: int, scene_index: int,
                       seed_offset: int = 1,
                       custom_prompt: str = None,
                       db: Session = Depends(get_db)):
    """Regenerate ONE scene without running the rest of the pipeline.

    Re-runs ComfyUI t2v for that one scene with a new seed (deterministic
    offset from the original), overwrites videos/{idx}/scene_{NN:02d}.mp4,
    and updates the Asset row. Does NOT touch voiceover, music, or assembly.
    After regenerating, call /reassemble to rebuild the final video.

    Args:
        project_id: Project ID
        video_index: 0-based video index
        scene_index: 0-based scene index
        seed_offset: How much to shift the seed from the original (default 1).
                     Increase to get a more different take.
        custom_prompt: Optional user-tweaked visual description. When
                       provided, replaces the script's visual_description
                       for this scene. Trigger words + suffix are still
                       applied automatically. The script itself is NOT
                       updated — this is a one-shot override.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = scheduler_service.regenerate_single_scene(
        project_id=project_id,
        video_index=video_index,
        scene_index=scene_index,
        seed_offset=seed_offset,
        custom_prompt=custom_prompt,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Regeneration failed"))
    return result


@router.post("/{project_id}/videos/{video_index}/reassemble", response_model=dict)
def reassemble_final_video(project_id: int, video_index: int,
                            db: Session = Depends(get_db)):
    """Re-run only the assembly step to rebuild the final video.

    Uses the existing scene_NN.mp4 files in videos/{idx}/ and existing
    audio assets. Does NOT regenerate t2v, voice, or music. Use after
    per-scene regeneration to incorporate new clips into the final mp4.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = scheduler_service.reassemble_video(
        project_id=project_id,
        video_index=video_index,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Reassembly failed"))
    return result


@router.post("/{project_id}/videos/{video_index}/clean-scenes", response_model=dict)
def clean_video_scenes(project_id: int, video_index: int, db: Session = Depends(get_db)):
    """Delete intermediate scene clips and audio chunks to free disk space.

    Keeps the final_video.mp4 and the script. After cleanup, per-scene
    regeneration on this video is LOCKED (would need a full re-render).
    Idempotent: returns 200 with bytes_freed=0 if already cleaned.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    script = db.query(models.Script).filter(
        models.Script.project_id == project_id,
        models.Script.video_index == video_index
    ).order_by(models.Script.created_at.desc()).first()
    if not script:
        raise HTTPException(status_code=404, detail="No script for this video")

    result = scheduler_service.cleanup_intermediate_scenes(
        project_id=project_id,
        video_index=video_index,
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", "Cleanup failed"))
    return result


@router.get("/{project_id}/videos/{video_index}/scenes", response_model=list)
def list_video_scenes(project_id: int, video_index: int,
                       db: Session = Depends(get_db)):
    """List all scenes for a video with file existence info + prompt details.

    Used by the EditVideoModal Scenes tab to show per-scene regenerate UI
    AND a prompt editor where the user can tweak the visual description
    before regenerating. Returns one row per scene with: scene_index,
    scene_number, has_clip, clip_path, full narration text, full
    visual_description, the last `final_prompt` that was sent to ComfyUI
    (for context), trigger_words, lora_name, and regen status.
    """
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    script = db.query(models.Script).filter(
        models.Script.project_id == project_id,
        models.Script.video_index == video_index,
    ).order_by(models.Script.created_at.desc()).first()
    if not script:
        return []

    # Scenes are stored in the dedicated JSON column
    scenes = script.scenes or []

    base_dir = settings.PROJECTS_DIR / str(project_id)
    videos_dir = base_dir / "videos" / str(video_index)

    # Pull the most-recent PromptLog per scene for this project (any job).
    # Keyed by scene_index for quick lookup in the loop below.
    latest_prompts = {}
    try:
        log_rows = db.query(models.PromptLog).filter(
            models.PromptLog.project_id == project_id,
            models.PromptLog.scene_index.isnot(None),
        ).order_by(models.PromptLog.created_at.desc()).limit(200).all()
        for row in log_rows:
            if row.scene_index not in latest_prompts:
                latest_prompts[row.scene_index] = row
    except Exception:
        pass

    out = []
    for i, scene in enumerate(scenes):
        clip = videos_dir / f"scene_{i+1:02d}.mp4"
        narration = (scene.get("narration_text") or scene.get("narration") or "") if isinstance(scene, dict) else ""
        visual_desc = (scene.get("visual_description") or "") if isinstance(scene, dict) else ""
        prompt_row = latest_prompts.get(i)
        out.append({
            "scene_index": i,
            "scene_number": i + 1,
            "has_clip": clip.exists(),
            "clip_path": str(clip) if clip.exists() else None,
            "narration": narration,
            "narration_preview": narration[:140] + ("..." if len(narration) > 140 else ""),
            "visual_description": visual_desc,
            "visual_description_preview": visual_desc[:200] + ("..." if len(visual_desc) > 200 else ""),
            "duration_seconds": scene.get("duration_seconds", 8) if isinstance(scene, dict) else 8,
            # From the latest PromptLog (if any) so the user can see what
            # was actually sent to ComfyUI for this scene:
            "final_prompt": prompt_row.final_prompt if prompt_row else None,
            "trigger_words": prompt_row.trigger_words if prompt_row else None,
            "suffix": prompt_row.suffix if prompt_row else None,
            "lora_name": prompt_row.lora_name if prompt_row else None,
            "seed": prompt_row.seed if prompt_row else None,
            "status": prompt_row.status if prompt_row else None,
        })
    return out

# ── Calendar endpoints ──────────────────────────────────────────────────

@router.get("/{project_id}/calendar", response_model=dict)
def get_project_calendar(project_id: int, year: int, month: int, db: Session = Depends(get_db)):
    """Return uploads grouped by day for a given month.
    Response: { "days": { "1": 3, "5": 1, ... }, "uploads": [...] } """
    from datetime import date, timedelta
    from calendar import monthrange

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    start = date(year, month, 1)
    _, last = monthrange(year, month)
    end = date(year, month, last)

    uploads = db.query(models.Upload).filter(
        models.Upload.project_id == project_id,
        models.Upload.scheduled_for >= start,
        models.Upload.scheduled_for <= end + timedelta(days=1),
    ).order_by(models.Upload.scheduled_for).all()

    days = {}
    upload_list = []
    for u in uploads:
        d = u.scheduled_for.day if u.scheduled_for else None
        if d:
            days[str(d)] = days.get(str(d), 0) + 1
        upload_list.append({
            "id": u.id,
            "script_id": u.script_id,
            "title": u.title,
            "status": u.status,
            "scheduled_for": u.scheduled_for.isoformat() if u.scheduled_for else None,
            "youtube_video_id": u.youtube_video_id,
            "video_path": u.video_path,
        })

    return {"days": days, "uploads": upload_list}


@router.get("/{project_id}/calendar/{datestr}", response_model=dict)
def get_project_calendar_day(project_id: int, datestr: str, db: Session = Depends(get_db)):
    """Return detailed uploads for a specific day (YYYY-MM-DD)."""
    from datetime import date, datetime as dt

    try:
        d = dt.strptime(datestr, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    uploads = db.query(models.Upload).filter(
        models.Upload.project_id == project_id,
        models.Upload.scheduled_for >= dt(d.year, d.month, d.day),
        models.Upload.scheduled_for < dt(d.year, d.month, d.day) + timedelta(days=1),
    ).order_by(models.Upload.scheduled_for).all()

    return {
        "date": datestr,
        "uploads": [{
            "id": u.id,
            "script_id": u.script_id,
            "title": u.title,
            "status": u.status,
            "scheduled_for": u.scheduled_for.isoformat() if u.scheduled_for else None,
            "time": u.scheduled_for.strftime("%H:%M") if u.scheduled_for else None,
            "youtube_video_id": u.youtube_video_id,
            "video_path": u.video_path,
        } for u in uploads],
    }


def _project_to_dict(project):
    import json as _json
    def _parse(val):
        if val is None:
            return {}
        if isinstance(val, str):
            try:
                return _json.loads(val)
            except Exception:
                return {}
        return val
    channel = project.youtube_channel
    return {
        "id": project.id,
        "name": project.name,
        "status": project.status,
        "source_type": project.source_type,
        "source_value": project.source_value,
        "category": project.category,
        "subcategory": project.subcategory,
        "visual_type": project.visual_type,
        "visual_settings": _parse(project.visual_settings),
        "audio_settings": _parse(project.audio_settings),
        "caption_settings": _parse(project.caption_settings),
        "schedule_settings": _parse(project.schedule_settings),
        "seo_settings": _parse(project.seo_settings),
        "youtube_channel_id": project.youtube_channel_id,
        "archive_path": project.archive_path,
        "archived_at": project.archived_at.isoformat() if project.archived_at else None,
        "youtube_channel": {
            "id": channel.id,
            "name": channel.name,
            "channel_id": channel.channel_id,
            "channel_title": channel.channel_title,
            "thumbnail_url": channel.thumbnail_url,
        } if channel else None,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None
    }
