from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from pathlib import Path
import tempfile
from app.database import get_db
from app import models
from app.services.youtube import youtube_service
from app.services.visuals import visuals_service
from app.services.audio import audio_service
from app.config import settings
import json

router = APIRouter(prefix="/settings", tags=["settings"])

@router.get("/", response_model=dict)
def get_settings(db: Session = Depends(get_db)):
    """Get all application settings."""
    settings_dict = {}
    rows = db.query(models.Setting).all()
    for row in rows:
        try:
            import json
            settings_dict[row.key] = json.loads(row.value) if row.value else None
        except:
            settings_dict[row.key] = row.value
    
    settings_dict.setdefault("ollama_host", settings.OLLAMA_HOST)
    settings_dict.setdefault("ollama_model", settings.OLLAMA_MODEL)
    settings_dict.setdefault("pixabay_api_key", settings.PIXABAY_API_KEY)
    settings_dict.setdefault("external_models_dir", settings.EXTERNAL_MODELS_DIR)
    
    return settings_dict

@router.put("/", response_model=dict)
def update_settings(data: dict, db: Session = Depends(get_db)):
    """Update application settings and reload in-memory config."""
    import json
    for key, value in data.items():
        setting = db.query(models.Setting).filter(models.Setting.key == key).first()
        serialized = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        if setting:
            setting.value = serialized
        else:
            setting = models.Setting(key=key, value=serialized)
            db.add(setting)
    db.commit()
    _reload_settings(db)
    return {"status": "success"}

def _reload_settings(db: Session = None):
    """Reload in-memory settings from database."""
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
    try:
        from app.services.visuals import visuals_service
        rows = db.query(models.Setting).all()
        for row in rows:
            key_upper = row.key.upper()
            if hasattr(settings, key_upper):
                try:
                    val = json.loads(row.value) if row.value else getattr(settings, key_upper)
                except Exception:
                    val = row.value
                setattr(settings, key_upper, val)
        if hasattr(visuals_service, 'comfyui'):
            visuals_service.comfyui.host = settings.COMFYUI_HOST
    except Exception:
        pass
    finally:
        if db is not None:
            db.close()

@router.get("/youtube/channels", response_model=list)
def list_youtube_channels(db: Session = Depends(get_db)):
    """List all linked YouTube channels."""
    channels = db.query(models.YouTubeChannel).order_by(models.YouTubeChannel.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "channel_id": c.channel_id,
            "channel_title": c.channel_title,
            "thumbnail_url": c.thumbnail_url,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in channels
    ]


@router.post("/youtube/channels", response_model=dict)
def add_youtube_channel(data: dict, db: Session = Depends(get_db)):
    """Save a new YouTube channel after OAuth flow completes."""
    required = ["name", "channel_id", "credentials_file"]
    for key in required:
        if not data.get(key):
            return {"status": "error", "message": f"Missing required field: {key}"}

    # Check if channel already linked
    existing = db.query(models.YouTubeChannel).filter(
        models.YouTubeChannel.channel_id == data["channel_id"]
    ).first()
    if existing:
        return {"status": "error", "message": "Channel already linked", "channel_id": existing.id}

    channel = models.YouTubeChannel(
        name=data["name"],
        channel_id=data["channel_id"],
        channel_title=data.get("channel_title", data["name"]),
        thumbnail_url=data.get("thumbnail_url", ""),
        credentials_file=data["credentials_file"],
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return {
        "status": "success",
        "channel": {
            "id": channel.id,
            "name": channel.name,
            "channel_id": channel.channel_id,
            "channel_title": channel.channel_title,
            "thumbnail_url": channel.thumbnail_url,
        }
    }


@router.post("/youtube/auth/start", response_model=dict)
def youtube_auth_start():
    """Start YouTube OAuth flow. Returns auth_url (legacy manual-code path)."""
    return youtube_service.start_auth()


@router.post("/youtube/auth/start-local", response_model=dict)
def youtube_auth_start_local():
    """Start OAuth with a local callback server. No manual code copy/paste needed."""
    return youtube_service.start_local_auth()


@router.get("/youtube/auth/status", response_model=dict)
def youtube_auth_status(state: str = ""):
    """Poll for the result of a local OAuth flow. Returns pending|success|error."""
    return youtube_service.check_auth(state)


@router.post("/youtube/upload-secrets")
async def youtube_upload_secrets(file: UploadFile = File(...)):
    """Upload client_secrets.json from Google Cloud Console."""
    content = await file.read()
    return youtube_service.save_secrets(content)


@router.get("/youtube/setup-info", response_model=dict)
def youtube_setup_info():
    """Check whether client_secrets.json is in place and return setup hints."""
    has = youtube_service.has_secrets()
    return {
        "secrets_file_exists": has,
        "secrets_file_path": str(youtube_service.client_secrets_file),
        "callback_port": 8765,
        "callback_url": "http://127.0.0.1:8765/oauth/youtube/callback",
    }


@router.post("/youtube/auth/complete", response_model=dict)
def youtube_auth_complete(data: dict):
    """Complete YouTube OAuth with code, return channel info ready to save."""
    code = data.get("code")
    channel_name = data.get("channel_name", "")
    if not code:
        return {"status": "error", "message": "Missing code"}
    return youtube_service.complete_auth(code, channel_name)


@router.delete("/youtube/channels/{channel_id}", response_model=dict)
def remove_youtube_channel(channel_id: int, db: Session = Depends(get_db)):
    """Unlink a YouTube channel and delete its credentials file."""
    channel = db.query(models.YouTubeChannel).filter(
        models.YouTubeChannel.id == channel_id
    ).first()
    if not channel:
        return {"status": "error", "message": "Channel not found"}

    # Detach from any projects using this channel
    projects_using = db.query(models.Project).filter(
        models.Project.youtube_channel_id == channel_id
    ).all()
    for p in projects_using:
        p.youtube_channel_id = None

    # Delete credentials file
    youtube_service.remove_channel_credentials(channel.credentials_file)

    db.delete(channel)
    db.commit()
    return {"status": "success", "message": "Channel unlinked", "detached_projects": len(projects_using)}


@router.post("/youtube/channels/{channel_id}/refresh", response_model=dict)
def refresh_youtube_channel(channel_id: int, db: Session = Depends(get_db)):
    """Re-fetch channel title/thumbnail from YouTube API."""
    channel = db.query(models.YouTubeChannel).filter(
        models.YouTubeChannel.id == channel_id
    ).first()
    if not channel:
        return {"status": "error", "message": "Channel not found"}

    result = youtube_service.refresh_channel_info(channel.credentials_file)
    if result.get("status") == "success":
        info = result["channel"]
        channel.channel_title = info.get("channel_title", channel.channel_title)
        channel.thumbnail_url = info.get("thumbnail_url", channel.thumbnail_url)
        db.commit()
        return {"status": "success", "channel": {
            "id": channel.id,
            "channel_title": channel.channel_title,
            "thumbnail_url": channel.thumbnail_url,
        }}
    return result

@router.get("/comfyui/status", response_model=dict)
async def comfyui_status():
    """Check local ComfyUI connection status."""
    import asyncio
    try:
        connected = await visuals_service.comfyui.is_connected()
        if connected:
            return {
                "status": "connected",
                "host": settings.COMFYUI_HOST,
                "message": "Built-in ComfyUI is running"
            }
    except:
        pass
    return {
        "status": "disconnected",
        "host": settings.COMFYUI_HOST,
        "message": "Built-in ComfyUI not running. Click Start in Pinokio to launch it."
    }

@router.get("/comfyui/models", response_model=dict)
def comfyui_models():
    """List available ComfyUI models."""
    loras = visuals_service.get_available_loras()
    styles = visuals_service.get_available_styles()

    models_dir = settings.COMFYUI_MODELS_DIR

    def _find_model(subdirs, patterns):
        """Search for a model in subdirectories matching any pattern."""
        for sub in subdirs:
            search_dir = models_dir / sub
            if not search_dir.exists():
                continue
            for f in search_dir.rglob("*.safetensors"):
                for pat in patterns:
                    if pat.lower() in f.name.lower():
                        return True
        return False

    ltx_video = _find_model(["checkpoints", "diffusion_models"], ["ltx"])
    vae = _find_model(["vae"], [".safetensors"])  # any VAE
    text_encoder = _find_model(["text_encoders", "clip"], ["gemma", "t5", "clip"])
    upscaler = _find_model(["latent_upscale_models"], ["ltx", "spatial"])

    return {
        "status": "success",
        "models": {
            "ltx_video": ltx_video,
            "vae": vae,
            "text_encoder": text_encoder,
            "upscaler": upscaler,
        },
        "loras": loras,
        "styles": styles,
        "external_models_dir": settings.EXTERNAL_MODELS_DIR,
        "models_linked": bool(settings.EXTERNAL_MODELS_DIR)
    }

@router.post("/comfyui/link-models", response_model=dict)
def link_comfyui_models(data: dict):
    """Create junctions from external ComfyUI models folder."""
    external_dir = data.get("external_models_dir", "")
    if not external_dir:
        return {"status": "error", "message": "No external models directory provided"}
    
    external_path = Path(external_dir)
    if not external_path.exists():
        return {"status": "error", "message": f"Directory not found: {external_dir}"}
    
    # Run the setup script
    import subprocess
    import sys
    
    script_path = Path(__file__).parent.parent / "scripts" / "setup_model_links.py"
    app_models = settings.COMFYUI_MODELS_DIR
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), external_dir, str(app_models)],
            capture_output=True, text=True, timeout=120
        )
        
        if result.returncode == 0:
            # Update config
            settings.EXTERNAL_MODELS_DIR = external_dir
            return {"status": "success", "message": "Models linked successfully", "output": result.stdout}
        else:
            return {"status": "error", "message": result.stderr}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/voices", response_model=list)
async def list_voices():
    """List available TTS voices (Qwen3-TTS speakers)."""
    voices = await audio_service.list_voices()
    result = []
    for v in voices:
        result.append({
            "name": v.get("name", v.get("Name", "")),
            "display_name": v.get("name", v.get("DisplayName", "")),
            "locale": v.get("locale", v.get("Locale", "English")),
            "gender": v.get("gender", v.get("Gender", "")),
            "suggested": True
        })
    return result

@router.get("/preview-voice", response_class=FileResponse)
async def preview_voice(voice_id: str = "en-US-AriaNeural"):
    """Generate a short TTS preview clip for a given voice."""
    preview_dir = Path(tempfile.gettempdir()) / "ai-shorts-preview"
    preview_dir.mkdir(exist_ok=True)
    safe_name = voice_id.replace("/", "_").replace("\\", "_")
    output_path = preview_dir / f"voice_{safe_name}.mp3"
    if not output_path.exists():
        preview_text = "Hello, this is a voice preview. How does this sound?"
        ok = await audio_service.generate_voiceover(preview_text, voice_id, output_path)
        if not ok:
            raise HTTPException(500, "Failed to generate voice preview")
    return FileResponse(str(output_path), media_type="audio/mpeg")

@router.get("/preview-music/{genre}", response_class=FileResponse)
async def preview_music(genre: str):
    """Generate a short music preview clip for a given genre."""
    preview_dir = Path(tempfile.gettempdir()) / "ai-shorts-preview"
    preview_dir.mkdir(exist_ok=True)
    safe_name = genre.replace("/", "_").replace("\\", "_")
    output_path = preview_dir / f"music_{safe_name}.mp3"
    if not output_path.exists():
        path = await audio_service.get_background_music(genre, output_path, duration=8)
        if not path:
            raise HTTPException(500, "Failed to generate music preview")
    return FileResponse(str(output_path), media_type="audio/mpeg")
