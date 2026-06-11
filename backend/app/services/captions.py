"""Generate .ass subtitle files with word-by-word animation for video captions."""
from pathlib import Path
from typing import List, Dict
import re


def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    import subprocess
    from app.services.video import _ensure_ffmpeg_on_path_once
    _ensure_ffmpeg_on_path_once()
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"ffprobe failed for {audio_path}: {e}")
        return 5.0  # fallback


def words_with_timings(narration_text: str, audio_duration: float) -> List[Dict]:
    """Distribute words evenly across audio duration."""
    words = re.findall(r"\S+", narration_text)
    if not words:
        return []
    word_duration = audio_duration / len(words)
    timings = []
    for i, word in enumerate(words):
        start = i * word_duration
        end = (i + 1) * word_duration
        timings.append({"word": word, "start": start, "end": end})
    return timings


def hex_to_ass_color(hex_color: str) -> str:
    """Convert #RRGGBB to ASS &HBBGGRR format."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "&H00FFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H00{b}{g}{r}".upper()


def hex_to_ass_stroke(hex_color: str) -> str:
    """Convert stroke color to ASS format."""
    return hex_to_ass_color(hex_color)


def hex_to_ass_bg_color(hex_color: str, opacity: float) -> str:
    """Convert hex color (#RRGGBB) and opacity (0.0 to 1.0) to ASS &HAABBGGRR format."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        # Fallback to 80% transparent black
        return "&HCC000000"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    alpha = int(round((1.0 - opacity) * 255))
    alpha = max(0, min(255, alpha))
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def generate_ass_subtitles(
    scenes: List[Dict],
    audio_assets: List[Dict],
    caption_settings: Dict,
    output_path: Path,
    transition_duration: float = 0.0,
    scene_clips: List[Path] = None,
) -> Path:
    """Generate .ass subtitle file with word-by-word animation.

    Args:
        scenes: List of scene dicts (visual_description, narration_text, duration_seconds)
        audio_assets: List of audio asset dicts with local_path
        caption_settings: Dict with style, font, font_size, color, stroke_color, stroke_width, animation
        output_path: Where to save the .ass file
        transition_duration: Seconds trimmed from each scene's audio start
            when transitions are applied. The video timeline = audio_timeline -
            (i * transition_duration) for scene i, so captions must match
            that math exactly. Pass 0.0 for hard-cut (no transition) projects.

    Returns:
        Path to the .ass subtitle file
    """
    # Caption settings
    font = caption_settings.get("font", "Impact")
    base_height = caption_settings.get("base_resolution_height", 1280)
    raw_size = caption_settings.get("font_size", 96)
    scaled_size = int(round(raw_size * (base_height / 1280.0)))
    font_size = max(20, min(300, scaled_size))
    color = hex_to_ass_color(caption_settings.get("color", "#FFD700"))
    stroke_color = hex_to_ass_stroke(caption_settings.get("stroke_color", "#000000"))
    stroke_width = caption_settings.get("stroke_width", 3)
    animation = caption_settings.get("animation", "word_by_word")
    all_caps = caption_settings.get("all_caps", False)

    box_color_hex = caption_settings.get("box_color", "#000000")
    box_opacity = float(caption_settings.get("box_opacity", 0.8) if caption_settings.get("box_opacity") is not None else 0.8)
    box_shape = caption_settings.get("box_shape", "rectangle")

    back_color = hex_to_ass_bg_color(box_color_hex, box_opacity)
    underline = -1 if box_shape == "underline" else 0

    # Caption style configuration
    style = caption_settings.get("style", "standard")
    
    # 1. Bold setting
    bold = -1 if (style == "bold" or caption_settings.get("style", "").startswith("bold")) else 0
    
    # 2. Border Style: 3 is opaque background box, 1 is standard outline
    border_style = 3 if (style == "boxed" or caption_settings.get("boxed", False)) else 1
    
    # 3. Outline width: thin for minimal, custom otherwise. For boxed style (border_style=3),
    # we need a positive outline width to render the background box.
    if border_style == 3:
        outline_width = max(3, stroke_width)
    else:
        outline_width = min(1, stroke_width) if style == "minimal" else stroke_width
    
    # 4. Shadow offset: none for minimal/boxed, 2 otherwise
    shadow_offset = 0 if (style in ("minimal", "boxed") or caption_settings.get("boxed", False)) else 2
    
    # 5. Colors mapping
    # For karaoke, PrimaryColour is active color, SecondaryColour is inactive base (white/grey).
    # For typewriter, SecondaryColour is transparent (&HFFFFFFFF).
    primary_color = color
    secondary_color = "&H00FFFFFF"
    if animation == "typewriter":
        secondary_color = "&HFFFFFFFF"
    elif style == "karaoke" or animation == "karaoke":
        secondary_color = "&H00FFFFFF"

    # 6. Alignment & Position mapping (Standard ASS layout)
    position = caption_settings.get("position", "middle")
    alignment = 5  # Always anchor to the middle-center of the pos coordinate box
    x_pos = 540
    if position == "top":
        y_pos = 380
    elif position == "bottom":
        y_pos = 1540
    else:  # middle
        y_pos = 960

    # ASS Header
    ass_content = f"""[Script Info]
Title: AI Shorts Captions
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary_color},{secondary_color},{stroke_color},{back_color},{bold},0,{underline},0,100,100,0,0,{border_style},{outline_width},{shadow_offset},{alignment},80,80,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Build events
    current_time = 0.0
    for i, scene in enumerate(scenes):
        narration = scene.get("narration_text", "")
        if all_caps:
            narration = narration.upper()
        if not narration:
            continue

        # Speech duration is the actual voiceover audio duration (unpadded)
        audio_path = None
        if i < len(audio_assets) and audio_assets[i].get("local_path"):
            audio_path = Path(audio_assets[i]["local_path"])
        if audio_path and audio_path.exists():
            speech_duration = get_audio_duration(audio_path)
        else:
            speech_duration = float(scene.get("duration_seconds", 6) or 6)

        scene_duration = float(scene.get("duration_seconds", 6) or 6)
        if scene_clips and i < len(scene_clips) and scene_clips[i] and Path(scene_clips[i]).exists():
            try:
                actual_vid_dur = get_audio_duration(Path(scene_clips[i]))
                if actual_vid_dur > 0:
                    scene_duration = actual_vid_dur
            except Exception:
                pass
        speech_duration = min(speech_duration, scene_duration)

        # Check if sidecar JSON exists
        json_path = audio_path.with_suffix(".json") if audio_path else None
        precise_timings = None
        if json_path and json_path.exists():
            try:
                import json as _json
                with open(str(json_path), "r", encoding="utf-8") as jf:
                    precise_timings = _json.load(jf)
                if not isinstance(precise_timings, list) or not precise_timings:
                    precise_timings = None
            except Exception as je:
                print(f"Failed to read sidecar JSON {json_path}: {je}")
                precise_timings = None

        if precise_timings is not None:
            timings = []
            for item in precise_timings:
                w_start = min(float(item.get("start", 0.0)), speech_duration)
                w_end = min(float(item.get("end", 0.0)), speech_duration)
                word = item.get("word", "")
                if all_caps:
                    word = word.upper()
                timings.append({"word": word, "start": w_start, "end": w_end})
        else:
            timings = words_with_timings(narration, speech_duration)

        # Apply different animation logic
        if animation in ("word_by_word", "pop") or (animation == "fade" and style not in ("karaoke", "boxed")):
            for timing in timings:
                start_ts = format_ass_time(current_time + timing["start"])
                end_ts = format_ass_time(current_time + timing["end"])
                word = timing["word"].replace("\n", " ")
                
                # Apply word effect
                if animation == "pop":
                    effect = "{\\fscx120\\fscy120\\t(0,100,\\fscx100\\fscy100)}"
                elif animation == "fade":
                    effect = "{\\fad(80,80)}"
                else:
                    effect = "{\\fscx110\\fscy110\\t(0,80,\\fscx100\\fscy100)}"
                ass_content += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{{\\pos({x_pos},{y_pos})}}{effect}{word}\n"
        elif style == "karaoke" or animation in ("karaoke", "typewriter"):
            # Karaoke / Typewriter highlighting
            if timings:
                dialogue_text = ""
                prev_end = 0.0
                for timing in timings:
                    w_start = timing["start"]
                    w_end = timing["end"]
                    word = timing["word"].replace("\n", " ")
                    gap = w_start - prev_end
                    if gap > 0.01:
                        gap_cs = int(round(gap * 100))
                        dialogue_text += f"{{\\K{gap_cs}}}"
                    dur_cs = int(round((w_end - w_start) * 100))
                    dur_cs = max(1, dur_cs)
                    dialogue_text += f"{{\\K{dur_cs}}}{word} "
                    prev_end = w_end
                
                start_ts = format_ass_time(current_time)
                end_ts = format_ass_time(current_time + speech_duration)
                fade_prefix = "\\fad(200,200)" if animation == "fade" else ""
                # Mux pos tag and fade prefix inside one tag block
                tag_block = f"\\pos({x_pos},{y_pos})"
                if fade_prefix:
                    tag_block += f"|{fade_prefix}"
                tag_block = "{" + tag_block.replace("|", "") + "}"
                ass_content += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{tag_block}{dialogue_text.strip()}\n"
        else:
            # Static caption - show whole line for duration
            start_ts = format_ass_time(current_time)
            end_ts = format_ass_time(current_time + speech_duration)
            text = narration.replace("\n", " ")
            fade_prefix = "\\fad(200,200)" if animation == "fade" else ""
            tag_block = f"\\pos({x_pos},{y_pos})"
            if fade_prefix:
                tag_block += f"|{fade_prefix}"
            tag_block = "{" + tag_block.replace("|", "") + "}"
            ass_content += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{tag_block}{text}\n"

        # Advance the timeline by the scene's visual duration instead of the audio file's duration.
        # This keeps the subtitles aligned with the scene cuts.
        if i < len(scenes) - 1:
            current_time += max(0.0, scene_duration - transition_duration)
        else:
            current_time += scene_duration

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(ass_content, encoding="utf-8")
    return output_path


def format_ass_time(seconds: float) -> str:
    """Format seconds as H:MM:SS.cc (ASS time format)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"
