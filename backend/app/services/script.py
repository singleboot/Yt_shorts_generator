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
    "kokoro-af_heart": ("Kokoro Heart", "Female"),
    "kokoro-af_bella": ("Kokoro Bella", "Female"),
    "kokoro-af_nicole": ("Kokoro Nicole", "Female"),
    "kokoro-af_sarah": ("Kokoro Sarah", "Female"),
    "kokoro-af_sky": ("Kokoro Sky", "Female"),
    "kokoro-am_adam": ("Kokoro Adam", "Male"),
    "kokoro-am_fenrir": ("Kokoro Fenrir", "Male"),
    "kokoro-am_puck": ("Kokoro Puck", "Male"),
    "kokoro-bf_emma": ("Kokoro Emma", "Female"),
    "kokoro-bm_george": ("Kokoro George", "Male"),
}
SPEAKER_DEFAULT = ("Kokoro Adam", "Male")

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
                              voice_custom: str = None, music_custom: str = None,
                              prev_scripts_context: str = "",
                              is_vlog: bool = False) -> Dict:
        """Generate a full script with scenes using Ollama."""

        # Scene pacing. The user's requested total duration is split into:
        #   - AI scene content: round(effective_duration / per_scene) scenes
        #   - Outro: 6s (added by video.py after this script is built)
        #
        # per_scene changes with the requested duration so long-form
        # videos get longer scenes (8s for 180s, 10s for 300s) - the 4-act
        # narrative structure breathes better that way.
        #
        # Cap at 30 scenes to keep the LLM JSON output under ~10K tokens;
        # some 7B/8B Ollama models cap output at 8K and will silently
        # truncate a 50-scene response.
        #
        # OUTRO RESERVE: video.py appends a 6s "like & subscribe" outro to
        # the final video. We subtract that here so the AI content fills
        # (duration - 6)s and the final video is still the user-requested
        # total. Floor at 6s of AI content so we always have at least one
        # meaningful scene.
        from app.config import settings as _settings
        outro_seconds = getattr(_settings, "OUTRO_DURATION_SECONDS", 0) or 0
        effective_duration = max(duration - outro_seconds, 6)

        # Per-scene pacing by length. The 4-act long-form structure (>=180s)
        # uses longer scenes.
        if effective_duration <= 120:
            per_scene = 6
        elif effective_duration <= 180:
            per_scene = 8
        else:
            per_scene = 10

        # Compute num_scenes so the AI content exactly fills effective_duration.
        # Cap at 30 to keep the LLM prompt small. Never less than 1.
        num_scenes = max(1, min(30, round(effective_duration / per_scene)))

        long_form = duration >= 180

        # Narration word budget scales with per_scene. ~3.0-3.5 words/sec spoken.
        # This replaces the hardcoded "MAX 18-22 words" rule.
        narration_min = int(per_scene * 3.0)
        narration_max = int(per_scene * 3.5)

        # Category-specific tone instructions
        if category.lower() in ("history", "historical"):
            category_instruction = (
                "This is a HISTORY video. You MUST write a historical narrative about the subject. "
                "Frame the topic with rich historical context: cover the origins, compare past history to the present "
                "(e.g., contrast past eras, historical milestones, or past records with the subject), "
                "detail key historical events, evolution over time, and its historical significance. "
                "CRITICAL FOR HISTORY TONE:\n"
                "- Do NOT write a purely contemporary news-style description, current qualifiers breakdown, or modern overview.\n"
                "- At least 70% of the narration MUST cover the historical backstory, origins, and past evolution (mentioning specific past years, eras, historical figures, or former milestones) of the subject.\n"
                "- The narration MUST sound like a professional, high-quality historical documentary narrator (e.g. 'For centuries...', 'Historically, the journey began in...', 'Legendary figures of the past...').\n"
                "- Only refer to the modern/present event as a brief comparison or resolution at the end of the script."
            )
        elif category.lower() in ("children story", "children's story", "kids story", "kids", "children"):
            category_instruction = "This is a CHILDREN'S STORY. Write a whimsical, age-appropriate story with simple language, fun characters, clear moral/lesson, and imaginative scenes. NOT a factual documentary."
        elif category.lower() in ("science", "technology", "tech"):
            category_instruction = "This is a SCIENCE/TECH video. Explain the concept in an accessible, fascinating way with clear cause-effect and wonder-inducing facts."
        elif category.lower() in ("sports", "sport"):
            category_instruction = "This is a SPORTS video. Write with high energy, focus on epic moments, athlete achievements, records, and game-defining plays."
        elif category.lower() in ("entertainment", "celebrity", "pop culture"):
            category_instruction = "This is an ENTERTAINMENT video. Write a fast-paced, gossipy, pop-culture style piece with surprising reveals and hype."
        elif category.lower() in ("reddit", "reddit_stories", "reddit story", "aita", "askreddit", "stories"):
            category_instruction = "This is a REDDIT STORY / AITA video. Retell the Reddit story from a first-person dramatic perspective ('I', 'my'). Maintain the original narrative conflict, suspense, and emotional hook, keeping it conversational and highly engaging for vertical video formats."
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
- Any text, words, labels, signs, alphabets, letters, or subtitles. The video frames MUST be strictly visual without any textual characters. All captions/text are burned-in separately.

EVERY visual_description must follow this template:
"[Camera move] of [single specific subject] in [specific location/setting], [subject's spatial relationship to background], [doing one clear action or held pose], [sensory details: texture, material, surface], [lighting], [mood/style], [any style LoRA triggers if relevant], high detail, cinematic, 9:16 vertical"

GOOD visual_description examples:
- "Slow push-in on a lone football player standing in the left foreground of a floodlit stadium pitch at twilight, the background out of focus, head bowed, ball at his feet, crisp fabric of his jersey, dramatic backlight, cinematic mood, 9:16 vertical, high detail"
- "Slow orbit around an ancient leather football resting on dewy grass with morning light filtering through, shallow depth of field, rough leather texture, warm golden tones, 9:16 vertical"
- "Static wide shot of a roaring stadium crowd holding scarves aloft under bright floodlights in the background, confetti mid-air, vibrant high-contrast color, cinematic 9:16 vertical"

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

        # 4-act structure for long-form (180s+). LLMs handle multi-act narratives
        # better than a flat list of 30 scenes - it gives the scriptwriter a
        # structural skeleton to follow so the story has rising tension, a
        # clear climax, and a satisfying resolution instead of a wandering list.
        long_form_block = ""
        if long_form:
            # Divide num_scenes into 4 acts (setup / development / climax / resolution).
            # Last scene is always the closing shot (resolution + CTA).
            act_setup_end = max(1, num_scenes // 4)
            act_dev_end = max(act_setup_end + 1, num_scenes // 2)
            act_climax_end = max(act_dev_end + 1, (num_scenes * 3) // 4)
            long_form_block = f"""

LONG-FORM 4-ACT STRUCTURE (this is a {duration}s long-form video, plan acts carefully):
- ACT 1 - SETUP (scenes 1-{act_setup_end}): Establish the world, the era, the key players. Visual anchor #1 introduced. Tone is immersive and inviting.
- ACT 2 - DEVELOPMENT (scenes {act_setup_end+1}-{act_dev_end}): Build the central conflict or curiosity. Introduce complications, deeper details, escalating tension. Visual anchor #2 introduced.
- ACT 3 - CLIMAX (scenes {act_dev_end+1}-{act_climax_end}): The peak emotional or dramatic moment. Most intense visuals, fastest camera moves, strongest contrast. Visual anchor #3 introduced.
- ACT 4 - RESOLUTION (scenes {act_climax_end+1}-{num_scenes}): Payoff + reflection. The final scene ({num_scenes}) is a slow, contemplative closing shot with the CTA narration. Pace this act with longer visual dwell time so the viewer feels the story has resolved.

Make sure each act has a clear tonal shift (not just more of the same)."""

        vlog_block = ""
        if is_vlog:
            vlog_block = """
VLOG STYLE REQUIREMENTS:
This is a "Vlog" style video where a host narrating the story is visible on screen.
You MUST add a "scene_type" field to each scene. It must be either "host_talking" or "b_roll".
- "host_talking" scenes must have a visual_description that starts with "A vlog-style shot of a host speaking to the camera..." (or similar) and MUST be exactly 100% focused on the host narrating.
- "host_talking" scenes MUST also include an "i2i_prompt" describing the background location AND the specific clothing/attire the host should be wearing to match the story's context (e.g., "medieval streets of Toledo, sandstone buildings, host wearing a rustic linen tunic and leather armor").
- "b_roll" scenes must illustrate the subject matter being discussed (standard LTX 2.3 guidelines apply) and should have an empty "i2i_prompt".
- All scenes MUST include an "ambient_sounds" field detailing the specific background noises (e.g., "market chatter, footsteps, horses, birds").
- Alternate between "host_talking" and "b_roll" scenes. The first scene MUST be "host_talking".
"""

        scene_fields = f"""   - scene_number (1 to {num_scenes})
   - visual_description (FOLLOW THE TEMPLATE IN SYSTEM PROMPT — single subject, one action, one camera move, specific lighting; NEVER use montage/calendar/archival/etc.)
   - narration_text ({narration_min}-{narration_max} words, fits ~{per_scene} seconds spoken)
   - duration_seconds ({per_scene})"""
        if is_vlog:
            scene_fields += """
   - scene_type (MUST be "host_talking" or "b_roll")
   - i2i_prompt (Required for host_talking, empty for b_roll)
   - ambient_sounds (Required)"""

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
{scene_fields}
3. VISUAL CONTINUITY: Pick 2-3 recurring visual anchors (e.g., "stadium at twilight", "vintage leather ball", "lone player") and use them across multiple scenes
4. CAMERA VARIETY: Each scene must use a DIFFERENT camera move from this set: slow push-in, slow pan, slow dolly forward, slow orbit, slow zoom, static wide, slow tilt up
5. CLIMAX: Scene {num_scenes - 1} must be visually the most dramatic (e.g., a goal scored, a trophy lifted, a crowd erupting)
6. CLOSING SHOT: Scene {num_scenes} is the final scene and must consist of a short, reflective wrap-up (1-2 sentences) about the story/topic.
   - Do NOT include any call-to-action (CTA) such as "like", "subscribe", or "hit the bell" in the narration text of this scene. The narration text should purely wrap up the story topic itself.
   - The visual should still be a deliberate, slow, contemplative closing shot (trophy, lone object, empty stadium, wide sunset).
   - The narration text should end cleanly by wrapping up the topic.
7. Also generate:
   - title: catchy, max 60 chars
   - description: 2-sentence summary
   - hashtags: 10 relevant hashtags
   - call_to_action: short (e.g., "Like and subscribe for more!")
   - music_prompt: comma-separated ACE 1.5 music description (genre, mood, instruments, BPM, key). Example for "Epic": "epic, cinematic, orchestral, dramatic, powerful, 100 BPM, E minor"

{long_form_block}

{vlog_block}

Respond ONLY in valid JSON. No markdown, no commentary, no code blocks — just raw JSON:

{{
  "title": "...",
  "description": "...",
  "hashtags": ["#tag1", "#tag2", ...],
  "hook": "...",
  "scenes": [
    {{"scene_number": 1, "scene_type": "host_talking", "visual_description": "Slow push-in on ...", "i2i_prompt": "Background location...", "ambient_sounds": "outdoor market, distant chatter...", "narration_text": "...", "duration_seconds": {per_scene}}},
    {{"scene_number": 2, "scene_type": "b_roll", "visual_description": "Slow pan across ...", "i2i_prompt": "", "ambient_sounds": "whoosh, dramatic hit...", "narration_text": "...", "duration_seconds": {per_scene}}},
    ...
    {{"scene_number": {num_scenes - 1}, "scene_type": "b_roll", "visual_description": "Fast push-in on the climactic moment ...", "i2i_prompt": "", "ambient_sounds": "crowd roaring...", "narration_text": "...", "duration_seconds": {per_scene}}},
    {{"scene_number": {num_scenes}, "scene_type": "b_roll", "visual_description": "Slow wide shot of ... contemplative closing image", "i2i_prompt": "", "ambient_sounds": "gentle wind, birds...", "narration_text": "Reflective conclusion. Like and subscribe for more!", "duration_seconds": {per_scene}}}
  ],
  "call_to_action": "Like and subscribe for more!",
  "music_prompt": "genre, mood, instruments, BPM, key"
}}"""

        if prev_scripts_context:
            prompt += f"""

CRITICAL — PREVENT DUPLICATION:
This is part of a multi-video batch. To prevent duplicate videos, the following script(s) have already been generated for this project:
{prev_scripts_context}

You MUST generate a completely unique script. Do NOT reuse the same hooks, key facts, stories, visual descriptions, or phrasing from the scripts shown above. Focus on completely different aspects, angles, or facts!
"""

        self.current_is_vlog = is_vlog

        response = await research_service._ollama_generate(prompt, system_prompt)
        
        if not response:
            raise ValueError("Ollama returned an empty response. It may have timed out or crashed.")

        # Try to parse JSON from response
        try:
            # Sometimes LLM wraps in markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            script_data = json.loads(response)
            # Truncation guard
            print(f"[script] Ollama returned {len(script_data.get('scenes', []))} scenes, num_scenes={num_scenes}", flush=True)
            script_data = self._topup_scenes(script_data, num_scenes, per_scene, topic, category)
            print(f"[script] After topup: {len(script_data.get('scenes', []))} scenes", flush=True)
            # ENFORCE: explicit CTA at end of last scene's narration.
            # Many LLMs end the script abruptly after the reflective wrap-up
            # and forget the call-to-action. We append/strengthen it here so
            # the user always hears a clear Like/Subscribe/bell sign-off.
            script_data = self._enforce_final_cta(script_data, topic=topic, category=category)

            # Sanitize all texts in script_data
            if "hook" in script_data and isinstance(script_data["hook"], str):
                script_data["hook"] = self._sanitize_text(script_data["hook"])
            if "description" in script_data and isinstance(script_data["description"], str):
                script_data["description"] = self._sanitize_text(script_data["description"])
            if "scenes" in script_data and isinstance(script_data["scenes"], list):
                for i, s in enumerate(script_data["scenes"]):
                    if isinstance(s, dict):
                        if "narration_text" in s and isinstance(s["narration_text"], str):
                            s["narration_text"] = self._sanitize_text(s["narration_text"])
                        if is_vlog:
                            expected_type = "host_talking" if i % 2 == 0 else "b_roll"
                            s["scene_type"] = expected_type
                            if expected_type == "host_talking":
                                if "vlog-style shot" not in s.get("visual_description", "").lower():
                                    s["visual_description"] = f"A vlog-style shot of a host speaking to the camera about {topic}"
                                if not s.get("i2i_prompt"):
                                    s["i2i_prompt"] = "A clean, well-lit vlog studio background"

            return script_data
        except json.JSONDecodeError:
            # Fallback: return raw text structured manually
            return self._fallback_parse_script(response, topic, num_scenes, per_scene, style, is_vlog)

    def _topup_scenes(self, script_data: Dict, num_scenes: int, per_scene: int,
                      topic: str, category: str) -> Dict:
        """Pad scenes to num_scenes if LLM truncated.

        Adds generic-but-valid filler scenes with proper structure so the
        downstream pipeline (t2v, audio, assembly) has the expected count.
        """
        scenes = script_data.get("scenes") or []
        if not isinstance(scenes, list):
            scenes = []
        # Remove invalid scenes (non-dict or missing required keys)
        scenes = [s for s in scenes if isinstance(s, dict) and s.get("narration_text")]
        if len(scenes) >= num_scenes:
            script_data["scenes"] = scenes[:num_scenes]
            return script_data

        existing_nums = {s.get("scene_number") for s in scenes}
        camera_moves = [
            "Slow pan across", "Slow push-in on", "Static wide shot of",
            "Slow orbit around", "Slow dolly forward toward",
        ]
        last_idx = len(scenes)
        for i in range(last_idx, num_scenes):
            move = camera_moves[i % len(camera_moves)]
            cam_desc = (
                f"{move} a contemplative view of the {topic} subject, "
                f"matching the visual style of the previous scenes, soft "
                f"lighting, cinematic mood"
            )
            narration = (
                f"Continuing the story of {topic} as we explore another "
                f"fascinating detail in this ongoing journey."
            )
            is_vlog = getattr(self, "current_is_vlog", False)
            scene_type = "host_talking" if is_vlog and i % 2 == 0 else "b_roll"
            
            scenes.append({
                "scene_number": i + 1,
                "scene_type": scene_type,
                "visual_description": f"A vlog-style shot of a host speaking to the camera about {topic}" if scene_type == "host_talking" else cam_desc,
                "i2i_prompt": "A clean, well-lit vlog studio background" if scene_type == "host_talking" else "",
                "ambient_sounds": "gentle background noise",
                "narration_text": narration,
                "duration_seconds": per_scene,
            })
        script_data["scenes"] = scenes
        return script_data

    def _enforce_final_cta(self, script_data: Dict, topic: str, category: str) -> Dict:
        """Guarantee the last scene's narration_text ends with an explicit
        Like / Subscribe / bell call-to-action.

        We now generate a separate outro voiceover for the final 6 seconds,
        so we do not enforce or append any CTA in the main scenes' narration text.
        """
        return script_data
    
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
    
    def _sanitize_text(self, text: str) -> str:
        if not text:
            return text
        text = text.strip()
        
        # Clean up JSON formatting artifacts if present
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()
        elif text.startswith('"'):
            text = text[1:].strip()
        elif text.endswith('"'):
            text = text[:-1].strip()
            
        text = text.rstrip(',}:; ')
        text = text.lstrip('{: ')
        
        if not text:
            return text
            
        # Check if the text ends with valid sentence/clause punctuation or quotes.
        terminal_punctuations = ('.', '!', '?', '"', "'", '”', '’')
        if text.endswith(terminal_punctuations):
            return text
            
        # Try to find the last occurrence of '.', '!', '?'
        last_punc_idx = -1
        for char in ('.', '!', '?'):
            idx = text.rfind(char)
            if idx > last_punc_idx:
                last_punc_idx = idx
                
        if last_punc_idx != -1:
            sanitized = text[:last_punc_idx + 1].strip()
            if sanitized:
                return sanitized
                
        return text + "."

    def _fallback_parse_script(self, text: str, topic: str, num_scenes: int = 4, per_scene: int = 6, style: str = "", is_vlog: bool = False) -> Dict:
        """Fallback if JSON parsing fails."""
        lines = text.strip().split('\n')
        scenes = []
        for i in range(num_scenes):
            raw_line = lines[i] if i < len(lines) else f"Continuing the story of {topic}."
            narration = self._sanitize_text(raw_line)
            scene_type = "host_talking" if is_vlog and i % 2 == 0 else "b_roll"
            
            scenes.append({
                "scene_number": i + 1,
                "scene_type": scene_type,
                "visual_description": f"A vlog-style shot of a host speaking to the camera about {topic}" if scene_type == "host_talking" else f"Scene {i+1} about {topic}",
                "i2i_prompt": "A clean, well-lit vlog studio background" if scene_type == "host_talking" else "",
                "narration_text": narration,
                "duration_seconds": per_scene,
            })
        hook_val = self._sanitize_text(lines[0] if lines else topic)
        return {
            "title": topic,
            "description": f"Learn about {topic} in this amazing short video!",
            "hashtags": ["#shorts", f"#{topic.replace(' ', '')}", "#facts"],
            "hook": hook_val,
            "scenes": scenes,
            "call_to_action": "Like and subscribe for more!"
        }

script_service = ScriptService()
