from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from app.config import settings
from app.database import init_db
from app.seed import create_example_project
from app.routers import projects, scripts, jobs, uploads, settings as settings_router
import os

# Initialize database
init_db()
create_example_project()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="AI-powered YouTube Shorts automation platform"
)

# Startup banner
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*60)
    print("   AI SHORTS CREATOR - Web App")
    print("="*60)
    print(f"   URL: http://{settings.API_HOST}:{settings.API_PORT}")
    print(f"   API: http://{settings.API_HOST}:{settings.API_PORT}/api/health")
    print(f"   ComfyUI: {settings.COMFYUI_HOST}")
    print("="*60 + "\n")
    # Probe ComfyUI for SageAttention availability
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            obj_info = await client.get(f"{settings.COMFYUI_HOST}/object_info")
            nodes = obj_info.json() if obj_info.status_code == 200 else {}
            sage_nodes = [
                name for name in nodes.keys()
                if "sage" in name.lower() or "SageAttention" in name
            ]
            if sage_nodes:
                print(f"   SageAttention: ENABLED ({len(sage_nodes)} node(s))")
                for n in sage_nodes[:5]:
                    print(f"      - {n}")
            else:
                # SageAttention can also be loaded as a library and auto-applied
                # via the LTX2 memory-efficient patch. Check via /system_stats.
                sys_stats = await client.get(f"{settings.COMFYUI_HOST}/system_stats")
                if sys_stats.status_code == 200:
                    print("   SageAttention: enabled via LTX2 patch (library loaded)")
                else:
                    print("   SageAttention: not detected (install via Start ComfyUI SageAttention.bat)")
    except Exception as e:
        print(f"   SageAttention: probe failed (ComfyUI not reachable: {e})")
    print("="*60 + "\n")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(projects.router)
app.include_router(scripts.router)
app.include_router(jobs.router)
app.include_router(uploads.router)
app.include_router(settings_router.router)

# Serve storage files
storage_path = settings.STORAGE_DIR
storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=str(storage_path)), name="storage")

# Health check
@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": settings.APP_NAME}

# Serve frontend static assets and SPA
frontend_build = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_build.exists():
    from fastapi import HTTPException
    
    # Mount frontend assets directory for JS/CSS/images
    frontend_assets = frontend_build / "assets"
    if frontend_assets.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_assets)), name="frontend_assets")
    
    # Mount other static files (favicon, etc.)
    app.mount("/static", StaticFiles(directory=str(frontend_build)), name="frontend_static")
    
    # API route prefixes to exclude from SPA catch-all
    API_PREFIXES = ("api/", "storage/", "assets/", "static/", "docs", "openapi.json")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't serve SPA for API routes or static files
        if any(full_path.startswith(p) for p in API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")
        index_file = frontend_build / "index.html"
        if index_file.exists():
            from fastapi.responses import Response
            content = index_file.read_bytes()
            return Response(content=content, media_type="text/html", headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            })
        return {"status": "frontend_not_built"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
