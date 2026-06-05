from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.database import get_db
from app import models
from app.services.scheduler import scheduler_service

router = APIRouter(prefix="/projects", tags=["projects"])

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
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"status": "deleted"}

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
    video_count = schedule_settings.get("video_count", 1) if isinstance(schedule_settings, dict) else 1
    
    # Check pending overrides
    pending_overrides = {}
    if isinstance(schedule_settings, dict):
        pending_overrides = schedule_settings.get("pending_overrides", {})
    
    scripts = db.query(models.Script).filter(models.Script.project_id == project_id).order_by(models.Script.video_index).all()
    uploads = db.query(models.Upload).filter(models.Upload.project_id == project_id).all()
    jobs = db.query(models.Job).filter(models.Job.project_id == project_id, models.Job.job_type == "video").order_by(models.Job.created_at.desc()).all()
    
    # Map uploads and jobs to scripts
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
    for i in range(video_count):
        script = next((s for s in scripts if s.video_index == i), None)
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
        
        videos.append({
            "index": i,
            "script": {
                "id": script.id if script else None,
                "title": script.title if script else None,
                "content": script.content[:500] if script and script.content else None,
                "scenes": script.scenes if script and script.scenes else [],
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
            } if upload else None,
            "job": {
                "id": job.id,
                "status": job.status,
                "progress": job.progress,
                "logs": job.logs,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.created_at.isoformat() if job.created_at else None,
            } if job else None,
            "overrides": overrides,
        })
    
    return {"status": "success", "videos": videos, "video_count": video_count}

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
def suggest_topics(body: dict = {}):
    """Generate topic ideas for a category using Ollama."""
    import asyncio as _aio
    from app.services.research import research_service
    category = body.get("category", "tech")
    seed = body.get("seed", "")
    try:
        loop = _aio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                topics = pool.submit(_aio.run, research_service.suggest_topics(category, seed)).result()
        else:
            topics = loop.run_until_complete(research_service.suggest_topics(category, seed))
    except RuntimeError:
        topics = _aio.run(research_service.suggest_topics(category, seed))
    return {"status": "success", "topics": topics}

@router.post("/trending-topics", response_model=dict)
def trending_topics(body: dict = {}):
    """Search web for trending topics in a category."""
    import asyncio as _aio
    from app.services.research import research_service
    category = body.get("category", "tech")
    try:
        loop = _aio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                topics = pool.submit(_aio.run, research_service.trending_topics(category)).result()
        else:
            topics = loop.run_until_complete(research_service.trending_topics(category))
    except RuntimeError:
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

    trending = run_async(research_service.trending_topics(category))
    if not trending:
        trending = run_async(research_service.suggest_topics(category, "trending viral topics right now"))
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

    video_count = body.get("video_count", 3)
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
    duration = visual_settings.get("total_duration", 45)
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
def generate_scripts(project_id: int, body: dict = {}, db: Session = Depends(get_db)):
    """Generate ONLY scripts (no t2v) for a batch. Synchronous — all Ollama calls."""
    import json as _json
    import asyncio as _aio
    from app.services.research import research_service
    from app.services.script import script_service

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

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
            vs = _json.loads(vs) if vs else {}
        elif vs is None:
            vs = {}
        elif isinstance(vs, dict):
            vs = dict(vs)
        vs["total_duration"] = body["duration"]
        project.visual_settings = vs
    if body.get("video_count"):
        ss = project.schedule_settings
        if isinstance(ss, str):
            ss = _json.loads(ss) if ss else {}
        elif ss is None:
            ss = {}
        elif isinstance(ss, dict):
            ss = dict(ss)
        ss["video_count"] = body["video_count"]
        project.schedule_settings = ss
    db.commit()

    schedule_settings = project.schedule_settings
    if isinstance(schedule_settings, str):
        schedule_settings = _json.loads(schedule_settings) if schedule_settings else {}
    visual_settings = project.visual_settings
    if isinstance(visual_settings, str):
        visual_settings = _json.loads(visual_settings) if visual_settings else {}
    duration = visual_settings.get("total_duration", 45)
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

    return {"status": "success", "scripts": results, "video_count": video_count}

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
    duration = visual_settings.get("total_duration", 45)
    video_count = schedule_settings.get("video_count", 1) if isinstance(schedule_settings, dict) else 1
    audio_settings = project.audio_settings
    if isinstance(audio_settings, str):
        audio_settings = _json.loads(audio_settings) if audio_settings else {}
    elif not isinstance(audio_settings, dict):
        audio_settings = {}
    voice_id = audio_settings.get("voice_id", "en-US-AriaNeural")
    music_genre = audio_settings.get("music_genre", "ambient")

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
