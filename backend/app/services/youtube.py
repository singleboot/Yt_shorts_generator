import os
import json
from pathlib import Path
from typing import Dict, Optional, List
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from app.config import settings

CHANNELS_DIR_NAME = "youtube_channels"


class YouTubeService:
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
              "https://www.googleapis.com/auth/youtube.readonly"]
    API_SERVICE_NAME = "youtube"
    API_VERSION = "v3"

    def __init__(self):
        self.client_secrets_file = settings.YOUTUBE_CLIENT_SECRETS_FILE
        self.channels_dir = settings.STORAGE_DIR / CHANNELS_DIR_NAME
        self.channels_dir.mkdir(parents=True, exist_ok=True)

    def _get_credentials_path(self, channel_id: str) -> Path:
        """Get the path to a channel's credentials file."""
        # Sanitize channel_id for filesystem
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in channel_id)
        return self.channels_dir / f"{safe}.json"

    def start_auth(self) -> Dict:
        """Start YouTube OAuth flow. Returns auth_url for user to visit."""
        if not self.client_secrets_file.exists():
            return {"status": "error", "message": "client_secrets.json not found. Please download it from Google Cloud Console and place in storage/."}

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secrets_file), self.SCOPES)
        auth_url, _ = flow.authorization_url(prompt='consent')
        # Store flow state in memory keyed by state param
        # For simplicity, use a single pending flow
        self._pending_flow = flow
        return {"status": "needs_auth", "auth_url": auth_url}

    def complete_auth(self, code: str, channel_name: str) -> Dict:
        """Complete OAuth flow with code, fetch channel info, save to DB-ready dict."""
        if not hasattr(self, "_pending_flow") or not self._pending_flow:
            return {"status": "error", "message": "No pending auth. Start again."}
        try:
            self._pending_flow.fetch_token(code=code)
            creds = self._pending_flow.credentials

            # Get channel info from API
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

            # Save credentials to per-channel file
            creds_path = self._get_credentials_path(channel_id)
            creds_path.write_text(creds.to_json())

            self._pending_flow = None

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
        """Load and refresh credentials from a per-channel file."""
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
        """Get YouTube API service for a specific channel."""
        if not credentials_file:
            return None
        creds = self._load_credentials(credentials_file)
        if not creds:
            return None
        return build(self.API_SERVICE_NAME, self.API_VERSION,
                    credentials=creds, cache_discovery=False)

    def upload_video(self, credentials_file: str, video_path: str,
                     title: str, description: str,
                     tags: list, category_id: str = "22",
                     privacy_status: str = "private",
                     publish_at: str = None,
                     thumbnail_path: str = None) -> Dict:
        """Upload video to a specific YouTube channel."""
        youtube = self.get_authenticated_service(credentials_file)
        if not youtube:
            return {"status": "error", "message": "Not authenticated for this channel"}

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
                body["status"]["privacyStatus"] = "private"  # Must be private until publish time

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
        """Re-fetch channel info from YouTube API (refreshes title, thumbnail)."""
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
        """Delete a channel's credentials file."""
        try:
            p = Path(credentials_file)
            if p.exists():
                p.unlink()
            return True
        except Exception:
            return False


youtube_service = YouTubeService()
