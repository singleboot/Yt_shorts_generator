# AI Shorts Creator

An automated YouTube Shorts generation platform. Research topics, generate scripts, produce videos with stock footage or AI visuals, and schedule uploads to YouTube.

## Features

- **Multi-Source Research**: DuckDuckGo web search, YouTube transcript extraction, or manual topics
- **AI Script Writing**: Ollama-powered script generation with scene splitting
- **Visual Production**: Pixabay stock footage or ComfyUI AI-generated images
- **Voiceover**: Free Edge-TTS with 100+ voices in multiple languages
- **Video Assembly**: MoviePy-based assembly with captions, transitions, and background music
- **YouTube Integration**: OAuth upload with scheduled publishing (`publishAt`)
- **Batch Mode**: Generate a week's worth of Shorts in one run
- **Web UI**: React-based wizard for project creation and management

## Architecture

```
backend/     FastAPI + SQLAlchemy + APScheduler
frontend/    React + Vite + TailwindCSS + shadcn/ui
storage/     SQLite DB, project assets, ComfyUI (optional)
pinokio/     1-click launcher scripts
```

## Quick Start (Pinokio)

1. Install via Pinokio
2. Click **Install** to set up Python environment and dependencies
3. Click **Start** to launch backend + frontend
4. Open the web UI and create your first project

## Manual Setup

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### First Time Setup

1. Go to Settings → YouTube and authenticate
2. (Optional) Add your Pixabay API key for better stock footage
3. (Optional) Configure ComfyUI endpoint if using AI visuals
4. Create a project using the wizard

## API Documentation

When running, visit: `http://localhost:8000/docs`

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/` | List all projects |
| POST | `/projects/` | Create project |
| POST | `/projects/{id}/batch` | Trigger batch generation |
| POST | `/scripts/generate` | Generate script from topic |
| POST | `/uploads/{id}/now` | Upload video immediately |
| GET | `/settings/youtube/status` | Check YouTube auth |

## Environment Variables

Create `.env` in `backend/`:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1
COMFYUI_HOST=http://127.0.0.1:8188
PIXABAY_API_KEY=your_key_here
```

## Category Presets

Built-in categories with subcategories:
- **History**: Explainer, Mystery, This Day That Year, For Children
- **Tech**: AI News, Gadget Reviews, How It Works
- **Horror**: Creepy Stories, Urban Legends, True Crime
- **Children's Stories**: Fairy Tales, Educational, Bedtime Stories
- **General**: Fun Facts, Top 10, Did You Know

## License

MIT
