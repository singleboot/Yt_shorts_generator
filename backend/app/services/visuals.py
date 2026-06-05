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
    
    async def wait_for_completion(self, prompt_id: str, timeout: int = 300) -> Optional[dict]:
        """Poll history until prompt completes or timeout."""
        start_time = time.time()
        while time.time() - start_time < timeout:
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

        Returns path with BACKSLASHES (ComfyUI's required format for LoraLoader lora_name).
        """
        if not lora_name:
            return None

        # Normalize input to forward slashes for path joining
        lora_name_fwd = lora_name.replace("\\", "/")

        # Direct path check (supports subfolders like "ltx2/CozyFelt.safetensors")
        lora_path = self.lora_dir / lora_name_fwd
        if lora_path.exists():
            # ComfyUI LoraLoader expects backslashes for subfolder paths
            return lora_name_fwd.replace("/", "\\")

        # Check if it's a style key - look up the mapped filename
        style_key = lora_name.lower().replace(" ", "_")
        mapped_file = settings.STYLE_LORAS.get(style_key)
        if mapped_file:
            mapped_fwd = mapped_file.replace("\\", "/")
            mapped_path = self.lora_dir / mapped_fwd
            if mapped_path.exists():
                return mapped_fwd.replace("/", "\\")

            # Try partial/fuzzy match for mapped style
            available = self.get_available_loras()
            lora_stem = mapped_file.replace(".safetensors", "").lower()
            for avail in available:
                avail_stem = Path(avail).stem.lower()
                if lora_stem in avail_stem or avail_stem in lora_stem:
                    return avail.replace("/", "\\")

        # Try direct fuzzy match against available LoRAs
        available = self.get_available_loras()
        search_term = lora_name.lower().replace(".safetensors", "")
        for avail in available:
            avail_stem = Path(avail).stem.lower()
            if search_term in avail_stem or avail_stem in search_term:
                return avail.replace("/", "\\")

        return None
    
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
                                     video_length: int = 65) -> Optional[bytes]:
        """Generate video from text using LTX 2.3 (pure t2v, 2-stage sampling, no input image).

        Workflow: video_t2v_ltx.json (MickMumpitz-style 2-stage: 360x640 -> 720x1280)
        - Stage 1: 9-step distilled at half resolution
        - Stage 2: 3-step refinement after 2x latent upscaling
        - LoRA chain: distilled (fixed) -> gemma abliterated (fixed) -> STYLE (injectable)
        """
        if not await self.comfyui.is_connected():
            print("ComfyUI not connected")
            return None

        # Load t2v workflow
        workflow = self._load_workflow("video_t2v_ltx.json")

        # Resolve style LoRA: lora_name can be a style key, filename, or full path
        style_lora_path = self._resolve_lora(lora_name) if lora_name else None
        if lora_name and not style_lora_path:
            print(f"Style LoRA not found: {lora_name}, using base model (no style)")

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
        else:
            # No style - use Ghibli LoRA at 0.0 strength (effectively disabled)
            workflow["5"]["inputs"]["lora_name"] = "ltx2\\ltx-2-19b-ghibli-style-lora.safetensors"
            workflow["5"]["inputs"]["strength_model"] = 0.0
            workflow["5"]["inputs"]["strength_clip"] = 0.0

        # Inject text/dims/seed at the dict level too (cleaner than string replace)
        workflow["6"]["inputs"]["text"] = prompt or "cinematic motion, smooth camera movement"
        workflow["9"]["inputs"]["width"] = half_w
        workflow["9"]["inputs"]["height"] = half_h
        workflow["9"]["inputs"]["length"] = length
        workflow["10"]["inputs"]["noise_seed"] = seed if seed is not None else random.randint(0, 2**32)
        workflow["21"]["inputs"]["filename_prefix"] = f"ltx_t2v_scene_{seed}"

        # Serialize to JSON for queue submission
        workflow_str = json.dumps(workflow)

        # Queue prompt
        prompt_id = await self.comfyui.queue_prompt(workflow)
        if not prompt_id:
            return None

        # Wait for completion (video takes longer)
        result = await self.comfyui.wait_for_completion(prompt_id, timeout=900)
        if not result:
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
                        return video_bytes

        return None

    async def generate_scene_videos(self, scenes: List[Dict], project_dir: Path,
                                      lora_name: str = None, lora_strength: float = 0.6,
                                      project_id: int = 0, video_index: int = 0,
                                      on_progress: callable = None) -> List[Path]:
        """Generate one t2v clip per scene, sequentially, with VRAM clearing between scenes.

        Args:
            scenes: List of scene dicts with visual_description, duration_seconds
            project_dir: Where to save scene_NN.mp4 files
            lora_name: Optional LoRA filename (currently ignored - workflow has fixed LoRAs)
            lora_strength: LoRA strength (currently ignored)
            project_id: For deterministic seed
            video_index: For deterministic seed
            on_progress: Callback(scene_index, total_scenes, message) for progress updates

        Returns:
            List of Paths to scene_NN.mp4 files
        """
        project_dir.mkdir(parents=True, exist_ok=True)
        paths = []

        for i, scene in enumerate(scenes):
            duration = scene.get("duration_seconds", 8)
            # Convert duration to frames at 25fps, clamp to LTX max of ~250 frames
            video_length = min(int(duration * 25) + 1, 250)
            # Ensure frame count is (n*8+1) per LTX requirements
            video_length = max(9, (video_length // 8) * 8 + 1)

            # Deterministic seed
            seed = hash((project_id, video_index, i, scene.get("visual_description", "")[:50])) & 0xFFFFFFFF

            # Enhance prompt with style guidance
            base_prompt = scene.get("visual_description", "cinematic motion")
            prompt = (
                f"{base_prompt}, smooth camera movement, 25fps, high quality, "
                f"vertical 9:16, cinematic lighting, 720x1280 resolution"
            )

            if on_progress:
                on_progress(i, len(scenes), f"Generating scene {i+1}/{len(scenes)}: {base_prompt[:50]}...")

            mp4_bytes = await self.generate_ai_video_t2v(
                prompt=prompt,
                seed=seed,
                lora_name=lora_name,
                lora_strength=lora_strength,
                width=720,
                height=1280,
                video_length=video_length,
            )

            if mp4_bytes is None:
                print(f"Failed to generate scene {i+1}, using fallback black clip")
                mp4_bytes = self._make_fallback_clip(duration, 720, 1280)

            scene_path = project_dir / f"scene_{i+1:02d}.mp4"
            scene_path.write_bytes(mp4_bytes)
            paths.append(scene_path)

            # Free VRAM between scenes to keep within 12GB budget
            await self.comfyui.clear_vram()

        return paths

    def _make_fallback_clip(self, duration: float, width: int, height: int) -> bytes:
        """Generate a simple black clip as fallback when t2v fails."""
        import subprocess
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
        
        url = "https://pixabay.com/api/videos/"
        params = {
            "key": self.pixabay_key,
            "q": query,
            "per_page": per_page,
            "safesearch": "true",
            "orientation": "vertical"
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
        
        url = "https://pixabay.com/api/"
        params = {
            "key": self.pixabay_key,
            "q": query,
            "per_page": per_page,
            "safesearch": "true",
            "orientation": "vertical"
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
