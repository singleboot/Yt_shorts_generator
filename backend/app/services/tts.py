import asyncio
import json
import logging
import random
import sys
import time
import uuid
from pathlib import Path
from typing import List, Dict, Optional
import httpx
from app.config import settings

log = logging.getLogger(__name__)

QWEN3_SPEAKERS = [
    "Aiden", "Dylan", "Eric", "Ono_anna",
    "Ryan", "Serena", "Sohee", "Uncle_fu", "Vivian"
]

QWEN3_VOICES = [
    {"id": s.lower(), "name": s, "gender": "Male" if s in ("Aiden","Dylan","Eric","Ryan","Uncle_fu") else "Female", "locale": "English"}
    for s in QWEN3_SPEAKERS
]

GENRE_TO_ACE_TAGS = {
    "ambient": "ambient, atmospheric, pad, slow, ethereal, 80 BPM, peaceful",
    "upbeat": "upbeat, energetic, pop, dance, driving beat, 128 BPM, happy",
    "epic": "epic, cinematic, orchestral, dramatic, powerful, 100 BPM, majestic",
    "lofi": "lo-fi, chill, hip hop, relaxed, vinyl crackle, 85 BPM, mellow",
    "cinematic": "cinematic, orchestral, film score, dramatic, strings, 90 BPM",
    "corporate": "corporate, motivational, professional, bright, 110 BPM, clean",
    "none": "",
}


class _ComfyClient:
    """Shared ComfyUI HTTP client for TTS and music generation."""

    def __init__(self):
        self.host = settings.COMFYUI_HOST
        self.client_id = str(uuid.uuid4())
        self.workflows_dir = settings.WORKFLOWS_DIR

    async def is_connected(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.host}/system_stats")
                return resp.status_code == 200
        except:
            return False

    async def queue_prompt(self, workflow: dict) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {"prompt": workflow, "client_id": self.client_id}
                resp = await client.post(f"{self.host}/prompt", json=payload)
                return resp.json().get("prompt_id")
        except Exception as e:
            log.error(f"ComfyUI queue error: {e}")
            print(f"ComfyUI queue error: {e}", file=sys.stderr, flush=True)
            return None

    async def get_history(self, prompt_id: str) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.host}/history/{prompt_id}")
                return resp.json()
        except Exception as e:
            log.error(f"ComfyUI history error: {e}")
            print(f"ComfyUI history error: {e}", file=sys.stderr, flush=True)
            return None

    async def wait_for_completion(self, prompt_id: str, timeout: int = 120) -> Optional[dict]:
        start = time.time()
        while time.time() - start < timeout:
            history = await self.get_history(prompt_id)
            if history and prompt_id in history:
                data = history[prompt_id]
                status = data.get("status", {})
                if status.get("completed"):
                    return data
                if status.get("status_str") == "error":
                    err_msg = data.get("status", {}).get("messages", [])
                    log.error(f"ComfyUI execution error on {prompt_id}: {err_msg}")
                    print(f"[TTS] ComfyUI execution error on {prompt_id}: {err_msg}", file=sys.stderr, flush=True)
                    return None
            await asyncio.sleep(0.5)
        log.error(f"ComfyUI timeout after {timeout}s for {prompt_id}")
        print(f"[TTS] ComfyUI timeout after {timeout}s for {prompt_id}", file=sys.stderr, flush=True)
        return None

    async def download_file(self, filename: str, subfolder: str = "", folder_type: str = "output") -> Optional[bytes]:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
                resp = await client.get(f"{self.host}/view", params=params)
                if resp.status_code == 200:
                    return resp.content
            return None
        except Exception as e:
            log.error(f"ComfyUI download error: {e}")
            print(f"[TTS] ComfyUI download error: {e}", file=sys.stderr, flush=True)
            return None

    def load_workflow(self, filename: str) -> dict:
        path = self.workflows_dir / filename
        with open(path) as f:
            return json.load(f)

    async def queue_and_wait(self, workflow: dict, timeout: int = 120) -> Optional[dict]:
        prompt_id = await self.queue_prompt(workflow)
        if not prompt_id:
            return None
        return await self.wait_for_completion(prompt_id, timeout)

    async def retrieve_audio(self, result: dict, prefix: str) -> Optional[bytes]:
        audio_bytes = None
        outputs = result.get("outputs", {})
        for node_id, node_output in outputs.items():
            for key in ("audio", "images", "gifs", "videos"):
                items = node_output.get(key)
                if items:
                    for item in items:
                        filename = item["filename"]
                        subfolder = item.get("subfolder", "")
                        audio_bytes = await self.download_file(filename, subfolder)
                        if audio_bytes:
                            break
                if audio_bytes:
                    break
            if audio_bytes:
                break
        if not audio_bytes:
            comfyui_output = settings.COMFYUI_DIR / "output"
            if comfyui_output.exists():
                matches = sorted(comfyui_output.glob(f"{prefix}*.mp3"))
                if matches:
                    audio_bytes = matches[-1].read_bytes()
        return audio_bytes


_client = _ComfyClient()


class ComfyTTS:
    async def is_connected(self) -> bool:
        return await _client.is_connected()

    async def generate_voiceover(self, text: str, speaker: str, output_path: Path) -> bool:
        if not await self.is_connected():
            log.error("ComfyUI not connected, TTS unavailable")
            print("ComfyUI not connected, TTS unavailable", file=sys.stderr, flush=True)
            return False

        speaker_name = self._resolve_speaker(speaker)
        if not speaker_name:
            log.warning(f"Unknown speaker: {speaker}, falling back to Ryan")
            speaker_name = "Ryan"

        workflow = _client.load_workflow("tts_qwen3.json")
        seed = random.randint(0, 2**32)
        workflow["1"]["inputs"]["text"] = text
        workflow["1"]["inputs"]["speaker"] = speaker_name
        workflow["1"]["inputs"]["seed"] = seed
        workflow["1"]["inputs"]["unload_model_after_generate"] = True
        prefix = f"qwen3_tts_{seed}"
        workflow["2"]["inputs"]["filename_prefix"] = prefix

        result = await _client.queue_and_wait(workflow)
        if not result:
            log.error(f"TTS queue_and_wait returned None for {prefix}")
            return False

        audio_bytes = await _client.retrieve_audio(result, prefix)
        if not audio_bytes:
            log.error(f"TTS: could not retrieve audio for {prefix} (ComfyUI returned no audio output)")
            print(f"[TTS] could not retrieve audio for {prefix}", file=sys.stderr, flush=True)
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)
        return True

    def _resolve_speaker(self, voice_id: str) -> Optional[str]:
        voice_id_lower = voice_id.lower().strip()
        old_voice_mapping = {
            "en-us-arianeural": "Aiden",
            "en-us-guyneural": "Dylan",
            "en-us-jennyneural": "Serena",
            "en-us-michelleneural": "Vivian",
            "en-us-davisneural": "Eric",
            "en-us-tonyneural": "Ryan",
            "en-gb-sonianeural": "Sohee",
            "en-gb-ryanneural": "Ryan",
            "en-au-natashaneural": "Serena",
            "en-in-prabhatneural": "Eric",
        }
        if voice_id_lower in old_voice_mapping:
            return old_voice_mapping[voice_id_lower]
        for entry in QWEN3_VOICES:
            if entry["id"] == voice_id_lower:
                return entry["name"]
        for s in QWEN3_SPEAKERS:
            if s.lower() == voice_id_lower:
                return s
        return None

    async def generate_scene_voiceovers(self, scenes: List[Dict], speaker: str, project_dir: Path) -> List[Dict]:
        audio_assets = []
        for i, scene in enumerate(scenes):
            text = scene.get("narration_text", "")
            if not text:
                continue
            output_path = project_dir / f"voice_{i+1:02d}.mp3"
            success = await self.generate_voiceover(text, speaker, output_path)
            if success:
                audio_assets.append({
                    "scene_index": i,
                    "type": "audio",
                    "source": "comfyui_qwen3_tts",
                    "local_path": str(output_path),
                    "text": text,
                    "voice_id": speaker
                })
        return audio_assets

    def list_voices(self) -> List[Dict]:
        return QWEN3_VOICES


class ComfyMusic:
    async def generate_background_music(self, tags: str, duration: float,
                                        output_path: Path, seed: int = None) -> Optional[str]:
        if not await _client.is_connected():
            print("ComfyUI not connected, ACE 1.5 music unavailable")
            return None

        workflow = _client.load_workflow("ace15_text2music.json")
        seed = seed or random.randint(0, 2**32)

        # Parse tags to extract bpm and keyscale hints
        tags_lower = tags.lower()
        bpm = 100
        for word in tags_lower.split():
            if word.endswith("bpm") and word[:-3].isdigit():
                bpm = int(word[:-3])
                break

        keyscale = "C major"
        for key in ("C major", "C minor", "D major", "D minor", "E minor", "E major",
                     "G major", "A minor", "F major", "B minor", "C# minor", "F minor",
                     "G minor", "A major", "B major", "D# minor", "Eb minor", "Ab major",
                     "Db major", "Gb major", "Bb major", "Bb minor", "F# minor"):
            if key.lower() in tags_lower:
                keyscale = key
                break

        workflow["3"]["inputs"]["seconds"] = duration
        workflow["4"]["inputs"]["tags"] = tags
        workflow["4"]["inputs"]["seed"] = seed
        workflow["4"]["inputs"]["bpm"] = bpm
        workflow["4"]["inputs"]["duration"] = duration
        workflow["4"]["inputs"]["keyscale"] = keyscale
        workflow["6"]["inputs"]["seed"] = seed

        prefix = f"ace15_music_{seed}"
        workflow["8"]["inputs"]["filename_prefix"] = prefix

        result = await _client.queue_and_wait(workflow, timeout=180)
        if not result:
            return None

        audio_bytes = await _client.retrieve_audio(result, prefix)
        if not audio_bytes:
            print(f"ACE 1.5: could not retrieve audio for {prefix}")
            return None

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)
        return str(output_path)

    def build_music_tags(self, genre: str, mood: str = "",
                         scene_description: str = "", duration: int = 60) -> str:
        """Build ACE 1.5 tags from genre, mood, and scene context."""
        base = GENRE_TO_ACE_TAGS.get(genre, genre)

        if mood:
            if mood not in base:
                base = f"{mood}, {base}"

        # Inject scene description keywords if available
        if scene_description:
            keywords = scene_description.split()[:5]
            kw_str = ", ".join(kw for kw in keywords if kw not in base)
            if kw_str:
                base = f"{base}, {kw_str}"

        # Ensure duration-appropriate BPM
        if "80 BPM" in base and duration <= 30:
            base = base.replace("80 BPM", "100 BPM")
        if "85 BPM" in base and duration <= 30:
            base = base.replace("85 BPM", "100 BPM")

        return base

    async def generate_music_for_script(self, scenes: List[Dict], genre: str,
                                         project_dir: Path, duration: int = 60) -> Optional[str]:
        """Generate background music for entire script using ACE 1.5."""
        combined_mood = " ".join(
            s.get("music_mood", s.get("visual_description", ""))[:100]
            for s in scenes[:3]
        )
        scene_desc = scenes[0].get("visual_description", "") if scenes else ""

        tags = self.build_music_tags(genre, combined_mood, scene_desc, duration)
        output_path = project_dir / "background_music.mp3"
        return await self.generate_background_music(tags, float(duration), output_path)


comfy_tts = ComfyTTS()
comfy_music = ComfyMusic()
