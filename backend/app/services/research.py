import httpx
import json
import time
from typing import List, Dict, Optional
from app.config import settings
from app.models import ResearchLog

class ResearchService:
    def __init__(self):
        self.ollama_host = settings.OLLAMA_HOST
        self.model = settings.OLLAMA_MODEL

    def _log(
        self,
        db,
        project_id: int,
        job_id: Optional[int],
        video_index: int,
        source_type: str,
        query: str,
        topic_used: str,
        search_results: List[Dict],
        context_text: str = "",
        web_content: str = "",
        source_url: str = "",
        status: str = "completed",
        error: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Persist a row to research_logs (best-effort; never raises).

        The caller may be inside a worker thread (when the request handler
        runs an asyncio coroutine via a thread executor). To stay thread-safe
        we open a fresh SessionLocal, write, and close — never reusing the
        request's session across threads.
        """
        from app.database import SessionLocal
        sess = None
        try:
            sess = db if db is not None else SessionLocal()
            row = ResearchLog(
                project_id=project_id,
                job_id=job_id,
                video_index=video_index,
                source_type=source_type,
                query=query,
                topic_used=topic_used,
                search_results=search_results or [],
                context_text=context_text or "",
                web_content=web_content or "",
                source_url=source_url or "",
                result_count=len(search_results or []),
                status=status,
                error=error or "",
                duration_ms=duration_ms,
            )
            sess.add(row)
            sess.commit()
        except Exception as e:
            try:
                if sess is not None:
                    sess.rollback()
            except Exception:
                pass
            print(f"ResearchLog insert failed: {type(e).__name__}: {e}")
        finally:
            # Only close if we created the session ourselves
            if db is None and sess is not None:
                try:
                    sess.close()
                except Exception:
                    pass

    async def search_web(
        self,
        query: str,
        max_results: int = 5,
        db=None,
        project_id: int = 0,
        job_id: Optional[int] = None,
        video_index: int = 0,
        source_type: str = "auto_research",
    ) -> List[Dict]:
        """Search the web using DuckDuckGo (free, no API key)."""
        t0 = time.time()
        results: List[Dict] = []
        err = ""
        # Prefer the modern `ddgs` package; fall back to legacy `duckduckgo_search`
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                DDGS = None
        if DDGS is None:
            err = "Neither ddgs nor duckduckgo_search is installed"
            print(f"DuckDuckGo search error: {err}")
        else:
            try:
                with DDGS() as ddgs:
                    for r in ddgs.text(query, max_results=max_results):
                        results.append({
                            "title": r.get("title", ""),
                            "href": r.get("href", ""),
                            "body": r.get("body", "")
                        })
            except Exception as e:
                err = str(e)
                print(f"DuckDuckGo search error: {e}")

        self._log(
            db=db,
            project_id=project_id,
            job_id=job_id,
            video_index=video_index,
            source_type=source_type,
            query=query,
            topic_used=query,
            search_results=results,
            context_text="",
            status="failed" if err else "completed",
            error=err,
            duration_ms=int((time.time() - t0) * 1000),
        )
        return results
    
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
    
    async def summarize_webpage(
        self,
        url: str,
        db=None,
        project_id: int = 0,
        job_id: Optional[int] = None,
        video_index: int = 0,
    ) -> str:
        """Fetch and summarize a webpage."""
        t0 = time.time()
        text = ""
        err = ""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                text = resp.text
                import re
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                text = text[:8000]
        except Exception as e:
            err = str(e)
            print(f"Webpage fetch error: {e}")

        self._log(
            db=db,
            project_id=project_id,
            job_id=job_id,
            video_index=video_index,
            source_type="url",
            query="",
            topic_used=url,
            search_results=[],
            web_content=text,
            source_url=url,
            status="failed" if err else "completed",
            error=err,
            duration_ms=int((time.time() - t0) * 1000),
        )
        return text
    
    async def suggest_topics(
        self,
        category: str,
        seed: str = "",
        db=None,
        project_id: int = 0,
        job_id: Optional[int] = None,
    ) -> List[str]:
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
        # Log the Ollama call (no web search, no results, but mark it as a research interaction)
        if project_id:
            self._log(
                db=db,
                project_id=project_id,
                job_id=job_id,
                video_index=0,
                source_type="topic",
                query=f"suggest_topics: {category}" + (f" seed={seed}" if seed else ""),
                topic_used=seed or category,
                search_results=[],
                context_text=result[:2000],
                status="completed",
            )
        return topics[:8]

    async def trending_topics(
        self,
        category: str,
        db=None,
        project_id: int = 0,
        job_id: Optional[int] = None,
    ) -> List[str]:
        """Search web for trending topics in a category and return suggestions."""
        search_query = f"trending {category} topics 2026 viral"
        search_results = await self.search_web(
            search_query,
            max_results=5,
            db=db,
            project_id=project_id,
            job_id=job_id,
            video_index=0,
            source_type="auto_research",
        )
        context = "\n\n".join([f"Title: {r['title']}\n{r['body']}" for r in search_results])
        if not context:
            return await self.suggest_topics(
                category,
                "trending viral topics right now",
                db=db,
                project_id=project_id,
                job_id=job_id,
            )
        prompt = f"""Based on these search results about trending topics in {category}, identify 5 specific, factual trending topics suitable for YouTube Shorts.

Search results:
{context}

Return ONLY a numbered list of 5 topics, one per line, no explanation."""
        result = await self._ollama_generate(prompt)
        topics = [line.strip().lstrip("0123456789.)- ") for line in result.split("\n") if line.strip()]
        # Log the LLM call (and the search results it used) for visibility
        if project_id:
            self._log(
                db=db,
                project_id=project_id,
                job_id=job_id,
                video_index=0,
                source_type="auto_research",
                query=search_query,
                topic_used=category,
                search_results=search_results,
                context_text=context,
                status="completed",
            )
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
    
    async def research_topic(
        self,
        topic: str,
        category: str,
        db=None,
        project_id: int = 0,
        job_id: Optional[int] = None,
        video_index: int = 0,
    ) -> Dict:
        """Full research pipeline: search web, summarize, return findings."""
        # Search for the topic
        search_query = f"{topic} {category} facts interesting"
        search_results = await self.search_web(
            search_query,
            max_results=5,
            db=db,
            project_id=project_id,
            job_id=job_id,
            video_index=video_index,
            source_type="auto_research",
        )

        # Combine search snippets into context
        context = "\n\n".join([f"Title: {r['title']}\n{r['body']}" for r in search_results[:3]])

        # One more row capturing the FULL research outcome (search + context joined)
        self._log(
            db=db,
            project_id=project_id,
            job_id=job_id,
            video_index=video_index,
            source_type="auto_research",
            query=search_query,
            topic_used=topic,
            search_results=search_results,
            context_text=context,
            status="completed",
        )

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
