"""YouTube transcript fetcher and metadata extractor using yt-dlp."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class VideoMeta:
    """Metadata for a YouTube video, with optional transcript."""

    id: str
    title: str
    url: str
    upload_date: str  # YYYYMMDD format from yt-dlp
    transcript: str | None = None


def _parse_upload_date(raw: str) -> str:
    """Convert yt-dlp's YYYYMMDD to ISO YYYY-MM-DD."""
    if not raw or len(raw) < 8:
        return raw
    try:
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    except Exception:
        return raw


def _is_after(upload_date_str: str, since_date: date) -> bool:
    """Check if upload_date (YYYYMMDD) is on or after since_date."""
    try:
        iso = _parse_upload_date(upload_date_str)
        parts = iso.split("-")
        if len(parts) == 3:
            udate = date(int(parts[0]), int(parts[1]), int(parts[2]))
            return udate >= since_date
    except (ValueError, IndexError):
        pass
    return True  # If we can't parse, include it


def fetch_recent_videos(
    channel_url: str, since_date: date, limit: int = 50
) -> list[VideoMeta]:
    """Fetch recent videos from a YouTube channel since since_date.

    Uses yt-dlp with extract_flat to list videos without full extraction.
    Returns an empty list on any error (never crashes).
    """
    try:
        opts: dict[str, Any] = {
            "extract_flat": True,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "playlistend": limit,
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)

        videos: list[VideoMeta] = []
        entries = []
        if info and "entries" in info:
            entries = info["entries"] or []
        elif info and "url" in info:
            # Single video
            entries = [info]

        for entry in entries:
            if not entry:
                continue
            vid = entry.get("id") or entry.get("url", "")
            if not vid:
                continue
            upload_raw = entry.get("upload_date", "")
            if not _is_after(upload_raw, since_date):
                continue

            title = entry.get("title", "Unknown")
            url = entry.get("url") or f"https://www.youtube.com/watch?v={vid}"

            videos.append(
                VideoMeta(
                    id=vid,
                    title=title,
                    url=url if url.startswith("http") else f"https://www.youtube.com/watch?v={vid}",
                    upload_date=_parse_upload_date(upload_raw),
                    transcript=None,
                )
            )

        return videos

    except Exception as e:
        logger.warning("Failed to fetch videos from %s: %s", channel_url, e)
        return []


def fetch_transcript(video_id: str) -> str | None:
    """Fetch transcript for a YouTube video by ID.

    Returns None if transcripts are disabled, unavailable, or any error occurs.
    """
    if not video_id:
        return None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
        )

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        # transcript_list is a list of {text, start, duration} dicts
        text = " ".join(
            snippet.get("text", "") for snippet in transcript_list
        ).strip()
        return text if text else None

    except Exception as e:
        logger.debug("No transcript for %s: %s", video_id, e)
        return None


# Import yt_dlp at module level but guard it
try:
    import yt_dlp
except ImportError:
    yt_dlp = None  # type: ignore
    logger.warning("yt-dlp not installed — fetcher will return empty lists")
