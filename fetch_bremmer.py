"""Fetch Ian Bremmer's Quick Take predictions from GZERO Media YouTube channel."""
import json
import re
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DATA = 'data/predictions.json'
SINCE = date(2024, 1, 1)
CATEGORIES = ["finance", "energy", "ukraine", "china", "ai", "geopolitics"]

import yt_dlp
import httpx

def fetch_quick_takes():
    """Fetch recent videos from GZERO Media, focusing on Quick Takes and Ian Explains."""
    url = "https://www.youtube.com/@GZEROMedia/videos"
    opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlistend": 50,
    }
    videos = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries", []) or []
    for entry in entries:
        if not entry:
            continue
        title = entry.get("title", "")
        vid = entry.get("id") or entry.get("url", "")
        if not vid:
            continue
        # ONLY include Quick Takes / Ian Explains / Ask Ian — skip everything else
        title_lower = title.lower()
        if not any(kw in title_lower for kw in ["quick take", "ian explain", "ian bremmer explain", "ask ian"]):
            logger.debug("Skipping non-Quick-Take: %s", title)
            continue
        # Get upload date
        upload_raw = ""
        try:
            full_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
            with yt_dlp.YoutubeDL(full_opts) as ydl2:
                full_info = ydl2.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                if full_info:
                    upload_raw = full_info.get("upload_date", "")
                    # Also get the full title
                    title = full_info.get("title", title)
        except Exception:
            pass

        upload_iso = ""
        if upload_raw and len(upload_raw) >= 8:
            upload_iso = f"{upload_raw[0:4]}-{upload_raw[4:6]}-{upload_raw[6:8]}"

        videos.append({
            "id": vid,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "upload_date": upload_iso,
        })
        logger.info("Found: %s (%s) - %s", title, upload_iso, vid)

    logger.info("Total videos found: %d", len(videos))
    return videos

def fetch_transcript(video_id):
    """Fetch transcript using yt-dlp (youtube_transcript_api is IP-blocked)."""
    try:
        import yt_dlp as _ydl
        import urllib.request
        opts = {
            "quiet": True, "no_warnings": True, "skip_download": True,
            "writesubtitles": True, "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-orig"],
            "subtitlesformat": "json3",
        }
        with _ydl.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        subs = info.get("subtitles", {}) or {}
        auto = info.get("automatic_captions", {}) or {}
        en = subs.get("en") or subs.get("en-US") or auto.get("en") or auto.get("en-US")
        if not en:
            return None
        url = en[0].get("url", "")
        if not url:
            return None
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        texts = []
        for event in data.get("events", []):
            segs = event.get("segs", [])
            line = "".join(s.get("utf8", "") for s in segs).strip()
            if line:
                texts.append(line)
        text = " ".join(texts).strip()
        return text if text else None
    except Exception as e:
        logger.debug("No transcript for %s: %s", video_id, e)
        return None

def extract_predictions(transcript, video_url, individual_name, categories, upload_date=None):
    """Send transcript to LLM and extract predictions."""
    LLM_ENDPOINTS = [
        {"url": "http://127.0.0.1:8081/v1/chat/completions", "model": "qwen3.8-27b"},
        {"url": "http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions", "model": "qwen3-coder:30b-32k"},
    ]
    cats_str = ", ".join(categories)
    system_msg = (
        "You are an analyst extracting predictions from transcripts. "
        "Extract specific, testable predictions or forecasts made by the speaker. "
        f"Classify each prediction into one of these categories: {cats_str}. "
        "If a prediction doesn't fit any of those categories, use 'other'. "
        "Return a JSON array of objects with keys: 'claim', 'category', 'excerpt'. "
        "'excerpt' should be the relevant 1-2 sentence quote from the transcript. "
        "Only include predictions (things that WILL happen or are predicted to happen IN THE FUTURE), "
        "not opinions, statements of fact, or things that already happened. "
        "Do NOT include predictions about past events or dates that have already passed. "
        "If a claim references a year that is already in the past relative to the video date, exclude it. "
        "Maximum 2 predictions per video. "
        "Prioritize predictions with specific dates, timeframes, or measurable outcomes. "
        "If no predictions are found, return an empty array []."
    )
    user_msg = f"Transcript from {individual_name}:\n\n{transcript[:8000]}"
    messages = [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}]

    for endpoint in LLM_ENDPOINTS:
        try:
            resp = httpx.post(
                endpoint["url"],
                json={"model": endpoint["model"], "messages": messages, "temperature": 0.3, "max_tokens": 2000},
                timeout=60.0,
            )
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            if choices:
                raw = choices[0].get("message", {}).get("content", "")
                break
        except Exception as e:
            logger.debug("LLM endpoint %s failed: %s", endpoint["url"], e)
            raw = None
            continue
    else:
        return []

    if not raw:
        return []

    # Parse JSON array
    items = []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        fence = re.search(r'```(?:json)?\s*\n?(.*?)```', raw, re.DOTALL)
        if fence:
            try:
                items = json.loads(fence.group(1).strip())
            except json.JSONDecodeError:
                pass
        if not items:
            arr = re.search(r'\[.*\]', raw, re.DOTALL)
            if arr:
                try:
                    items = json.loads(arr.group(0))
                except json.JSONDecodeError:
                    pass

    if not items:
        return []

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    VALID = {"finance", "energy", "ukraine", "china", "ai", "geopolitics"}
    predictions = []

    for i, item in enumerate(items[:2]):  # Max 2 per video
        if not isinstance(item, dict):
            continue
        claim = item.get("claim", "").strip()
        if not claim:
            continue
        cat = item.get("category", "other").lower().strip()
        if cat not in VALID and cat not in categories:
            cat = "other"
        excerpt = item.get("excerpt", "").strip()

        from datetime import date as date_cls
        if upload_date:
            try:
                pred_date = date_cls.fromisoformat(upload_date)
            except (ValueError, TypeError):
                pred_date = datetime.now().date()
        else:
            pred_date = datetime.now().date()

        pred = {
            "id": f"pred_{timestamp}_{i:03d}",
            "individual_name": individual_name,
            "date": pred_date.isoformat(),
            "category": cat,
            "claim": claim,
            "source_url": video_url,
            "transcript_excerpt": excerpt,
            "verdict": None,
            "created_at": datetime.now().isoformat(),
        }
        predictions.append(pred)

    return predictions

def main():
    with open(DATA, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Make sure Ian Bremmer is a tracked individual
    existing_names = {i['name'] for i in data['individuals']}
    if 'Ian Bremmer' not in existing_names:
        data['individuals'].append({
            'name': 'Ian Bremmer',
            'handle': 'gzero',
            'sources': ['https://www.youtube.com/@GZEROMedia/videos'],
            'categories': ['geopolitics']
        })
        logger.info("Added Ian Bremmer as tracked individual")

    # Fetch videos
    videos = fetch_quick_takes()

    # Get existing prediction source URLs to avoid duplicates
    existing_urls = {p['source_url'] for p in data['predictions'] if 'bremmer' in p.get('individual_name', '').lower()}

    total_added = 0
    for video in videos[:15]:  # Process up to 15 recent videos
        if video['url'] in existing_urls:
            logger.info("Skipping already-fetched: %s", video['title'])
            continue

        logger.info("Processing: %s (%s)", video['title'], video['upload_date'])
        transcript = fetch_transcript(video['id'])
        if not transcript:
            logger.info("  No transcript available, skipping")
            continue

        preds = extract_predictions(
            transcript=transcript,
            video_url=video['url'],
            individual_name="Ian Bremmer",
            categories=CATEGORIES,
            upload_date=video['upload_date'],
        )

        for pred in preds:
            # Dedup by checking if we already have this claim from this URL
            dupes = [p for p in data['predictions'] if p['source_url'] == video['url'] and p['claim'] == pred['claim']]
            if not dupes:
                data['predictions'].append(pred)
                total_added += 1
                logger.info("  Extracted: [%s] %s", pred['category'], pred['claim'][:80])

    logger.info("Total new predictions for Bremmer: %d", total_added)

    with open(DATA, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Saved. Total predictions: %d", len(data['predictions']))

if __name__ == '__main__':
    main()
