import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class PreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=400)

    @field_validator("url")
    @classmethod
    def spotify_url(cls, value: str) -> str:
        value = value.strip()
        uri = re.fullmatch(r"spotify:(track|album|playlist):([A-Za-z0-9]{22})", value)
        if uri:
            return f"https://open.spotify.com/{uri[1]}/{uri[2]}"
        parsed = urlparse(value)
        match = re.fullmatch(r"/(?:intl-[a-zA-Z-]+/)?(track|album|playlist)/([A-Za-z0-9]{22})/?", parsed.path)
        if parsed.scheme != "https" or parsed.netloc != "open.spotify.com" or not match:
            raise ValueError("Paste a Spotify track, album or public playlist link (open.spotify.com).")
        return f"https://open.spotify.com/{match[1]}/{match[2]}"


class DownloadRequest(BaseModel):
    preview_id: str
    indices: list[int] = Field(min_length=1, max_length=1000)
    format: Literal["mp3", "m4a", "opus", "flac"] = "mp3"
    bitrate: Literal["auto", "128k", "192k", "256k", "320k"] = "auto"


class Preferences(BaseModel):
    format: Literal["mp3", "m4a", "opus", "flac"] = "mp3"
    bitrate: Literal["auto", "128k", "192k", "256k", "320k"] = "auto"
