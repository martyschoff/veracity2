# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Comprehensive fetch + extract script — fetches all videos, transcripts, and predictions for 3 tracked individuals."""

import sys, os, json, logging, time, hashlib
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(__file__))

import yt_dlp
import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from src.store import Store
from src.models import Individual, Prediction

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "predictions.json")
SINCE_DATE = date(2024, 1, 1)
ALL_CATEGORIES = ["finance", "energy", "ukraine", "china", "ai", "geopolitics"]

LLM_URL = "http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions"
LLM_MODEL = "qwen3-coder:30b-32k"

# --- 12 Panelists (NOT tracked individuals, just stored for future veracity evaluation) ---
PANELISTS = [
    {"name": "UnHerd", "handle": "unherd", "categories": ["geopolitics"], "sources": ["https://www.youtube.com/@unherd/videos"]},
    {"name": "Jeff Snider (Eurodollar University)", "handle": "eurodollar", "categories": ["finance", "geopolitics"], "sources": ["https://www.youtube.com/@EurodollarUniversity/videos"]},
    {"name": "Viktoriya M Finance", "handle": "viktoriya", "categories": ["finance"], "sources": ["https://www.youtube.com/@ViktoriyaMFinance/videos"]},
    {"name": "David McAlvany (McAlvany Financial)", "handle": "mcalvany", "categories": ["finance"], "sources": ["https://www.youtube.com/@McAlvanyFinancialGroup/videos"]},
    {"name": "Ian Bremmer (GZERO Media)", "handle": "gzero", "categories": ["geopolitics"], "sources": ["https://www.youtube.com/@GZEROMedia/videos"]},
    {"name": "Stephen Miller (White House)", "handle": "smiller", "categories": ["geopolitics"], "sources": ["https://www.whitehouse.gov"]},
    {"name": "H.R. McMaster", "handle": "mcmaster", "categories": ["geopolitics"], "sources": ["https://www.youtube.com/results?search_query=HR+McMaster+geopolitics"]},
    {"name": "Niall Ferguson", "handle": "nferguson", "categories": ["geopolitics"], "sources": ["https://www.youtube.com/results?search_query=Niall+Ferguson"]},
    {"name": "John Cochrane", "handle": "jcochrane", "categories": ["finance"], "sources": ["https://www.youtube.com/results?search_query=John+Cochrane+economics"]},
    {"name": "Stephen Kotkin", "handle": "skotkin", "categories": ["geopolitics"], "sources": ["https://www.youtube.com/results?search_query=Stephen+Kotkin"]},
    {"name": "Victor Davis Hanson", "handle": "vdhanson", "categories": ["geopolitics"], "sources": ["https://www.youtube.com/results?search_query=Victor+Davis+Hanson"]},
    {"name": "Kevin Hassett (White House)", "handle": "khassett", "categories": ["finance"], "sources": ["https://www.whitehouse.gov"]},
]

TRACKED_INDIVIDUALS = [
    Individual(
        name="Peter Zeihan",
        handle="zeihan",
        sources=["https://www.youtube.com/@ZeihanonGeopolitics/videos"],
        categories=["geopolitics", "energy", "china", "ukraine", "finance"]
    ),
    Individual(
        name="Doomberg",
        handle="doomberg",
        sources=["https://newsletter.doomberg.com", "https://www.youtube.com/results?search_query=doomberg"],
        categories=["energy", "finance", "geopolitics"]
    ),
    Individual(
        name="Peter Diamandis",
        handle="diamandis",
        sources=["https://www.youtube.com/@PeterHDiamandis/videos"],
        categories=["ai"]
    ),
]


def list_channel_videos(channel_url: str, limit: int = 30) -> list[dict]:
    """List videos from a YouTube channel using yt-dlp flat extraction, with full metadata."""
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlistend": limit,
    }
    videos = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
        entries = info.get("entries", []) or []
        for entry in entries:
            if not entry:
                continue
            vid = entry.get("id") or entry.get("url", "")
            if not vid:
                continue
            title = entry.get("title", "Unknown")
            upload_date_raw = entry.get("upload_date", "")
            # If flat extraction doesn't have upload_date, try to get it
            if not upload_date_raw:
                try:
                    full_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
                    with yt_dlp.YoutubeDL(full_opts) as ydl2:
                        full_info = ydl2.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                        if full_info:
                            upload_date_raw = full_info.get("upload_date", "")
                except Exception:
                    pass
            videos.append({
                "id": vid,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "upload_date_raw": upload_date_raw,
            })
    except Exception as e:
        logger.warning("Failed to list videos from %s: %s", channel_url, e)
    return videos


def search_youtube_videos(query: str, limit: int = 20) -> list[dict]:
    """Search YouTube for videos matching a query using yt-dlp."""
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlistend": limit,
    }
    videos = []
    try:
        search_url = f"ytsearch{limit}:{query}"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(search_url, download=False)
        entries = info.get("entries", []) or []
        for entry in entries:
            if not entry:
                continue
            vid = entry.get("id") or entry.get("url", "")
            if not vid:
                continue
            title = entry.get("title", "Unknown")
            upload_date_raw = entry.get("upload_date", "")
            # Get full upload date
            if not upload_date_raw:
                try:
                    full_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
                    with yt_dlp.YoutubeDL(full_opts) as ydl2:
                        full_info = ydl2.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                        if full_info:
                            upload_date_raw = full_info.get("upload_date", "")
                except Exception:
                    pass
            videos.append({
                "id": vid,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "upload_date_raw": upload_date_raw,
            })
    except Exception as e:
        logger.warning("Failed to search YouTube for %s: %s", query, e)
    return videos


def fetch_transcript(video_id: str) -> str | None:
    """Fetch transcript for a YouTube video using youtube_transcript_api."""
    if not video_id:
        return None
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        text = " ".join(snippet.text for snippet in transcript).strip()
        return text if text else None
    except Exception as e:
        logger.debug("No transcript for %s: %s", video_id, e)
        return None


def call_llm(transcript: str, individual_name: str, categories: list[str]) -> list[dict]:
    """Send transcript to LLM and extract predictions."""
    cats_str = ", ".join(categories)
    system_msg = (
        "You are an analyst extracting predictions from transcripts. "
        "Extract specific, testable predictions or forecasts made by the speaker. "
        f"Classify each prediction into one of these categories: {cats_str}. "
        "If a prediction doesn't fit any of those categories, use 'other'. "
        "Return a JSON array of objects with keys: 'claim', 'category', 'excerpt'. "
        "'excerpt' should be the relevant 1-2 sentence quote from the transcript. "
        "Only include predictions (things that will happen or are predicted to happen), "
        "not opinions or statements of fact. If no predictions are found, return an empty array []."
    )
    user_msg = f"Transcript from {individual_name}:\n\n{transcript[:8000]}"
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
    try:
        resp = httpx.post(
            LLM_URL,
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 2000,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            # Try to extract JSON array from the response
            import re
            # Try direct parse
            try:
                result = json.loads(content)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
            # Try markdown fences
            fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
            if fence_match:
                try:
                    result = json.loads(fence_match.group(1).strip())
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass
            # Try finding JSON array
            array_match = re.search(r"\[.*\]", content, re.DOTALL)
            if array_match:
                try:
                    result = json.loads(array_match.group(0))
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass
            return []
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return []


def main():
    store = Store(DATA_PATH)

    # Add tracked individuals
    for ind in TRACKED_INDIVIDUALS:
        store.add_individual(ind)
        logger.info("Added individual: %s (%s)", ind.name, ind.handle)

    # Add panelists as individuals (for future veracity evaluation)
    for p in PANELISTS:
        ind = Individual(
            name=p["name"],
            handle=p["handle"],
            sources=p["sources"],
            categories=p["categories"],
        )
        store.add_individual(ind)
        logger.info("Added panelist: %s (%s)", p["name"], p["handle"])

    # Fetch videos and transcripts for each tracked individual
    for ind in TRACKED_INDIVIDUALS:
        logger.info("=" * 60)
        logger.info("Processing: %s", ind.name)
        logger.info("=" * 60)
        total_preds = 0

        all_videos = []
        for source_url in ind.sources:
            if "youtube.com/@ZeihanonGeopolitics" in source_url or "youtube.com/@PeterHDiamandis" in source_url:
                logger.info("  Listing channel videos from %s", source_url)
                vids = list_channel_videos(source_url, limit=30)
                all_videos.extend(vids)
                logger.info("  Found %d videos from channel", len(vids))
            elif "search_query" in source_url:
                # For Doomberg, search YouTube
                logger.info("  Searching YouTube for 'doomberg'")
                vids = search_youtube_videos("doomberg", limit=20)
                all_videos.extend(vids)
                logger.info("  Found %d videos from search", len(vids))
            else:
                logger.info("  Skipping non-YouTube source: %s", source_url)

        # Dedupe by video id
        seen_ids = set()
        unique_videos = []
        for v in all_videos:
            if v["id"] not in seen_ids:
                seen_ids.add(v["id"])
                unique_videos.append(v)

        logger.info("  Total unique videos: %d", len(unique_videos))

        # Process each video
        for i, video in enumerate(unique_videos):
            logger.info("  [%d/%d] Processing: %s", i + 1, len(unique_videos), video["title"][:80])

            transcript = fetch_transcript(video["id"])
            if not transcript or len(transcript.strip()) < 100:
                logger.info("    No transcript available, skipping")
                continue

            logger.info("    Got transcript (%d chars)", len(transcript))

            # Extract predictions via LLM
            items = call_llm(transcript, ind.name, ALL_CATEGORIES)
            if not items:
                logger.info("    No predictions extracted")
                continue

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            for j, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                claim = item.get("claim", "").strip()
                if not claim:
                    continue
                category = item.get("category", "other").lower().strip()
                if category not in ALL_CATEGORIES and category != "other":
                    category = "other"
                excerpt = item.get("excerpt", "").strip()

                # Generate unique ID using hash to avoid collisions
                id_hash = hashlib.md5(f"{video['id']}_{j}_{claim[:50]}".encode()).hexdigest()[:12]
                pred = Prediction(
                    id=f"pred_{timestamp}_{id_hash}",
                    individual_name=ind.name,
                    date=datetime.now().date(),
                    category=category,
                    claim=claim,
                    source_url=video["url"],
                    transcript_excerpt=excerpt,
                    verdict=None,
                )
                store.add_prediction(pred)
                total_preds += 1
                logger.info("    Extracted: [%s] %s", category, claim[:80])

            time.sleep(1)  # Rate limit

        logger.info("Total predictions for %s: %d", ind.name, total_preds)

    # Summary
    total = len(store.get_all())
    logger.info("=" * 60)
    logger.info("COMPLETE! Total predictions in store: %d", total)
    logger.info("Total individuals: %d", len(store.individuals()))
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
