# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Fix prediction dates by looking up actual YouTube upload dates."""
import json
import re
from datetime import date

DATA = 'data/predictions.json'

with open(DATA, 'r', encoding='utf-8') as f:
    data = json.load(f)

preds = data['predictions']

# Collect all unique video IDs
video_dates = {}

def get_upload_date(video_id):
    """Use yt-dlp to get the upload date for a YouTube video."""
    if video_id in video_dates:
        return video_dates[video_id]
    try:
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            raw = info.get("upload_date", "")
            if raw and len(raw) >= 8:
                iso = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
                video_dates[video_id] = iso
                return iso
    except Exception as e:
        print(f"  Failed to get date for {video_id}: {e}")
    video_dates[video_id] = None
    return None

# Extract video ID from YouTube URL
def extract_video_id(url):
    m = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url or '')
    return m.group(1) if m else None

# Fix each prediction
fixed = 0
for p in preds:
    url = p.get('source_url', '')
    vid = extract_video_id(url)
    if vid:
        upload = get_upload_date(vid)
        if upload:
            old = p.get('date', '')
            p['date'] = upload
            if old != upload:
                fixed += 1
                print(f"  {vid}: {old} -> {upload}")

print(f"\nFixed {fixed} predictions out of {len(preds)} total")

# Save
with open(DATA, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("Saved.")
