"""Generate .ass subtitle files with word-by-word animation for video captions."""
from pathlib import Path
from typing import List, Dict
import re


def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    import subprocess
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


def generate_ass_subtitles(
    scenes: List[Dict],
    audio_assets: List[Dict],
    caption_settings: Dict,
    output_path: Path,
) -> Path:
    """Generate .ass subtitle file with word-by-word animation.

    Args:
        scenes: List of scene dicts (visual_description, narration_text, duration_seconds)
        audio_assets: List of audio asset dicts with local_path
        caption_settings: Dict with style, font, font_size, color, stroke_color, stroke_width, animation
        output_path: Where to save the .ass file

    Returns:
        Path to the .ass file
    """
    # Caption settings
    font = caption_settings.get("font", "Impact")
    font_size = caption_settings.get("font_size", 52)
    color = hex_to_ass_color(caption_settings.get("color", "#FFD700"))
    stroke_color = hex_to_ass_stroke(caption_settings.get("stroke_color", "#000000"))
    stroke_width = caption_settings.get("stroke_width", 3)
    animation = caption_settings.get("animation", "word_by_word")
    bold = -1 if caption_settings.get("style", "").startswith("bold") else 0

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
Style: Default,{font},{font_size},{color},&H000000FF,{stroke_color},&H80000000,{bold},0,0,0,100,100,0,0,1,{stroke_width},2,2,80,80,500,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Build events
    current_time = 0.0
    for i, scene in enumerate(scenes):
        narration = scene.get("narration_text", "")
        if not narration:
            continue

        # Get audio duration for this scene
        audio_path = None
        if i < len(audio_assets) and audio_assets[i].get("local_path"):
            audio_path = Path(audio_assets[i]["local_path"])
        if audio_path and audio_path.exists():
            audio_duration = get_audio_duration(audio_path)
        else:
            audio_duration = scene.get("duration_seconds", 5)

        if animation == "word_by_word":
            timings = words_with_timings(narration, audio_duration)
            for timing in timings:
                start_ts = format_ass_time(current_time + timing["start"])
                end_ts = format_ass_time(current_time + timing["end"])
                word = timing["word"].replace("\n", " ")
                # Pop-in animation: scale up briefly
                effect = "{\\fscx110\\fscy110\\t(0,80,\\fscx100\\fscy100)}"
                ass_content += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{effect}{word}\n"
        else:
            # Static caption - show whole line for duration
            start_ts = format_ass_time(current_time)
            end_ts = format_ass_time(current_time + audio_duration)
            text = narration.replace("\n", " ")
            ass_content += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}\n"

        current_time += audio_duration

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
