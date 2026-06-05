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

        system_prompt = f"""You are an expert YouTube Shorts scriptwriter. You create scripts that are:
- Highly engaging and hook viewers in the first 3 seconds
- Factually accurate based on provided research
- Optimized for {duration}-second videos
- Split into visual scenes for AI video generation (LTX 2.3 t2v)
- Written in a conversational, energetic tone
- Each scene's narration must fit within 8-10 seconds of speaking time

{category_instruction}"""

        prompt = f"""Write a YouTube Shorts script about: {topic}
Category: {category}
Target Duration: {duration} seconds
Style: {style}
Selected Voice: {speaker_name} ({speaker_gender}, English) — {gender_note}
Music Genre: {music_label} — {music_hint}

Research Context:
{context}

Requirements:
1. Start with an attention-grabbing HOOK (first 3 seconds)
2. Include EXACTLY {num_scenes} scenes, each {per_scene} seconds (total ~{duration}s)
3. Each scene must have: scene_number, visual_description (detailed, cinematic, for LTX 2.3 t2v), narration_text (what the voiceover says, MAX 20-25 words), duration_seconds ({per_scene})
4. Each scene's visual_description should be a complete cinematic prompt (camera angle, lighting, mood, subject, action)
5. End with a strong call-to-action (like, subscribe, comment)
6. Also generate: a catchy title (max 60 chars), 10 relevant hashtags, a 2-sentence description
7. Also generate a 'music_prompt' field: a short comma-separated ACE 1.5 music description matching the "{music_label}" music genre and the script mood (genre, mood, instruments, BPM, key). Example for "Epic": "epic, cinematic, orchestral, dramatic, powerful, 100 BPM, E minor". Example for "Lofi": "lofi, chill, hip hop, relaxed, vinyl crackle, 85 BPM, A minor".

Respond ONLY in valid JSON format like this:
{{
  "title": "...",
  "description": "...",
  "hashtags": ["#tag1", "#tag2", ...],
  "hook": "...",
  "scenes": [
    {{"scene_number": 1, "visual_description": "Cinematic shot of ...", "narration_text": "...", "duration_seconds": {per_scene}}},
    ...
  ],
  "call_to_action": "...",
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
