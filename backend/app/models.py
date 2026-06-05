from sqlalchemy import Column, Integer, String, DateTime, JSON, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base
import json

class YouTubeChannel(Base):
    __tablename__ = "youtube_channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # user-friendly name
    channel_id = Column(String, nullable=False, index=True)  # YouTube's channel ID
    channel_title = Column(String, nullable=True)  # fetched from API
    thumbnail_url = Column(String, nullable=True)
    credentials_file = Column(String, nullable=False)  # path to OAuth token file
    created_at = Column(DateTime, default=datetime.utcnow)

    projects = relationship("Project", back_populates="youtube_channel")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default="active")  # active, paused, archived

    # Source
    source_type = Column(String, default="auto_research")  # auto_research, youtube_url, web_url, topic
    source_value = Column(String, nullable=True)

    # Category
    category = Column(String, nullable=False)
    subcategory = Column(String, nullable=True)

    # Visuals
    visual_type = Column(String, default="stock_footage")  # stock_footage, ai_generated
    visual_settings = Column(JSON, default=lambda: {
        "style": "cinematic",
        "transitions": "fade",
        "duration_per_scene": 5,
        "total_duration": 45
    })

    # Audio
    audio_settings = Column(JSON, default=lambda: {
        "voice_id": "en-US-AriaNeural",
        "language": "en",
        "music_genre": "ambient",
        "music_volume": 0.15,
        "voice_volume": 1.0
    })

    # Captions
    caption_settings = Column(JSON, default=lambda: {
        "style": "standard",
        "font": "Arial-Bold",
        "font_size": 48,
        "color": "#FFFFFF",
        "stroke_color": "#000000",
        "stroke_width": 3,
        "animation": "word_by_word"
    })

    # Schedule
    schedule_settings = Column(JSON, default=lambda: {
        "days": ["monday", "wednesday", "friday"],
        "frequency": 1,
        "times": ["09:00"],
        "auto_generate": False
    })

    # SEO
    seo_settings = Column(JSON, default=lambda: {
        "title_template": "{topic} | Amazing Facts",
        "description_template": "Discover amazing facts about {topic}. Don't forget to like and subscribe!",
        "hashtag_count": 10,
        "auto_hashtags": True
    })

    # YouTube channel assignment
    youtube_channel_id = Column(Integer, ForeignKey("youtube_channels.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    scripts = relationship("Script", back_populates="project", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="project", cascade="all, delete-orphan")
    uploads = relationship("Upload", back_populates="project")
    youtube_channel = relationship("YouTubeChannel", back_populates="projects")

class Script(Base):
    __tablename__ = "scripts"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    scenes = Column(JSON, default=list)  # Array of scene objects
    hashtags = Column(String, nullable=True)
    status = Column(String, default="draft")  # draft, approved, used
    video_index = Column(Integer, default=0)  # position in batch
    global_serial = Column(Integer, nullable=True, index=True)  # global auto-increment
    video_overrides = Column(JSON, nullable=True)  # per-video style/voice/music overrides
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="scripts")
    uploads = relationship("Upload", back_populates="script", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="script", cascade="all, delete-orphan")

class Asset(Base):
    __tablename__ = "assets"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    script_id = Column(Integer, ForeignKey("scripts.id"), nullable=True)
    scene_index = Column(Integer, default=-1)
    asset_type = Column(String, nullable=False)  # video, image, audio, music
    source = Column(String, nullable=True)  # pixabay, comfyui, generated
    source_url = Column(String, nullable=True)
    local_path = Column(String, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    script = relationship("Script", back_populates="assets")

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    job_type = Column(String, nullable=False)  # research, generate, assemble, upload, batch
    status = Column(String, default="queued")  # queued, running, completed, failed, cancelled
    progress = Column(Integer, default=0)  # 0-100
    logs = Column(Text, default="")
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    project = relationship("Project", back_populates="jobs")

class Upload(Base):
    __tablename__ = "uploads"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    script_id = Column(Integer, ForeignKey("scripts.id"))
    video_path = Column(String, nullable=True)
    scheduled_for = Column(DateTime, nullable=True)
    youtube_video_id = Column(String, nullable=True)
    status = Column(String, default="queued")  # queued, processing, done, failed
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(String, nullable=True)
    thumbnail_path = Column(String, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    uploaded_at = Column(DateTime, nullable=True)
    
    project = relationship("Project", back_populates="uploads")
    script = relationship("Script", back_populates="uploads")

class Setting(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
