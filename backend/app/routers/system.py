"""Service management router: start, stop, and probe ComfyUI / backend.

The backend itself is special: the API can't kill or restart its own process
cleanly. So we expose:

  GET  /system/status          - probe ComfyUI + backend, return running state
  POST /system/start-comfyui   - start ComfyUI via schtasks, wait for ready
  POST /system/stop-comfyui    - stop ComfyUI via schtasks
  POST /system/start-all       - start ComfyUI, wait for ready, return status
  POST /system/stop-all        - stop ComfyUI (backend must be killed by hand)

The frontend uses /system/status to show a "Start Services" button when
ComfyUI is down, and "Running" badge when up.
"""
import asyncio
import subprocess
import time
from typing import Optional
import httpx
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.config import settings

router = APIRouter(prefix="/system", tags=["system"])

COMFYUI_SCHTASK = "ComfyUI"
COMFYUI_HOST = settings.COMFYUI_HOST
COMFYUI_URL = COMFYUI_HOST
COMFYUI_START_TIMEOUT_S = 90
COMFYUI_POLL_INTERVAL_S = 1.5


def _is_port_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    """Quick TCP probe to see if a service is listening on host:port."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _probe_comfyui(timeout: float = 2.0) -> dict:
    """Hit ComfyUI /system_stats. Returns {running: bool, info: dict|None}."""
    try:
        resp = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return {"running": True, "info": data}
    except Exception as e:
        return {"running": False, "info": None, "error": str(e)}
    return {"running": False, "info": None}


def _probe_backend() -> dict:
    """The backend is always running if it can answer — return True."""
    return {"running": True, "info": {"url": f"http://{settings.API_HOST}:{settings.API_PORT}"}}


@router.get("/status", response_model=dict)
def get_status():
    """Probe ComfyUI and backend; return running state for the frontend."""
    comfy = _probe_comfyui()
    backend = _probe_backend()
    listening = _is_port_listening("127.0.0.1", 8188) and _is_port_listening("127.0.0.1", 8002)
    return {
        "backend": backend,
        "comfyui": comfy,
        "all_running": comfy["running"] and backend["running"],
        "checked_at": time.time(),
    }


@router.post("/start-comfyui", response_model=dict)
def start_comfyui():
    """Start ComfyUI via the Windows schtasks system. Polls /system_stats until ready.

    Returns when ComfyUI is responsive, or after COMFYUI_START_TIMEOUT_S seconds.
    """
    # Check if it's already running
    probe = _probe_comfyui()
    if probe["running"]:
        return {
            "status": "already_running",
            "comfyui": probe,
            "elapsed_s": 0,
        }

    # Trigger the schtask (fire-and-forget; the .bat will spawn python in the background)
    try:
        result = subprocess.run(
            ["schtasks", "/Run", "/TN", COMFYUI_SCHTASK],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {
                "status": "error",
                "error": f"schtasks failed: {result.stderr or result.stdout}",
                "comfyui": _probe_comfyui(),
            }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Could not run schtasks: {e}",
        }

    # Poll until ComfyUI responds (or timeout)
    start = time.time()
    last = None
    while time.time() - start < COMFYUI_START_TIMEOUT_S:
        time.sleep(COMFYUI_POLL_INTERVAL_S)
        probe = _probe_comfyui()
        if probe["running"]:
            return {
                "status": "success",
                "comfyui": probe,
                "elapsed_s": round(time.time() - start, 2),
            }
        last = probe

    return {
        "status": "timeout",
        "error": f"ComfyUI did not respond within {COMFYUI_START_TIMEOUT_S}s",
        "comfyui": last or _probe_comfyui(),
        "elapsed_s": COMFYUI_START_TIMEOUT_S,
    }


@router.post("/stop-comfyui", response_model=dict)
def stop_comfyui():
    """Stop ComfyUI by ending the schtask and force-killing any stray python procs on port 8188."""
    killed = []
    try:
        subprocess.run(
            ["schtasks", "/End", "/TN", COMFYUI_SCHTASK],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        return {"status": "error", "error": f"schtasks /End failed: {e}"}

    # Belt-and-suspenders: kill any python procs whose cmdline targets ComfyUI/main.py
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() in ("python", "python.exe"):
                    cmdline = " ".join(proc.info.get("cmdline") or [])
                    if "comfyui" in cmdline.lower() and "main.py" in cmdline.lower():
                        proc.kill()
                        killed.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        # psutil not available; fall back to netstat + taskkill
        try:
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in out.splitlines():
                if ":8188" in line and "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        pid = parts[-1]
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/PID", pid],
                                capture_output=True, text=True, timeout=5,
                            )
                            killed.append(int(pid))
                        except Exception:
                            pass
        except Exception:
            pass

    return {
        "status": "success",
        "killed_pids": killed,
        "comfyui": _probe_comfyui(),
    }


@router.post("/start-all", response_model=dict)
def start_all():
    """Start ComfyUI, wait for ready, return final status. Backend cannot be
    self-started by this process (it's the one running the API), so we assume
    backend is up. If you need to start the backend, use the Start_Backend
    schtask separately."""
    comfy_result = start_comfyui()
    return {
        "comfyui_start": comfy_result,
        "backend": _probe_backend(),
        "all_running": comfy_result.get("comfyui", {}).get("running", False),
    }


@router.post("/stop-all", response_model=dict)
def stop_all():
    """Stop ComfyUI. Backend is left running (killing it would also kill this
    request). Use schtasks /End /TN Backend_Shorts to stop the backend."""
    return stop_comfyui()
