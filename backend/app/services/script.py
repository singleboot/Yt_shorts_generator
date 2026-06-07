import json
from typing import List, Dict
from app.config import settings
from app.services.research import research_service

SPEAKER_MAP = {
    "aiden":    ("Aiden",    "Male"),
    "dylan":    ("Dylan",    "Male"),
    "eric":     ("Eric",     "Male"),
    "ono_anna": ("Ono Anna", "Female"),
    "ryan":     ("Ryan",     "Male"),
    "serena":   ("Serena",   "Female"),
    "sohee":    ("Sohee",    "Female"),
    "uncle_fu": ("Uncle Fu", "Male"),
    "vivian":   ("Vivian",   "Female"),
}
SPEAKER_DEFAULT = ("Ryan", "Male")

GENRE_HINTS = {
    "Ambient": "Use calm, atmospheric, slow-moving background music with soft pads and gentle textures.",
    "Upbeat":  "Use high-energy, fast-tempo, positive music with driving rhythm and major-key melodies.",
    "Epic":    "Use grand, cinematic orchestral music with rising brass, powerful drums, and heroic themes.",
    "Lo-fi":   "Use chill lo-fi hip-hop beats with jazzy chords, vinyl crackle, and a relaxed groove.",
    "Cinematic": "Use cinematic, sweeping orchestral score with emotional dynamics and orchestral swells.",
    "Corporate": "Use clean, modern, upbeat corporate music with synth elements — motivational and professional.",
    "None":    "Do not reference any specific music style; the video will be generated without background music.",
}

class ScriptService:
    def __init__(self):
        self.ollama_host = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_MODEL

    def _resolve_speaker(self, voice_id: str = None, voice_custom: str = None):
        if not voice_id:
            return SPEAKER_DEFAULT
        vid = voice_id.lower().strip()
        # "__custom__" means user typed their own description
        if vid == "__custom__" and voice_custom:
            return (f'Custom voice: "{voice_custom}"', "Custom")
        # Handle Azure-style names like "en-US-AriaNeural"
        AZURE_MAP = {
            "en-us-arianeural":   "aiden",
            "en-us-guyneural":    "dylan",
            "en-us-jessicaneural": "sohee",
            "en-us-amberneural":  "vivian",
        }
        vid = AZURE_MAP.get(vid, vid)
        return SPEAKER_MAP.get(vid, SPEAKER_DEFAULT)

    async def generate_script(self, topic: str, category: str, context: str,
                              duration: int = 45, style: str = "engaging",
                              voice_id: str = None, music_genre: str = None,
                              voice_custom: str = None, music_custom: str = None) -> Dict:
        """Generate a full script with scenes using Ollama."""

        if duration <= 30:
            num_scenes = 5
            per_scene = 6
        elif duration <= 45:
            num_scenes = 7
            per_scene = 6
        elif duration <= 60:
            num_scenes = 10
            per_scene = 6
        elif duration <= 90:
            num_scenes = 15
            per_scene = 6
        else:
            num_scenes = 20
            per_scene = 6

        # Category-specific tone instructions
        if category.lower() in ("history", "historical"):
            category_instruction = "This is a HISTORY video. Write a historical narrative about the subject — origins, key events, evolution over time, historical significance. NOT a contemporary/modern description."
        elif category.lower() in ("children story", "children's story", "kids story", "kids", "children"):
            category_instruction = "This is a CHILDREN'S STORY. Write a whimsical, age-appropriate story with simple language, fun characters, clear moral/lesson, and imaginative scenes. NOT a factual documentary."
        elif category.lower() in ("science", "technology", "tech"):
            category_instruction = "This is a SCIENCE/TECH video. Explain the concept in an accessible, fascinating way with clear cause-effect and wonder-inducing facts."
        elif category.lower() in ("sports", "sport"):
            category_instruction = "This is a SPORTS video. Write with high energy, focus on epic moments, athlete achievements, records, and game-defining plays."
        elif category.lower() in ("entertainment", "celebrity", "pop culture"):
            category_instruction = "This is an ENTERTAINMENT video. Write a fast-paced, gossipy, pop-culture style piece with surprising reveals and hype."
        else:
            category_instruction = "Write a general engaging YouTube Shorts script appropriate for the subject."

        # Resolve speaker for the prompt
        speaker_name, speaker_gender = self._resolve_speaker(voice_id, voice_custom)
        # Determine effective music label
        if (music_genre or "").lower() == "__custom__" and music_custom:
            music_label = f'Custom: "{music_custom}"'
            music_hint = f"Use music matching this custom description: {music_custom}"
        else:
            music_label = (music_genre or "ambient").capitalize()
            music_hint = GENRE_HINTS.get(music_label, f"Use {music_label} style music.")
        if speaker_gender == "Custom":
            gender_note = ""
        elif speaker_gender == "Female":
            gender_note = "Consider the female voice talent when choosing tone and phrasing."
        else:
            gender_note = "Consider the male voice talent when choosing tone and phrasing."

        system_prompt = f"""You are an expert YouTube Shorts scriptwriter AND cinematographer. You create scripts that:
- Hook viewers in the first 3 seconds
- Are factually accurate based on provided research
- Are optimized for {duration}-second vertical (9:16) videos
- Have scenes whose visuals DIRECTLY ILLUSTRATE the spoken narration
- Use a conversational, energetic narration tone
- Each scene's narration must fit within 8-10 seconds of speaking time

{category_instruction}

CRITICAL — VISUAL DESCRIPTIONS FOR LTX 2.3 T2V:
The visual_description for each scene is fed directly into a 6-second text-to-video AI (LTX 2.3) that renders ONE short clip per scene. The model has very specific strengths and weaknesses:

CAN render well:
- A single specific subject in a specific location (e.g., "a tall cathedral in a quiet mountain village at dawn")
- One clear action or pose (a player kicking, hands gripping a trophy, a person looking up)
- One camera move per scene (slow push-in, slow pan, dolly forward, gentle zoom, static wide shot, slow orbit)
- Specific lighting/mood (golden hour, overcast, floodlit, candlelit, neon-lit)
- One clear foreground subject and a blurred background

CANNOT render well — DO NOT USE:
- "Montage", "collage", "split screen", "transition to", "cut to", "fade to black", "dissolve"
- "Calendar flipping", "time passing", "decades of history", abstract metaphors
- Multiple unrelated subjects in one frame (e.g., "players, fans, referees, and politicians all in one shot")
- Photo/film/documentary effects ("archival black and white", "8mm film grain", "vintage filter") — these produce inconsistent results
- Heavy text overlays, logos, on-screen graphics
- People doing complex choreographed actions (dance routines, full football matches)

EVERY visual_description must follow this template:
"[Camera move] of [single specific subject] in [specific location/setting], [doing one clear action or held pose], [lighting], [mood/style], [any style LoRA triggers if relevant], high detail, cinematic, 9:16 vertical"

GOOD visual_description examples:
- "Slow push-in on a lone football player standing at the center spot of a floodlit stadium pitch at twilight, head bowed, ball at his feet, dramatic backlight, cinematic mood, 9:16 vertical, high detail"
- "Slow orbit around an ancient leather football resting on dewy grass with morning light filtering through, shallow depth of field, warm golden tones, 9:16 vertical"
- "Static wide shot of a roaring stadium crowd holding scarves aloft under bright floodlights, confetti mid-air, vibrant high-contrast color, cinematic 9:16 vertical"

BAD visual_description examples (NEVER do this):
- "Montage of historical football moments"  ← abstract montage
- "Calendar pages flipping rapidly through the decades"  ← abstract metaphor
- "Archival black and white photos showing early football"  ← effect LTX can't reproduce
- "A player scores, fans cheer, commentators shout"  ← too many subjects/actions
- "Dramatic zoom with cinematic fade to black"  ← fade effect impossible

NARRATIVE ARC REQUIREMENTS:
- The first scene must visually establish the HOOK of the story (the most striking image that makes viewers want to watch)
- The middle scenes (3-8) should each introduce ONE new visual element that builds on the previous (e.g., start with empty pitch → players appear → crowd → trophy)
- The SECOND-TO-LAST scene (scene N-1) should be the CLIMAX — the most visually dramatic moment
- The FINAL scene (scene {num_scenes}) MUST be a deliberate CLOSING SHOT:
  * A wide, slow, contemplative shot that visually summarizes the story
  * A subject returning to a calm, resolved state (empty pitch, lone figure, sunset over the setting)
  * The narration should be a reflective conclusion that matches the closing image
  * This scene's pacing should feel like a slow exhale — slow camera, minimal motion, warm/soft light
  * Visual example: "Slow wide shot of a single football resting on the center spot of an empty stadium at sunset, camera holds still, golden light, contemplative mood, 9:16 vertical, cinematic"

VISUAL CONTINUITY:
- Reuse 2-3 key visual anchors across scenes (e.g., the same stadium, the same ball, the same time-of-day) so the video feels like one continuous story
- Vary the camera move per scene (push-in, pan, orbit, static, dolly) for visual rhythm
- Keep the lighting palette consistent (don't jump from noon to night randomly)
"""

        prompt = f"""Write a YouTube Shorts script about: {topic}
Category: {category}
Target Duration: {duration} seconds
Style: {style}
Selected Voice: {speaker_name} ({speaker_gender}, English) — {gender_note}
Music Genre: {music_label} — {music_hint}

Research Context:
{context}

Requirements:
1. HOOK: The first 3 seconds must grab attention with a striking question, surprising fact, or bold claim
2. SCENES: Include EXACTLY {num_scenes} scenes, each {per_scene} seconds (total ~{duration}s). Each scene must have:
   - scene_number (1 to {num_scenes})
   - visual_description (FOLLOW THE TEMPLATE IN SYSTEM PROMPT — single subject, one action, one camera move, specific lighting; NEVER use montage/calendar/archival/etc.)
   - narration_text (MAX 18-22 words, ~6 seconds spoken)
   - duration_seconds ({per_scene})
3. VISUAL CONTINUITY: Pick 2-3 recurring visual anchors (e.g., "stadium at twilight", "vintage leather ball", "lone player") and use them across multiple scenes
4. CAMERA VARIETY: Each scene must use a DIFFERENT camera move from this set: slow push-in, slow pan, slow dolly forward, slow orbit, slow zoom, static wide, slow tilt up
5. CLIMAX: Scene {num_scenes - 1} must be visually the most dramatic (e.g., a goal scored, a trophy lifted, a crowd erupting)
6. CLOSING SHOT: Scene {num_scenes} MUST be a deliberate, slow, contemplative closing shot — wide, calm, warm, with minimal motion. The narration should be a reflective wrap-up, not a call-to-action. Save the call-to-action for the LAST LINE of narration_text in scene {num_scenes} (after the reflective thought).
7. Also generate:
   - title: catchy, max 60 chars
   - description: 2-sentence summary
   - hashtags: 10 relevant hashtags
   - call_to_action: short (e.g., "Like and subscribe for more!")
   - music_prompt: comma-separated ACE 1.5 music description (genre, mood, instruments, BPM, key). Example for "Epic": "epic, cinematic, orchestral, dramatic, powerful, 100 BPM, E minor"

Respond ONLY in valid JSON. No markdown, no commentary, no code blocks — just raw JSON:

{{
  "title": "...",
  "description": "...",
  "hashtags": ["#tag1", "#tag2", ...],
  "hook": "...",
  "scenes": [
    {{"scene_number": 1, "visual_description": "Slow push-in on ...", "narration_text": "...", "duration_seconds": {per_scene}}},
    {{"scene_number": 2, "visual_description": "Slow pan across ...", "narration_text": "...", "duration_seconds": {per_scene}}},
    ...
    {{"scene_number": {num_scenes - 1}, "visual_description": "Fast push-in on the climactic moment ...", "narration_text": "...", "duration_seconds": {per_scene}}},
    {{"scene_number": {num_scenes}, "visual_description": "Slow wide shot of ... contemplative closing image", "narration_text": "Reflective conclusion. Like and subscribe for more!", "duration_seconds": {per_scene}}}
  ],
  "call_to_action": "Like and subscribe for more!",
  "music_prompt": "genre, mood, instruments, BPM, key"
}}"""

        response = await research_service._ollama_generate(prompt, system_prompt)
        
        # Try to parse JSON from response
        try:
            # Sometimes LLM wraps in markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            script_data = json.loads(response)
            return script_data
        except json.JSONDecodeError:
            # Fallback: return raw text structured manually
            return self._fallback_parse_script(response, topic)
    
    async def split_script_into_scenes(self, script_text: str) -> List[Dict]:
        """Split an existing script into scenes."""
        prompt = f"""Split the following script into 4-6 visual scenes.
For each scene, provide:
- visual_description: detailed description for finding stock footage
- narration_text: the voiceover text for that scene
- duration_seconds: estimated time

Script:
{script_text}

Respond in JSON array format."""
        
        response = await research_service._ollama_generate(prompt)
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            return json.loads(response)
        except:
            return [{"scene_number": 1, "visual_description": script_text, "narration_text": script_text, "duration_seconds": 45}]
    
    async def generate_seo_metadata(self, topic: str, category: str, script_content: str) -> Dict:
        """Generate YouTube SEO metadata."""
        prompt = f"""Generate SEO-optimized YouTube metadata for this Shorts video:
Topic: {topic}
Category: {category}
Script: {script_content[:2000]}

Create:
1. Title: catchy, includes keywords, under 60 characters
2. Description: 2-3 sentences with keywords and call-to-action
3. Tags: 15 relevant tags (comma separated)
4. Hashtags: 10 trending hashtags

Respond in JSON format with keys: title, description, tags, hashtags"""
        
        response = await research_service._ollama_generate(prompt)
        try:
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            return json.loads(response)
        except:
            return {
                "title": f"Amazing Facts About {topic}",
                "description": f"Discover amazing facts about {topic}. Like and subscribe for more!",
                "tags": topic.split() + [category, "shorts", "facts"],
                "hashtags": ["#shorts", "#facts", f"#{category}", "#viral", "#trending"]
            }
    
    def _fallback_parse_script(self, text: str, topic: str) -> Dict:
        """Fallback if JSON parsing fails."""
        lines = text.strip().split('\n')
        return {
            "title": topic,
            "description": f"Learn about {topic} in this amazing short video!",
            "hashtags": ["#shorts", f"#{topic.replace(' ', '')}", "#facts"],
            "hook": lines[0] if lines else topic,
            "scenes": [
                {"scene_number": 1, "visual_description": topic, "narration_text": text, "duration_seconds": 45}
            ],
            "call_to_action": "Like and subscribe for more!"
        }

script_service = ScriptService()
