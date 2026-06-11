import asyncio
import httpx
from pathlib import Path
from typing import List, Dict, Optional
from app.config import settings
from app.services.tts import comfy_tts, comfy_music
import subprocess
import math
import struct
import wave


class AudioService:
    def __init__(self):
        self.voices_cache = None
        self._music_cache = {}
    
    async def list_voices(self) -> List[Dict]:
        if self.voices_cache is None:
            edge_voices = [
                {"id": "en-US-AriaNeural", "name": "Microsoft Aria (Female)", "gender": "Female", "locale": "English (US)", "provider": "edge_tts"},
                {"id": "en-US-GuyNeural", "name": "Microsoft Guy (Male)", "gender": "Male", "locale": "English (US)", "provider": "edge_tts"},
                {"id": "en-US-JennyNeural", "name": "Microsoft Jenny (Female)", "gender": "Female", "locale": "English (US)", "provider": "edge_tts"},
                {"id": "en-US-MichelleNeural", "name": "Microsoft Michelle (Female)", "gender": "Female", "locale": "English (US)", "provider": "edge_tts"},
                {"id": "en-US-ChristopherNeural", "name": "Microsoft Christopher (Male)", "gender": "Male", "locale": "English (US)", "provider": "edge_tts"},
                {"id": "en-GB-SoniaNeural", "name": "Microsoft Sonia (Female)", "gender": "Female", "locale": "English (UK)", "provider": "edge_tts"},
                {"id": "en-GB-RyanNeural", "name": "Microsoft Ryan (Male)", "gender": "Male", "locale": "English (UK)", "provider": "edge_tts"},
                {"id": "en-AU-NatashaNeural", "name": "Microsoft Natasha (Female)", "gender": "Female", "locale": "English (AU)", "provider": "edge_tts"},
            ]
            
            qwen_voices = []
            try:
                qwen_raw = comfy_tts.list_voices()
                for v in qwen_raw:
                    qwen_voices.append({
                        "id": v["id"],
                        "name": f"Qwen3 {v['name']} ({v['gender']})",
                        "gender": v["gender"],
                        "locale": v["locale"],
                        "provider": "comfyui_qwen3_tts"
                    })
            except Exception:
                pass
            
            self.voices_cache = qwen_voices + edge_voices
        return self.voices_cache
    
    async def generate_voiceover(self, text: str, voice_id: str, output_path: Path,
                                  rate: str = "-5%", pitch: str = "+0Hz", volume: str = "+10%") -> bool:
        # Determine if it's a Qwen3 voice or Edge-TTS voice
        qwen_ids = ["aiden", "dylan", "eric", "ono_anna", "ryan", "serena", "sohee", "uncle_fu", "vivian"]
        is_qwen = voice_id.lower() in qwen_ids or any(q in voice_id.lower() for q in qwen_ids)
        
        if is_qwen:
            try:
                from app.services.tts import comfy_tts
                connected = await comfy_tts.is_connected()
                if connected:
                    # Resolve voice_id to raw speaker name (e.g. "Aiden")
                    speaker = voice_id
                    if " " in voice_id:
                        parts = voice_id.split()
                        for p in parts:
                            if p.lower() in qwen_ids:
                                speaker = p
                                break
                    # Capitalize first letter (Aiden, Dylan, etc.)
                    speaker = speaker.strip().capitalize()
                    print(f"[TTS] Using ComfyUI Qwen3 TTS for voice: {speaker}")
                    success = await comfy_tts.generate_voiceover(text, speaker, output_path)
                    if success:
                        return True
                    print(f"[TTS] ComfyUI Qwen3 TTS failed, falling back to edge-tts")
            except Exception as e:
                print(f"[TTS] ComfyUI Qwen3 TTS error: {e}, falling back to edge-tts")
        
        # Otherwise (or fallback), use edge-tts (Microsoft online TTS)
        try:
            import edge_tts
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Map Qwen3 voice names to Edge-TTS equivalent neural voices for fallback
            fallback_mapping = {
                "aiden": "en-US-AriaNeural",
                "dylan": "en-US-GuyNeural",
                "serena": "en-US-JennyNeural",
                "vivian": "en-US-MichelleNeural",
                "eric": "en-US-EricNeural",
                "ryan": "en-US-ChristopherNeural",
                "sohee": "en-GB-SoniaNeural",
                "uncle_fu": "en-US-GuyNeural",
                "ono_anna": "en-US-JennyNeural"
            }
            
            effective_voice = voice_id
            for qkey, fallback_v in fallback_mapping.items():
                if qkey in voice_id.lower():
                    effective_voice = fallback_v
                    break
            
            # If the voice name is still not a valid Microsoft voice (doesn't contain "neural"), use default
            if "neural" not in effective_voice.lower():
                effective_voice = "en-US-AriaNeural"
                
            communicate = edge_tts.Communicate(text, effective_voice, rate=rate, volume=volume, pitch=pitch, boundary="WordBoundary")
            words_data = []
            
            with open(str(output_path), "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        start_time = chunk["offset"] / 10000000.0
                        duration = chunk["duration"] / 10000000.0
                        words_data.append({
                            "word": chunk["text"],
                            "start": start_time,
                            "end": start_time + duration
                        })
            
            if output_path.exists() and output_path.stat().st_size > 1024:
                import json as _json
                json_path = output_path.with_suffix(".json")
                with open(str(json_path), "w", encoding="utf-8") as jf:
                    _json.dump(words_data, jf, indent=2)
                return True
            else:
                print(f"[TTS] edge-tts produced empty/missing file for {effective_voice}")
                return False
        except Exception as e:
            print(f"[TTS] edge-tts failed for {voice_id}: {e}")
            return False
    
    async def generate_scene_voiceovers(self, scenes: List[Dict], voice_id: str,
                                        project_dir: Path) -> List[Dict]:
        audio_assets = []
        for i, scene in enumerate(scenes):
            text = scene.get("narration_text", "")
            if not text:
                continue
            output_path = project_dir / f"voice_{i+1:02d}.mp3"
            success = await self.generate_voiceover(text, voice_id, output_path)
            if success:
                audio_assets.append({
                    "scene_index": i,
                    "type": "audio",
                    "source": "tts",
                    "local_path": str(output_path),
                    "text": text,
                    "voice_id": voice_id
                })
            else:
                print(f"[TTS] WARNING: voiceover failed for scene {i+1}, skipping")
        return audio_assets
    
    async def get_background_music(self, genre: str = "ambient", output_path: Path = None, 
                                    duration: int = 60) -> Optional[str]:
        """Generate background music using ACE 1.5 via ComfyUI. Falls back to Pixabay/local/tone."""
        if output_path and output_path.exists():
            return str(output_path)
        
        if not output_path:
            return None
        
        # Primary: ACE 1.5 music generation via ComfyUI
        try:
            tags = comfy_music.build_music_tags(genre, duration=duration)
            music_path = await comfy_music.generate_background_music(tags, float(duration), output_path)
            if music_path:
                print(f"ACE 1.5 music generated: {music_path}")
                return music_path
        except Exception as e:
            print(f"ACE 1.5 music generation failed: {e}")
        
        # Fallback: Pixabay music search
        if settings.PIXABAY_API_KEY:
            try:
                music_url = await self._search_pixabay_music(genre)
                if music_url:
                    success = await self._download_music(music_url, output_path)
                    if success:
                        return str(output_path)
            except Exception as e:
                print(f"Pixabay music search failed: {e}")
        
        # Fallback: local music files
        music_dir = settings.STORAGE_DIR / "music"
        if music_dir.exists():
            genre_map = {
                "ambient": ["ambient", "calm", "peaceful"],
                "upbeat": ["upbeat", "happy", "energetic"],
                "epic": ["epic", "dramatic", "cinematic"],
                "lo-fi": ["lofi", "lo-fi", "chill"],
                "corporate": ["corporate", "business", "professional"],
                "cinematic": ["cinematic", "movie", "trailer"],
            }
            keywords = genre_map.get(genre.lower(), [genre.lower()])
            for f in music_dir.glob("*.mp3"):
                for kw in keywords:
                    if kw in f.stem.lower():
                        return str(f)
            files = list(music_dir.glob("*.mp3"))
            if files:
                return str(files[0])
        
        # Last resort: ambient tone
        try:
            self._generate_ambient_tone(output_path, duration)
            return str(output_path)
        except Exception as e:
            print(f"Ambient tone generation failed: {e}")
            return None
    
    async def _search_pixabay_music(self, genre: str) -> Optional[str]:
        """Search Pixabay for royalty-free music."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://pixabay.com/api/",
                params={
                    "key": settings.PIXABAY_API_KEY,
                    "media_type": "music",
                    "q": genre,
                    "per_page": 3,
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", [])
                if hits:
                    return hits[0].get("audio_url")
        return None
    
    async def _download_music(self, url: str, output_path: Path) -> bool:
        """Download music file from URL."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200:
                    output_path.write_bytes(resp.content)
                    return True
        except Exception as e:
            print(f"Music download error: {e}")
        return False
    
    def _generate_ambient_tone(self, output_path: Path, duration: int = 60):
        """Generate a soft ambient background tone as fallback."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 44100
        num_samples = sample_rate * duration
        
        # Create a soft ambient pad with multiple sine waves
        with wave.open(str(output_path), 'w') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            
            frames = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                # Multiple low frequencies for ambient feel
                val = 0
                val += 0.15 * math.sin(2 * math.pi * 65.4 * t)  # C2
                val += 0.10 * math.sin(2 * math.pi * 98.0 * t)  # G2
                val += 0.08 * math.sin(2 * math.pi * 130.8 * t)  # C3
                val += 0.05 * math.sin(2 * math.pi * 196.0 * t)  # G3
                # Slow LFO for movement
                lfo = 0.5 + 0.5 * math.sin(2 * math.pi * 0.1 * t)
                val *= lfo * 0.3
                sample = max(-1.0, min(1.0, val))
                frames.extend(struct.pack('<h', int(sample * 32767)))
            wav.writeframes(bytes(frames))
    
    async def mix_audio(self, voiceover_path: Path, music_path: Path,
                        output_path: Path, music_volume: float = 0.15,
                        voice_volume: float = 1.0) -> bool:
        """Mix voiceover with background music using moviepy CompositeAudioClip.

        - Voiceover at full volume (foreground)
        - Music at low volume (background)
        - Music loops to match voiceover length
        - Music fades in over first 1s, fades out over last 2s
        """
        try:
            from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips
            from moviepy.audio.fx import AudioFadeIn, AudioFadeOut
            import math

            output_path.parent.mkdir(parents=True, exist_ok=True)

            voice = AudioFileClip(str(voiceover_path))
            music = AudioFileClip(str(music_path))

            # Loop music to match voiceover duration
            target_duration = voice.duration
            if music.duration < target_duration:
                loops_needed = math.ceil(target_duration / music.duration)
                music = concatenate_audioclips([music] * loops_needed)
            music = music.subclipped(0, target_duration)

            # Apply volume + fades
            music = music.with_volume_scaled(music_volume)
            music = music.with_effects([AudioFadeIn(1.0), AudioFadeOut(2.0)])
            voice = voice.with_volume_scaled(voice_volume)

            # Composite
            mixed = CompositeAudioClip([voice, music])
            mixed.write_audiofile(str(output_path), fps=44100, logger=None)

            # Cleanup
            voice.close()
            music.close()
            mixed.close()
            return True

        except Exception as e:
            print(f"Audio mixing error (moviepy): {e}")
            # Fallback: just copy voiceover
            try:
                import shutil
                shutil.copy(voiceover_path, output_path)
                return True
            except:
                return False

audio_service = AudioService()
