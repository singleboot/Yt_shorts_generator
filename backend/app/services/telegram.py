import logging
import threading
import time
import json
import urllib.request
import urllib.parse
from pathlib import Path
from sqlalchemy.orm import Session
from app.config import settings
from app.database import SessionLocal
from app import models

log = logging.getLogger("telegram_bot")

class TelegramBotService:
    def __init__(self):
        self.token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        self.default_chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")
        self.thread = None
        self.running = False
        self.offset = 0
        # In-memory mapping of job_id -> chat_id for progress reports
        self.job_chats = {}

    def start(self):
        if not self.token:
            print("Telegram Bot Token is not configured. Telegram bot service disabled.")
            log.warning("Telegram Bot Token is not configured. Telegram bot service disabled.")
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"Telegram Bot service started with token: {self.token[:10]}...")
        log.info("Telegram Bot service started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print("Telegram Bot service stopped.")
        log.info("Telegram Bot service stopped.")

    def send_message(self, chat_id, text: str):
        if not self.token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, data=data, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print(f"Telegram sendMessage failed: {e}")
            log.error(f"Telegram sendMessage failed: {e}")
            return False

    def send_video(self, chat_id, video_path: str, caption: str = None):
        if not self.token or not chat_id:
            return False
        file_path = Path(video_path)
        if not file_path.exists():
            print(f"Telegram sendVideo failed: File not found at {video_path}")
            log.error(f"Telegram sendVideo failed: File not found at {video_path}")
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendVideo"
        boundary = f"----TelegramBotBoundary{time.time()}"
        parts = []
        parts.append(f"--{boundary}")
        parts.append('Content-Disposition: form-data; name="chat_id"')
        parts.append("")
        parts.append(str(chat_id))

        if caption:
            parts.append(f"--{boundary}")
            parts.append('Content-Disposition: form-data; name="caption"')
            parts.append("")
            parts.append(str(caption))

        parts.append(f"--{boundary}")
        parts.append(f'Content-Disposition: form-data; name="video"; filename="{file_path.name}"')
        parts.append("Content-Type: video/mp4")
        parts.append("")

        body_start = "\r\n".join(parts).encode("utf-8") + b"\r\n"
        body_end = f"\r\n--{boundary}--\r\n".encode("utf-8")

        try:
            with open(file_path, "rb") as f:
                file_content = f.read()
            body = body_start + file_content + body_end

            req = urllib.request.Request(url, data=body)
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            req.add_header("Content-Length", len(body))

            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print(f"Telegram sendVideo failed: {e}")
            log.error(f"Telegram sendVideo failed: {e}")
            return False

    def notify_job_status(self, job_id: int, logs: str, progress: int, status: str, result: dict = None):
        """Notify the chat associated with this job (or default chat) about status changes."""
        chat_id = self.job_chats.get(job_id) or self.default_chat_id
        if not chat_id:
            return

        # Notify on major milestones or completion
        if status == "running" and progress == 5:
            self.send_message(chat_id, f"🎬 Video creation started! (Job ID: {job_id})")
        elif status == "completed":
            msg = f"✅ Video generation complete!\n"
            if result and result.get("seo"):
                seo = result["seo"]
                msg += f"📌 Title: {seo.get('title', 'N/A')}\n"
                msg += f"📝 Tags: {seo.get('tags', 'N/A')}\n"
            self.send_message(chat_id, msg)
            if result and result.get("video_path"):
                self.send_message(chat_id, "📤 Uploading video to Telegram...")
                self.send_video(chat_id, result["video_path"], caption="Here is your generated short! 🚀")
            # Remove job from tracking map
            self.job_chats.pop(job_id, None)
        elif status == "failed":
            self.send_message(chat_id, f"❌ Job ID {job_id} failed.\nError details:\n{logs[-300:]}")
            self.job_chats.pop(job_id, None)

    def _run_loop(self):
        print("Telegram Bot poll loop running in thread.")
        log.info("Telegram Bot loop started.")
        while self.running:
            try:
                self._poll_updates()
            except Exception as e:
                print(f"Error in Telegram Bot poll loop: {e}")
                log.error(f"Error in Telegram Bot poll loop: {e}")
            time.sleep(2)

    def _poll_updates(self):
        url = f"https://api.telegram.org/bot{self.token}/getUpdates?offset={self.offset}&timeout=15"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=20) as response:
                res = json.loads(response.read().decode("utf-8"))
                if not res.get("ok"):
                    return
                for update in res.get("result", []):
                    print(f"Telegram update received: {update}")
                    self.offset = update["update_id"] + 1
                    message = update.get("message")
                    if message and message.get("text"):
                        self._handle_message(message)
        except Exception as e:
            # Print network errors or SSL errors, but silence normal timeout messages
            err_str = str(e)
            if "timeout" not in err_str.lower():
                print(f"Telegram poll network/SSL error: {e}")

    def _handle_message(self, message):
        chat_id = message["chat"]["id"]
        text = message["text"].strip()

        if text.startswith("/start") or text.startswith("/help"):
            help_text = (
                "🤖 *AI Shorts Creator Bot*\n\n"
                "You can trigger video generation jobs directly from here!\n\n"
                "*Commands:*\n"
                "• `/generate topic=\"...\"` - Create a video in the latest project\n"
                "• `/generate topic=\"...\" project_id=N` - Create in project N\n"
                "• `/status` - Check the status of current projects and active jobs\n\n"
                "Alternatively, *just send any text message* (without commands) and it will be treated as the topic for a new video!"
            )
            self.send_message(chat_id, help_text)
            return

        db = SessionLocal()
        try:
            if text.startswith("/status"):
                self._handle_status(chat_id, db)
            elif text.startswith("/generate"):
                self._handle_generate(chat_id, text, db)
            else:
                # Treat raw text as simple topic generation
                self._trigger_generation(chat_id, topic=text, project_id=None, db=db)
        finally:
            db.close()

    def _handle_status(self, chat_id, db: Session):
        active_jobs = db.query(models.Job).filter(
            models.Job.status.in_(["queued", "running"])
        ).order_by(models.Job.created_at.desc()).limit(5).all()

        if not active_jobs:
            self.send_message(chat_id, "ℹ️ No active generation jobs running at the moment.")
            return

        status_text = "📊 *Current Active Jobs:*\n\n"
        for job in active_jobs:
            status_text += f"• *Job ID {job.id}* ({job.job_type}): {job.status.upper()} - {job.progress}%\n  `Logs: {job.logs}`\n"
        self.send_message(chat_id, status_text)

    def _handle_generate(self, chat_id, text, db: Session):
        # Parse topic="火山" or similar
        topic = ""
        project_id = None
        
        # Simple extraction
        import re
        topic_match = re.search(r'topic=["\'](.+?)["\']', text)
        if topic_match:
            topic = topic_match.group(1)
        else:
            # Fallback to everything after /generate if no quotes
            topic = text.replace("/generate", "").strip()

        project_match = re.search(r'project_id=(\d+)', text)
        if project_match:
            project_id = int(project_match.group(1))

        if not topic:
            self.send_message(chat_id, "⚠️ Please specify a topic. E.g.: `/generate topic=\"Fun Fact About Space\"`")
            return

        self._trigger_generation(chat_id, topic, project_id, db)

    def _trigger_generation(self, chat_id, topic, project_id, db: Session):
        # 1. Resolve project
        project = None
        if project_id:
            project = db.query(models.Project).get(project_id)
        else:
            project = db.query(models.Project).order_by(models.Project.id.desc()).first()

        if not project:
            self.send_message(chat_id, "⚠️ No project found. Please create a project in the Web UI first.")
            return

        self.send_message(chat_id, f"📝 Creating video script on topic: *\"{topic}\"* in Project: *{project.name}*...")

        # 2. Find video_index
        from sqlalchemy import func
        max_idx = db.query(func.max(models.Script.video_index)).filter(models.Script.project_id == project.id).scalar()
        video_index = (max_idx + 1) if max_idx is not None else 0

        # 3. Trigger research & script generation
        from app.services.research import research_service
        from app.services.script import script_service
        from app.services.scheduler import scheduler_service
        import asyncio

        # Run script generation synchronously or via background thread safely
        def run_async(coro):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        return pool.submit(asyncio.run, coro).result()
                else:
                    return loop.run_until_complete(coro)
            except Exception:
                return asyncio.run(coro)

        try:
            # Generate research context
            research = run_async(research_service.research_topic(topic, project.category))
            visual_settings = json.loads(project.visual_settings) if isinstance(project.visual_settings, str) else project.visual_settings
            duration = visual_settings.get("total_duration", 45)

            # Generate script
            script_data = run_async(script_service.generate_script(
                topic=research["topic"],
                category=project.category,
                context=research["context"],
                duration=duration
            ))

            # Apply Telegram default overrides if configured
            overrides = {}
            t_style = getattr(settings, "TELEGRAM_DEFAULT_STYLE", "")
            t_voice = getattr(settings, "TELEGRAM_DEFAULT_VOICE", "")
            t_preset = getattr(settings, "TELEGRAM_DEFAULT_CAPTION_PRESET", "")
            
            if t_style:
                overrides["ai_style"] = t_style
            if t_voice:
                overrides["voice_id"] = t_voice
            if t_preset:
                overrides["caption_preset"] = t_preset

            max_serial = db.query(func.max(models.Script.global_serial)).scalar() or 0
            script = models.Script(
                project_id=project.id,
                title=script_data.get("title", research["topic"]),
                content=script_data.get("hook", "") + "\n\n" + "\n".join([s["narration_text"] for s in script_data.get("scenes", [])]),
                scenes=script_data.get("scenes", []),
                hashtags=",".join(script_data.get("hashtags", [])),
                status="approved",
                video_index=video_index,
                global_serial=max_serial + 1,
                video_overrides=overrides if overrides else None
            )
            db.add(script)
            db.commit()
            db.refresh(script)

            # 4. Enqueue the video rendering Job
            job = models.Job(
                project_id=project.id,
                job_type="video",
                status="queued",
                logs=f"Video {video_index + 1}/{video_index + 1}",
                progress=0
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            # Track this job ID for Telegram updates
            self.job_chats[job.id] = chat_id

            # Trigger scheduler to start compiling
            scheduler_service.scheduler.add_job(
                scheduler_service._process_job_queue,
                "date"
            )

            self.send_message(chat_id, f"🚀 Script generated: *\"{script.title}\"*!\nQueued video rendering (Job ID: {job.id}). You will receive progress updates directly here.")

        except Exception as e:
            self.send_message(chat_id, f"❌ Failed to initiate video creation: {e}")
            log.exception(e)

telegram_bot = TelegramBotService()
