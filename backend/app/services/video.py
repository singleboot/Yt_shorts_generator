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
        target_width: int = 1080,         # final video width (was hardcoded 1080)
        target_height: int = 1920,        # final video height (was hardcoded 1920)
        transition_style: str = "none",   # ffmpeg xfade transition (or "none")
        transition_duration: float = 0.0, # seconds trimmed from each cut
        audio_transition: str = "match_video",  # "match_video" | "none"
    ) -> bool:
        """Assemble final video: concat clips, mix audio, burn captions.

        New pipeline (post-t2v refactor):
        1. Upscale each scene clip to (target_w x target_h) (ffmpeg scale filter)
        2. Concat all scene clips with optional xfade transitions
        3. Mix voiceover + music (moviepy CompositeAudioClip)
        4. Generate .ass subtitle file (transition_duration-aware timeline)
        5. ffmpeg mux: video + audio + .ass subtitles → final.mp4

        target_w/target_h: per-project aspect ratio from visual_settings.
            vertical=720x1280, horizontal=1280x720, horizontal_hd=1920x1080.
        transition_style: one of the values in config.TRANSITION_STYLES, or "none".
            "none" preserves the original hard-cut behavior (fast, no re-encode).
        transition_duration: 0.0-1.5 seconds. Trimmed from each scene's
            audio start (except the last). Total output duration =
            sum(scene_durations) - (N-1) * transition_duration.
        audio_transition: "match_video" applies acrossfade to voiceover +
            music in lockstep with the video transition; "none" hard-cuts audio.
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            work_dir = output_path.parent / "_work"
            work_dir.mkdir(parents=True, exist_ok=True)

            # 1. Upscale each clip to (target_w x target_h)
            upscaled_clips = self._upscale_clips(scene_clips, work_dir, target_width, target_height)

            # 2. Concat all upscaled clips (with optional xfade transitions)
            raw_video = work_dir / "raw_concat.mp4"
            if not self._concat_videos(
                upscaled_clips, raw_video,
                transition_style=transition_style,
                transition_duration=transition_duration,
                audio_assets=audio_assets,
                audio_transition=audio_transition,
            ):
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
                    transition_duration=transition_duration,
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

    def _upscale_clips(self, clips: List[Path], work_dir: Path,
                       target_w: int = 1080, target_h: int = 1920) -> List[Path]:
        """Upscale scene clips to (target_w x target_h) using ffmpeg lanczos.

        Honors any aspect ratio - 720x1280 (vertical Shorts), 1280x720
        (horizontal LD), 1920x1080 (horizontal HD). The hardcoded 1080:1920
        was correct only for vertical Shorts and broke horizontal projects.
        """
        upscaled = []
        for i, clip in enumerate(clips):
            out = work_dir / f"upscaled_{i:02d}.mp4"
            try:
                cmd = [
                    "ffmpeg", "-y", "-i", str(clip),
                    "-vf", f"scale={target_w}:{target_h}:flags=lanczos",
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

    def _concat_videos(
        self,
        clips: List[Path],
        output: Path,
        transition_style: str = "none",
        transition_duration: float = 0.0,
        audio_assets: List[Dict] = None,
        audio_transition: str = "match_video",
    ) -> bool:
        """Concatenate videos, optionally with ffmpeg xfade transitions.

        transition_style == "none" (the default and the 99% case for projects
        that haven't opted into transitions): use the original ffmpeg concat
        demuxer path - no re-encode, no extra cost, no risk.

        Otherwise: build an N-1 xfade filter graph chained across all clips,
        with acrossfade on the audio in lockstep. Output is re-encoded once
        (libx264) which is the only way to do transitions. Total output
        duration = sum(scene_durations) - (N-1) * transition_duration.

        Validation: if transition_duration >= min(scene_duration * 0.5) the
        transition would eat more than half the shortest scene. We clamp
        to 0.4 * min(scene_duration) and log a warning.
        """
        if not clips:
            return False
        if len(clips) == 1:
            shutil.copy(clips[0], output)
            return True

        # If no transitions requested, use the original fast path.
        if transition_style == "none" or transition_duration <= 0.0:
            return self._concat_hardcut(clips, output)

        # Validate transition_duration is sane for the shortest clip.
        try:
            durations = [self._get_duration(c) for c in clips]
            min_dur = min(d for d in durations if d > 0)
            if transition_duration >= min_dur * 0.5:
                old = transition_duration
                transition_duration = round(min_dur * 0.4, 3)
                print(f"[concat] transition_duration {old}s too long for shortest clip "
                      f"({min_dur:.2f}s), clamping to {transition_duration}s", flush=True)
        except Exception as e:
            print(f"[concat] duration probe failed, using requested transition_duration: {e}", flush=True)

        return self._concat_with_xfade(
            clips, output, transition_style, transition_duration,
            audio_assets or [], audio_transition
        )

    def _concat_hardcut(self, clips: List[Path], output: Path) -> bool:
        """Original concat demuxer path (no transitions)."""
        try:
            concat_list = output.parent / "concat_list.txt"
            with open(concat_list, "w") as f:
                for clip in clips:
                    f.write(f"file '{clip.resolve()}'\n")

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

    def _concat_with_xfade(
        self,
        clips: List[Path],
        output: Path,
        transition_style: str,
        transition_duration: float,
        audio_assets: List[Dict],
        audio_transition: str,
    ) -> bool:
        """Build ffmpeg xfade filter graph for N clips with chained transitions.

        For N clips, the filter graph is:
            [0][1]xfade=transition=T:d=D:offset=O0[v01];
            [v01][2]xfade=transition=T:d=D:offset=O1[v012];
            ...
        where O_i = sum(durations[0..i+1]) - transition_duration.

        Audio is either acrossfaded in lockstep (audio_transition="match_video")
        or passed through unchanged ("none"). Either way the voice lines
        end up on the same timeline as the visuals because we trim the
        transition_duration from the offset.

        On any failure we fall back to the hardcut path and log a warning.
        """
        try:
            # Resolve ffmpeg transition name from project setting
            xfade_name = settings.TRANSITION_STYLES.get(transition_style)
            if not xfade_name:
                print(f"[concat] Unknown transition_style '{transition_style}', falling back to hardcut")
                return self._concat_hardcut(clips, output)

            # Probe each clip's duration for offset math
            durations = []
            for c in clips:
                d = self._get_duration(c)
                durations.append(d if d > 0 else 6.0)  # fallback to 6s if probe fails

            n = len(clips)
            td = transition_duration

            # Build video filter graph
            video_filters = []
            # Cumulative offset starts at durations[0] - td (the first scene's
            # end, minus the transition that will overlap into scene 2).
            cumulative = durations[0] - td
            for i in range(1, n):
                v_in = f"v{i-1}{i}" if i > 1 else "v01"
                v_out = f"v{i}{i+1}" if i < n - 1 else "vout"
                video_filters.append(
                    f"[{v_in}][{i}:v]xfade=transition={xfade_name}:duration={td}:offset={cumulative:.3f}[{v_out}]"
                )
                if i < n - 1:
                    cumulative += durations[i] - td
                # last iteration: cumulative is the total output duration, not used further

            video_filter_str = ";\n".join(video_filters)

            # Build audio filter graph
            audio_filter_str = ""
            if audio_transition == "match_video" and audio_assets:
                # Collect voiceover paths; only build acrossfade graph for those that exist
                voice_paths = []
                for asset in audio_assets:
                    p = asset.get("local_path") or asset.get("path")
                    if p and Path(p).exists():
                        voice_paths.append(str(p))
                if len(voice_paths) == len(clips):
                    af = []
                    cumulative_a = durations[0] - td
                    for i in range(1, n):
                        a_in = f"a{i-1}{i}" if i > 1 else "a01"
                        a_out = f"a{i}{i+1}" if i < n - 1 else "aout"
                        af.append(
                            f"[{a_in}][{i}:a]acrossfade=d={td}:c1=tri:c2=tri[{a_out}]"
                        )
                        if i < n - 1:
                            cumulative_a += durations[i] - td
                    audio_filter_str = ";\n".join(af)
                else:
                    # Some voiceovers missing - just pass audio through unfiltered
                    print(f"[concat] voiceover count mismatch (have {len(voice_paths)} for {len(clips)} clips), skipping audio crossfade")
            elif audio_transition == "none" or not audio_assets:
                # Use voiceover concatenation later (audio_service), skip here
                pass

            # Build ffmpeg input args (with explicit -i for each clip)
            cmd = ["ffmpeg", "-y"]
            for c in clips:
                cmd.extend(["-i", str(c)])
            filter_complex = f"-filter_complex \"{video_filter_str}"
            if audio_filter_str:
                filter_complex += f";\n{audio_filter_str}"
            filter_complex += "\""
            cmd.extend(filter_complex.split())
            # Map final video + audio (if filter graph has audio)
            cmd.extend(["-map", "[vout]"])
            if audio_filter_str:
                cmd.extend(["-map", "[aout]"])
            else:
                # No audio filter - take audio from first clip via stream copy
                cmd.extend(["-map", "0:a?"])
            cmd.extend([
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                "-movflags", "+faststart",
                "-shortest",
                str(output)
            ])

            print(f"[concat] Building xfade graph for {n} clips, transition={xfade_name} td={td}s", flush=True)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[concat] xfade failed: {result.stderr[:500]}", flush=True)
                print(f"[concat] Falling back to hardcut", flush=True)
                return self._concat_hardcut(clips, output)
            return True
        except Exception as e:
            print(f"[concat] xfade exception: {e}, falling back to hardcut", flush=True)
            return self._concat_hardcut(clips, output)

    def _get_duration(self, clip: Path) -> float:
        """Get video clip duration in seconds using ffprobe. Returns 0.0 on failure."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(clip)],
                capture_output=True, text=True, timeout=10
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

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
