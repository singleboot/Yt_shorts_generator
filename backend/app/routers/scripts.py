from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.services.research import research_service
from app.services.script import script_service

router = APIRouter(prefix="/scripts", tags=["scripts"])

@router.post("/generate-metadata", response_model=dict)
async def generate_metadata(data: dict):
    """Generate title, description, hashtags for a topic using LLM."""
    topic = data.get("topic", "")
    category = data.get("category", "general")
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")
    seo = await script_service.generate_seo_metadata(topic, category, "")
    return {"status": "success", "seo": seo}

@router.post("/generate", response_model=dict)
async def generate_script(data: dict, db: Session = Depends(get_db)):
    """Generate a script from a topic or URL."""
    source_type = data.get("source_type", "topic")
    source_value = data.get("source_value", "")
    category = data.get("category", "tech")
    duration = data.get("duration", 45)
    
    context = ""
    topic = source_value
    
    if source_type == "youtube_url":
        context = await research_service.get_youtube_transcript(source_value)
        topic = "YouTube Video Summary"
    elif source_type == "web_url":
        context = await research_service.summarize_webpage(source_value)
        topic = source_value
    elif source_type == "auto_research":
        research = await research_service.research_topic(source_value, category)
        context = research["context"]
        topic = research["topic"]
    
    script_data = await script_service.generate_script(
        topic=topic,
        category=category,
        context=context,
        duration=duration
    )
    
    return {
        "status": "success",
        "topic": topic,
        "script": script_data
    }

@router.post("/{script_id}/approve", response_model=dict)
def approve_script(script_id: int, db: Session = Depends(get_db)):
    script = db.query(models.Script).filter(models.Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    script.status = "approved"
    db.commit()
    return {"status": "approved", "script_id": script_id}

@router.post("/{script_id}/regenerate-scenes", response_model=dict)
async def regenerate_scenes(script_id: int, data: dict, db: Session = Depends(get_db)):
    script = db.query(models.Script).filter(models.Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    
    scenes = await script_service.split_script_into_scenes(script.content)
    script.scenes = scenes
    db.commit()
    return {"status": "success", "scenes": scenes}

@router.post("/{script_id}/seo", response_model=dict)
async def generate_seo(script_id: int, db: Session = Depends(get_db)):
    script = db.query(models.Script).filter(models.Script.id == script_id).first()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    
    seo = await script_service.generate_seo_metadata(
        topic=script.title,
        category=script.project.category if script.project else "general",
        script_content=script.content
    )
    return {"status": "success", "seo": seo}
