import os
import json
import socket
import secrets
import threading
from pathlib import Path
from typing import Dict, Optional, List
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from app.config import settings

CHANNELS_DIR_NAME = "youtube_channels"
LOCAL_OAUTH_PORT = 8765

_HTML_SUCCESS = """<!doctype html>
<html><head><title>YouTube Linked - You can close this window</title>
<style>
body { font-family: -apple-system, system-ui, sans-serif; background:#050608; color:#F5F5F5;
       display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }
.card { background:#0E1116; border:1px solid #C6F11D; border-radius:16px; padding:40px 60px;
        text-align:center; box-shadow:0 0 40px rgba(198,241,29,0.15); }
h1 { color:#C6F11D; font-size:32px; margin:0 0 12px; }
p { color:#9AA0A6; font-size:16px; margin:0; }
</style></head>
<body><div class="card">
<h1>Linked!</h1>
<p>Your YouTube channel is connected. You can close this tab and return to AI Shorts Creator.</p>
</div></body></html>"""

_HTML_ERROR = """<!doctype html>
<html><head><title>YouTube Link Failed</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; background:#050608; color:#F5F5F5;
       display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }}
.card {{ background:#0E1116; border:1px solid #FF5757; border-radius:16px; padding:40px 60px;
        text-align:center; max-width:600px; }}
h1 {{ color:#FF5757; font-size:28px; margin:0 0 12px; }}
p {{ color:#9AA0A6; font-size:15px; margin:0; line-height:1.5; }}
code {{ color:#FF5757; background:#1a0e0e; padding:2px 6px; border-radius:4px; }}
</style></head>
<body><div class="card">
<h1>Link Failed</h1>
<p>Error: <code>{msg}</code><br><br>Close this tab and try again in AI Shorts Creator.</p>
</div></body></html>"""


class YouTubeService:
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube.readonly"]
    API_SERVICE_NAME = "youtube"
    API_VERSION = "v3"

    def __init__(self):
        self.client_secrets_file = settings.YOUTUBE_CLIENT_SECRETS_FILE
        self.channels_dir = settings.STORAGE_DIR / CHANNELS_DIR_NAME
        self.channels_dir.mkdir(parents=True, exist_ok=True)
        self._pending_flows: Dict[str, InstalledAppFlow] = {}
        self._pending_results: Dict[str, Dict] = {}
        self._httpd: Optional[HTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def _get_credentials_path(self, channel_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in channel_id)
        return self.channels_dir / f"{safe}.json"

    def has_secrets(self) -> bool:
        return self.client_secrets_file.exists()

    def save_secrets(self, content: bytes) -> Dict:
        try:
            data = json.loads(content.decode("utf-8"))
            if data.get("installed") is None and data.get("web") is None:
                return {"status": "error", "message": "Not a valid OAuth client config. Need 'installed' or 'web' key."}
            self.client_secrets_file.parent.mkdir(parents=True, exist_ok=True)
            self.client_secrets_file.write_bytes(content)
            return {"status": "success", "path": str(self.client_secrets_file)}
        except json.JSONDecodeError as e:
            return {"status": "error", "message": f"Invalid JSON: {e}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _is_port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    def _ensure_local_server(self) -> int:
        if self._httpd is not None:
            return LOCAL_OAUTH_PORT
        if not self._is_port_free(LOCAL_OAUTH_PORT):
            raise RuntimeError(
                f"Port {LOCAL_OAUTH_PORT} is in use by another application. "
                "Please close the other application or choose a different port."
            )

        service_ref = self

        class CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path != "/oauth/youtube/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                params = parse_qs(parsed.query)
                code = params.get("code", [None])[0]
                state = params.get("state", [None])[0]
                error = params.get("error", [None])[0]

                if error:
                    service_ref._pending_results[state or "_"] = {
                        "status": "error",
                        "message": f"Google returned error: {error}",
                    }
                    body = _HTML_ERROR.format(msg=error).encode("utf-8")
                elif not code or not state:
                    service_ref._pending_results[state or "_"] = {
                        "status": "error",
                        "message": "Missing code or state in callback.",
                    }
                    body = _HTML_ERROR.format(msg="Missing code or state.").encode("utf-8")
                else:
                    result = service_ref._finalize_auth(state, code)
                    if result.get("status") == "success":
                        body = _HTML_SUCCESS.encode("utf-8")
                    else:
                        body = _HTML_ERROR.format(msg=result.get("message", "Unknown error")).encode("utf-8")

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        try:
            self._httpd = HTTPServer(("127.0.0.1", LOCAL_OAUTH_PORT), CallbackHandler)
        except OSError:
            raise RuntimeError(
                f"Port {LOCAL_OAUTH_PORT} is in use. Please free it and try again."
            )
        self._server_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._server_thread.start()
        return LOCAL_OAUTH_PORT

    def _finalize_auth(self, state: str, code: str) -> Dict:
        flow = self._pending_flows.pop(state, None)
        if not flow:
            return {"status": "error", "message": "Auth session expired. Try again."}
        try:
            flow.fetch_token(code=code)
            creds = flow.credentials
            youtube = build(self.API_SERVICE_NAME, self.API_VERSION,
                          credentials=creds, cache_discovery=False)
            resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
            items = resp.get("items", [])
            if not items:
                raise RuntimeError("No YouTube channel found for this Google account.")
            ch = items[0]
            channel_id = ch["id"]
            channel_title = ch["snippet"]["title"]
            thumbnail_url = ch["snippet"]["thumbnails"].get("default", {}).get("url", "")
            creds_path = self._get_credentials_path(channel_id)
            creds_path.write_text(creds.to_json())
            result = {
                "status": "success",
                "channel": {
                    "name": channel_title,
                    "channel_id": channel_id,
                    "channel_title": channel_title,
                    "thumbnail_url": thumbnail_url,
                    "credentials_file": str(creds_path),
                },
            }
            self._pending_results[state] = result
            return result
        except Exception as e:
            err = {"status": "error", "message": str(e)}
            self._pending_results[state] = err
            return err

    def start_auth(self) -> Dict:
        if not self.client_secrets_file.exists():
            return {"status": "error",
                    "message": "client_secrets.json not found. Upload it via Settings > YouTube."}
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secrets_file), self.SCOPES)
        auth_url, _ = flow.authorization_url(prompt='consent')
        self._pending_flows["_legacy"] = flow
        return {"status": "needs_auth", "auth_url": auth_url}

    def start_local_auth(self) -> Dict:
        if not self.client_secrets_file.exists():
            return {"status": "error",
                    "message": "Upload client_secrets.json first (see Setup Instructions)."}
        try:
            port = self._ensure_local_server()
        except RuntimeError as e:
            return {"status": "error", "message": str(e)}
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secrets_file), self.SCOPES)
        flow.redirect_uri = f"http://127.0.0.1:{port}/oauth/youtube/callback"
        state = secrets.token_urlsafe(16)
        auth_url, _ = flow.authorization_url(prompt='consent', state=state)
        self._pending_flows[state] = flow
        self._pending_results[state] = {"status": "pending"}
        return {"status": "ready", "auth_url": auth_url, "state": state, "port": port}

    def check_auth(self, state: str) -> Dict:
        if not state:
            return {"status": "error", "message": "Missing state."}
        result = self._pending_results.get(state)
        if not result:
            return {"status": "pending"}
        return result

    def complete_auth(self, code: str, channel_name: str = "") -> Dict:
        flow = self._pending_flows.pop("_legacy", None)
        if not flow:
            return {"status": "error", "message": "No pending auth. Start again."}
        try:
            flow.fetch_token(code=code)
            creds = flow.credentials
            youtube = build(self.API_SERVICE_NAME, self.API_VERSION,
                          credentials=creds, cache_discovery=False)
            resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
            items = resp.get("items", [])
            if not items:
                return {"status": "error", "message": "No channel found for this account."}
            ch = items[0]
            channel_id = ch["id"]
            channel_title = ch["snippet"]["title"]
            thumbnail_url = ch["snippet"]["thumbnails"].get("default", {}).get("url", "")
            creds_path = self._get_credentials_path(channel_id)
            creds_path.write_text(creds.to_json())
            return {
                "status": "success",
                "channel": {
                    "name": channel_name or channel_title,
                    "channel_id": channel_id,
                    "channel_title": channel_title,
                    "thumbnail_url": thumbnail_url,
                    "credentials_file": str(creds_path),
                }
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _load_credentials(self, credentials_file: str) -> Optional[Credentials]:
        creds_path = Path(credentials_file)
        if not creds_path.exists():
            return None
        try:
            creds = Credentials.from_authorized_user_file(str(creds_path), self.SCOPES)
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    creds_path.write_text(creds.to_json())
                else:
                    return None
            return creds
        except Exception:
            return None

    def get_authenticated_service(self, credentials_file: str = None):
        if not credentials_file:
            return None
        creds = self._load_credentials(credentials_file)
        if not creds:
            return None
        return build(self.API_SERVICE_NAME, self.API_VERSION,
                    credentials=creds, cache_discovery=False)

    def upload_video(self, credentials_file, video_path, title, description,
                     tags, category_id="22", privacy_status="private",
                     publish_at=None, thumbnail_path=None) -> Dict:
        youtube = self.get_authenticated_service(credentials_file)
        if not youtube:
            return {"status": "error", "message": "Not authenticated for this channel"}
        
        # Sanitize title to ensure it's not empty/None, and is within YouTube's 100-character limit
        if not title or not str(title).strip():
            title = "Untitled Short"
        else:
            title = str(title).strip()
            if len(title) > 100:
                title = title[:97] + "..."

        try:
            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": category_id
                },
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False
                }
            }
            if publish_at:
                body["status"]["publishAt"] = publish_at
                body["status"]["privacyStatus"] = "private"

            media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
            request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media
            )
            response = request.execute()
            video_id = response["id"]

            if thumbnail_path and Path(thumbnail_path).exists():
                try:
                    youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail_path, mimetype="image/png")
                    ).execute()
                except Exception as e:
                    print(f"Thumbnail upload error: {e}")

            return {
                "status": "success",
                "video_id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}",
                "privacy_status": privacy_status
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def refresh_channel_info(self, credentials_file: str) -> Dict:
        youtube = self.get_authenticated_service(credentials_file)
        if not youtube:
            return {"status": "error", "message": "Not authenticated"}
        try:
            resp = youtube.channels().list(part="snippet,statistics", mine=True).execute()
            items = resp.get("items", [])
            if items:
                ch = items[0]
                return {
                    "status": "success",
                    "channel": {
                        "channel_id": ch["id"],
                        "channel_title": ch["snippet"]["title"],
                        "thumbnail_url": ch["snippet"]["thumbnails"].get("default", {}).get("url", ""),
                    }
                }
            return {"status": "error", "message": "No channel found"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def remove_channel_credentials(self, credentials_file: str) -> bool:
        try:
            p = Path(credentials_file)
            if p.exists():
                p.unlink()
            return True
        except Exception:
            return False


youtube_service = YouTubeService()
