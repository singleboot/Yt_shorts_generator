from sqlalchemy import create_engine, event, text, TypeDecorator, String
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
from pathlib import Path

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)

class StoragePathType(TypeDecorator):
    """SQLAlchemy custom type that converts absolute paths to relative paths relative to
    STORAGE_DIR on write, and resolves them back to absolute paths on read.
    """
    impl = String

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        try:
            storage = Path(settings.STORAGE_DIR).resolve()
            p = Path(value).resolve()
            return p.relative_to(storage).as_posix()
        except Exception:
            # If not relative to storage or fails, return POSIX format as is
            return Path(value).as_posix()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        p = Path(value)
        if p.is_absolute():
            return str(p)
        storage = Path(settings.STORAGE_DIR).resolve()
        return str(storage / p)

engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG
)

# Enable WAL mode for better concurrency
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _migrate_absolute_paths_to_relative():
    """Self-healing migration that runs on startup to convert any absolute paths
    in the database to relative paths from STORAGE_DIR, enabling complete database portability.
    """
    from app import models
    storage = Path(settings.STORAGE_DIR).resolve()
    db = SessionLocal()
    try:
        # 1. YouTube Channels (credentials_file)
        channels = db.query(models.YouTubeChannel).all()
        for ch in channels:
            if ch.credentials_file:
                p = Path(ch.credentials_file)
                if p.is_absolute():
                    try:
                        ch.credentials_file = p.resolve().relative_to(storage).as_posix()
                    except ValueError:
                        pass
        
        # 2. Projects (archive_path)
        projects = db.query(models.Project).all()
        for pr in projects:
            if pr.archive_path:
                p = Path(pr.archive_path)
                if p.is_absolute():
                    try:
                        pr.archive_path = p.resolve().relative_to(storage).as_posix()
                    except ValueError:
                        pass

        # 3. Assets (local_path)
        assets = db.query(models.Asset).all()
        for ass in assets:
            if ass.local_path:
                p = Path(ass.local_path)
                if p.is_absolute():
                    try:
                        ass.local_path = p.resolve().relative_to(storage).as_posix()
                    except ValueError:
                        pass

        # 4. Uploads (video_path, thumbnail_path)
        uploads = db.query(models.Upload).all()
        for up in uploads:
            if up.video_path:
                p = Path(up.video_path)
                if p.is_absolute():
                    try:
                        up.video_path = p.resolve().relative_to(storage).as_posix()
                    except ValueError:
                        pass
            if up.thumbnail_path:
                p = Path(up.thumbnail_path)
                if p.is_absolute():
                    try:
                        up.thumbnail_path = p.resolve().relative_to(storage).as_posix()
                    except ValueError:
                        pass

        # 5. Prompt Logs (output_path)
        prompt_logs = db.query(models.PromptLog).all()
        for pl in prompt_logs:
            if pl.output_path:
                p = Path(pl.output_path)
                if p.is_absolute():
                    try:
                        pl.output_path = p.resolve().relative_to(storage).as_posix()
                    except ValueError:
                        pass

        db.commit()
    except Exception as e:
        print(f"[migration] Absolute path migration failed: {e}", flush=True)
        db.rollback()
    finally:
        db.close()

def init_db():
    """Create tables and apply incremental migrations for missing columns/tables."""
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _reconcile_video_counts()
    _reconcile_aspect_defaults()
    _migrate_absolute_paths_to_relative()


def _reconcile_video_counts():
    """Reconcile projects.schedule_settings.video_count with the actual content.

    schedule_settings.video_count is a *write target* (it gets bumped when the
    user adds new videos or starts a batch). It must NOT be used as a source of
    truth for the video list - the list endpoint derives it from len(videos)
    instead. This migration only cleans up the stored value so that any code
    that still reads it (e.g. legacy frontends) doesn't show phantom slots.
    """
    import json
    from sqlalchemy import inspect
    with engine.connect() as conn:
        try:
            rows = conn.execute(text("SELECT id, schedule_settings FROM projects")).fetchall()
        except Exception:
            return
        for row in rows:
            pid, ss_raw = row[0], row[1]
            try:
                ss = json.loads(ss_raw) if isinstance(ss_raw, str) and ss_raw else (ss_raw or {})
            except Exception:
                continue
            if not isinstance(ss, dict):
                continue
            try:
                max_idx = conn.execute(
                    text("SELECT MAX(video_index) FROM scripts WHERE project_id = :pid"),
                    {"pid": pid},
                ).scalar()
            except Exception:
                max_idx = None
            # video_count is the count of video slots = max_idx + 1 if any
            # scripts exist, else 0
            actual = (max_idx + 1) if max_idx is not None and max_idx >= 0 else 0
            stored = ss.get("video_count", 0)
            if stored != actual:
                ss["video_count"] = actual
                conn.execute(
                    text("UPDATE projects SET schedule_settings = :ss WHERE id = :pid"),
                    {"ss": json.dumps(ss), "pid": pid},
                )
        try:
            conn.commit()
        except Exception:
            pass


def _reconcile_aspect_defaults():
    """Backfill aspect_ratio + transition_style on existing project rows.

    New fields added to visual_settings default (aspect_ratio, transition_style,
    transition_duration, audio_transition). Projects created before these fields
    existed have them missing in stored JSON. Backfill with safe defaults so
    the runtime always reads a complete dict.
    """
    import json
    DEFAULTS = {
        "aspect_ratio": "vertical",
        "transition_style": "none",
        "transition_duration": 0.4,
        "audio_transition": "match_video",
    }
    with engine.connect() as conn:
        try:
            rows = conn.execute(text("SELECT id, visual_settings FROM projects")).fetchall()
        except Exception:
            return
        changed = 0
        for row in rows:
            pid, vs_raw = row[0], row[1]
            try:
                vs = json.loads(vs_raw) if isinstance(vs_raw, str) and vs_raw else (vs_raw or {})
            except Exception:
                continue
            if not isinstance(vs, dict):
                continue
            dirty = False
            for k, v in DEFAULTS.items():
                if k not in vs:
                    vs[k] = v
                    dirty = True
            if dirty:
                conn.execute(
                    text("UPDATE projects SET visual_settings = :vs WHERE id = :pid"),
                    {"vs": json.dumps(vs), "pid": pid},
                )
                changed += 1
        if changed:
            try:
                conn.commit()
            except Exception:
                pass
        if changed:
            print(f"[migrate] Backfilled aspect/transition defaults on {changed} project(s)", flush=True)


def _run_migrations():
    """Add new columns/tables that Base.metadata.create_all doesn't handle for existing DBs."""
    with engine.connect() as conn:
        # Check if projects.youtube_channel_id exists, add if not
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(projects)")).fetchall()]
        if "archive_path" not in cols:
            try:
                conn.execute(text("ALTER TABLE projects ADD COLUMN archive_path VARCHAR"))
                conn.commit()
            except Exception:
                pass
        if "archived_at" not in cols:
            try:
                conn.execute(text("ALTER TABLE projects ADD COLUMN archived_at DATETIME"))
                conn.commit()
            except Exception:
                pass
        if "youtube_channel_id" not in cols:
            try:
                conn.execute(text("ALTER TABLE projects ADD COLUMN youtube_channel_id INTEGER REFERENCES youtube_channels(id)"))
                conn.commit()
            except Exception:
                pass
        # Check if scripts has video_overrides column, add if not
        script_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(scripts)")).fetchall()]
        if "video_overrides" not in script_cols:
            try:
                conn.execute(text("ALTER TABLE scripts ADD COLUMN video_overrides JSON"))
                conn.commit()
            except Exception:
                pass
        if "video_index" not in script_cols:
            try:
                conn.execute(text("ALTER TABLE scripts ADD COLUMN video_index INTEGER DEFAULT 0"))
                conn.commit()
            except Exception:
                pass
        # YouTube channels table - Base.metadata.create_all handles new DBs, but be safe
        tables = [row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
        if "jobs" in tables:
            job_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()]
            if "current_stage" not in job_cols:
                try:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN current_stage VARCHAR"))
                    conn.commit()
                except Exception:
                    pass
        if "youtube_channels" not in tables:
            try:
                conn.execute(text("""
                    CREATE TABLE youtube_channels (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR NOT NULL,
                        channel_id VARCHAR NOT NULL,
                        channel_title VARCHAR,
                        thumbnail_url VARCHAR,
                        credentials_file VARCHAR NOT NULL,
                        created_at DATETIME
                    )
                """))
                conn.execute(text("CREATE INDEX ix_youtube_channels_channel_id ON youtube_channels(channel_id)"))
                conn.commit()
            except Exception:
                pass
