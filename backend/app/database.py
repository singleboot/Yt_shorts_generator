from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)

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

def init_db():
    """Create tables and apply incremental migrations for missing columns/tables."""
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _reconcile_video_counts()


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
