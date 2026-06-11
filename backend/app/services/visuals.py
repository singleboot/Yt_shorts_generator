import httpx
import asyncio
import json
import uuid
import time
from typing import List, Dict, Optional
from pathlib import Path
import random
from app.config import settings
import os

class ComfyUIClient:
    """Full ComfyUI API client for local instance."""
    
    def __init__(self):
        self.host = settings.COMFYUI_HOST
        self.client_id = str(uuid.uuid4())
    
    async def is_connected(self) -> bool:
        """Check if ComfyUI server is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.host}/system_stats")
                return resp.status_code == 200
        except:
            return False
    
    async def upload_image(self, image_path: str) -> str:
        """Upload an image to ComfyUI for use in workflows."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(image_path, "rb") as f:
                    files = {"image": (Path(image_path).name, f, "image/png")}
                    data = {"type": "input", "overwrite": "true"}
                    resp = await client.post(f"{self.host}/upload/image", data=data, files=files)
                    result = resp.json()
                    return result.get("name", Path(image_path).name)
        except Exception as e:
            print(f"Image upload error: {e}")
            return Path(image_path).name
    
    async def queue_prompt(self, workflow: dict) -> Optional[str]:
        """Submit workflow to ComfyUI queue. Returns prompt_id."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {"prompt": workflow, "client_id": self.client_id}
                resp = await client.post(f"{self.host}/prompt", json=payload)
                result = resp.json()
                return result.get("prompt_id")
        except Exception as e:
            print(f"Queue prompt error: {e}")
            return None
    
    async def get_history(self, prompt_id: str) -> Optional[dict]:
        """Get execution history for a prompt."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.host}/history/{prompt_id}")
                return resp.json()
        except Exception as e:
            print(f"Get history error: {e}")
            return None
    
    async def get_image(self, filename: str, subfolder: str = "", folder_type: str = "output") -> Optional[bytes]:
        """Download generated image from ComfyUI."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
                resp = await client.get(f"{self.host}/view", params=params)
                if resp.status_code == 200:
                    return resp.content
            return None
        except Exception as e:
            print(f"Get image error: {e}")
            return None
    
    async def wait_for_completion(self, prompt_id: str, timeout: int = 300, check_cancel: callable = None) -> Optional[dict]:
        """Poll history until prompt completes or timeout, or job is cancelled."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if check_cancel and check_cancel():
                print(f"ComfyUI prompt execution {prompt_id} aborted via cancellation check.")
                return None
            history = await self.get_history(prompt_id)
            if history and prompt_id in history:
                prompt_data = history[prompt_id]
                status = prompt_data.get("status", {})
                if status.get("completed"):
                    return prompt_data
                if status.get("status_str") == "error":
                    print(f"ComfyUI execution error: {prompt_data}")
                    return None
            await asyncio.sleep(1)
        print(f"ComfyUI timeout after {timeout}s")
        return None

    async def clear_vram(self):
        """Free VRAM by unloading models via ComfyUI free endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(f"{self.host}/free", json={"unload_models": True, "free_memory": True})
                await asyncio.sleep(1)  # Brief settle
                return True
        except Exception as e:
            print(f"clear_vram failed (non-fatal): {e}")
            return False

    async def interrupt(self) -> bool:
        """Interrupt the currently running ComfyUI prompt.
        ComfyUI returns {'status': 'ok'} on success. Returns True if the
        interrupt was accepted (whether or not a prompt was actually running).
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{self.host}/interrupt")
                return resp.status_code == 200
        except Exception as e:
            print(f"ComfyUI interrupt failed: {e}")
            return False

    async def clear_queue(self) -> bool:
        """Delete all pending items from ComfyUI's internal queue.

        This must be called alongside interrupt() to fully stop generation:
        - interrupt() stops the *currently executing* prompt
        - clear_queue() removes all *pending* prompts so nothing starts next

        ComfyUI API: POST /queue  {"clear": true}
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{self.host}/queue", json={"clear": True})
                return resp.status_code == 200
        except Exception as e:
            print(f"ComfyUI clear_queue failed: {e}")
            return False

    async def full_stop(self) -> bool:
        """Interrupt current prompt AND clear the pending queue — complete halt."""
        interrupted = await self.interrupt()
        cleared = await self.clear_queue()
        return interrupted or cleared



class VisualsService:
    def __init__(self):
        self.pixabay_key = settings.PIXABAY_API_KEY
        self.comfyui = ComfyUIClient()
        self.workflows_dir = settings.WORKFLOWS_DIR
        self.lora_dir = settings.LORA_DIR
    
    def _load_workflow(self, filename: str) -> dict:
        """Load workflow JSON from file."""
        workflow_path = self.workflows_dir / filename
        with open(workflow_path, "r") as f:
            return json.load(f)
    
    def _resolve_lora(self, lora_name: str) -> Optional[str]:
        """Resolve a LoRA name or style to actual file path. Returns None if not found.

        Returns path with BACKSLASHES (ComfyUI's required format for LoraLoader lora_name on Windows).
        """
        if not lora_name:
            return None

        # Normalize input for path joining
        lora_name_fwd = lora_name.replace("\\", "/")

        # Direct path check (supports subfolders like "ltx2/CozyFelt.safetensors")
        lora_path = self.lora_dir / lora_name_fwd
        if lora_path.exists():
            # Return with backslashes for ComfyUI compatibility on Windows
            return lora_name_fwd.replace("/", "\\")

        # Check if it's a style key - look up the mapped filename
        style_key = lora_name.lower().replace(" ", "_")
        mapped_file = settings.STYLE_LORAS.get(style_key)
        if mapped_file:
            mapped_fwd = mapped_file.replace("\\", "/")
            mapped_path = self.lora_dir / mapped_fwd
            if mapped_path.exists():
                # Return with backslashes for ComfyUI compatibility
                return mapped_fwd.replace("/", "\\")

            # Try partial/fuzzy match for mapped style
            available = self.get_available_loras()
            lora_stem = mapped_file.replace(".safetensors", "").lower()
            for avail in available:
                avail_stem = Path(avail).stem.lower()
                if lora_stem in avail_stem or avail_stem in lora_stem:
                    return avail

        # Try direct fuzzy match against available LoRAs
        available = self.get_available_loras()
        search_term = lora_name.lower().replace(".safetensors", "")
        for avail in available:
            avail_stem = Path(avail).stem.lower()
            if search_term in avail_stem or avail_stem in search_term:
                return avail

        return None

    def _resolve_scene_dims(self) -> tuple:
        """Resolve the (width, height, aspect_str) for the current scene.

        The scheduler stashes the project's width/height/aspect_str on the
        _active_visual_settings module-level hook (see app.config.settings).
        This lets a single t2v call read the project's current aspect without
        threading it through every function signature, and lets the per-scene
        regen path pick up aspect changes automatically.

        Falls back to 720x1280 vertical (legacy default) if the hook is empty
        or the aspect is unknown.
        """
        try:
            from app.config import settings as _settings
            _active = getattr(_settings, "_active_visual_settings", None)
            if isinstance(_active, dict):
                w = int(_active.get("_width") or 0)
                h = int(_active.get("_height") or 0)
                a = _active.get("_aspect_str") or "vertical"
                if w > 0 and h > 0:
                    return (w, h, a)
        except Exception:
            pass
        return (720, 1280, "vertical")

    def _inject_lora(self, workflow: dict, lora_name: str, strength: float = 0.8) -> dict:
        """Dynamically insert LoRA nodes into workflow if LoRA file exists."""
        if not lora_name:
            return workflow
        
        # Resolve to actual file path
        resolved_lora = self._resolve_lora(lora_name)
        if not resolved_lora:
            print(f"LoRA not found: {lora_name}, using base model")
            return workflow
        
        print(f"Using LoRA: {resolved_lora} (strength: {strength})")
        
        # Find nodes to modify
        workflow = json.loads(json.dumps(workflow))  # Deep copy
        
        # Check if workflow already has LoraLoader nodes
        lora_nodes = {k: v for k, v in workflow.items() if v.get("class_type") == "LoraLoader"}
        
        if not lora_nodes:
            # Insert LoraLoader between UNETLoader and ModelSamplingAuraFlow
            # and between CLIPLoader and CLIPTextEncode
            
            # Find the UNETLoader output connection
            unet_loader_id = None
            clip_loader_id = None
            model_sampling_id = None
            clip_text_id = None
            
            for node_id, node in workflow.items():
                if node.get("class_type") == "UNETLoader":
                    unet_loader_id = node_id
                elif node.get("class_type") == "CLIPLoader":
                    clip_loader_id = node_id
                elif node.get("class_type") == "ModelSamplingAuraFlow":
                    model_sampling_id = node_id
                elif node.get("class_type") == "CLIPTextEncode":
                    if clip_text_id is None:
                        clip_text_id = node_id
            
            if unet_loader_id and model_sampling_id:
                # Create LoraLoader node
                lora_id = f"{unet_loader_id}_lora"
                workflow[lora_id] = {
                    "inputs": {
                        "lora_name": resolved_lora,
                        "strength_model": strength,
                        "strength_clip": strength,
                        "model": [unet_loader_id, 0],
                        "clip": [clip_loader_id, 0]
                    },
                    "class_type": "LoraLoader",
                    "_meta": {"title": f"Load LoRA: {resolved_lora}"}
                }
                
                # Redirect ModelSamplingAuraFlow input
                workflow[model_sampling_id]["inputs"]["model"] = [lora_id, 0]
                
                # Redirect CLIPTextEncode input
                if clip_text_id:
                    workflow[clip_text_id]["inputs"]["clip"] = [lora_id, 1]
        else:
            # Update existing LoraLoader
            for node_id, node in lora_nodes.items():
                node["inputs"]["lora_name"] = resolved_lora
                node["inputs"]["strength_model"] = strength
                node["inputs"]["strength_clip"] = strength
                node["_meta"]["title"] = f"Load LoRA: {resolved_lora}"
        
        return workflow
    
    async def generate_ai_video(self, image_path: str, prompt: str = "",
                                 seed: int = None) -> Optional[bytes]:
        """Generate video from image using LTX Video."""
        
        if not await self.comfyui.is_connected():
            print("ComfyUI not connected")
            return None
        
        # Upload image to ComfyUI
        image_name = await self.comfyui.upload_image(image_path)
        
        # Load workflow
        workflow = self._load_workflow("video_gen_ltx.json")
        
        # Replace template variables (placeholders are valid JSON values)
        workflow_str = json.dumps(workflow)
        workflow_str = workflow_str.replace("PLACEHOLDER_INPUT_IMAGE", image_name)
        workflow_str = workflow_str.replace("PLACEHOLDER_PROMPT", prompt or "cinematic motion, smooth camera movement")
        workflow_str = workflow_str.replace('"seed": 0', f'"seed": {seed if seed is not None else random.randint(0, 2**32)}')
        workflow = json.loads(workflow_str)
        
        # Queue prompt
        prompt_id = await self.comfyui.queue_prompt(workflow)
        if not prompt_id:
            return None
        
        # Wait for completion (video takes longer)
        result = await self.comfyui.wait_for_completion(prompt_id, timeout=600)
        if not result:
            return None
        
        # Extract output video
        outputs = result.get("outputs", {})
        for node_id, node_output in outputs.items():
            if "gifs" in node_output or "videos" in node_output:
                items = node_output.get("gifs", []) or node_output.get("videos", [])
                for item_data in items:
                    filename = item_data["filename"]
                    subfolder = item_data.get("subfolder", "")
                    
                    # Download video
                    video_bytes = await self.comfyui.get_image(filename, subfolder)
                    if video_bytes:
                        return video_bytes
        
        return None

    async def generate_ai_video_t2v(self, prompt: str, seed: int = None,
                                     lora_name: str = None, lora_strength: float = 0.6,
                                     width: int = 720, height: int = 1280,
                                     video_length: int = 65,
                                     log_meta: Optional[Dict] = None,
                                     db: Optional[object] = None,
                                     check_cancel: Optional[callable] = None) -> Optional[bytes]:
        """Generate video from text using LTX 2.3 (pure t2v, 2-stage sampling, no input image).

        Workflow: video_t2v_ltx.json (MickMumpitz-style 2-stage: 360x640 -> 720x1280)
        - Stage 1: 9-step distilled at half resolution
        - Stage 2: 3-step refinement after 2x latent upscaling
        - LoRA chain: distilled (fixed) -> gemma abliterated (fixed) -> STYLE (injectable)

        Args:
            log_meta: Optional dict with {project_id, job_id, scene_index, scene_number,
                raw_visual_description, sanitized_visual_description, trigger_words,
                suffix, narration_text} for Prompt Console logging.
            db: Optional SQLAlchemy Session. If provided AND log_meta is set, a
                PromptLog row is created (status=queued) before sending to ComfyUI,
                then updated to status=completed/failed once we know the result.
        """
        if not await self.comfyui.is_connected():
            print("ComfyUI not connected")
            return None

        # Clamp lora_strength to UI's slider range [0.0, 1.5]
        lora_strength = max(0.0, min(1.5, float(lora_strength)))

        # Load t2v workflow
        workflow = self._load_workflow("video_t2v_ltx.json")

        # Resolve style LoRA: lora_name can be a style key, filename, or full path
        style_lora_path = self._resolve_lora(lora_name) if lora_name else None
        if lora_name and not style_lora_path:
            print(f"Style LoRA not found: {lora_name}, using base model (no style)", flush=True)

        # Stage 1 runs at half resolution, stage 2 upscales 2x
        half_w = max(64, (width // 2) // 32 * 32)
        half_h = max(64, (height // 2) // 32 * 32)

        # Frame count must be (n*8+1) per LTX requirements
        length = max(9, (video_length // 8) * 8 + 1)

        # Inject style LoRA at the dict level (avoids JSON escape issues with backslashes)
        if style_lora_path:
            workflow["5"]["inputs"]["lora_name"] = style_lora_path
            workflow["5"]["inputs"]["strength_model"] = lora_strength
            workflow["5"]["inputs"]["strength_clip"] = round(lora_strength * 0.75, 3)
            print(f"[t2v] Injecting style LoRA: {style_lora_path} @ model={lora_strength} clip={round(lora_strength*0.75,3)} (from input '{lora_name}')", flush=True)
        else:
            # No style — use a known-existing LoRA at 0.0 strength to keep the
            # LoraLoader node happy without applying any stylistic effect.
            # Must be a file that actually exists in models/loras/ltx2/
            workflow["5"]["inputs"]["lora_name"] = "ltx2\\ltx-2-19b-distilled-lora-384.safetensors"
            workflow["5"]["inputs"]["strength_model"] = 0.0
            workflow["5"]["inputs"]["strength_clip"] = 0.0
            if lora_name:
                print(f"[t2v] Style LoRA not found for '{lora_name}', falling back to disabled Ghibli placeholder", flush=True)
            else:
                print(f"[t2v] No style requested, using base model only (no LoRA)", flush=True)

        # Inject text/dims/seed at the dict level too (cleaner than string replace)
        workflow["6"]["inputs"]["text"] = prompt or "cinematic motion, smooth camera movement"
        workflow["9"]["inputs"]["width"] = half_w
        workflow["9"]["inputs"]["height"] = half_h
        workflow["9"]["inputs"]["length"] = length
        workflow["10"]["inputs"]["noise_seed"] = seed if seed is not None else random.randint(0, 2**32)
        workflow["21"]["inputs"]["filename_prefix"] = f"ltx_t2v_scene_{seed}"

        # Serialize to JSON for queue submission
        workflow_str = json.dumps(workflow)

        # Create or update PromptLog row BEFORE sending to ComfyUI so the console
        # can see queued prompts in real time. Reuse existing row for the same
        # scene on retry to avoid duplicate entries in the Prompt Console.
        log_id = None
        if db is not None and log_meta is not None:
            try:
                from app.models import PromptLog
                from datetime import datetime
                # Check if a log already exists for this scene (retry case)
                existing = db.query(PromptLog).filter(
                    PromptLog.project_id == (log_meta.get("project_id", 0) or 0),
                    PromptLog.job_id == log_meta.get("job_id"),
                    PromptLog.scene_number == log_meta.get("scene_number", 1),
                ).first()
                if existing:
                    existing.status = "running"
                    existing.final_prompt = prompt
                    existing.seed = seed
                    existing.error = None
                    existing.created_at = datetime.utcnow()
                    db.commit()
                    log_id = existing.id
                else:
                    row = PromptLog(
                        project_id=log_meta.get("project_id", 0) or 0,
                        job_id=log_meta.get("job_id"),
                        video_index=log_meta.get("video_index"),
                        scene_index=log_meta.get("scene_index", 0),
                        scene_number=log_meta.get("scene_number", 1),
                        raw_visual_description=log_meta.get("raw_visual_description"),
                        sanitized_visual_description=log_meta.get("sanitized_visual_description"),
                        trigger_words=log_meta.get("trigger_words"),
                        suffix=log_meta.get("suffix"),
                        final_prompt=prompt,
                        lora_name=lora_name,
                        lora_strength_model=lora_strength,
                        lora_strength_clip=round(lora_strength * 0.75, 3),
                        seed=seed,
                        width=width,
                        height=height,
                        frame_count=length,
                        duration_seconds=round((length - 1) / 25.0, 2),
                        status="running",
                        narration_text=log_meta.get("narration_text"),
                        created_at=datetime.utcnow(),
                    )
                    db.add(row)
                    db.commit()
                    db.refresh(row)
                    log_id = row.id
            except Exception as e:
                print(f"[prompt_log] Failed to create log row: {e}", flush=True)
                try:
                    db.rollback()
                except Exception:
                    pass

        # Queue prompt
        try:
            prompt_id = await self.comfyui.queue_prompt(workflow)
        except Exception as e:
            print(f"[t2v] queue_prompt failed: {e}", flush=True)
            if log_id is not None and db is not None:
                try:
                    row = db.query(type(log_meta.get("__model__", object))).__class__ if False else None
                except Exception:
                    pass
                try:
                    from app.models import PromptLog
                    from datetime import datetime
                    row = db.query(PromptLog).filter(PromptLog.id == log_id).first()
                    if row:
                        row.status = "failed"
                        row.error = f"queue_prompt failed: {e}"
                        row.completed_at = datetime.utcnow()
                        db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
            return None

        if not prompt_id:
            if log_id is not None and db is not None:
                try:
                    from app.models import PromptLog
                    from datetime import datetime
                    row = db.query(PromptLog).filter(PromptLog.id == log_id).first()
                    if row:
                        row.status = "failed"
                        row.error = "queue_prompt returned no prompt_id"
                        row.completed_at = datetime.utcnow()
                        db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
            return None

        # Update the log row with the ComfyUI prompt_id immediately
        if log_id is not None and db is not None:
            try:
                from app.models import PromptLog
                row = db.query(PromptLog).filter(PromptLog.id == log_id).first()
                if row:
                    row.comfyui_prompt_id = prompt_id
                    db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass

        # Wait for completion (video takes longer)
        result = await self.comfyui.wait_for_completion(prompt_id, timeout=3600, check_cancel=check_cancel)
        if not result:
            if log_id is not None and db is not None:
                try:
                    from app.models import PromptLog
                    from datetime import datetime
                    row = db.query(PromptLog).filter(PromptLog.id == log_id).first()
                    if row:
                        row.status = "failed"
                        row.error = "wait_for_completion timed out or returned no result"
                        row.completed_at = datetime.utcnow()
                        db.commit()
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
            return None

        # Extract output video (SaveVideo outputs "images" with mp4 + "animated" bool)
        outputs = result.get("outputs", {})
        for node_id, node_output in outputs.items():
            if "images" in node_output or "gifs" in node_output or "videos" in node_output:
                items = (
                    node_output.get("images", [])
                    or node_output.get("gifs", [])
                    or node_output.get("videos", [])
                )
                for item_data in items:
                    filename = item_data["filename"]
                    subfolder = item_data.get("subfolder", "")

                    video_bytes = await self.comfyui.get_image(filename, subfolder)
                    if video_bytes:
                        # Mark log row as completed
                        if log_id is not None and db is not None:
                            try:
                                from app.models import PromptLog
                                from datetime import datetime
                                row = db.query(PromptLog).filter(PromptLog.id == log_id).first()
                                if row:
                                    row.status = "completed"
                                    row.output_path = f"ComfyUI/output/{subfolder}/{filename}" if subfolder else f"ComfyUI/output/{filename}"
                                    row.completed_at = datetime.utcnow()
                                    db.commit()
                            except Exception:
                                try:
                                    db.rollback()
                                except Exception:
                                    pass
                        return video_bytes

        # No output extracted
        if log_id is not None and db is not None:
            try:
                from app.models import PromptLog
                from datetime import datetime
                row = db.query(PromptLog).filter(PromptLog.id == log_id).first()
                if row:
                    row.status = "failed"
                    row.error = "No video output extracted from ComfyUI result"
                    row.completed_at = datetime.utcnow()
                    db.commit()
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass

        return None

    async def generate_scene_videos(self, scenes: List[Dict], project_dir: Path,
                                      lora_name: str = None, lora_strength: float = 0.6,
                                      style_key: str = None,
                                      project_id: int = 0, video_index: int = 0,
                                      job_id: int = None,
                                      db: Optional[object] = None,
                                      on_progress: callable = None,
                                      is_cancelled: callable = None) -> List[Path]:
        """Generate one t2v clip per scene, sequentially, with VRAM clearing between scenes.

        Args:
            scenes: List of scene dicts with visual_description, duration_seconds
            project_dir: Where to save scene_NN.mp4 files
            lora_name: Optional LoRA filename (currently ignored - workflow has fixed LoRAs)
            lora_strength: LoRA strength (currently ignored)
            project_id: For deterministic seed
            video_index: For deterministic seed
            job_id: For PromptLog row linkage
            db: Optional SQLAlchemy session. If provided, one PromptLog row is
                created per scene and updated as ComfyUI runs.
            on_progress: Callback(scene_index, total_scenes, message) for progress updates
            is_cancelled: Optional callable returning True if the job was cancelled.
                          When set, the loop bails out between scenes so partial
                          generation is returned and ComfyUI is interrupted.

        Returns:
            List of Paths to scene_NN.mp4 files (may be shorter than len(scenes) on cancel)
        """
        project_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        for i, scene in enumerate(scenes):
            # RESUME: if a previous run already rendered this scene and the
            # mp4 file is on disk with content, reuse it instead of burning
            # another ComfyUI round-trip. This is what makes
            # cancel-then-restart actually resume.
            existing_scene = project_dir / f"scene_{i+1:02d}.mp4"
            if existing_scene.exists() and existing_scene.stat().st_size > 4096:
                print(
                    f"Scene {i+1} already rendered "
                    f"({existing_scene.stat().st_size} bytes) — skipping"
                )
                paths.append(existing_scene)
                continue

            # Cancellation check between scenes
            if is_cancelled and is_cancelled():
                print(f"Scene generation cancelled before scene {i+1}")
                # Make sure ComfyUI is interrupted so any in-flight prompt stops
                try:
                    await self.comfyui.interrupt()
                except Exception:
                    pass
                break

            # Resolve render dimensions for this scene. Scheduler stashes
            # width/height/aspect_str on the _active_visual_settings hook so
            # every scene in the same job uses consistent dims, and per-scene
            # regen picks up the project's current aspect automatically.
            scene_w, scene_h, aspect_str = self._resolve_scene_dims()
            width = scene_w
            height = scene_h

            # Resolve per-scene duration. HD aspect auto-shortens (5s) to stay
            # inside RTX 3060 12GB VRAM at 1920x1080.
            aspect_per_scene = settings.ASPECT_RATIOS.get(aspect_str, {}).get("per_scene", 6)
            scene_duration = scene.get("duration_seconds", aspect_per_scene)
            # Honor the aspect's per-scene cap (HD=5s, others=6s) so a script
            # with duration_seconds=8 doesn't OOM on HD.
            if scene_duration > aspect_per_scene:
                scene_duration = aspect_per_scene
            duration = scene_duration
            # Convert duration to frames at 25fps, clamp to LTX max of ~250 frames
            video_length = min(int(duration * 25) + 1, 250)
            # Ensure frame count is (n*8+1) per LTX requirements
            video_length = max(9, (video_length // 8) * 8 + 1)

            # Deterministic seed
            # Allow a per-project offset for per-scene regeneration. If the
            # project visual_settings includes "_regen_offset", the seed will
            # shift so a regen produces a fresh take while staying in the same
            # "family" (same style, similar content).
            _regen_offset = 0
            try:
                from app.config import settings as _settings
                _active = getattr(_settings, "_active_visual_settings", None)
                if isinstance(_active, dict):
                    _regen_offset = int(_active.get("_regen_offset", 0) or 0)
            except Exception:
                pass
            seed = random.randint(0, 2**32 - 1)
            seed = (seed + _regen_offset) & 0xFFFFFFFF

            # Sanitize the visual_description: strip abstract phrases LTX 2.3 cannot
            # render (montages, fades, calendar flips, archival effects) and force
            # an explicit camera move if one is missing. Falls back to a static wide
            # shot if the description is empty.
            raw_desc = scene.get("visual_description", "") or "cinematic wide shot of an empty stadium at golden hour, no movement"
            base_prompt = self._sanitize_visual_description(raw_desc, scene_index=i, total_scenes=len(scenes))

            # CUSTOM PROMPT OVERRIDE: when the user has manually tweaked a
            # scene's prompt in the EditVideoModal, scheduler sets
            # _active_visual_settings["_custom_prompt_for"][scene_index] and
            # we use that exact text here. Trigger words + suffix are still
            # prepended/appended so LoRA + format stay consistent, but the
            # user's content is preserved.
            try:
                from app.config import settings as _settings
                _active = getattr(_settings, "_active_visual_settings", None)
                if isinstance(_active, dict):
                    custom_map = _active.get("_custom_prompt_for") or {}
                    if isinstance(custom_map, dict) and str(i) in custom_map:
                        custom = (custom_map[str(i)] or "").strip()
                        if custom:
                            base_prompt = custom
            except Exception:
                pass

            # Prepend style trigger words so the LoRA actually applies the intended
            # style. Without trigger words, the LoRA's effect blends in weakly and
            # the base prompt's content style dominates — causing inconsistent
            # style across scenes. Trigger words are the LoRA's trained tokens
            # (e.g., "claymation, stop motion" for the Claymation LoRA).
            # Allow an override via _active_visual_settings (set by scheduler when
            # doing a per-scene regen, so the log row records the same triggers).
            trigger_prefix = ""
            try:
                from app.config import settings as _settings
                _active = getattr(_settings, "_active_visual_settings", None)
                if isinstance(_active, dict) and _active.get("_trigger_words"):
                    trigger_prefix = f"{_active['_trigger_words']}, "
            except Exception:
                pass
            if not trigger_prefix and style_key:
                triggers = settings.STYLE_LORA_TRIGGERS.get(style_key, "")
                if triggers:
                    trigger_prefix = f"{triggers}, "

            # Compose the suffix for the current aspect. The LTX-2.3 model
            # interprets these tokens as compositional guidance; the suffix
            # also appears in the Prompt Console log so the user can audit it.
            if aspect_str == "horizontal":
                aspect_term = "horizontal 16:9, cinematic lighting, 1280x720 resolution"
            elif aspect_str == "horizontal_hd":
                aspect_term = "horizontal 16:9, cinematic lighting, 1920x1080 resolution"
            else:
                aspect_term = "vertical 9:16, cinematic lighting, 720x1280 resolution"

            prompt = (
                f"{trigger_prefix}{base_prompt}, 25fps, high quality, "
                f"{aspect_term}, no text, no captions, no subtitles, no watermark, no overlay, clean video"
            )

            if on_progress:
                on_progress(i, len(scenes), f"Generating scene {i+1}/{len(scenes)}: {base_prompt[:50]}...")

            # Build log metadata for the Prompt Console
            suffix = f"25fps, high quality, {aspect_term}"
            log_meta = None
            if db is not None:
                log_meta = {
                    "project_id": project_id,
                    "job_id": job_id,
                    "video_index": video_index,
                    "scene_index": i,
                    "scene_number": i + 1,
                    "raw_visual_description": raw_desc,
                    "sanitized_visual_description": base_prompt,
                    "trigger_words": trigger_prefix.rstrip(", ").strip() or None,
                    "suffix": suffix,
                    "narration_text": scene.get("narration_text") or scene.get("narration"),
                }

            mp4_bytes = await self.generate_ai_video_t2v(
                prompt=prompt,
                seed=seed,
                lora_name=lora_name,
                lora_strength=lora_strength,
                width=width,
                height=height,
                video_length=video_length,
                log_meta=log_meta,
                db=db,
                check_cancel=is_cancelled,
            )

            # Cancellation check after each scene finishes (which can take minutes)
            if is_cancelled and is_cancelled():
                # Persist whatever we have so far
                if mp4_bytes:
                    scene_path = project_dir / f"scene_{i+1:02d}.mp4"
                    scene_path.write_bytes(mp4_bytes)
                    paths.append(scene_path)
                try:
                    await self.comfyui.interrupt()
                except Exception:
                    pass
                break

            if mp4_bytes is None:
                print(f"Failed to generate scene {i+1}, using fallback black clip", flush=True)
                mp4_bytes = self._make_fallback_clip(duration, width, height)
                # Mark the prompt log as failed for this scene
                if db is not None and log_meta is not None:
                    try:
                        from app.models import PromptLog
                        log_row = db.query(PromptLog).filter(
                            PromptLog.project_id == (log_meta.get("project_id", 0) or 0),
                            PromptLog.job_id == log_meta.get("job_id"),
                            PromptLog.scene_number == i + 1,
                        ).order_by(PromptLog.id.desc()).first()
                        if log_row:
                            log_row.status = "failed"
                            log_row.error = "Scene generation failed, used fallback clip"
                            db.commit()
                    except Exception:
                        pass

            scene_path = project_dir / f"scene_{i+1:02d}.mp4"
            scene_path.write_bytes(mp4_bytes)
            paths.append(scene_path)

            # Free VRAM between scenes to keep within 12GB budget
            await self.comfyui.clear_vram()

        return paths

    def _sanitize_visual_description(self, desc: str, scene_index: int = 0, total_scenes: int = 1) -> str:
        """Clean up a scene's visual_description for LTX 2.3 t2v.

        LTX 2.3 cannot render:
        - Montages / collages / split screens / quick cuts
        - Calendar/clock/time-passing metaphors
        - "Fade to black", "dissolve to", transition cues
        - Archival black-and-white, 8mm/film-grain effects
        - On-screen text / logos / graphics
        - Multiple unrelated subjects in one frame

        Strips those phrases, drops generic suffixes ("high quality", "8k"), and
        prepends a slow camera move if the description doesn't already have one.
        Also enforces a "slow" / "contemplative" final-scene closer.
        """
        import re
        d = (desc or "").strip()
        if not d:
            d = "Cinematic wide shot of an empty stadium at golden hour, no movement"

        # Strip abstract / impossible WORDS (conservatively — only the literal
        # term, not the entire clause). This keeps the subject intact.
        bad_words = [
            r"\b(montage of)\b",
            r"\b(montage)\b",
            r"\b(collage of)\b",
            r"\b(collage)\b",
            r"\b(split screen)\b",
            r"\b(quick cuts?)\b",
            r"\b(calendar pages? flipping)\b",
            r"\b(calendar flipping)\b",
            r"\b(time passing)\b",
            r"\b(decades of history)\b",
            r"\b(fade to black)\b",
            r"\b(dissolve to)\b",
            r"\b(transition to)\b",
            r"\b(immediate cut to)\b",
            r"\b(cut to)\b",
            r"\b(archival black and white)\b",
            r"\b(archival)\b",
            r"\b(black and white)\b",
            r"\b(8mm film grain)\b",
            r"\b(8mm)\b",
            r"\b(film grain)\b",
            r"\b(sepia tone)\b",
            r"\b(sepia)\b",
            r"\b(quick cut to)\b",
        ]
        for pat in bad_words:
            d = re.sub(pat, "", d, flags=re.IGNORECASE)
        # Drop generic quality suffixes LTX already handles via workflow
        d = re.sub(r",?\s*(high quality|8k|4k|ultra ?realistic|hyperrealistic)[^,\.]*", "", d, flags=re.IGNORECASE)
        # Drop aspect/resolution terms across all supported aspects. The
        # suffix is re-appended in generate_scene_videos based on the current
        # aspect ratio, so we never want the LLM's own aspect term in the
        # sanitized base (it would either duplicate or contradict).
        d = re.sub(
            r",?\s*(vertical 9:?16|horizontal 16:?9|landscape|cinematic lighting|"
            r"720x1280|1280x720|1920x1080)[^,\.]*",
            "", d, flags=re.IGNORECASE
        )
        # Collapse multiple commas/spaces
        d = re.sub(r"\s*,\s*,\s*", ", ", d)
        d = re.sub(r"\s{2,}", " ", d).strip().strip(",").strip()
        # Clean up leftover "and"/"with" connector artifacts after stripping
        d = re.sub(r"\s+with\s+and\s+", " ", d, flags=re.IGNORECASE)
        d = re.sub(r"\s+and\s+and\s+", " ", d, flags=re.IGNORECASE)
        d = re.sub(r"\s+with\s*,", ",", d, flags=re.IGNORECASE)
        d = re.sub(r"\s+and\s*,", ",", d, flags=re.IGNORECASE)
        d = re.sub(r"\s*,?\s*and\s*$", "", d, flags=re.IGNORECASE)
        d = re.sub(r"\s+,", ",", d)
        d = re.sub(r",\s*,", ",", d)
        d = re.sub(r"\s{2,}", " ", d).strip().strip(",").strip()
        # Trailing connector: ", with" or " with" at end
        d = re.sub(r",?\s+with$", "", d, flags=re.IGNORECASE).strip().strip(",").strip()
        d = re.sub(r",?\s+and$", "", d, flags=re.IGNORECASE).strip().strip(",").strip()
        # Trailing "cinematic ," or "mood ," or "scene ,"
        d = re.sub(r",\s*$", "", d).strip()
        # If we stripped the whole description, fall back
        if len(d) < 10:
            d = "Cinematic wide shot of an empty stadium at golden hour, no movement"

        # Check whether description already starts with a camera move
        camera_moves = [
            "slow push-in", "slow push in", "push-in", "push in",
            "slow dolly", "dolly", "slow pan", "pan across", "pan left", "pan right",
            "slow orbit", "orbit", "slow zoom", "zoom in", "zoom out",
            "slow tilt", "tilt up", "tilt down",
            "static wide", "static shot", "static close", "wide shot", "close-up", "close up",
            "tracking shot", "slow tracking", "slow crane", "crane shot",
            "handheld", "slow motion",
        ]
        d_lower = d.lower()
        has_camera = any(d_lower.startswith(cm) or f" {cm} " in f" {d_lower} " for cm in camera_moves)

        # Force a slow camera if missing
        if not has_camera:
            if d:
                d = f"Slow push-in on {d[0].lower() + d[1:]}"
            else:
                d = "Slow push-in on the scene"
            d = d[0].upper() + d[1:]

        # Re-derive d_lower after the camera-move fix above
        d_lower = d.lower()

        # Force a "slow, contemplative" closer on the FINAL scene so the video
        # has a deliberate ending rather than an abrupt cut. Only replace if the
        # description doesn't already lead with a "slow" or "static" move.
        if total_scenes > 0 and scene_index == total_scenes - 1:
            starts_slow = (
                d_lower.startswith("slow")
                or d_lower.startswith("static")
                or d_lower.startswith("contemplative")
            )
            if not starts_slow:
                # Prepend a contemplative, slow camera move to set a deliberate
                # ending pace.
                d = f"Slow, contemplative push-in, {d[0].lower() + d[1:]}"
                d = d[0].upper() + d[1:]
            else:
                # Already has a slow/static start; just inject "contemplative"
                # into the existing slow move to reinforce the closing-shot feel.
                if "contemplative" not in d_lower:
                    d = re.sub(
                        r"^(slow (?:push-?in|push in|dolly|pan|orbit|zoom|tracking|crane))",
                        r"\1, contemplative",
                        d,
                        count=1,
                        flags=re.IGNORECASE,
                    )

        # Trim to a sane length
        if len(d) > 500:
            d = d[:500].rsplit(",", 1)[0].strip()

        return d

    def _make_fallback_clip(self, duration: float, width: int, height: int) -> bytes:
        """Generate a simple black clip as fallback when t2v fails."""
        import subprocess
        # Make sure ffmpeg is on PATH before calling it from this fallback path
        from app.services.video import _ensure_ffmpeg_on_path_once
        _ensure_ffmpeg_on_path_once()
        output_path = settings.STORAGE_DIR / f"fallback_{int(time.time())}.mp4"
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=black:s={width}x{height}:d={duration}:r=24",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                str(output_path)
            ], check=True, capture_output=True)
            return output_path.read_bytes()
        except Exception as e:
            print(f"Fallback clip failed: {e}")
            return b""

    async def search_stock_videos(self, query: str, per_page: int = 5) -> List[Dict]:
        """Search Pixabay for free stock videos."""
        if not self.pixabay_key:
            return []

        # Pick orientation from the active aspect. HD still uses 'horizontal'
        # since Pixabay doesn't distinguish 720p from 1080p; aspect_term is
        # what matters for relevance ranking.
        _, _, aspect_str = self._resolve_scene_dims()
        pixabay_orientation = "horizontal" if aspect_str.startswith("horizontal") else "vertical"

        url = "https://pixabay.com/api/videos/"
        params = {
            "key": self.pixabay_key,
            "q": query,
            "per_page": per_page,
            "safesearch": "true",
            "orientation": pixabay_orientation
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
                hits = data.get("hits", [])
                results = []
                for hit in hits:
                    videos = hit.get("videos", {})
                    size_order = ["small", "medium", "large", "tiny"]
                    video_url = None
                    for size in size_order:
                        if size in videos:
                            video_url = videos[size].get("url")
                            if video_url:
                                break
                    if video_url:
                        results.append({
                            "id": hit["id"],
                            "url": video_url,
                            "thumbnail": hit.get("videos", {}).get("medium", {}).get("thumbnail", hit.get("pageURL", "")),
                            "duration": hit.get("duration", 10),
                            "tags": hit.get("tags", ""),
                            "source": "pixabay"
                        })
                return results
        except Exception as e:
            print(f"Pixabay video search error: {e}")
            return []
    
    async def search_stock_images(self, query: str, per_page: int = 5) -> List[Dict]:
        """Search Pixabay for free stock images."""
        if not self.pixabay_key:
            return []

        _, _, aspect_str = self._resolve_scene_dims()
        pixabay_orientation = "horizontal" if aspect_str.startswith("horizontal") else "vertical"

        url = "https://pixabay.com/api/"
        params = {
            "key": self.pixabay_key,
            "q": query,
            "per_page": per_page,
            "safesearch": "true",
            "orientation": pixabay_orientation
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
                hits = data.get("hits", [])
                return [{
                    "id": h["id"],
                    "url": h.get("largeImageURL", h.get("webformatURL", "")),
                    "thumbnail": h.get("previewURL", ""),
                    "source": "pixabay"
                } for h in hits]
        except Exception as e:
            print(f"Pixabay image search error: {e}")
            return []
    
    async def download_media(self, url: str, output_path: Path) -> bool:
        """Download media file to local storage."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    output_path.write_bytes(resp.content)
                    return True
            return False
        except Exception as e:
            print(f"Download error: {e}")
            return False
    
    async def find_or_generate_visuals(self, scenes: List[Dict], visual_type: str = "stock_footage",
                                       project_dir: Path = None, style: str = "",
                                       lora_strength: float = 0.8, custom_lora: str = "") -> List[Dict]:
        """For each scene, find stock footage. (Z-Image gen removed - using LTX t2v only.)"""
        assets = []
        if project_dir is None:
            project_dir = settings.PROJECTS_DIR / "temp"
            project_dir.mkdir(parents=True, exist_ok=True)

        for i, scene in enumerate(scenes):
            desc = scene.get("visual_description", scene.get("narration_text", ""))
            duration = scene.get("duration_seconds", 8)

            if visual_type in ("stock_footage", "ai_generated"):
                results = await self.search_stock_videos(desc)
                if not results:
                    results = await self.search_stock_images(desc)

                if results:
                    chosen = random.choice(results)
                    ext = ".mp4" if chosen["source"] == "pixabay" and "url" in chosen else ".jpg"
                    filename = f"scene_{i+1:02d}{ext}"
                    local_path = project_dir / filename

                    success = await self.download_media(chosen["url"], local_path)
                    if success:
                        assets.append({
                            "scene_index": i,
                            "type": "video" if ext == ".mp4" else "image",
                            "source": "pixabay",
                            "source_url": chosen["url"],
                            "local_path": str(local_path),
                            "description": desc
                        })
                        continue

            # Fallback
            assets.append({
                "scene_index": i,
                "type": "placeholder",
                "source": "none",
                "source_url": "",
                "local_path": "",
                "description": desc
            })

        return assets
    
    def get_available_loras(self) -> List[str]:
        """List available LoRA files (searches recursively in subfolders)."""
        if not self.lora_dir.exists():
            return []
        # Search recursively for .safetensors files
        lora_files = []
        for lora_path in self.lora_dir.rglob("*.safetensors"):
            # Get relative path from loras dir for subfolder support
            rel_path = lora_path.relative_to(self.lora_dir)
            lora_files.append(str(rel_path))
        return lora_files
    
    def get_available_styles(self) -> List[Dict]:
        """Get styles with availability status (supports partial name matching)."""
        available_loras = self.get_available_loras()
        available_lora_stems = [Path(l).stem.lower() for l in available_loras]
        available_lora_names = [l.lower() for l in available_loras]
        
        styles = []
        for style_key, lora_file in settings.STYLE_LORAS.items():
            lora_stem = lora_file.replace(".safetensors", "").lower()
            # Check exact match, stem match, or partial match
            is_available = (
                lora_file.lower() in available_lora_names or
                lora_stem in available_lora_stems or
                any(lora_stem in name for name in available_lora_stems)
            )
            styles.append({
                "id": style_key,
                "name": style_key.replace("_", " ").title(),
                "lora_file": lora_file,
                "available": is_available,
                "matched_lora": next((l for l in available_loras if lora_stem in l.lower()), None) if is_available else None
            })
        return styles
    
    def get_all_loras(self) -> List[Dict]:
        """Get all available LoRAs with their relative paths."""
        available_loras = self.get_available_loras()
        loras = []
        for lora_path in available_loras:
            lora_name = Path(lora_path).stem
            loras.append({
                "path": lora_path,
                "name": lora_name,
                "folder": str(Path(lora_path).parent) if Path(lora_path).parent != Path(".") else ""
            })
        return loras

visuals_service = VisualsService()
