# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Market signal integration: match claims to Polymarket markets.

Phase 4 from DESIGN_STEALS.md - uses embeddings for semantic matching.

Polymarket CLOB API: https://docs.polymarket.com/
- Markets list: GET https://clob.polymarket.com/markets
- Market details: GET https://clob.polymarket.com/markets/{condition_id}
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np

logger = logging.getLogger("market_matcher")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
MARKET_CACHE_FILE = DATA_DIR / "polymarket_cache.json"
MARKET_CONFLICTS_FILE = DATA_DIR / "market_conflicts.jsonl"

# Polymarket CLOB API
POLYMARKET_API = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

# Matching thresholds (from DESIGN_STEALS.md)
AUTO_MATCH_THRESHOLD = 0.85
REVIEW_MATCH_THRESHOLD = 0.75
VOLUME_THRESHOLD = 50000  # $50k minimum volume
MIN_PRICE_HISTORY = 3  # minimum data points


def load_dotenv() -> None:
    """Load .env file for API keys."""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip().strip("\"'")
                    os.environ.setdefault(key, value)


def get_embedding(text: str, model: str = "text-embedding-3-large") -> list[float] | None:
    """Get embedding from OpenAI API."""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, trying local embeddings")
        return get_local_embedding(text)

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"input": text, "model": model},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
    except Exception as e:
        logger.error("OpenAI embedding failed: %s", e)
        return get_local_embedding(text)


def get_local_embedding(text: str) -> list[float] | None:
    """Fallback: get embedding from local Ollama nomic-embed-text."""
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                "http://100.84.167.88:11434/api/embed",
                json={"model": "nomic-embed-text", "input": [text]},
            )
            resp.raise_for_status()
            return (resp.json().get("embeddings") or [[None]])[0]
    except Exception as e:
        logger.debug("Local embedding failed: %s", e)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np, b_np = np.array(a), np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np)))


def fetch_polymarket_markets(limit: int = 500) -> list[dict]:
    """Fetch active markets from Polymarket Gamma API."""
    markets = []
    try:
        with httpx.Client(timeout=30.0) as client:
            # Gamma API provides enriched market data
            resp = client.get(
                f"{GAMMA_API}/markets",
                params={"limit": limit, "active": "true", "closed": "false"},
                headers={"User-Agent": "Mozilla/5.0 (SeerScore harvester)"},
            )
            resp.raise_for_status()
            data = resp.json()
            markets = data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        logger.error("Failed to fetch Polymarket markets: %s", e)

    # Cache markets locally
    if markets:
        cache_markets(markets)

    return markets


def cache_markets(markets: list[dict]) -> None:
    """Cache markets to local file."""
    try:
        MARKET_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MARKET_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"fetched_at": datetime.now().isoformat(), "markets": markets},
                f,
                indent=2,
            )
    except Exception as e:
        logger.debug("Failed to cache markets: %s", e)


def load_cached_markets() -> list[dict]:
    """Load markets from cache if recent (< 6 hours old)."""
    if not MARKET_CACHE_FILE.exists():
        return []
    try:
        with open(MARKET_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        fetched_at = datetime.fromisoformat(data["fetched_at"])
        if (datetime.now() - fetched_at).total_seconds() < 6 * 3600:
            return data.get("markets", [])
    except Exception:
        pass
    return []


def get_market_question(market: dict) -> str:
    """Extract the question text from a market."""
    return (
        market.get("question")
        or market.get("title")
        or market.get("description", "")[:200]
    )


def get_market_volume(market: dict) -> float:
    """Get market volume in USD."""
    vol = market.get("volume") or market.get("volumeNum") or 0
    if isinstance(vol, str):
        vol = float(vol.replace(",", "").replace("$", ""))
    return float(vol)


def get_market_price(market: dict) -> float | None:
    """Get current market price (YES probability)."""
    # Try various field names used by different API versions
    for field in ["outcomePrices", "lastTradePrice", "bestBid", "price"]:
        if field in market:
            val = market[field]
            if isinstance(val, list) and len(val) > 0:
                return float(val[0])  # First outcome is typically YES
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    pass
    return None


def match_claim_to_markets(
    claim: str,
    markets: list[dict] | None = None,
    min_threshold: float = REVIEW_MATCH_THRESHOLD,
) -> list[dict]:
    """Match a claim to potential Polymarket markets.

    PRIMARY: keyword search via public-search API.
    FALLBACK: embedding similarity over fetched markets.
    Returns list of matches sorted by relevance.
    """
    matches = []

    # PRIMARY: keyword search
    try:
        import urllib.request as _ur
        import urllib.parse as _up
        keywords = re.sub(r"[^a-zA-Z0-9 $%]", " ", claim)
        keywords = " ".join(keywords.split()[:8])
        url = f"https://gamma-api.polymarket.com/public-search?q={_up.quote(keywords)}&limit_per_type=8"
        resp = _ur.urlopen(_ur.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30)
        events = json.loads(resp.read()).get("events", [])
        for ev in events[:8]:
            title = ev.get("title", "")
            if not title:
                continue
            matches.append({
                "market": ev,
                "market_id": ev.get("id"),
                "market_question": title,
                "similarity": 0.9,
                "match_method": "keyword_search",
            })
    except Exception as e:
        logger.warning("Search API failed: %s", e)

    # FALLBACK: embedding similarity
    if not matches:
        if markets is None:
            markets = load_cached_markets() or fetch_polymarket_markets()
        if markets:
            claim_embedding = get_embedding(claim)
            if claim_embedding:
                for market in markets:
                    question = get_market_question(market)
                    if not question:
                        continue
                    market_embedding = get_embedding(question)
                    if not market_embedding:
                        continue
                    similarity = cosine_similarity(claim_embedding, market_embedding)
                    if similarity >= min_threshold:
                        matches.append({
                            "market": market,
                            "market_id": market.get("condition_id") or market.get("id"),
                            "market_question": question,
                            "similarity": similarity,
                            "match_method": "embedding_fallback",
                        })

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches


def link_prediction_to_market(
    pred: dict,
    market_match: dict,
    auto_link: bool = True,
) -> dict:
    """Add market_link to a prediction dict.

    Args:
        pred: prediction dict to update
        market_match: result from match_claim_to_markets
        auto_link: if True, only link if above auto threshold and volume

    Returns:
        Updated prediction dict (mutated in place)
    """
    similarity = market_match["similarity"]
    volume = market_match.get("volume", 0)

    # Check auto-link criteria
    if auto_link:
        if similarity < AUTO_MATCH_THRESHOLD:
            logger.info("Similarity %.2f below auto threshold, queuing for review", similarity)
            return pred
        if volume < VOLUME_THRESHOLD:
            logger.info("Volume $%.0f below threshold, queuing for review", volume)
            return pred

    market = market_match["market"]
    pred["market_link"] = {
        "platform": "polymarket",
        "market_id": market_match["market_id"],
        "market_question": market_match["market_question"],
        "match_confidence": round(similarity, 4),
        "match_method": market_match["match_method"],
        "linked_at": datetime.now().isoformat(),
        "volume": volume,
    }

    # Initialize price history
    price = get_market_price(market)
    if price is not None:
        pred["market_prices"] = [
            {"ts": datetime.now().isoformat(), "price": round(price, 4)}
        ]

    return pred


def get_market_price_by_id(market_id: str) -> dict | None:
    """Fetch current price and status for a market by ID."""
    try:
        with httpx.Client(timeout=30.0) as client:
            # Try CLOB API first
            resp = client.get(f"{POLYMARKET_API}/markets/{market_id}")
            if resp.status_code == 200:
                return resp.json()

            # Fallback to Gamma API
            resp = client.get(f"{GAMMA_API}/markets/{market_id}")
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.error("Failed to fetch market %s: %s", market_id, e)
    return None


def is_market_resolved(market: dict) -> tuple[bool, int | None]:
    """Check if market is resolved and get outcome.

    Returns:
        (is_resolved, outcome) where outcome is 1 for YES, 0 for NO, None if not resolved
    """
    # Check various resolution indicators
    if market.get("closed") or market.get("resolved"):
        resolution = market.get("resolution") or market.get("winningOutcome")
        if resolution is not None:
            # Polymarket uses "YES"/"NO" or 0/1
            if resolution in ("YES", "Yes", 1, "1"):
                return True, 1
            if resolution in ("NO", "No", 0, "0"):
                return True, 0
        return True, None  # Closed but unknown resolution
    return False, None


def log_market_conflict(pred: dict, market: dict, our_verdict: str, market_verdict: str) -> None:
    """Log when market resolution conflicts with our LLM consensus."""
    conflict = {
        "pred_id": pred.get("id"),
        "claim": pred.get("claim", "")[:200],
        "our_verdict": our_verdict,
        "market_verdict": market_verdict,
        "market_id": pred.get("market_link", {}).get("market_id"),
        "logged_at": datetime.now().isoformat(),
    }
    try:
        MARKET_CONFLICTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MARKET_CONFLICTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(conflict) + "\n")
    except Exception as e:
        logger.error("Failed to log market conflict: %s", e)


def compute_market_weight(pred: dict) -> float:
    """Compute market signal weight for adjudication.

    From DESIGN_STEALS.md:
    - Weight 1.2 if match_confidence >= 0.90, volume >= $50k, >= 3 price points
    - Otherwise 0 (not included)
    """
    market_link = pred.get("market_link")
    if not market_link:
        return 0.0

    confidence = market_link.get("match_confidence", 0)
    volume = market_link.get("volume", 0)
    price_history = pred.get("market_prices", [])

    if (
        confidence >= 0.90
        and volume >= VOLUME_THRESHOLD
        and len(price_history) >= MIN_PRICE_HISTORY
    ):
        return 1.2

    return 0.0


def market_price_to_verdict(price: float) -> str | None:
    """Convert market price to verdict indication.

    Market price is probability of YES outcome.
    - >= 0.85: likely correct
    - <= 0.15: likely wrong
    - else: unclear
    """
    if price >= 0.85:
        return "correct"
    if price <= 0.15:
        return "wrong"
    return None  # Market unclear


def add_market_judgement(pred: dict) -> dict | None:
    """Create a market-based judgement for a prediction if eligible.

    Returns a judgement dict or None if not eligible.
    """
    weight = compute_market_weight(pred)
    if weight == 0:
        return None

    prices = pred.get("market_prices", [])
    if not prices:
        return None

    # Use most recent price
    latest_price = prices[-1].get("price")
    if latest_price is None:
        return None

    verdict = market_price_to_verdict(latest_price)
    if verdict is None:
        return None

    return {
        "panelist": "Polymarket price",
        "verdict": verdict,
        "weight": weight,
        "reasoning": f"Market price {latest_price:.1%} indicates {verdict} outcome",
        "judged_at": datetime.now().date().isoformat(),
        "source": "polymarket",
        "market_price": latest_price,
    }


# ---- Review Queue for Ambiguous Matches ----

REVIEW_QUEUE_FILE = DATA_DIR / "market_review_queue.jsonl"


def queue_for_review(pred: dict, match: dict) -> None:
    """Add a market match to the review queue (similarity 0.75-0.85)."""
    entry = {
        "pred_id": pred.get("id"),
        "claim": pred.get("claim", "")[:200],
        "market_id": match["market_id"],
        "market_question": match["market_question"],
        "similarity": round(match["similarity"], 4),
        "volume": match.get("volume", 0),
        "queued_at": datetime.now().isoformat(),
        "status": "pending",
    }
    try:
        REVIEW_QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(REVIEW_QUEUE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.error("Failed to queue for review: %s", e)


def get_review_queue() -> list[dict]:
    """Get pending items from review queue."""
    if not REVIEW_QUEUE_FILE.exists():
        return []
    items = []
    try:
        with open(REVIEW_QUEUE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    if entry.get("status") == "pending":
                        items.append(entry)
    except Exception:
        pass
    return items


def resolve_review(pred_id: str, action: str) -> bool:
    """Resolve a review queue item.
    
    Args:
        pred_id: prediction ID
        action: "link" to create link, "skip" to mark as not a match
    
    Returns True if resolved.
    """
    if not REVIEW_QUEUE_FILE.exists():
        return False
    
    lines = []
    resolved = False
    try:
        with open(REVIEW_QUEUE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    if entry.get("pred_id") == pred_id and entry.get("status") == "pending":
                        entry["status"] = action
                        entry["resolved_at"] = datetime.now().isoformat()
                        resolved = True
                    lines.append(json.dumps(entry))
        
        with open(REVIEW_QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception as e:
        logger.error("Failed to resolve review: %s", e)
        return False
    
    return resolved


# ---- Batch Matching ----

def batch_match_predictions(predictions: list[dict], max_matches: int = 20) -> dict:
    """Match multiple predictions to markets in batch.
    
    Returns stats dict with counts of auto_linked, queued_review, no_match.
    """
    stats = {"auto_linked": 0, "queued_review": 0, "no_match": 0, "errors": 0}
    
    # Fetch markets once
    markets = fetch_polymarket_markets()
    if not markets:
        logger.warning("No markets available")
        return stats
    
    for pred in predictions[:max_matches]:
        if pred.get("market_link"):
            continue  # Already linked
        
        claim = pred.get("claim", "")
        if not claim:
            continue
        
        try:
            matches = match_claim_to_markets(claim, markets)
            if not matches:
                stats["no_match"] += 1
                continue
            
            best = matches[0]
            if best["similarity"] >= AUTO_MATCH_THRESHOLD:
                link_prediction_to_market(pred, best, auto_link=True)
                if pred.get("market_link"):
                    stats["auto_linked"] += 1
                    logger.info("Auto-linked: %s", pred.get("id"))
            elif best["similarity"] >= REVIEW_MATCH_THRESHOLD:
                queue_for_review(pred, best)
                stats["queued_review"] += 1
            else:
                stats["no_match"] += 1
        except Exception as e:
            logger.error("Error matching %s: %s", pred.get("id"), e)
            stats["errors"] += 1
    
    return stats


# ---- CLI for testing ----

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python -m src.market_matcher 'claim text'")
        sys.exit(1)

    claim = " ".join(sys.argv[1:])
    print(f"Matching claim: {claim}\n")

    matches = match_claim_to_markets(claim)
    if not matches:
        print("No matches found")
    else:
        for i, m in enumerate(matches[:5], 1):
            print(f"{i}. [{m['similarity']:.2f}] {m['market_question'][:80]}")
            print(f"   Volume: ${m['volume']:,.0f} | Method: {m['match_method']}")
            print()
