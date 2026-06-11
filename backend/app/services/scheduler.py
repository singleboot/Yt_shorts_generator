import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import List
from pathlib import Path
from sqlalchemy import func
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.config import settings
from app.database import SessionLocal
from app import models
from app.services.research import research_service
from app.services.script import script_service
from app.services.visuals import visuals_service
from app.services.audio import audio_service
from app.services.video import video_service
from app.services.youtube import youtube_service
from app.services.telegram import telegram_bot

class SchedulerService:
    def __init__(self):
        import threading
        self._queue_lock = threading.Lock()
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self._register_default_jobs()
        # Active job tracker for cancellation. Maps job_id -> True when cancelled.
        # Polled by long-running pipeline stages so they bail out promptly.
        self._cancelled: set = set()
        # Tracks which job is currently driving the ComfyUI client, so the
        # /jobs/{id}/cancel route can interrupt ComfyUI.
        self._active_job_id: int = None

        # Clean up any stuck "running" jobs from a previous run
        db = SessionLocal()
        try:
            stuck_jobs = db.query(models.Job).filter(models.Job.status == "running").all()
            for job in stuck_jobs:
                job.status = "failed"
                job.logs += "\n[System] Job aborted due to server restart."
            db.commit()
        except Exception as e:
            print(f"Failed to clean up stuck running jobs: {e}")
        finally:
            db.close()

    def is_cancelled(self, job_id: int) -> bool:
        return job_id in self._cancelled

    def mark_cancelled(self, job_id: int):
        self._cancelled.add(job_id)
        # Best-effort: interrupt the current ComfyUI render AND clear its queue
        # so nothing in the pending queue starts next.
        try:
            import asyncio as aio
            try:
                loop = aio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        pool.submit(aio.run, visuals_service.comfyui.full_stop()).result(timeout=10)
                else:
                    loop.run_until_complete(visuals_service.comfyui.full_stop())
            except RuntimeError:
                aio.run(visuals_service.comfyui.full_stop())
        except Exception as e:
            print(f"mark_cancelled: ComfyUI full_stop failed (non-fatal): {e}")


    def _register_default_jobs(self):
        """Register the daily research job."""
        # Daily research at midnight
        self.scheduler.add_job(
            self._daily_research_job,
            CronTrigger(hour=0, minute=0),
            id="daily_research",
            replace_existing=True
        )

        # Periodic job-queue processor — picks up any orphaned "queued" jobs
        # (e.g., a previous uvicorn process was killed mid-run) every 10s.
        self.scheduler.add_job(
            self._process_job_queue,
            "interval",
            seconds=10,
            id="job_queue_picker",
            replace_existing=True,
            max_instances=1,
            coalesce=True
        )

        # Upload checker every 15 minutes
        self.scheduler.add_job(
            self._process_upload_queue,
            "interval",
            minutes=15,
            id="upload_queue",
            replace_existing=True
        )
    
    def _daily_research_job(self):
        """Run research for all active projects with auto_generate enabled."""
        db = SessionLocal()
        try:
            projects = db.query(models.Project).filter(
                models.Project.status == "active"
            ).all()
            
            for project in projects:
                import json
                schedule_settings = json.loads(project.schedule_settings) if isinstance(project.schedule_settings, str) else project.schedule_settings
                if schedule_settings.get("auto_generate"):
                    # Create a job for batch generation
                    job = models.Job(
                        project_id=project.id,
                        job_type="batch",
                        status="queued"
                    )
                    db.add(job)
            
            db.commit()
            
            # Process queued jobs
            self._process_job_queue()
            
        finally:
            db.close()
    
    def _process_job_queue(self):
        """Process ONE queued generation job, then return.

        The APScheduler periodic trigger (every 10 s) will pick up the next
        queued job after the current one finishes.  This guarantees strictly
        sequential execution: one complete video is produced before the next
        one starts, regardless of how many are queued.
        """
        # Non-blocking acquire so that only one thread drives the queue at a time.
        if not self._queue_lock.acquire(blocking=False):
            return

        try:
            db = SessionLocal()
            try:
                # If any generation job is still marked "running" (e.g. from a
                # previous call that is not yet finished), do nothing — the
                # periodic trigger will retry in 10 s.
                running_job = db.query(models.Job).filter(
                    models.Job.status == "running",
                    models.Job.job_type.in_(["batch", "generate", "video"])
                ).first()
                if running_job:
                    return

                # Fetch the single oldest queued job.
                job = db.query(models.Job).filter(
                    models.Job.status == "queued",
                    models.Job.job_type.in_(["batch", "generate", "video"])
                ).order_by(models.Job.id.asc()).first()

                if not job:
                    return

                # Mark it as running immediately so concurrent callers see it.
                job.status = "running"
                job.started_at = datetime.utcnow()
                db.commit()
                db.refresh(job)

                try:
                    if job.job_type == "video":
                        self._run_single_video_job(db, job)
                    else:
                        self._run_generation_job(db, job)
                    job.status = "completed"
                    job.progress = 100
                    db.commit()
                    telegram_bot.notify_job_status(job.id, job.logs, job.progress, job.status, result=getattr(job, "result", None))
                except Exception as e:
                    job.status = "failed"
                    job.logs += f"\nError: {str(e)}"
                    db.commit()
                    telegram_bot.notify_job_status(job.id, job.logs, job.progress, job.status)
            finally:
                db.close()
        finally:
            self._queue_lock.release()

        # After completing (or failing) a job, schedule an immediate check for
        # the next queued job via APScheduler (avoids deep recursion for large
        # batches and keeps the call stack clean).
        try:
            self.scheduler.add_job(
                self._process_job_queue,
                "date",
                run_date=datetime.now() + timedelta(seconds=1),
                id="job_queue_next",
                replace_existing=True,
            )
        except Exception:
            pass  # Non-fatal — periodic 10-second trigger will catch it

    
    def _run_generation_job(self, db, job):
        """Run the full generation pipeline for a project. Generates video_count videos."""
        import json
        import asyncio as aio
        
        def run_async(coro):
            try:
                loop = aio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(aio.run, coro)
                        return future.result()
                else:
                    return loop.run_until_complete(coro)
            except RuntimeError:
                return aio.run(coro)
        
        project = db.query(models.Project).get(job.project_id)
        if not project:
            return
        
        schedule_settings = json.loads(project.schedule_settings) if isinstance(project.schedule_settings, str) else project.schedule_settings
        visual_settings = json.loads(project.visual_settings) if isinstance(project.visual_settings, str) else project.visual_settings
        audio_settings = json.loads(project.audio_settings) if isinstance(project.audio_settings, str) else project.audio_settings
        caption_settings = json.loads(project.caption_settings) if isinstance(project.caption_settings, str) else project.caption_settings
        
        video_count = schedule_settings.get("video_count", 1)
        duration = visual_settings.get("total_duration", 45)
        
        job.logs = f"Starting batch generation: {video_count} videos, {duration}s each"
        db.commit()
        
        for video_index in range(video_count):
            # Create individual video job
            video_job = models.Job(
                project_id=project.id,
                job_type="video",
                status="queued",
                logs=f"Video {video_index + 1}/{video_count}",
                progress=0
            )
            db.add(video_job)
            db.commit()
        
        job.status = "completed"
        job.progress = 100
        db.commit()
    
    def _run_single_video_job_by_id(self, job_id: int):
        """Wrapper that processes the job queue, ensuring only one video runs at a time.

        Previously this called _run_single_video_job directly, which bypassed the
        queue lock and the running-job guard. Now we delegate to _process_job_queue
        so that all sequencing logic is in one place.
        """
        self._process_job_queue()

    def _run_single_video_job(self, db, job):
        """Generate a single video for a project."""
        import json
        # Register as the active ComfyUI job for cancellation
        self._active_job_id = job.id
        try:
            self._run_single_video_job_inner(db, job)
        finally:
            self._active_job_id = None

    def _run_single_video_job_inner(self, db, job):
        import json
        job_id = job.id
        def check_cancel():
            """Returns True if the job was cancelled via /jobs/{id}/cancel.
            Also interrupts the running ComfyUI prompt so generation halts
            within a few seconds."""
            if self.is_cancelled(job_id):
                # Make doubly sure ComfyUI is interrupted
                try:
                    import asyncio as aio
                    try:
                        loop = aio.get_event_loop()
                        if loop.is_running():
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as pool:
                                pool.submit(aio.run, visuals_service.comfyui.interrupt()).result(timeout=5)
                        else:
                            loop.run_until_complete(visuals_service.comfyui.interrupt())
                    except RuntimeError:
                        aio.run(visuals_service.comfyui.interrupt())
                except Exception:
                    pass
                return True
            return False

        import asyncio as aio
        
        def run_async(coro):
            try:
                loop = aio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(aio.run, coro)
                        return future.result()
                else:
                    return loop.run_until_complete(coro)
            except RuntimeError:
                return aio.run(coro)
        
        project = db.query(models.Project).get(job.project_id)
        if not project:
            return
        
        schedule_settings = json.loads(project.schedule_settings) if isinstance(project.schedule_settings, str) else project.schedule_settings
        visual_settings = json.loads(project.visual_settings) if isinstance(project.visual_settings, str) else project.visual_settings
        audio_settings = json.loads(project.audio_settings) if isinstance(project.audio_settings, str) else project.audio_settings
        caption_settings = json.loads(project.caption_settings) if isinstance(project.caption_settings, str) else project.caption_settings
        
        duration = visual_settings.get("total_duration", 45)
        video_count = schedule_settings.get("video_count", 1)
        
        # Extract video number from logs
        try:
            parts = job.logs.split("/")
            video_num = int(parts[0].replace("Video ", ""))
        except:
            video_num = 1
        
        job.progress = 5
        job.logs = f"Video {video_num}/{video_count} - Researching topic..."
        db.commit()
        telegram_bot.notify_job_status(job.id, job.logs, job.progress, job.status)
        
        # 1. Research topic (URL mode, Reddit mode, or auto_research mode)
        if project.source_type == "url" and project.source_value:
            web_content = run_async(research_service.summarize_webpage(
                project.source_value,
                db=db,
                project_id=project.id,
                job_id=job.id,
                video_index=video_num - 1,
            ))
            topic = f"{project.source_value} part {video_num}"
            research = {"topic": topic, "context": web_content}
        elif project.source_type == "reddit" and project.source_value:
            reddit_data = run_async(research_service.get_reddit_story(project.source_value))
            story_title = reddit_data.get("title", "")
            story_content = reddit_data.get("story", "")
            subreddit_name = reddit_data.get("subreddit", "")
            
            web_content = f"Subreddit: r/{subreddit_name}\nTitle: {story_title}\nStory Content:\n{story_content}"
            topic = f"Reddit Story: {story_title}"
            research = {"topic": topic, "context": web_content}
        else:
            research = run_async(research_service.research_topic(
                f"{project.source_value} part {video_num}",
                project.category,
                db=db,
                project_id=project.id,
                job_id=job.id,
                video_index=video_num - 1,
            ))
        topic = research["topic"]

        job.progress = 15
        job.logs = f"Video {video_num}/{video_count} - Checking for existing script..."
        db.commit()

        # 2. Use the existing script if one is already saved for this video_index
        #    (the user may have reviewed and approved it). Only run the LLM
        #    script generation step if no script exists yet.
        existing_script = db.query(models.Script).filter(
            models.Script.project_id == project.id,
            models.Script.video_index == video_num - 1
        ).first()

        if existing_script and existing_script.scenes:
            # Reuse the reviewed/approved script as-is
            import json as _json
            scenes_data = existing_script.scenes
            if isinstance(scenes_data, str):
                scenes_data = _json.loads(scenes_data) if scenes_data else []
            script_data = {
                "title": existing_script.title,
                "hook": (existing_script.content or "").split("\n\n")[0] if existing_script.content else "",
                "scenes": scenes_data,
                "hashtags": [h for h in (existing_script.hashtags or "").split(",") if h],
                "music_prompt": "",
            }
            job.logs = f"Video {video_num}/{video_count} - Using approved script"
        else:
            # 2b. No existing script -> generate a fresh one
            job.logs = f"Video {video_num}/{video_count} - Generating script..."
            db.commit()

            # Query previous scripts for duplication prevention
            prev_scripts = db.query(models.Script).filter(
                models.Script.project_id == project.id,
                models.Script.video_index < video_num - 1
            ).order_by(models.Script.video_index.asc()).all()

            prev_context_list = []
            for ps in prev_scripts:
                prev_context_list.append(f"--- PREVIOUS PART {ps.video_index + 1} SCRIPT ---\nTitle: {ps.title}\nContent:\n{ps.content}")
            prev_scripts_context = "\n\n".join(prev_context_list)

            script_data = run_async(script_service.generate_script(
                topic=topic,
                category=project.category,
                context=research["context"],
                duration=duration,
                prev_scripts_context=prev_scripts_context
            ))

        # 3. Save script (only if we generated a new one; otherwise the existing
        #    script is the source of truth and we just touch its updated_at via
        #    the job commit below)
        if not existing_script or not existing_script.scenes:
            max_serial = db.query(func.max(models.Script.global_serial)).scalar() or 0
            script = models.Script(
                project_id=project.id,
                title=script_data.get("title", topic),
                content=script_data.get("hook", "") + "\n\n" + "\n".join([s["narration_text"] for s in script_data.get("scenes", [])]),
                scenes=script_data.get("scenes", []),
                hashtags=",".join(script_data.get("hashtags", [])),
                status="approved",
                video_index=video_num - 1,
                global_serial=max_serial + 1
            )
            db.add(script)
            db.commit()
        else:
            script = existing_script

        # RESUME: parse job.current_stage (set by the router when the user
        # restarts a cancelled/failed job) and derive per-stage skip flags.
        # The stage values are stable strings documented on the Job model.
        # Stages that completed before the cancel should be skipped; the
        # underlying files (scene clips, voice MP3s, music MP3, final MP4)
        # persist on disk between runs so the "skip if file exists" check
        # is the actual guard, not this flag.
        def _parse_resume(stage_str):
            """Returns (skipped_stages, partial_counts) from a current_stage value.
            skipped_stages: set of stage names that are already done.
            partial_counts: dict with int counts for stages that have sub-progress
                            (e.g. {'scenes_t2v': 2} means scenes 0 and 1 are done).
            """
            skipped = set()
            partial = {}
            if not stage_str or stage_str == "completed":
                return skipped, partial
            # Linear pipeline: research < script < scenes_t2v < voiceover < music < assembly
            order = ["research", "script", "scenes_t2v", "voiceover", "music", "assembly"]
            if ":" in stage_str:
                name, n = stage_str.split(":", 1)
                try:
                    n = int(n)
                except ValueError:
                    n = 0
            else:
                name, n = stage_str, 0
            if name in order:
                idx = order.index(name)
                skipped.update(order[:idx])
                if name in ("scenes_t2v", "voiceover") and n > 0:
                    partial[name] = n
            return skipped, partial

        skipped_stages, partial_counts = _parse_resume(job.current_stage)
        # Mark the script stage as complete (we just did the reuse-or-generate above).
        skipped_stages.add("script")
        if skipped_stages:
            job.logs = (
                f"Video {video_num}/{video_count} - Resuming from {job.current_stage} "
                f"(skipping: {', '.join(sorted(skipped_stages))})"
            )
            db.commit()

        # Apply per-video overrides if they exist
        override = script.video_overrides
        if override:
            if isinstance(override, str):
                override = json.loads(override)
        if override:
            if override.get("ai_style"):
                visual_settings["ai_style"] = override["ai_style"]
            if override.get("voice_id"):
                audio_settings["voice_id"] = override["voice_id"]
            if override.get("music_genre"):
                audio_settings["music_genre"] = override["music_genre"]
            if override.get("lora_strength") is not None:
                visual_settings["lora_strength"] = override["lora_strength"]
        
        # Resolve LoRA from style first so we can log the actual file the pipeline will use
        style_key = visual_settings.get("ai_style", "")
        lora_name = visuals_service._resolve_lora(style_key) if style_key else None
        lora_strength = visual_settings.get("lora_strength", 0.6)

        # Surface LoRA resolution in the job log so the user can see what was used
        if not style_key:
            t2v_log = f"Video {video_num}/{video_count} - No style set, using base model (no style LoRA)"
        elif lora_name:
            t2v_log = f"Video {video_num}/{video_count} - Style '{style_key}' -> {lora_name.split(chr(92))[-1]} @ {lora_strength} strength"
        else:
            t2v_log = f"Video {video_num}/{video_count} - Style '{style_key}' LoRA not found in models/loras, falling back to base model"

        job.progress = 30
        job.logs = t2v_log
        db.commit()

        # 4. Generate t2v scene videos
        video_idx = video_num - 1
        base_dir = settings.PROJECTS_DIR / str(project.id)
        videos_dir = base_dir / "videos" / str(video_idx)
        audio_dir = base_dir / "audio" / str(video_idx)
        final_dir = base_dir / "final" / str(video_idx)
        videos_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)
        final_dir.mkdir(parents=True, exist_ok=True)

        # Cancellation check right before the long ComfyUI run
        if check_cancel():
            job.logs = f"Video {video_num}/{video_count} - Cancelled by user"
            job.status = "cancelled"
            db.commit()
            return

        # Resolve aspect ratio from project visual_settings. Width/height and
        # aspect_str get stashed on the _active_visual_settings module hook
        # so visuals_service._resolve_scene_dims reads them for every scene
        # (including per-scene regen via the same hook).
        aspect_str = visual_settings.get("aspect_ratio", "vertical")
        aspect_cfg = settings.ASPECT_RATIOS.get(aspect_str, settings.ASPECT_RATIOS["vertical"])
        target_w = aspect_cfg["width"]
        target_h = aspect_cfg["height"]
        aspect_per_scene = aspect_cfg["per_scene"]

        # Re-clamp each scene's duration to the aspect's per-scene cap.
        # When a project is switched from vertical to HD horizontal (5s cap)
        # the existing script's duration_seconds=8 would OOM at 1920x1080.
        scenes = script_data.get("scenes", [])
        clamped = 0
        for sc in scenes:
            if isinstance(sc, dict) and sc.get("duration_seconds", 6) > aspect_per_scene:
                sc["duration_seconds"] = aspect_per_scene
                clamped += 1
        if clamped:
            script_data["scenes"] = scenes
            # Persist the clamped script so subsequent reassembles don't
            # re-trigger the clamp.
            try:
                from app.services.scheduler import _clamp_script_durations
            except ImportError:
                pass
            if existing_script and existing_script.scenes:
                existing_script.scenes = scenes
                db.commit()
            job.logs = (
                f"Video {video_num}/{video_count} - Clamped {clamped} scene(s) "
                f"to {aspect_per_scene}s for {aspect_str}"
            )
            db.commit()

        def scene_progress(idx, total, msg):
            """Update job progress during scene generation."""
            try:
                # Map scene gen to 30-55% of total job
                pct = 30 + int((idx / max(total, 1)) * 25)
                job.progress = pct
                job.logs = f"Video {video_num}/{video_count} - Scene {idx+1}/{total}..."
                db.commit()
            except:
                pass

        # Stash aspect/transition/dims on the module-level hook so
        # visuals_service._resolve_scene_dims + per-scene regen see the
        # project's current values without threading them through every
        # function signature. Cleared in a finally block at the end of the job.
        import app.config as _settings_module
        _settings_module._active_visual_settings = {
            "_width": target_w,
            "_height": target_h,
            "_aspect_str": aspect_str,
        }
        try:
            scene_clip_paths = run_async(visuals_service.generate_scene_videos(
                scenes=scenes,
                project_dir=videos_dir,
                lora_name=lora_name,
                lora_strength=lora_strength,
                style_key=style_key,
                project_id=project.id,
                video_index=video_idx,
                job_id=job.id,
                db=db,
                on_progress=scene_progress,
                is_cancelled=check_cancel,
            ))

            if check_cancel():
                return

            # Abort if no scenes were generated (all failed/timed out)
            if not scene_clip_paths or len(scene_clip_paths) == 0:
                job.status = "failed"
                job.logs = f"Video {video_num}/{video_count} - Scene generation failed (0/{len(scenes)} clips)"
                db.commit()
                return

            if len(scene_clip_paths) < len(scenes):
                logging.warning(
                    "Video %s/%s: only %s/%s scenes generated, proceeding with partial",
                    video_num, video_count, len(scene_clip_paths), len(scenes)
                )
        finally:
            try:
                if hasattr(_settings_module, "_active_visual_settings"):
                    del _settings_module._active_visual_settings
            except Exception:
                pass

        # Save scene clips as visual assets
        for i, path in enumerate(scene_clip_paths):
            db.add(models.Asset(
                project_id=project.id,
                script_id=script.id,
                scene_index=i,
                asset_type="video",
                source="comfyui_ltx_t2v",
                local_path=str(path)
            ))
        db.commit()

        # CHECKPOINT: scenes t2v complete
        job.current_stage = f"scenes_t2v:{len(scene_clip_paths)}/{len(scenes)}"
        db.commit()

        # Look up the actual saved script (created by generate-scripts endpoint) for this video_index
        # to get any per-video overrides (voice, music, etc.)
        existing_script = db.query(models.Script).filter(
            models.Script.project_id == project.id,
            models.Script.video_index == video_num - 1
        ).first()
        script_vo = {}
        if existing_script and existing_script.video_overrides:
            script_vo = existing_script.video_overrides
            if isinstance(script_vo, str):
                script_vo = json.loads(script_vo)

        # Resolve voice settings
        effective_voice = audio_settings.get("voice_id", "en-US-AriaNeural")
        voice_custom = audio_settings.get("voice_custom", "")
        if script_vo.get("voice_id"):
            effective_voice = script_vo["voice_id"]
            voice_custom = script_vo.get("voice_custom", "")
        speaker_for_tts = voice_custom if effective_voice == "__custom__" else effective_voice

        # Determine if voice is Edge TTS
        qwen_ids = ["aiden", "dylan", "eric", "ono_anna", "ryan", "serena", "sohee", "uncle_fu", "vivian"]
        is_edge_tts = not (speaker_for_tts.lower() in qwen_ids or any(q in speaker_for_tts.lower() for q in qwen_ids))

        # If every scene is already on disk (full resume case), the t2v loop
        # above did zero work. Skip voiceover too if it's already done.
        if "voiceover" in skipped_stages and not check_cancel():
            # Verify files exist before declaring voiceover done
            voice_dir = audio_dir
            all_voice_present = all(
                (voice_dir / f"voice_{i+1:02d}.mp3").exists()
                and (voice_dir / f"voice_{i+1:02d}.mp3").stat().st_size > 1024
                and (not is_edge_tts or (voice_dir / f"voice_{i+1:02d}.json").exists())
                for i in range(len(scenes))
                if scenes[i].get("narration_text")
            )
            if all_voice_present:
                job.logs = f"Video {video_num}/{video_count} - Voiceover already on disk, skipping"
                db.commit()
                # Skip the voiceover block below
                job.current_stage = "voiceover:1/1"  # sentinel: all done
                db.commit()

        job.progress = 55
        job.logs = f"Video {video_num}/{video_count} - Generating voiceover..."
        db.commit()

        # RESUME: if the previous run completed voiceover (current_stage passed
        # it OR we set the sentinel above in the scenes_t2v check), reuse the
        # mp3 files on disk rather than calling ComfyUI TTS again.
        skip_voiceover = (
            "voiceover" in skipped_stages
            or job.current_stage == "voiceover:1/1"
        )
        if skip_voiceover:
            audio_assets = []
            for i, sc in enumerate(script_data.get("scenes", [])):
                if not sc.get("narration_text"):
                    continue
                v_path = audio_dir / f"voice_{i+1:02d}.mp3"
                if v_path.exists() and v_path.stat().st_size > 1024 and (not is_edge_tts or v_path.with_suffix(".json").exists()):
                    audio_assets.append({
                        "scene_index": i,
                        "type": "audio",
                        "source": "comfyui_qwen3_tts" if not is_edge_tts else "tts",
                        "local_path": str(v_path),
                        "text": sc["narration_text"],
                        "voice_id": speaker_for_tts,
                    })
            if audio_assets:
                job.logs = f"Video {video_num}/{video_count} - Voiceover already on disk ({len(audio_assets)} clips), skipping TTS"
                db.commit()
            else:
                # Files missing - fall through to regeneration
                skip_voiceover = False

        if not skip_voiceover:
            try:
                audio_assets = run_async(audio_service.generate_scene_voiceovers(
                    script_data.get("scenes", []),
                    voice_id=speaker_for_tts,
                    project_dir=audio_dir
                ))
            except Exception as e:
                logging.warning("Video %s/%s - TTS voiceover failed (continuing without): %s",
                    video_num, video_count, str(e)[:200])
                job.logs = f"Video {video_num}/{video_count} - Voiceover failed, continuing without"
                db.commit()
                audio_assets = []

        # Map each audio asset to its planned duration
        scenes = script_data.get("scenes", [])
        for asset in audio_assets:
            idx = asset.get("scene_index")
            if idx is not None and idx < len(scenes):
                asset["duration_seconds"] = scenes[idx].get("duration_seconds", 6)

        # Generate and append outro voiceover if configured
        outro_seconds = getattr(settings, "OUTRO_DURATION_SECONDS", 0) or 0
        outro_path_setting = getattr(settings, "LIKE_SUBSCRIBE_OUTRO_PATH", None)
        if outro_seconds > 0 and outro_path_setting and Path(outro_path_setting).exists():
            outro_text = script_data.get("call_to_action", "Like, subscribe, and hit the bell for more!")
            outro_vo_path = audio_dir / "voice_outro.mp3"
            
            outro_exists = outro_vo_path.exists() and outro_vo_path.stat().st_size > 1024
            success = True
            if not outro_exists:
                try:
                    success = run_async(audio_service.generate_voiceover(
                        text=outro_text,
                        voice_id=speaker_for_tts,
                        output_path=outro_vo_path
                    ))
                except Exception as e:
                    print(f"[Outro VO] generation failed: {e}")
                    success = False
            
            if success and outro_vo_path.exists():
                outro_asset = {
                    "scene_index": 999,
                    "type": "audio",
                    "source": "tts",
                    "local_path": str(outro_vo_path),
                    "text": outro_text,
                    "voice_id": speaker_for_tts,
                    "duration_seconds": float(outro_seconds)
                }
                if not any(a.get("scene_index") == 999 for a in audio_assets):
                    audio_assets.append(outro_asset)
                    # Add to database assets if not already there
                    db_has_outro = db.query(models.Asset).filter(
                        models.Asset.project_id == project.id,
                        models.Asset.script_id == script.id,
                        models.Asset.scene_index == 999,
                        models.Asset.asset_type == "audio"
                    ).first()
                    if not db_has_outro:
                        db.add(models.Asset(
                            project_id=project.id,
                            script_id=script.id,
                            scene_index=999,
                            asset_type="audio",
                            source="tts",
                            local_path=str(outro_vo_path)
                        ))
                        db.commit()

        for asset in audio_assets:
            # Check if asset is already in database to avoid duplicate DB insertions
            existing_asset = db.query(models.Asset).filter(
                models.Asset.project_id == project.id,
                models.Asset.script_id == script.id,
                models.Asset.scene_index == asset["scene_index"],
                models.Asset.asset_type == "audio"
            ).first()
            if not existing_asset:
                db.add(models.Asset(
                    project_id=project.id,
                    script_id=script.id,
                    scene_index=asset["scene_index"],
                    asset_type="audio",
                    source=asset.get("source", "tts"),
                    local_path=asset["local_path"]
                ))

        db.commit()

        # CHECKPOINT: voiceover complete
        voice_count = len([s for s in script_data.get("scenes", []) if s.get("narration_text")])
        job.current_stage = f"voiceover:{voice_count}/{voice_count}" if voice_count else "voiceover:0/0"
        db.commit()

        # RESUME: if music was already complete in a previous run, reuse the
        # mp3 on disk rather than hitting ComfyUI music gen again.
        music_output_path = audio_dir / "background_music.mp3"
        if "music" in skipped_stages and music_output_path.exists() and music_output_path.stat().st_size > 1024:
            music_path = music_output_path
            job.logs = f"Video {video_num}/{video_count} - Music already on disk, skipping"
            job.current_stage = "music"
            db.commit()
        else:
            music_path = None

        job.progress = 70
        job.logs = f"Video {video_num}/{video_count} - Getting background music..."
        db.commit()

        # Per-video override music_genre takes precedence over project-level
        effective_music_genre = (script_vo.get("music_genre") if script_vo.get("music_genre") else audio_settings.get("music_genre", "ambient"))
        music_custom = script_vo.get("music_custom") if script_vo.get("music_custom") else audio_settings.get("music_custom", "")
        music_prompt = (script_vo or {}).get("music_prompt", "")

        if music_path is None:
            if music_prompt:
                music_path = run_async(audio_service.get_background_music(
                    genre=music_prompt,
                    output_path=music_output_path,
                    duration=duration
                ))
            elif effective_music_genre == "__custom__" and music_custom:
                music_path = run_async(audio_service.get_background_music(
                    genre=music_custom,
                    output_path=music_output_path,
                    duration=duration
                ))
            else:
                music_path = run_async(audio_service.get_background_music(
                    genre=effective_music_genre,
                    output_path=music_output_path,
                    duration=duration
                ))

        # CHECKPOINT: music done
        if music_path:
            job.current_stage = "music"
            db.commit()

        # RESUME: if the final video is already on disk and valid (resume case),
        # skip the expensive assembly step. If the file exists but is older than
        # any of the input files, we'd need to re-run — but for simplicity, treat
        # any existing final_video.mp4 as valid (we're not editing scenes in
        # this path; use Reassemble from the EditVideoModal for full rebuilds).
        output_path = final_dir / "final_video.mp4"
        if "assembly" in skipped_stages and output_path.exists() and output_path.stat().st_size > 1024:
            job.logs = f"Video {video_num}/{video_count} - Final video already on disk, skipping assembly"
            job.current_stage = "completed"
            db.commit()
            # Create upload record if missing so frontend can show video
            existing_upload = db.query(models.Upload).filter(
                models.Upload.project_id == project.id,
                models.Upload.script_id == script.id,
            ).first()
            if not existing_upload:
                upload = models.Upload(
                    project_id=project.id, script_id=script.id,
                    video_path=str(output_path), scheduled_for=None,
                    status="done",
                    title=script.title, description="", tags=""
                )
                db.add(upload)
                db.commit()
            job.progress = 100
            job.logs = f"Video {video_num}/{video_count} - Complete! (resumed from checkpoint)"
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()
            return

        job.progress = 80
        job.logs = f"Video {video_num}/{video_count} - Assembling video..."
        db.commit()

        # 6. Assemble final video
        output_path = final_dir / "final_video.mp4"

        # Resolve transition settings from visual_settings. Default = none
        # (preserves the original hard-cut behavior for projects that
        # haven't opted into transitions).
        transition_style = visual_settings.get("transition_style", "none")
        transition_duration = float(visual_settings.get("transition_duration", 0.4) or 0.4)
        audio_transition = visual_settings.get("audio_transition", "match_video")
        if transition_style == "none" or transition_duration <= 0.0:
            transition_duration = 0.0

        # Caption font scaling: pass the output height so captions.py can
        # auto-scale font_size for horizontal/HD aspects.
        caption_settings_for_assembly = dict(caption_settings or {})
        caption_settings_for_assembly["base_resolution_height"] = target_h

        success = video_service.assemble_video(
            scene_clips=scene_clip_paths,
            audio_assets=audio_assets,
            music_path=Path(music_path) if music_path else None,
            scenes=scenes,
            caption_settings=caption_settings_for_assembly,
            output_path=output_path,
            music_volume=audio_settings.get("music_volume", 0.15),
            voice_volume=audio_settings.get("voice_volume", 1.0),
            target_width=target_w,
            target_height=target_h,
            transition_style=transition_style,
            transition_duration=transition_duration,
            audio_transition=audio_transition,
        )
        
        if success:
            job.progress = 85
            job.logs = f"Video {video_num}/{video_count} - Generating SEO metadata..."
            db.commit()
            
            # 7. Generate SEO metadata (non-critical — use script title as fallback)
            seo = {}
            try:
                seo = run_async(script_service.generate_seo_metadata(
                    topic=topic,
                    category=project.category,
                    script_content=script.content
                ))
            except Exception as e:
                logging.warning("Video %s/%s - SEO generation failed (using fallback): %s",
                    video_num, video_count, str(e)[:200])
            
            # Create an Upload record with status="done" (ready for manual YouTube upload)
            existing_upload = db.query(models.Upload).filter(
                models.Upload.project_id == project.id,
                models.Upload.script_id == script.id,
            ).first()
            if not existing_upload:
                upload = models.Upload(
                    project_id=project.id,
                    script_id=script.id,
                    video_path=str(output_path),
                    scheduled_for=None,
                    status="done",
                    title=seo.get("title", script.title),
                    description=seo.get("description", ""),
                    tags=",".join(seo.get("hashtags", [])[:15])
                )
                db.add(upload)
                db.commit()
            
            job.result = {
                "video_path": str(output_path),
                "seo": seo,
            }
            
            job.progress = 100
            job.logs = f"Video {video_num}/{video_count} - Complete!"
            # CHECKPOINT: full pipeline complete
            job.current_stage = "completed"
            db.commit()
        else:
            job.progress = 0
            job.logs = f"Video {video_num}/{video_count} - Assembly failed"
            job.status = "failed"
            db.commit()
    
    def _process_upload_queue(self):
        """Process uploads that are scheduled for now or past."""
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            uploads = db.query(models.Upload).filter(
                models.Upload.status == "queued",
                models.Upload.scheduled_for <= now
            ).limit(5).all()

            for upload in uploads:
                # Get project's YouTube channel
                project = db.query(models.Project).filter(
                    models.Project.id == upload.project_id
                ).first()
                channel = project.youtube_channel if project else None
                if not channel:
                    upload.status = "failed"
                    db.commit()
                    continue

                upload.status = "processing"
                db.commit()

                try:
                    result = youtube_service.upload_video(
                        credentials_file=channel.credentials_file,
                        video_path=upload.video_path,
                        title=upload.title,
                        description=upload.description,
                        tags=upload.tags.split(",") if upload.tags else [],
                        privacy_status="private",
                        publish_at=upload.scheduled_for.isoformat() + "Z" if upload.scheduled_for else None,
                        thumbnail_path=upload.thumbnail_path
                    )

                    if result["status"] == "success":
                        upload.status = "done"
                        upload.youtube_video_id = result["video_id"]
                        upload.uploaded_at = datetime.utcnow()
                        db.commit()
                        from app.services.archive import archive_service
                        archived = archive_service.check_and_archive(db)
                        if archived:
                            print(f"Archived {archived} videos")
                    else:
                        upload.status = "failed"

                except Exception as e:
                    upload.status = "failed"

                db.commit()

        finally:
            db.close()
    
    def _get_next_upload_slot(self, project) -> datetime:
        """Calculate the next available upload slot based on project schedule and videos_per_day."""
        import json
        schedule_settings = json.loads(project.schedule_settings) if isinstance(project.schedule_settings, str) else project.schedule_settings
        
        days = schedule_settings.get("days", ["monday"])
        times = schedule_settings.get("times", ["09:00"])
        videos_per_day = schedule_settings.get("videos_per_day", 1)
        
        now = datetime.utcnow()
        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, 
                   "friday": 4, "saturday": 5, "sunday": 6}
        day_nums = [day_map.get(d.lower(), 0) for d in days]
        
        # Check existing uploads to respect videos_per_day limit
        db = SessionLocal()
        try:
            for i in range(30):
                check_day = now + timedelta(days=i)
                if check_day.weekday() not in day_nums:
                    continue
                
                # Count existing uploads for this day
                day_start = check_day.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                existing = db.query(models.Upload).filter(
                    models.Upload.scheduled_for >= day_start,
                    models.Upload.scheduled_for < day_end,
                    models.Upload.status.in_(["queued", "processing", "done"])
                ).count()
                
                if existing >= videos_per_day:
                    continue
                
                # Find available time slot
                hour, minute = map(int, times[0].split(":"))
                slot = check_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # Check if this specific slot is taken
                slot_taken = db.query(models.Upload).filter(
                    models.Upload.scheduled_for == slot,
                    models.Upload.status.in_(["queued", "processing", "done"])
                ).count() > 0
                
                if not slot_taken and slot > now:
                    return slot
                
                # Try next hour
                for h in range(1, 24):
                    slot = check_day.replace(hour=(hour + h) % 24, minute=minute, second=0, microsecond=0)
                    if slot > now:
                        slot_taken = db.query(models.Upload).filter(
                            models.Upload.scheduled_for == slot,
                            models.Upload.status.in_(["queued", "processing", "done"])
                        ).count() > 0
                        if not slot_taken:
                            return slot
        finally:
            db.close()
        
        return now + timedelta(days=1)
    
    def trigger_batch_now(self, project_id: int):
        """Manually trigger batch generation for a project. Creates one job per video."""
        db = SessionLocal()
        try:
            project = db.query(models.Project).get(project_id)
            if not project:
                return {"status": "error", "message": "Project not found"}
            
            schedule_settings = json.loads(project.schedule_settings) if isinstance(project.schedule_settings, str) else project.schedule_settings
            video_count = schedule_settings.get("video_count", 1)
            
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
            
            # Run immediately in background
            # NOTE: BackgroundScheduler defaults to local timezone; use datetime.now()
            # to match (datetime.utcnow() would schedule 5h+ in the future in IST)
            self.scheduler.add_job(
                self._process_job_queue,
                "date",
                run_date=datetime.now() + timedelta(seconds=2),
                id=f"manual_batch_{project_id}",
                replace_existing=True
            )
            
            return {"status": "success", "job_ids": job_ids, "video_count": video_count}
        finally:
            db.close()
    
    def schedule_uploads_for_project(self, project_id: int):
        """Schedule all queued uploads for a project using global settings."""
        db = SessionLocal()
        try:
            # Get global schedule settings
            videos_per_day_setting = db.query(models.Setting).filter(
                models.Setting.key == "videos_per_day"
            ).first()
            upload_times_setting = db.query(models.Setting).filter(
                models.Setting.key == "upload_times"
            ).first()
            
            videos_per_day = videos_per_day_setting.value if videos_per_day_setting else 2
            upload_times = upload_times_setting.value if upload_times_setting else ["10:00", "16:00"]
            
            if isinstance(videos_per_day, str):
                videos_per_day = int(videos_per_day)
            if isinstance(upload_times, str):
                import json as _json
                upload_times = _json.loads(upload_times)
            
            # Get all queued uploads for this project
            uploads = db.query(models.Upload).filter(
                models.Upload.project_id == project_id,
                models.Upload.status == "queued"
            ).order_by(models.Upload.created_at).all()
            
            if not uploads:
                return {"status": "success", "message": "No queued uploads to schedule"}
            
            now = datetime.utcnow()
            scheduled_count = 0
            day_offset = 0
            timeslot_index = 0
            
            for upload in uploads:
                # Find next available slot
                while True:
                    check_date = now + timedelta(days=day_offset)
                    hour, minute = map(int, upload_times[timeslot_index].split(":"))
                    slot = check_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    
                    # Check if slot is taken
                    existing = db.query(models.Upload).filter(
                        models.Upload.scheduled_for == slot,
                        models.Upload.status.in_(["queued", "processing", "done"])
                    ).count()
                    
                    if existing < videos_per_day and slot > now:
                        upload.scheduled_for = slot
                        scheduled_count += 1
                        db.commit()
                        
                        # Move to next timeslot
                        timeslot_index += 1
                        if timeslot_index >= len(upload_times):
                            timeslot_index = 0
                            day_offset += 1
                        break
                    
                    # Try next timeslot or next day
                    timeslot_index += 1
                    if timeslot_index >= len(upload_times):
                        timeslot_index = 0
                        day_offset += 1
                    
                    if day_offset > 30:
                        break
            
            return {
                "status": "success",
                "scheduled": scheduled_count,
                "videos_per_day": videos_per_day,
                "upload_times": upload_times
            }
        finally:
            db.close()
    
    def regenerate_video(self, project_id: int, video_index: int, overrides: dict = None):
        """Regenerate a single video, applying optional per-video overrides."""
        db = SessionLocal()
        try:
            # Find existing Script for this video_index
            script = db.query(models.Script).filter(
                models.Script.project_id == project_id,
                models.Script.video_index == video_index
            ).first()
            
            if overrides:
                if script:
                    existing_vo = script.video_overrides or {}
                    if isinstance(existing_vo, str):
                        existing_vo = json.loads(existing_vo)
                    merged = {**existing_vo, **overrides}
                    script.video_overrides = merged
                    db.commit()
                else:
                    # Store overrides in project for when script is created
                    schedule_settings = db.query(models.Project).get(project_id)
                    if schedule_settings:
                        ss = json.loads(schedule_settings.schedule_settings) if isinstance(schedule_settings.schedule_settings, str) else schedule_settings.schedule_settings
                        pending = ss.get("pending_overrides", {}) or {}
                        pending[str(video_index)] = {**(pending.get(str(video_index), {}) or {}), **overrides}
                        ss["pending_overrides"] = pending
                        schedule_settings.schedule_settings = ss
                        db.commit()
            
            # Delete old Upload for this video_index if exists
            if script:
                old_uploads = db.query(models.Upload).filter(
                    models.Upload.script_id == script.id,
                    models.Upload.status.in_(["queued", "failed"])
                ).all()
                for u in old_uploads:
                    db.delete(u)
                db.commit()
            
            # Get project for video count
            project = db.query(models.Project).get(project_id)
            schedule_settings = json.loads(project.schedule_settings) if isinstance(project.schedule_settings, str) else project.schedule_settings
            video_count = schedule_settings.get("video_count", 1)
            
            # Create new video job
            job = models.Job(
                project_id=project_id,
                job_type="video",
                status="queued",
                logs=f"Video {video_index + 1}/{video_count}",
                progress=0
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            
            self.scheduler.add_job(
                self._process_job_queue,
                "date",
                run_date=datetime.now() + timedelta(seconds=2),
                id=f"regen_video_{project_id}_{video_index}",
                replace_existing=True
            )
            
            return {"status": "success", "job_id": job.id}
        finally:
            db.close()
    
    def schedule_single_upload(self, project_id: int, video_index: int, db = None):
        """Schedule a single video upload using global settings."""
        is_local = False
        if db is None:
            db = SessionLocal()
            is_local = True
        try:
            script = db.query(models.Script).filter(
                models.Script.project_id == project_id,
                models.Script.video_index == video_index
            ).first()
            if not script:
                return {"status": "error", "message": "Script not found"}
            
            upload = db.query(models.Upload).filter(
                models.Upload.script_id == script.id,
                models.Upload.status == "queued"
            ).first()
            if not upload:
                return {"status": "error", "message": "No queued upload for this video"}
            
            # Get global settings
            vpd_setting = db.query(models.Setting).filter(models.Setting.key == "videos_per_day").first()
            ut_setting = db.query(models.Setting).filter(models.Setting.key == "upload_times").first()
            videos_per_day = vpd_setting.value if vpd_setting else 2
            upload_times = ut_setting.value if ut_setting else ["10:00", "16:00"]
            if isinstance(videos_per_day, str): videos_per_day = int(videos_per_day)
            if isinstance(upload_times, str): upload_times = json.loads(upload_times)
            
            now = datetime.utcnow()
            for day_offset in range(30):
                for t in upload_times:
                    hour, minute = map(int, t.split(":"))
                    check = now + timedelta(days=day_offset)
                    slot = check.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if slot <= now:
                        continue
                    existing = db.query(models.Upload).filter(
                        models.Upload.scheduled_for == slot,
                        models.Upload.status.in_(["queued", "processing", "done"])
                    ).count()
                    if existing < videos_per_day:
                        upload.scheduled_for = slot
                        db.commit()
                        return {
                            "status": "success",
                            "scheduled_for": slot.isoformat(),
                            "videos_per_day": videos_per_day
                        }
            
            return {"status": "error", "message": "No available slot found within 30 days"}
        finally:
            if is_local:
                db.close()

    def regenerate_single_scene(self, project_id: int, video_index: int, scene_index: int,
                                 seed_offset: int = 1, custom_prompt: str = None) -> dict:
        """Regenerate ONE scene clip without touching the rest of the pipeline.

        Steps:
        1. Load the script's scenes[scene_index]
        2. Sanitize + prepend trigger words (same logic as full pipeline)
        3. Call visuals_service.generate_scene_videos on a single-scene list
        4. Overwrite videos/{idx}/scene_{NN:02d}.mp4
        5. Update the corresponding Asset row

        Args:
            project_id: Project ID
            video_index: 0-based video index
            scene_index: 0-based scene index
            seed_offset: Added to the deterministic seed so the new attempt
                is a fresh take but stays in the same "family" as the original.
                Default 1 (next seed in the family).
            custom_prompt: Optional user-tweaked visual description. When
                provided, it replaces the script's visual_description for
                this scene. Trigger words + suffix are still applied
                automatically, so the user only writes the camera/subject/
                setting/mood portion.
        """
        import json
        import asyncio as aio

        def run_async(coro):
            try:
                loop = aio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(aio.run, coro)
                        return future.result()
                else:
                    return loop.run_until_complete(coro)
            except RuntimeError:
                return aio.run(coro)

        db = SessionLocal()
        try:
            project = db.query(models.Project).get(project_id)
            if not project:
                return {"status": "error", "message": "Project not found"}

            script = db.query(models.Script).filter(
                models.Script.project_id == project_id,
                models.Script.video_index == video_index,
            ).order_by(models.Script.created_at.desc()).first()
            if not script:
                return {"status": "error", "message": "Script not found for this video"}

            scenes = script.scenes or []
            if scene_index < 0 or scene_index >= len(scenes):
                return {"status": "error", "message": f"scene_index {scene_index} out of range (0..{len(scenes)-1})"}

            visual_settings = json.loads(project.visual_settings) if isinstance(project.visual_settings, str) else (project.visual_settings or {})
            caption_settings = json.loads(project.caption_settings) if isinstance(project.caption_settings, str) else (project.caption_settings or {})

            # Style LoRA + strength from project
            style_key = visual_settings.get("style", "none")
            if style_key in ("none", "", None):
                # Try ai_style as fallback (ProjectDetail uses ai_style)
                style_key = visual_settings.get("ai_style", "none")
            if style_key in ("none", "", None):
                style_key = None
            lora_name = visual_settings.get("lora_name") or None
            lora_strength = float(visual_settings.get("lora_strength", 0.6) or 0.6)
            if lora_name is None and style_key:
                # Map style key -> LoRA filename
                lora_name = style_key

            base_dir = settings.PROJECTS_DIR / str(project_id)
            videos_dir = base_dir / "videos" / str(video_index)
            videos_dir.mkdir(parents=True, exist_ok=True)

            scene = scenes[scene_index]
            single_scene_list = [scene]

            # Compute the trigger prefix here so the PromptLog can record it
            # (visuals_service also computes it internally for the actual prompt)
            trigger_words_str = None
            if style_key:
                triggers = settings.STYLE_LORA_TRIGGERS.get(style_key, "")
                if triggers:
                    trigger_words_str = triggers

            # Use the same seed formula but with a small offset to get a new take
            # while staying in the same "family"
            def _seed_for(idx: int, desc: str) -> int:
                base = hash((project_id, video_index, idx, desc[:50])) & 0xFFFFFFFF
                return (base + seed_offset) & 0xFFFFFFFF

            # Patch the visuals_service seed computation is inside generate_scene_videos
            # We pass through the standard call; it will compute its own seed.
            # For the offset we set a module-level hook on settings that the
            # visuals_service reads in its seed formula. This keeps the seed
            # deterministic but distinct from the original.
            from app.config import settings as _settings_module
            visual_settings_for_seed = dict(visual_settings)
            visual_settings_for_seed["_regen_offset"] = seed_offset
            visual_settings_for_seed["_trigger_words"] = trigger_words_str
            # CUSTOM PROMPT: user-tweaked visual description. Map keyed by
            # scene index (0-based) so visuals_service can pick the right
            # override per scene.
            if custom_prompt and custom_prompt.strip():
                visual_settings_for_seed["_custom_prompt_for"] = {
                    str(scene_index): custom_prompt.strip()
                }
            _settings_module._active_visual_settings = visual_settings_for_seed
            try:
                scene_clip_paths = run_async(visuals_service.generate_scene_videos(
                    scenes=single_scene_list,
                    project_dir=videos_dir,
                    lora_name=lora_name,
                    lora_strength=lora_strength,
                    style_key=style_key,
                    project_id=project_id,
                    video_index=video_index,
                    job_id=None,
                    db=db,
                ))
            finally:
                # Clear the hook so the next full-pipeline call uses the default seed
                try:
                    del _settings_module._active_visual_settings
                except AttributeError:
                    pass

            if not scene_clip_paths:
                return {"status": "error", "message": "Scene generation returned no output"}

            new_scene_path = scene_clip_paths[0]
            # Files were saved as scene_01.mp4 (since we passed a single scene).
            # Rename to scene_{scene_index+1:02d}.mp4
            desired = videos_dir / f"scene_{scene_index+1:02d}.mp4"
            if new_scene_path != desired and new_scene_path.exists():
                if desired.exists():
                    desired.unlink()
                new_scene_path.rename(desired)

            # Update Asset row (or create one)
            asset = db.query(models.Asset).filter(
                models.Asset.project_id == project_id,
                models.Asset.script_id == script.id,
                models.Asset.scene_index == scene_index,
                models.Asset.asset_type == "video",
            ).first()
            if asset:
                asset.local_path = str(desired)
            else:
                db.add(models.Asset(
                    project_id=project_id,
                    script_id=script.id,
                    scene_index=scene_index,
                    asset_type="video",
                    source="comfyui_ltx_t2v",
                    local_path=str(desired),
                ))
            db.commit()

            return {
                "status": "success",
                "scene_index": scene_index,
                "scene_path": str(desired),
            }
        finally:
            db.close()

    def reassemble_video(self, project_id: int, video_index: int) -> dict:
        """Re-run the assembly step using existing scene clips + audio assets.

        Use after per-scene regeneration to update the final video without
        re-running the entire pipeline. Does NOT regenerate t2v, voice, or music.
        """
        import json
        db = SessionLocal()
        try:
            project = db.query(models.Project).get(project_id)
            if not project:
                return {"status": "error", "message": "Project not found"}

            import asyncio as aio
            def run_async(coro):
                try:
                    loop = aio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(aio.run, coro)
                            return future.result()
                    else:
                        return loop.run_until_complete(coro)
                except RuntimeError:
                    return aio.run(coro)

            script = db.query(models.Script).filter(
                models.Script.project_id == project_id,
                models.Script.video_index == video_index,
            ).order_by(models.Script.created_at.desc()).first()
            if not script:
                return {"status": "error", "message": "Script not found for this video"}

            scenes = script.scenes or []

            visual_settings = json.loads(project.visual_settings) if isinstance(project.visual_settings, str) else (project.visual_settings or {})
            caption_settings = json.loads(project.caption_settings) if isinstance(project.caption_settings, str) else (project.caption_settings or {})

            base_dir = settings.PROJECTS_DIR / str(project_id)
            videos_dir = base_dir / "videos" / str(video_index)
            audio_dir = base_dir / "audio" / str(video_index)
            # Fallback: newer projects store audio directly under the video index dir
            audio_dir_fallback = base_dir / str(video_index)
            if not audio_dir.exists() and audio_dir_fallback.exists():
                audio_dir = audio_dir_fallback
            final_dir = base_dir / "final" / str(video_index)
            final_dir.mkdir(parents=True, exist_ok=True)

            # Collect scene clips in order
            scene_clips = []
            for i in range(len(scenes)):
                p = videos_dir / f"scene_{i+1:02d}.mp4"
                if p.exists():
                    scene_clips.append(p)
            if not scene_clips:
                return {"status": "error", "message": "No scene clips found on disk"}

            # Resolve voice settings
            audio_settings = json.loads(project.audio_settings) if isinstance(project.audio_settings, str) else (project.audio_settings or {})
            script_vo = {}
            if script.video_overrides:
                script_vo = script.video_overrides
                if isinstance(script_vo, str):
                    script_vo = json.loads(script_vo)

            effective_voice = audio_settings.get("voice_id", "en-US-AriaNeural")
            voice_custom = audio_settings.get("voice_custom", "")
            if script_vo.get("voice_id"):
                effective_voice = script_vo["voice_id"]
                voice_custom = script_vo.get("voice_custom", "")
            speaker_for_tts = voice_custom if effective_voice == "__custom__" else effective_voice

            qwen_ids = ["aiden", "dylan", "eric", "ono_anna", "ryan", "serena", "sohee", "uncle_fu", "vivian"]
            is_edge_tts = not (speaker_for_tts.lower() in qwen_ids or any(q in speaker_for_tts.lower() for q in qwen_ids))

            # Collect audio assets
            audio_assets = []
            for i in range(len(scenes)):
                a = audio_dir / f"voice_{i+1:02d}.mp3"
                if a.exists():
                    # Generate precise word timings if .json sidecar is missing for Edge-TTS
                    if is_edge_tts and not a.with_suffix(".json").exists():
                        try:
                            from app.services.audio import audio_service
                            text = scenes[i].get("narration_text", "")
                            if text:
                                print(f"[reassemble] Generating missing timing sidecar for scene {i+1}...", flush=True)
                                run_async(audio_service.generate_voiceover(text, speaker_for_tts, a))
                        except Exception as ge:
                            print(f"[reassemble] Failed to generate timings for scene {i+1}: {ge}", flush=True)

                    audio_assets.append({
                        "scene_index": i,
                        "type": "audio",
                        "local_path": str(a),
                        "duration_seconds": scenes[i].get("duration_seconds", 8)
                    })
                else:
                    audio_assets.append({
                        "scene_index": i,
                        "type": "audio",
                        "local_path": None,
                        "duration_seconds": scenes[i].get("duration_seconds", 8)
                    })

            # Check if voice_outro.mp3 exists, and append it
            a_outro = audio_dir / "voice_outro.mp3"
            if a_outro.exists():
                audio_assets.append({
                    "local_path": str(a_outro),
                    "duration_seconds": float(getattr(settings, "OUTRO_DURATION_SECONDS", 6.0) or 6.0),
                    "scene_index": 999
                })

            music_path = audio_dir / "background_music.mp3"
            if not music_path.exists():
                # Try fallback to common alt names
                for alt in ("background_music_v2.mp3", "music.mp3", "bgm.mp3"):
                    alt_path = audio_dir / alt
                    if alt_path.exists():
                        music_path = alt_path
                        break

            output_path = final_dir / "final_video.mp4"

            music_volume = float(visual_settings.get("music_volume", 0.15) or 0.15)
            voice_volume = 1.0

            # Resolve aspect + transition settings so the reassemble honors
            # the project's current visual_settings (not the ones at t2v time).
            aspect_str = visual_settings.get("aspect_ratio", "vertical")
            aspect_cfg = settings.ASPECT_RATIOS.get(aspect_str, settings.ASPECT_RATIOS["vertical"])
            target_w = aspect_cfg["width"]
            target_h = aspect_cfg["height"]
            transition_style = visual_settings.get("transition_style", "none")
            transition_duration = float(visual_settings.get("transition_duration", 0.4) or 0.4)
            audio_transition = visual_settings.get("audio_transition", "match_video")
            if transition_style == "none" or transition_duration <= 0.0:
                transition_duration = 0.0

            caption_settings_for_assembly = dict(caption_settings or {})
            caption_settings_for_assembly["base_resolution_height"] = target_h

            ok = video_service.assemble_video(
                scene_clips=scene_clips,
                audio_assets=audio_assets,
                music_path=music_path if music_path.exists() else None,
                scenes=scenes,
                caption_settings=caption_settings_for_assembly,
                output_path=output_path,
                music_volume=music_volume,
                voice_volume=voice_volume,
                target_width=target_w,
                target_height=target_h,
                transition_style=transition_style,
                transition_duration=transition_duration,
                audio_transition=audio_transition,
            )
            if not ok:
                return {"status": "error", "message": "Assembly failed"}

            return {
                "status": "success",
                "final_path": str(output_path),
            }
        finally:
            db.close()

    def cleanup_intermediate_scenes(self, project_id: int, video_index: int) -> dict:
        """Delete scene clips and audio chunks for a video to free disk space.

        Keeps:
            - The final assembled video (final/{idx}/final_video.mp4)
            - The script row in the DB
            - Any SEO metadata
            - The video_overrides blob (per-video settings)

        Deletes:
            - videos/{idx}/scene_*.mp4 (per-scene ComfyUI t2v outputs)
            - audio/{idx}/voice_*.mp3 (per-scene voiceover)
            - audio/{idx}/background_music*.mp3 (background music)
            - audio/{idx}/mixed_audio*.mp3 (pre-mixed audio if any)
            - Any orphan _work/ temp dirs

        After cleanup, the video's per-scene regen is LOCKED (no way to
        regenerate individual scenes). User must click "Restore intermediate
        scenes" (full re-render) to re-enable per-scene edits.

        Returns:
            {"status": "success", "bytes_freed": N, "files_deleted": M}
            or {"status": "error", "message": "..."}
        """
        import shutil
        db = SessionLocal()
        try:
            project = db.query(models.Project).get(project_id)
            if not project:
                return {"status": "error", "message": "Project not found"}

            script = db.query(models.Script).filter(
                models.Script.project_id == project_id,
                models.Script.video_index == video_index,
            ).order_by(models.Script.created_at.desc()).first()
            if not script:
                return {"status": "error", "message": "No script for this video"}

            # We check if the final video exists, but don't strictly block cleanup if it doesn't
            # (the user might want to clean up intermediate scenes for abandoned/failed renders to reclaim space).
            final_path = settings.PROJECTS_DIR / str(project_id) / "final" / str(video_index) / "final_video.mp4"


            # Idempotency: check videos, audio, and fallback audio dirs
            videos_dir = settings.PROJECTS_DIR / str(project_id) / "videos" / str(video_index)
            audio_dir = settings.PROJECTS_DIR / str(project_id) / "audio" / str(video_index)
            audio_dir_fallback = settings.PROJECTS_DIR / str(project_id) / str(video_index)

            if not videos_dir.exists() and not audio_dir.exists() and not audio_dir_fallback.exists():
                return {"status": "success", "bytes_freed": 0, "files_deleted": 0, "already_cleaned": True}

            import os
            import stat
            def remove_readonly(func, path, excinfo):
                try:
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception as chmod_err:
                    print(f"[cleanup] chmod failed for {path}: {chmod_err}", flush=True)

            bytes_freed = 0
            files_deleted = 0
            for target_dir in (videos_dir, audio_dir, audio_dir_fallback):
                if not target_dir.exists():
                    continue
                # Walk and sum sizes
                for p in target_dir.rglob("*"):
                    if p.is_file():
                        try:
                            bytes_freed += p.stat().st_size
                            files_deleted += 1
                        except Exception:
                            pass
                # rmtree
                try:
                    shutil.rmtree(target_dir, onerror=remove_readonly)
                except Exception as e:
                    print(f"[cleanup] Failed to remove {target_dir}: {e}", flush=True)

            # Mark the script as cleaned. Stash a flag in video_overrides JSON
            # so the front-end can show "intermediate scenes cleaned" badge
            # and the regen buttons get disabled.
            try:
                vo = script.video_overrides or {}
                if isinstance(vo, str):
                    import json as _json
                    vo = _json.loads(vo) if vo else {}
                if not isinstance(vo, dict):
                    vo = {}
                vo["intermediate_cleaned"] = True
                vo["intermediate_cleaned_at"] = datetime.utcnow().isoformat() + "Z"
                script.video_overrides = vo
                db.commit()
            except Exception as e:
                print(f"[cleanup] Failed to mark script as cleaned: {e}", flush=True)

            return {
                "status": "success",
                "bytes_freed": bytes_freed,
                "files_deleted": files_deleted,
            }
        except Exception as global_exc:
            print(f"[cleanup] Global exception in cleanup_intermediate_scenes: {global_exc}", flush=True)
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": f"Cleanup execution error: {str(global_exc)}"}
        finally:
            db.close()

scheduler_service = SchedulerService()
