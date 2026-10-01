"""LLM-based prediction extractor — sends transcripts to an LLM and parses predictions."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx

from src.models import Prediction

logger = logging.getLogger(__name__)

# LLM endpoints — try Hermes proxy first, fall back to Ollama
LLM_ENDPOINTS = [
    {"url": "http://127.0.0.1:8081/v1/chat/completions", "model": "qwen3-coder:30b"},
    {
        "url": "http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions",
        "model": "qwen3-coder:30b-32k",
    },
]

VALID_CATEGORIES = {"finance", "energy", "ukraine", "china", "ai", "geopolitics"}


def _build_prompt(transcript: str, individual_name: str, categories: list[str]) -> list[dict]:
    """Build the chat messages for the LLM."""
    cats_str = ", ".join(categories)
    system_msg = (
        "You are an analyst extracting predictions from transcripts. "
        "Extract specific, testable predictions or forecasts made by the speaker. "
        f"Classify each prediction into one of these categories: {cats_str}. "
        "If a prediction doesn't fit any of those categories, use 'other'. "
        "Return a JSON array of objects with keys: 'claim', 'category', 'excerpt'. "
        "'excerpt' should be the relevant 1-2 sentence quote from the transcript. "
        "Only include predictions made by the speaker in their own voice. "
        "Never extract predictions from quoted material, blockquotes, tweets, or statements "
        "attributed to other people - even if the speaker appears to endorse them. "
        "If a claim is inside quotation marks or attributed to someone else, exclude it. "
        "Only include predictions (things that WILL happen or are predicted to happen IN THE FUTURE), "
        "not opinions, statements of fact, or things that already happened. "
        "Do NOT include predictions about past events or dates that have already passed. "
        "If a claim references a year that is already in the past relative to the video date, exclude it. "
        "Maximum 2 predictions per video. "
        "Prioritize predictions with specific dates, timeframes, or measurable outcomes. "
        "If no predictions are found, return an empty array []."
    )
    user_msg = f"Transcript from {individual_name}:\n\n{transcript[:8000]}"
    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _call_llm(messages: list[dict]) -> str | None:
    """Try each LLM endpoint until one works. Returns the content string or None."""
    for endpoint in LLM_ENDPOINTS:
        try:
            resp = httpx.post(
                endpoint["url"],
                json={
                    "model": endpoint["model"],
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        except Exception as e:
            logger.debug("LLM endpoint %s failed: %s", endpoint["url"], e)
            continue
    return None


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from LLM output, which may have markdown fences or extra text."""
    if not text:
        return []

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try finding JSON array within markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        try:
            result = json.loads(fence_match.group(1).strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Try finding a JSON array with regex
    array_match = re.search(r"\[.*\]", text, re.DOTALL)
    if array_match:
        try:
            result = json.loads(array_match.group(0))
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return []


def _validate_category(category: str, valid_categories: list[str]) -> str:
    """Ensure category is valid; default to 'other' if not."""
    category = category.lower().strip() if category else "other"
    if category not in valid_categories and category not in VALID_CATEGORIES:
        return "other"
    return category


def extract_predictions(
    transcript: str | None,
    video_url: str,
    individual_name: str,
    categories: list[str],
    upload_date: str | None = None,
) -> list[Prediction]:
    """Extract predictions from a transcript using an LLM.

    Args:
        transcript: The video/article transcript text
        video_url: Source URL for the transcript
        individual_name: Name of the person making predictions
        categories: List of valid category labels

    Returns:
        List of Prediction objects. Empty if transcript is empty/None or LLM fails.
    """
    if not transcript or not transcript.strip():
        return []

    messages = _build_prompt(transcript, individual_name, categories)
    raw = _call_llm(messages)

    if not raw:
        logger.warning("LLM returned no content for %s", video_url)
        return []

    items = _extract_json_array(raw)
    if not items:
        logger.warning("No valid JSON array extracted from LLM response for %s", video_url)
        return []

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    predictions: list[Prediction] = []

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        claim = item.get("claim", "").strip()
        if not claim:
            continue
        category = _validate_category(item.get("category", "other"), categories)
        excerpt = item.get("excerpt", "").strip()

        # Use the video's upload date if provided, else today
        from datetime import date as date_cls
        if upload_date:
            try:
                pred_date = date_cls.fromisoformat(upload_date)
            except (ValueError, TypeError):
                pred_date = datetime.now().date()
        else:
            pred_date = datetime.now().date()

        pred = Prediction(
            id=f"pred_{timestamp}_{i:03d}",
            individual_name=individual_name,
            date=pred_date,
            category=category,
            claim=claim,
            source_url=video_url,
            transcript_excerpt=excerpt,
            verdict=None,
        )
        predictions.append(pred)

    return predictions
