"""Tests for the YouTube fetcher."""

from src.fetcher import fetch_recent_videos, fetch_transcript, VideoMeta
from datetime import date


def test_fetch_returns_list():
    """Fetch from Peter Zeihan's channel — should return a list (possibly empty if network issues)."""
    videos = fetch_recent_videos(
        "https://www.youtube.com/@ZeihanonGeopolitics/videos", date(2024, 1, 1), limit=3
    )
    assert isinstance(videos, list)
    # If we got videos, check structure
    if videos:
        v = videos[0]
        assert hasattr(v, "id")
        assert hasattr(v, "title")
        assert hasattr(v, "url")
        assert hasattr(v, "upload_date")


def test_video_meta_dataclass():
    """VideoMeta should be constructible with expected fields."""
    vm = VideoMeta(
        id="abc123",
        title="Test Video",
        url="https://youtube.com/watch?v=abc123",
        upload_date="2024-03-15",
    )
    assert vm.id == "abc123"
    assert vm.transcript is None


def test_fetch_transcript_none_for_invalid():
    """fetch_transcript should return None for invalid IDs, not crash."""
    result = fetch_transcript("INVALID_ID_12345")
    assert result is None
