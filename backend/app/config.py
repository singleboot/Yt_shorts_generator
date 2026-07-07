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
    TAVILY_API_KEY: str = ""
    SERPER_API_KEY: str = ""
    
    # YouTube
    YOUTUBE_CLIENT_SECRETS_FILE: Path = STORAGE_DIR / "client_secrets.json"
    YOUTUBE_CREDENTIALS_FILE: Path = STORAGE_DIR / "youtube_credentials.json"
    
    # Video Defaults
    DEFAULT_WIDTH: int = 1080
    DEFAULT_HEIGHT: int = 1920
    DEFAULT_FPS: int = 25
    DEFAULT_DURATION: int = 45

    # Aspect ratio settings: (width, height, per_scene_seconds, label)
    # per_scene_seconds is the recommended per-scene duration for this aspect,
    # honoring RTX 3060 12GB VRAM headroom. HD variants auto-shorten clips
    # because 1920x1080 at 8s starts OOM-ing at the 2-stage sampler's peak.
    ASPECT_RATIOS: dict = {
        "vertical":       {"width": 720,  "height": 1280, "per_scene": 6,  "label": "Vertical 9:16 (720x1280)"},
        "horizontal":     {"width": 1280, "height": 720,  "per_scene": 6,  "label": "Horizontal 16:9 (1280x720)"},
        "horizontal_hd":  {"width": 1920, "height": 1080, "per_scene": 5,  "label": "Horizontal HD 16:9 (1920x1080)"},
    }

    # Transition settings: maps project visual_settings.transition_style values
    # to the corresponding ffmpeg xfade filter transition names. "none" is a
    # sentinel meaning hard cut (no xfade filter applied).
    TRANSITION_STYLES: dict = {
        "none":         None,
        "fade":         "fade",
        "fadeblack":    "fadeblack",
        "fadewhite":    "fadewhite",
        "dissolve":     "dissolve",
        "slide_left":   "slideleft",
        "slide_right":  "slideright",
        "slide_up":     "slideup",
        "slide_down":   "slidedown",
        "wipe_left":    "wipeleft",
        "wipe_right":   "wiperight",
        "zoom_in":      "zoomin",
        "circle_open":  "circleopen",
        "circle_close": "circleclose",
    }
    
    # LoRA Settings
    DEFAULT_LORA_STRENGTH: float = 0.8

    # Outro: append a 6s "like & subscribe" clip to the end of every final
    # video. The script generator reserves OUTRO_DURATION_SECONDS of the user-
    # requested total so the AI content fills duration - outro. The video
    # assembly normalizes the outro to the project's aspect ratio and concat-
    # appends it after the last AI scene with a hard cut. Set the path to None
    # to disable the outro (videos will be built from AI content only).
    LIKE_SUBSCRIBE_OUTRO_PATH: Path = BASE_DIR / ".." / "like-and-subscribe.mov"
    OUTRO_DURATION_SECONDS: int = 3
    
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
        "ghibli": "ltx2/ghibli.safetensors",
        "walgro_style": "ltx2/walgro.safetensors",
        "goldenboy": "ltx2/goldenboy.comfy.safetensors",
        "golden_age_comic": "ltx2/GoldenAgeComic.safetensors",
        "anime90s": "ltx2/anime90s.safetensors",
        # Legacy aliases
        "studio_ghibli": "ltx2/ghibli.safetensors",
        "cinematic": "ltx2/Cinematic_sci-fi-cyberpunk.safetensors",
        "anime": "ltx2/Fantasy_Anime.safetensors",
        "realistic": "ltx2/Fantasy_Realism.safetensors",
        "cyberpunk": "ltx2/Cinematic_sci-fi-cyberpunk.safetensors",
        "comic": "ltx2/GoldenAgeComic.safetensors",
    }

    # Style to trigger words mapping. Prepended to scene visual prompts so the LoRA
    # actually applies the intended style (otherwise the LoRA blends in weakly and
    # the base prompt's content style dominates). Keep trigger words faithful to the
    # LoRA training data; check the LoRA's README on Civitai for exact trigger words.
    STYLE_LORA_TRIGGERS: dict = {
        "cozyfelt": "cozy felt, soft wool, handcrafted, stop motion, warm lighting",
        "fantasy_painterly": "fantasy painterly, oil painting style, rich brushstrokes, dramatic lighting",
        "paper_cut_out_style": "paper cutout, layered paper, handcrafted, storybook, paper art",
        "fantasy_anime": "fantasy anime, vibrant anime style, detailed, magical, glowing",
        "cinematic_sci_fi_cyberpunk": "cinematic sci-fi, cyberpunk, neon, futuristic, blade runner, dystopian",
        "fantasy_realism": "fantasy realism, photorealistic fantasy, epic, cinematic, hyperdetailed",
        "fantasy_puppet_style": "fantasy puppet, stop motion puppet, handcrafted puppet, clay puppet",
        "wild_west": "wild west, dusty frontier, cowboy, sepia, vintage western",
        "post_apocalyptic": "post-apocalyptic, ruined city, overgrown, dusty, abandoned, gritty",
        "claymation": "claymation, stop motion, clay, claymation style, plasticine",
        "pixar_toon": "pixar toon, 3d animation, pixar style, disney pixar, toon shaded",
        "ghibli": "studio ghibli, hayao miyazaki, ghibli anime, watercolor, soft pastel",
        "walgro_style": "walgro style, painterly, vibrant colors, illustrated",
        "goldenboy": "goldenboy, golden age comic, bold ink, vintage comic",
        "golden_age_comic": "golden age comic, vintage comic, halftone, retro comic, 1940s comic",
        "anime90s": "anime 90s, 90s anime style, vintage hand-drawn anime, retro anime, aesthetic cell animation",
        # Legacy aliases
        "studio_ghibli": "studio ghibli, hayao miyazaki, ghibli anime, watercolor, soft pastel",
        "cinematic": "cinematic sci-fi, cyberpunk, neon, futuristic, blade runner, dystopian",
        "anime": "fantasy anime, vibrant anime style, detailed, magical, glowing",
        "realistic": "fantasy realism, photorealistic fantasy, epic, cinematic, hyperdetailed",
        "cyberpunk": "cinematic sci-fi, cyberpunk, neon, futuristic, blade runner, dystopian",
        "comic": "golden age comic, vintage comic, halftone, retro comic, 1940s comic",
        # New Vlog-specific base styles (No LoRA required)
        "vlog_casual": "shot on smartphone, casual vlog, natural lighting, handheld, realistic",
        "vlog_documentary": "documentary style, high quality, professional cinematography, cinematic",
        "vlog_studio": "studio lighting, professional vlog setup, crisp focus, high quality, 4k",
    }
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    TELEGRAM_DEFAULT_STYLE: str = ""
    TELEGRAM_DEFAULT_CAPTION_PRESET: str = ""
    TELEGRAM_DEFAULT_VOICE: str = ""
    
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
