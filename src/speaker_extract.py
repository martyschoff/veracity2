# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Speaker attribution for multi-person YouTube videos.

Given a video title + description + transcript (YouTube captions, anonymous '>>' turns),
identifies the speaker cast, attributes predictions to NAMED speakers, and allocates
them to the tracked roster (data/predictions.json individuals) or the guest pool
(data/guest_pool.json). Predictions that cannot be confidently bound to a NAMED
speaker are SKIPPED — never guessed.

Endpoints: nimo128 gateway Ollama first (HermesMac host), local llama-server fallback.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# nimo128 remote gateway bot (Unitary memory machine on HermesMac) — Ollama, no auth.
NIMO128_ENDPOINT = {
    "url": "http://100.84.167.88:11500/v1/chat/completions",
    "model": "qwen3:32b",
    "label": "nimo128 (Ollama qwen3:32b on HermesMac)",
}
FALLBACK_ENDPOINT = {
    "url": "http://127.0.0.1:18434/v1/chat/completions",
    "model": "Qwen3.8-27B-UD-Q4_K_M",
    "key": "OyISwmqwQMak4mEOtO3zajuzSY8clG73",
    "label": "local llama-server Qwen3.8-27B",
}
ENDPOINTS = [NIMO128_ENDPOINT, FALLBACK_ENDPOINT]

TRACKED_NAMES = [
    "Peter Zeihan",
    "Doomberg",
    "Peter Diamandis",
    "Ian Bremmer",
    "David McAlvany",
]

VALID_CATEGORIES = {"finance", "energy", "ukraine", "china", "ai", "geopolitics"}
GUEST_POOL_PATH = "data/guest_pool.json"

_endpoint_used: str | None = None


def get_endpoint_used() -> str | None:
    return _endpoint_used


def call_llm(messages: list[dict], max_tokens: int = 2500, temperature: float = 0.2) -> str | None:
    """Try each endpoint until one works. Reasoning-model safe: max_tokens floor and
    reasoning_content fallback. Records which endpoint served the last successful call."""
    global _endpoint_used
    for ep in ENDPOINTS:
        headers = {}
        if ep.get("key"):
            headers["Authorization"] = f"Bearer {ep['key']}"
        try:
            resp = httpx.post(
                ep["url"],
                json={
                    "model": ep["model"],
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max(max_tokens, 1500),
                },
                headers=headers,
                timeout=600.0,
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            if not content:
                content = (msg.get("reasoning_content") or "").strip()
            if content:
                _endpoint_used = ep["label"]
                return content
        except Exception as e:
            logger.warning("LLM endpoint %s failed: %s", ep["url"], e)
            continue
    return None


def _extract_json(text: str | None) -> Any | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    for pat in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    return None


def identify_speakers(title: str, description: str, transcript: str) -> dict:
    """Return {"speakers": [{"name","role","evidence"}], "single_person": bool}.

    Uses introductions, self-identification, and name-drops. Single-person videos
    short-circuit to the channel owner / solo speaker.
    """
    system = (
        "You identify the speakers in a YouTube video from its title, description and caption "
        "transcript. Captions mark speaker turns with '>>' but do NOT name the speakers.\n"
        "Identify the cast of real, NAMED people who speak, using as evidence: introductions "
        "('my guest today is...'), self-identification ('I'm Peter Diamandis'), and name-drops "
        "where someone is clearly being addressed or quoted at length.\n"
        "Rules:\n"
        "- Each speaker's name must be a real full name actually stated in the video metadata or "
        "transcript. NEVER invent names.\n"
        "- A person named in the TITLE (e.g. '— Morgan Housel' or 'Guest: X') is speaking in the "
        "video; include them as a guest unless the description/transcript proves otherwise.\n"
        "- role is 'host' or 'guest'.\n"
        "- If the video is a single-person solo video (one narrator, no interview), return just "
        "that person with role 'host' and set single_person to true.\n"
        "- If you cannot confidently name a person who speaks, do NOT include them.\n"
        'Return ONLY JSON: {"speakers": [{"name": "...", "role": "host|guest", "evidence": "..."}], '
        '"single_person": true|false}'
    )
    user = (
        f"TITLE: {title}\n\nDESCRIPTION:\n{description[:2500]}\n\n"
        f"TRANSCRIPT (first part):\n{transcript[:9000]}"
    )
    raw = call_llm([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    data = _extract_json(raw) or {}
    speakers = [s for s in data.get("speakers", []) if isinstance(s, dict) and s.get("name")]
    return {"speakers": speakers, "single_person": bool(data.get("single_person"))}


_ATTRIBUTION_SYSTEM = (
    "You extract market/geopolitical PREDICTIONS from a YouTube transcript and attribute each "
    "to the correct speaker. The transcript marks speaker turns with '>>' but does not name "
    "them; use the provided cast list plus conversational cues (direct address, introductions, "
    "who answers which question) to decide who is talking.\n"
    "STRICT RULES:\n"
    "- Only include predictions made in the speaker's OWN voice. NEVER include anything inside "
    "quotation marks or attributed to a third party, even if the speaker endorses it.\n"
    "- Every prediction MUST name its speaker from the cast list. If you cannot confidently "
    "bind a claim to a NAMED speaker, put it in 'unattributed' instead — do not guess.\n"
    "- Only future predictions (things that WILL happen), not facts, past events, or opinions "
    "about the present. Exclude claims referencing a year already past relative to the video date.\n"
    "- Maximum 2 predictions for the whole video, prioritizing measurable claims (specific "
    "dates, quantities, timeframes).\n"
    '- Category must be one of: finance, energy, ukraine, china, ai, geopolitics, other.\n'
    'Return ONLY JSON: {"predictions": [{"speaker": "<cast name>", "claim": "...", '
    '"category": "...", "excerpt": "..."}], "unattributed": ["..."]}'
)


def extract_attributed_predictions(
    title: str,
    description: str,
    transcript: str | None,
    video_url: str,
    upload_date: str | None = None,
    categories: list[str] | None = None,
    channel_owner: str | None = None,
    debug_raw_path: str | None = None,
) -> dict:
    """Identify the cast and extract predictions attributed to NAMED speakers.

    Returns {"speakers": [...], "predictions": [...], "unattributed": [...], "video_url",
    "upload_date"}. Predictions are dicts with speaker, claim, category, excerpt.
    """
    result: dict[str, Any] = {
        "video_url": video_url,
        "upload_date": upload_date,
        "speakers": [],
        "predictions": [],
        "unattributed": [],
    }
    if not transcript or not transcript.strip():
        return result

    cats = categories or list(VALID_CATEGORIES)
    cast = identify_speakers(title, description or "", transcript)
    result["speakers"] = cast["speakers"]
    named = [s["name"] for s in cast["speakers"]]

    if not named:
        return result

    # Single-person short-circuit: sole speaker is the channel owner; attribution is trivial.
    if cast["single_person"] or len(named) == 1:
        sole = named[0] if cast["single_person"] else named[0]
        if channel_owner and not cast["single_person"]:
            sole = channel_owner
        attribution_hint = (
            f"This is a SINGLE-PERSON video. All predictions are made by {sole}. "
            f'For every prediction set "speaker" to "{sole}".'
        )
    else:
        cast_desc = "; ".join(f"{s['name']} ({s.get('role', '?')})" for s in cast["speakers"])
        attribution_hint = f"Speaker cast: {cast_desc}."

    user = (
        f"TITLE: {title}\nVIDEO DATE: {upload_date or 'unknown'}\n{attribution_hint}\n\n"
        f"DESCRIPTION:\n{(description or '')[:2000]}\n\nTRANSCRIPT:\n{transcript[:22000]}"
    )
    raw = call_llm([
        {"role": "system", "content": _ATTRIBUTION_SYSTEM},
        {"role": "user", "content": user},
    ])
    if debug_raw_path:
        with open(debug_raw_path, "w", encoding="utf-8") as f:
            f.write(raw or "EMPTY")
    data = _extract_json(raw) or {}
    if not isinstance(data, dict):
        return result

    # Parse upload year for the past-year post-filter.
    upload_year = None
    if upload_date:
        m = re.search(r"(20\d{2})", str(upload_date))
        if m:
            upload_year = int(m.group(1))

    for item in data.get("predictions", []):
        if not isinstance(item, dict):
            continue
        claim = (item.get("claim") or "").strip()
        speaker = (item.get("speaker") or "").strip()
        if not claim:
            continue
        # Never attribute to someone outside the verified cast.
        if speaker not in named:
            result["unattributed"].append(claim)
            continue
        # Quote guard: claims that are themselves quotes of others are excluded upstream,
        # but strip any residual quoted segment.
        category = (item.get("category") or "other").lower().strip()
        if category not in cats and category not in VALID_CATEGORIES:
            category = "other"
        # Post-filter: past-year references.
        if upload_year:
            years = [int(y) for y in re.findall(r"\b20\d{2}\b", claim)]
            if years and max(years) < upload_year:
                continue
        result["predictions"].append({
            "speaker": speaker,
            "claim": claim,
            "category": category,
            "excerpt": (item.get("excerpt") or "").strip(),
        })

    result["unattributed"].extend(
        c for c in data.get("unattributed", []) if isinstance(c, str)
    )
    # Hard cap: max 2 predictions per video.
    result["predictions"] = result["predictions"][:2]
    return result


def allocate_roster(attributed: dict) -> dict:
    """Split attributed predictions into tracked-roster entries vs guest pool rows.

    Returns {"tracked": {name: [prediction,...]}, "guests": [...]}.
    Nothing is written here; callers decide persistence (guest rows go to
    data/guest_pool.json; tracked rows would go to predictions.json under
    individual_name = the exact TRACKED_NAMES entry).
    """
    tracked: dict[str, list[dict]] = {}
    guests: list[dict] = []
    for pred in attributed.get("predictions", []):
        speaker = pred["speaker"]
        match = next((t for t in TRACKED_NAMES if t.lower() == speaker.lower()), None)
        row = {
            "speaker": speaker,
            "claim": pred["claim"],
            "category": pred["category"],
            "date": attributed.get("upload_date"),
            "source_url": attributed.get("video_url"),
            "excerpt": pred.get("excerpt", ""),
        }
        if match:
            row["individual_name"] = match
            tracked.setdefault(match, []).append(row)
        else:
            guests.append(row)
    return {"tracked": tracked, "guests": guests}


def log_guests(guests: list[dict], path: str = GUEST_POOL_PATH) -> int:
    """Append guest-pool rows to the side file (NOT predictions.json). Returns rows added."""
    if not guests:
        return 0
    existing = []
    try:
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    except (OSError, json.JSONDecodeError):
        existing = []
    seen = {(g.get("source_url"), g.get("claim")) for g in existing}
    added = 0
    for g in guests:
        key = (g.get("source_url"), g.get("claim"))
        if key in seen:
            continue
        existing.append(g)
        seen.add(key)
        added += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=1)
    return added
