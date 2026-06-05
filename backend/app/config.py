from pydantic_settings import BaseSettings
from pathlib import Path
import os
import json

class Settings(BaseSettings):
    APP_NAME: str = "AI Shorts Creator"
    DEBUG: bool = True
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STORAGE_DIR: Path = BASE_DIR / ".." / "storage"
    PROJECTS_DIR: Path = STORAGE_DIR / "projects"
    COMFYUI_DIR: Path = BASE_DIR / "comfyui" / "ComfyUI"
    COMFYUI_MODELS_DIR: Path = COMFYUI_DIR / "models"
    LORA_DIR: Path = COMFYUI_MODELS_DIR / "loras"
    DB_PATH: Path = STORAGE_DIR / "db.sqlite3"
    
    # Workflows
    WORKFLOWS_DIR: Path = BASE_DIR / "app" / "workflows"
    
    # API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8002
    FRONTEND_URL: str = "http://localhost:5173"
    
    # ComfyUI - Dynamic from env (set by Pinokio start.js)
    COMFYUI_HOST: str = os.getenv("COMFYUI_HOST", "http://127.0.0.1:8188")
    COMFYUI_PORT: int = int(os.getenv("COMFYUI_PORT", "8188"))
    
    # External Models (linked from existing ComfyUI)
    EXTERNAL_MODELS_DIR: str = ""
    
    # External Services
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4"
    PIXABAY_API_KEY: str = ""
    
    # YouTube
    YOUTUBE_CLIENT_SECRETS_FILE: Path = STORAGE_DIR / "client_secrets.json"
    YOUTUBE_CREDENTIALS_FILE: Path = STORAGE_DIR / "youtube_credentials.json"
    
    # Video Defaults
    DEFAULT_WIDTH: int = 1080
    DEFAULT_HEIGHT: int = 1920
    DEFAULT_FPS: int = 30
    DEFAULT_DURATION: int = 45
    
    # LoRA Settings
    DEFAULT_LORA_STRENGTH: float = 0.8
    
    # Style to LoRA mapping (filename relative to loras/ltx2/)
    STYLE_LORAS: dict = {
        # LTX 2.3 specialized styles (ltx2/ subfolder)
        "cozyfelt": "ltx2/CozyFelt.safetensors",
        "fantasy_painterly": "ltx2/Fantasy_Painterly.safetensors",
        "paper_cut_out_style": "ltx2/PaperCutOutStyle.safetensors",
        "fantasy_anime": "ltx2/Fantasy_Anime.safetensors",
        "cinematic_sci_fi_cyberpunk": "ltx2/Cinematic_sci-fi-cyberpunk.safetensors",
        "fantasy_realism": "ltx2/Fantasy_Realism.safetensors",
        "fantasy_puppet_style": "ltx2/FantasyPuppetStyle.safetensors",
        "wild_west": "ltx2/Wild_West.safetensors",
        "post_apocalyptic": "ltx2/Post_Apocalyptic.safetensors",
        "claymation": "ltx2/Claymation.safetensors",
        "pixar_toon": "ltx2/Pixar_Toon.safetensors",
        "ghibli": "ltx2/ltx-2-19b-ghibli-style-lora.safetensors",
        "walgro_style": "ltx2/LTXV-13B-walgro_style_step_42000_comfy.safetensors",
        "goldenboy": "ltx2/goldenboy_ltx23-step00067000.comfy.safetensors",
        "golden_age_comic": "ltx2/GoldenAgeComic.safetensors",
        # Legacy aliases
        "studio_ghibli": "ltx2/ltx-2-19b-ghibli-style-lora.safetensors",
        "cinematic": "ltx2/Cinematic_sci-fi-cyberpunk.safetensors",
        "anime": "ltx2/Fantasy_Anime.safetensors",
        "realistic": "ltx2/Fantasy_Realism.safetensors",
        "cyberpunk": "ltx2/Cinematic_sci-fi-cyberpunk.safetensors",
        "comic": "ltx2/GoldenAgeComic.safetensors",
    }
    
    class Config:
        env_file = ".env"

settings = Settings()

# Try to load external models config from model_config.json
model_config_path = settings.COMFYUI_DIR / ".model_config.json"
if model_config_path.exists():
    try:
        with open(model_config_path) as f:
            model_config = json.load(f)
            settings.EXTERNAL_MODELS_DIR = model_config.get("external_models_dir", "")
    except:
        pass
