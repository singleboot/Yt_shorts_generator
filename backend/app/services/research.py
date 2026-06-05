import httpx
import json
from typing import List, Dict, Optional
from app.config import settings

class ResearchService:
    def __init__(self):
        self.ollama_host = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_MODEL
    
    async def search_web(self, query: str, max_results: int = 5) -> List[Dict]:
        """Search the web using DuckDuckGo (free, no API key)."""
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", "")
                    })
            return results
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
            return []
    
    async def get_youtube_transcript(self, url: str) -> str:
        """Extract transcript from YouTube video using yt-dlp."""
        try:
            import yt_dlp
            ydl_opts = {
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en'],
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                # Try to get automatic captions
                subtitles = info.get('automatic_captions', {})
                if 'en' in subtitles:
                    # Get the first English subtitle format
                    sub_url = subtitles['en'][0]['url']
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(sub_url)
                        return resp.text
                # Fallback: description + title
                return f"{info.get('title', '')}\n\n{info.get('description', '')}"
        except Exception as e:
            print(f"YouTube transcript error: {e}")
            return ""
    
    async def summarize_webpage(self, url: str) -> str:
        """Fetch and summarize a webpage."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                text = resp.text
                # Simple extraction - in production use trafilatura or newspaper3k
                # For now, strip HTML tags roughly
                import re
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                # Limit to 8000 chars for context
                return text[:8000]
        except Exception as e:
            print(f"Webpage fetch error: {e}")
            return ""
    
    async def suggest_topics(self, category: str, seed: str = "") -> List[str]:
        """Use Ollama to generate topic ideas for a category."""
        prompt = f"""You are a content researcher for YouTube Shorts.
Category: {category}
Generate 8 specific, interesting, and factual topic ideas for YouTube Shorts (30-60 seconds).
Each should be engaging and suitable for visual storytelling.
Return ONLY a numbered list, one topic per line, no explanation."""
        if seed:
            prompt += f"\nRelated to or inspired by: {seed}"
        result = await self._ollama_generate(prompt)
        topics = [line.strip().lstrip("0123456789.)- ") for line in result.split("\n") if line.strip()]
        return topics[:8]

    async def trending_topics(self, category: str) -> List[str]:
        """Search web for trending topics in a category and return suggestions."""
        search_query = f"trending {category} topics 2026 viral"
        search_results = await self.search_web(search_query, max_results=5)
        context = "\n\n".join([f"Title: {r['title']}\n{r['body']}" for r in search_results])
        if not context:
            return await self.suggest_topics(category, "trending viral topics right now")
        prompt = f"""Based on these search results about trending topics in {category}, identify 5 specific, factual trending topics suitable for YouTube Shorts.

Search results:
{context}

Return ONLY a numbered list of 5 topics, one per line, no explanation."""
        result = await self._ollama_generate(prompt)
        topics = [line.strip().lstrip("0123456789.)- ") for line in result.split("\n") if line.strip()]
        return topics[:5]

    async def generate_topic(self, category: str, subcategory: str) -> str:
        """Use Ollama to generate a trending topic for today."""
        prompt = f"""You are a content researcher for YouTube Shorts. 
Category: {category}
Subcategory: {subcategory}

Generate ONE specific, interesting, and trending topic for a YouTube Short (30-60 seconds) that would perform well today.
The topic should be factual, engaging, and suitable for visual storytelling.

Respond ONLY with the topic title, no explanation."""
        
        return await self._ollama_generate(prompt)
    
    async def research_topic(self, topic: str, category: str) -> Dict:
        """Full research pipeline: search web, summarize, return findings."""
        # Search for the topic
        search_query = f"{topic} {category} facts interesting"
        search_results = await self.search_web(search_query, max_results=5)
        
        # Combine search snippets into context
        context = "\n\n".join([f"Title: {r['title']}\n{r['body']}" for r in search_results[:3]])
        
        return {
            "topic": topic,
            "search_results": search_results,
            "context": context
        }
    
    async def _ollama_generate(self, prompt: str, system: str = "") -> str:
        """Call Ollama API."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": 0.7}
                }
                resp = await client.post(f"{self.ollama_host}/api/generate", json=payload)
                data = resp.json()
                return data.get("response", "").strip()
        except Exception as e:
            print(f"Ollama error: {e}")
            return ""

research_service = ResearchService()
