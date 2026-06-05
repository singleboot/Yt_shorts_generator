import json
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models

def create_example_project():
    """Create an example project if no projects exist."""
    db = SessionLocal()
    try:
        existing = db.query(models.Project).first()
        if existing:
            return
        
        project = models.Project(
            name="Tech News Daily (Example)",
            status="paused",  # Paused so it doesn't auto-run
            source_type="auto_research",
            source_value="",
            category="tech",
            subcategory="AI News",
            visual_type="stock_footage",
            visual_settings={
                "style": "cinematic",
                "transitions": "fade",
                "duration_per_scene": 7,
                "total_duration": 45
            },
            audio_settings={
                "voice_id": "en-US-AriaNeural",
                "language": "en",
                "music_genre": "upbeat",
                "music_volume": 0.15,
                "voice_volume": 1.0
            },
            caption_settings={
                "style": "bold_yellow",
                "font": "Impact",
                "font_size": 52,
                "color": "#FFD700",
                "stroke_color": "#000000",
                "stroke_width": 3,
                "animation": "word_by_word"
            },
            schedule_settings={
                "days": ["monday", "wednesday", "friday"],
                "frequency": 1,
                "times": ["09:00"],
                "auto_generate": False
            },
            seo_settings={
                "title_template": "{topic} | Tech Explained",
                "description_template": "Stay updated with the latest in {topic}. Subscribe for daily tech shorts!",
                "hashtag_count": 12,
                "auto_hashtags": True
            }
        )
        db.add(project)
        db.commit()
        print("Example project created successfully!")
    except Exception as e:
        print(f"Seed error: {e}")
    finally:
        db.close()
