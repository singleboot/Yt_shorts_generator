import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from app import models
from app.database import SessionLocal


class ArchiveService:
    def _get_archive_path(self, db) -> Path:
        setting = db.query(models.Setting).filter(models.Setting.key == "archive_path").first()
        return Path(setting.value).resolve() if setting and setting.value else None

    def _get_threshold(self, db) -> int:
        setting = db.query(models.Setting).filter(models.Setting.key == "archive_threshold").first()
        try:
            return int(setting.value) if setting and setting.value else 20
        except (ValueError, TypeError):
            return 20

    def archive_single(self, db, upload) -> bool:
        project = db.query(models.Project).get(upload.project_id)
        script = db.query(models.Script).get(upload.script_id)
        archive_root = self._get_archive_path(db)
        if not archive_root or not upload.video_path or not Path(upload.video_path).exists():
            return False

        category = project.category if project and project.category else "uncategorized"
        date_str = datetime.utcnow().strftime("%d%m%Y")
        dest_dir = archive_root / category / date_str
        dest_dir.mkdir(parents=True, exist_ok=True)

        serial = script.global_serial if script and script.global_serial else upload.id
        safe_title = re.sub(r'[^\w\s-]', '', (upload.title or f"video_{serial}")).strip()[:60]
        dest_video = dest_dir / f"{serial}_{safe_title}.mp4"

        shutil.move(str(upload.video_path), str(dest_video))

        vs = project.visual_settings if project else {}
        if isinstance(vs, str):
            vs = json.loads(vs) if vs else {}

        metadata = {
            "serial": serial,
            "project_id": upload.project_id,
            "project_name": project.name if project else "",
            "category": category,
            "title": upload.title,
            "description": upload.description,
            "tags": upload.tags,
            "youtube_video_id": upload.youtube_video_id,
            "scheduled_for": upload.scheduled_for.isoformat() if upload.scheduled_for else None,
            "archived_at": datetime.utcnow().isoformat(),
            "style": vs.get("ai_style") if isinstance(vs, dict) else None,
        }
        meta_path = dest_dir / f"{serial}_{safe_title}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)

        upload.archived_at = datetime.utcnow()
        upload.video_path = str(dest_video)
        db.commit()
        return True

    def check_and_archive(self, db) -> int:
        archive_root = self._get_archive_path(db)
        if not archive_root:
            return 0
        threshold = self._get_threshold(db)
        done_count = db.query(models.Upload).filter(
            models.Upload.status == "done",
            models.Upload.archived_at.is_(None)
        ).count()
        if done_count < threshold:
            return 0
        uploads = db.query(models.Upload).filter(
            models.Upload.status == "done",
            models.Upload.archived_at.is_(None)
        ).order_by(models.Upload.scheduled_for.asc()).limit(threshold).all()
        count = 0
        for u in uploads:
            if self.archive_single(db, u):
                count += 1
        return count

    def archive_project(self, project_id: int) -> int:
        db = SessionLocal()
        try:
            archive_root = self._get_archive_path(db)
            if not archive_root:
                return 0
            uploads = db.query(models.Upload).filter(
                models.Upload.project_id == project_id,
                models.Upload.status == "done",
                models.Upload.archived_at.is_(None)
            ).all()
            count = 0
            for u in uploads:
                if self.archive_single(db, u):
                    count += 1
            return count
        finally:
            db.close()


archive_service = ArchiveService()
