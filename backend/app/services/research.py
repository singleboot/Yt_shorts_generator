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

    async def _search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict]:
        results = []
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                DDGS = None
        if DDGS is None:
            print("DuckDuckGo search skipped: neither ddgs nor duckduckgo_search is installed")
            return results
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", "")
                    })
        except Exception as e:
            print(f"DuckDuckGo search error: {e}")
        return results

    async def _search_wikipedia(self, query: str, max_results: int = 5) -> List[Dict]:
        results = []
        try:
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": max_results
            }
            headers = {"User-Agent": "AIShortsCreator/1.0 (contact: support@aishorts.local)"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    search_hits = data.get("query", {}).get("search", [])
                    for hit in search_hits:
                        title = hit.get("title", "")
                        snippet = hit.get("snippet", "")
                        import re
                        snippet = re.sub(r'<[^>]+>', ' ', snippet)
                        snippet = re.sub(r'\s+', ' ', snippet).strip()
                        results.append({
                            "title": title,
                            "href": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                            "body": snippet
                        })
        except Exception as e:
            print(f"Wikipedia search error: {e}")
        return results

    async def _search_tavily(self, query: str, max_results: int = 5) -> List[Dict]:
        results = []
        api_key = settings.TAVILY_API_KEY
        if not api_key:
            print("Tavily search skipped: API key not set in Settings")
            return results
        try:
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic"
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    for r in data.get("results", []):
                        results.append({
                            "title": r.get("title", ""),
                            "href": r.get("url", ""),
                            "body": r.get("content", "")
                        })
        except Exception as e:
            print(f"Tavily search error: {e}")
        return results

    async def _search_serper(self, query: str, max_results: int = 5) -> List[Dict]:
        results = []
        api_key = settings.SERPER_API_KEY
        if not api_key:
            print("Serper Google search skipped: API key not set in Settings")
            return results
        try:
            url = "https://google.serper.dev/search"
            headers = {
                "X-API-KEY": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "q": query,
                "num": max_results
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    for r in data.get("organic", []):
                        results.append({
                            "title": r.get("title", ""),
                            "href": r.get("link", ""),
                            "body": r.get("snippet", "")
                        })
        except Exception as e:
            print(f"Serper search error: {e}")
        return results

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
        """Search the web using the configured research provider."""
        t0 = time.time()
        results: List[Dict] = []
        err = ""
        
        # 1. Fetch provider from project visual_settings or script overrides
        provider = None
        if project_id:
            from app.database import SessionLocal
            from app.models import Project, Script
            temp_db = db or SessionLocal()
            try:
                # Check for card/script-specific override first
                script = temp_db.query(Script).filter(
                    Script.project_id == project_id,
                    Script.video_index == video_index
                ).first()
                if script and script.video_overrides:
                    vo = script.video_overrides
                    if isinstance(vo, str):
                        try:
                            import json
                            vo = json.loads(vo)
                        except:
                            vo = {}
                    if isinstance(vo, dict) and vo.get("research_provider"):
                        provider = vo["research_provider"]
                
                if not provider:
                    proj = temp_db.query(Project).filter(Project.id == project_id).first()
                    if proj and proj.visual_settings:
                        import json
                        vs = proj.visual_settings
                        if isinstance(vs, str):
                            try:
                                vs = json.loads(vs)
                            except:
                                vs = {}
                        if isinstance(vs, dict):
                            provider = vs.get("research_provider")
            except Exception as e:
                print(f"Error fetching project research provider: {e}")
            finally:
                if db is None:
                    temp_db.close()
        
        if not provider:
            provider = "duckduckgo"

        # 2. Call the chosen provider
        try:
            if provider == "wikipedia":
                import re
                cleaned_query = query
                # Strip "part X" (case-insensitive)
                cleaned_query = re.sub(r'(?i)\bpart\s+\d+\b', '', cleaned_query)
                # Strip noise words
                cleaned_query = re.sub(r'(?i)\b(facts|interesting|trivia|science|history|viral|trending|topics|story)\b', '', cleaned_query)
                # Clean double spaces and trim
                cleaned_query = re.sub(r'\s+', ' ', cleaned_query).strip()
                results = await self._search_wikipedia(cleaned_query, max_results)
            elif provider == "tavily":
                results = await self._search_tavily(query, max_results)
                if not results: # Fallback to DuckDuckGo if Tavily failed or key missing
                    results = await self._search_duckduckgo(query, max_results)
            elif provider == "google_serper":
                results = await self._search_serper(query, max_results)
                if not results: # Fallback to DuckDuckGo if Serper failed or key missing
                    results = await self._search_duckduckgo(query, max_results)
            else:
                results = await self._search_duckduckgo(query, max_results)
        except Exception as e:
            err = str(e)
            print(f"Web search execution error: {e}")

        # 3. Log results to research_logs
        self._log(
            db=db,
            project_id=project_id,
            job_id=job_id,
            video_index=video_index,
            source_type=source_type,
            query=f"[{provider.upper()}] {query}",
            topic_used=query,
            search_results=results,
            context_text="",
            status="failed" if (err or (not results and provider in ["tavily", "google_serper"])) else "completed",
            error=err or (f"{provider} returned 0 results" if (not results and provider in ["tavily", "google_serper"]) else ""),
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

    def extract_pdf_text(self, file_path: str) -> str:
        """Extract text content from a local PDF file using pypdf."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n\n".join(text_parts)
        except Exception as e:
            print(f"PDF extraction error for {file_path}: {e}")
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
        source: str = "web",
    ) -> List[str]:
        """Search web for trending topics in a category and return suggestions."""
        if source == "youtube":
            search_query = f"site:youtube.com trending {category} topics viral 2026"
            prompt_intro = f"Based on these YouTube search results about trending videos in {category}"
        else:
            search_query = f"trending {category} topics 2026 viral"
            prompt_intro = f"Based on these search results about trending topics in {category}"

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
        prompt = f"""{prompt_intro}, identify 5 specific, factual trending topics suitable for YouTube Shorts.

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
        if category.lower() in ("history", "historical"):
            search_query = f"{topic} history past records evolution origin"
        else:
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
    
    async def get_reddit_story(self, source_value: str) -> Dict:
        """Fetch post content from Reddit (either a subreddit name or a direct Reddit URL).
        Returns a dict: {"title": ..., "story": ..., "subreddit": ...}
        """
        title = ""
        story = ""
        subreddit = ""
        try:
            # Check if source_value is a direct URL or a Subreddit name
            if "reddit.com" in source_value.lower():
                clean_url = source_value
                if not clean_url.endswith(".json"):
                    if clean_url.endswith("/"):
                        clean_url = clean_url[:-1]
                    if "?" in clean_url:
                        parts = clean_url.split("?")
                        clean_url = parts[0] + ".json?" + parts[1]
                    else:
                        clean_url = clean_url + ".json"

                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(clean_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    if resp.status_code == 200:
                        data = resp.json()
                        post_data = data[0]["data"]["children"][0]["data"]
                        title = post_data.get("title", "")
                        story = post_data.get("selftext", "")
                        subreddit = post_data.get("subreddit", "")
            else:
                sub = source_value.replace("r/", "").replace("/", "").strip()
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=10"
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                    if resp.status_code == 200:
                        data = resp.json()
                        posts = data.get("data", {}).get("children", [])
                        story_posts = [p["data"] for p in posts if p["data"].get("selftext") and p["data"].get("is_self") != False]
                        if story_posts:
                            post_data = story_posts[0]
                            title = post_data.get("title", "")
                            story = post_data.get("selftext", "")
                            subreddit = post_data.get("subreddit", "")
                        else:
                            raise Exception(f"No text stories found in r/{sub}")
        except Exception as e:
            print(f"Reddit scraper error: {e}")
            story = f"Failed to fetch Reddit story from source: {source_value}. Error: {str(e)}"
        
        return {"title": title, "story": story, "subreddit": subreddit}

    async def _ollama_generate(self, prompt: str, system: str = "") -> str:
        """Call Ollama API."""
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 4096,
                        "num_ctx": 32768
                    }
                }
                resp = await client.post(f"{self.ollama_host}/api/generate", json=payload)
                data = resp.json()
                return data.get("response", "").strip()
        except Exception as e:
            print(f"Ollama error: {e}")
            return ""

research_service = ResearchService()
