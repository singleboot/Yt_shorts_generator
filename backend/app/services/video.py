import os
import subprocess
import shutil
from pathlib import Path
from typing import List, Dict
from app.config import settings
import moviepy
import random


class VideoService:
    def __init__(self):
        self.width = settings.DEFAULT_WIDTH    # 1080
        self.height = settings.DEFAULT_HEIGHT  # 1920
        self.fps = settings.DEFAULT_FPS        # 30

    def assemble_video(
        self,
        scene_clips: List[Path],          # 720p t2v outputs from ComfyUI
        audio_assets: List[Dict],         # voiceover mp3s per scene
        music_path: Path,                 # background music (already mixed optional)
        scenes: List[Dict],
        caption_settings: Dict,
        output_path: Path,
        mixed_audio_path: Path = None,    # pre-mixed voice+music (if None, will mix)
        music_volume: float = 0.15,
        voice_volume: float = 1.0,
    ) -> bool:
        """Assemble final video: concat clips, mix audio, burn captions.

        New pipeline (post-t2v refactor):
        1. Upscale each 720p scene clip to 1080p (ffmpeg scale filter)
        2. Concat all scene clips (ffmpeg concat demuxer, no re-encode)
        3. Mix voiceover + music (moviepy CompositeAudioClip)
        4. Generate .ass subtitle file
        5. ffmpeg mux: video + audio + .ass subtitles → final.mp4
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            work_dir = output_path.parent / "_work"
            work_dir.mkdir(parents=True, exist_ok=True)

            # 1. Upscale each clip 720p -> 1080p
            upscaled_clips = self._upscale_clips(scene_clips, work_dir)

            # 2. Concat all upscaled clips
            raw_video = work_dir / "raw_concat.mp4"
            if not self._concat_videos(upscaled_clips, raw_video):
                return False

            # 3. Mix voiceover + music (if not already mixed)
            if mixed_audio_path is None:
                mixed_audio_path = work_dir / "mixed_audio.mp3"
                voiceover_path = self._concat_audio_assets(audio_assets, work_dir)
                if not voiceover_path or not music_path or not Path(music_path).exists():
                    # Use voiceover only
                    if voiceover_path:
                        shutil.copy(voiceover_path, mixed_audio_path)
                    else:
                        # No audio at all - just use video
                        shutil.copy(raw_video, output_path)
                        return True
                else:
                    # Mix voice + music via moviepy (synchronous wrapper)
                    from app.services.audio import audio_service
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Already in event loop - run synchronously
                            self._sync_mix_audio(voiceover_path, music_path, mixed_audio_path,
                                                 music_volume, voice_volume)
                        else:
                            loop.run_until_complete(audio_service.mix_audio(
                                voiceover_path, music_path, mixed_audio_path,
                                music_volume, voice_volume
                            ))
                    except RuntimeError:
                        self._sync_mix_audio(voiceover_path, music_path, mixed_audio_path,
                                             music_volume, voice_volume)

            # 4. Generate .ass subtitles
            from app.services.captions import generate_ass_subtitles
            ass_path = work_dir / "subtitles.ass"
            try:
                generate_ass_subtitles(
                    scenes=scenes,
                    audio_assets=audio_assets,
                    caption_settings=caption_settings,
                    output_path=ass_path,
                )
            except Exception as e:
                print(f"Subtitle generation failed (continuing without): {e}")
                ass_path = None

            # 5. Mux everything: video + audio + subtitles
            success = self._mux_final(raw_video, mixed_audio_path, ass_path, output_path)

            # Cleanup work dir
            try:
                shutil.rmtree(work_dir)
            except:
                pass

            return success

        except Exception as e:
            print(f"assemble_video error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _sync_mix_audio(self, voiceover_path, music_path, output_path,
                        music_volume, voice_volume):
        """Synchronous wrapper for moviepy audio mixing (used inside threadpool)."""
        from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips
        from moviepy.audio.fx import AudioFadeIn, AudioFadeOut
        import math

        voice = AudioFileClip(str(voiceover_path))
        music = AudioFileClip(str(music_path))
        target_duration = voice.duration

        if music.duration < target_duration:
            loops_needed = math.ceil(target_duration / music.duration)
            music = concatenate_audioclips([music] * loops_needed)
        music = music.subclipped(0, target_duration)
        music = music.with_volume_scaled(music_volume)
        music = music.with_effects([AudioFadeIn(1.0), AudioFadeOut(2.0)])
        voice = voice.with_volume_scaled(voice_volume)
        mixed = CompositeAudioClip([voice, music])
        mixed.write_audiofile(str(output_path), fps=44100, logger=None)
        voice.close()
        music.close()
        mixed.close()

    def _upscale_clips(self, clips: List[Path], work_dir: Path) -> List[Path]:
        """Upscale 720p scene clips to 1080p using ffmpeg lanczos."""
        upscaled = []
        for i, clip in enumerate(clips):
            out = work_dir / f"upscaled_{i:02d}.mp4"
            try:
                cmd = [
                    "ffmpeg", "-y", "-i", str(clip),
                    "-vf", "scale=1080:1920:flags=lanczos",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "128k",
                    "-pix_fmt", "yuv420p",
                    "-r", "30",
                    str(out)
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                upscaled.append(out)
            except subprocess.CalledProcessError as e:
                print(f"Upscale failed for {clip}, using as-is: {e}")
                upscaled.append(clip)
        return upscaled

    def _concat_videos(self, clips: List[Path], output: Path) -> bool:
        """Concatenate videos using ffmpeg concat demuxer (no re-encode if codecs match)."""
        if not clips:
            return False
        if len(clips) == 1:
            shutil.copy(clips[0], output)
            return True

        try:
            # First, re-encode all to same codec for clean concat
            concat_list = output.parent / "concat_list.txt"
            with open(concat_list, "w") as f:
                for clip in clips:
                    f.write(f"file '{clip.resolve()}'\n")

            # Re-encode to consistent format
            intermediate = output.parent / "concat_intermediate.mp4"
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                "-movflags", "+faststart",
                str(intermediate)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            shutil.move(str(intermediate), str(output))
            return True
        except subprocess.CalledProcessError as e:
            print(f"Concat failed, falling back to moviepy: {e}")
            # Fallback to moviepy
            try:
                video_clips = [moviepy.VideoFileClip(str(c)) for c in clips]
                final = moviepy.concatenate_videoclips(video_clips, method="compose")
                final.write_videofile(str(output), fps=30, codec="libx264",
                                       audio_codec="aac", logger=None)
                for vc in video_clips:
                    vc.close()
                return True
            except Exception as e2:
                print(f"moviepy fallback also failed: {e2}")
                return False

    def _concat_audio_assets(self, audio_assets: List[Dict], work_dir: Path) -> Path:
        """Concatenate per-scene voiceover files into one mp3."""
        if not audio_assets:
            return None
        if len(audio_assets) == 1:
            return Path(audio_assets[0]["local_path"])

        output = work_dir / "voiceover_full.mp3"
        try:
            inputs = []
            for asset in audio_assets:
                p = asset.get("local_path")
                if p and Path(p).exists():
                    inputs.append(str(p))
            if not inputs:
                return None

            concat_list = work_dir / "audio_concat_list.txt"
            with open(concat_list, "w") as f:
                for inp in inputs:
                    f.write(f"file '{Path(inp).resolve()}'\n")

            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(output)
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return output
        except subprocess.CalledProcessError as e:
            print(f"Audio concat failed: {e}")
            return Path(audio_assets[0]["local_path"]) if audio_assets else None

    def _mux_final(self, video: Path, audio: Path, ass_subs: Path, output: Path) -> bool:
        """Final mux: combine video, audio, and (optional) .ass subtitles."""
        try:
            if ass_subs and ass_subs.exists():
                # Use subtitles filter for .ass burn-in
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video),
                    "-i", str(audio),
                    "-vf", f"subtitles={str(ass_subs).replace(chr(92), '/')}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k",
                    "-pix_fmt", "yuv420p",
                    "-shortest",
                    "-movflags", "+faststart",
                    str(output)
                ]
            else:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video),
                    "-i", str(audio),
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    "-movflags", "+faststart",
                    str(output)
                ]
            subprocess.run(cmd, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Final mux failed: {e.stderr.decode() if e.stderr else e}")
            # Fallback: copy video + try just audio merge
            try:
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(video),
                    "-i", str(audio),
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    str(output)
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                return True
            except Exception as e2:
                print(f"Fallback mux also failed: {e2}")
                return False

    def create_thumbnail(self, video_path: Path, output_path: Path, text: str = "") -> bool:
        """Create a thumbnail from the first frame of the video."""
        try:
            clip = moviepy.VideoFileClip(str(video_path))
            frame = clip.get_frame(0.5)
            from PIL import Image
            img = Image.fromarray(frame)
            img.save(str(output_path))
            clip.close()
            return True
        except Exception as e:
            print(f"Thumbnail error: {e}")
            return False


video_service = VideoService()
