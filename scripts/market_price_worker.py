# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Market price polling worker.

Phase 4 from DESIGN_STEALS.md - polls Polymarket prices every 6 hours
for predictions with market_link.

Run: python scripts/market_price_worker.py
Cadence: Every 6 hours via cron/task scheduler

Features:
- Updates market_prices array for linked predictions
- Detects market resolutions and applies as ground truth
- Logs conflicts when market resolves opposite to LLM consensus
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_lock import locked_data

from src.market_matcher import (
    get_market_price,
    get_market_price_by_id,
    is_market_resolved,
    log_market_conflict,
    match_claim_to_markets,
    link_prediction_to_market,
    fetch_polymarket_markets,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("market_price_worker")

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data" / "predictions.json"
HEARTBEAT = BASE / "data" / "market_heartbeat.txt"

MAX_UPDATES_PER_RUN = 50  # Limit API calls per run
PRICE_POLL_INTERVAL = 6 * 3600  # 6 hours in seconds


def load_data() -> dict:
    """Load data without lock (for dry-run mode only)."""
    with open(DATA, "r", encoding="utf-8") as f:
        return json.load(f)


def write_heartbeat(msg: str) -> None:
    """Write heartbeat file for monitoring."""
    try:
        HEARTBEAT.write_text(f"{datetime.now().isoformat()} | {msg}\n")
    except Exception:
        pass


def update_market_prices(data: dict) -> dict:
    """Update prices for all predictions with market_link.

    Returns stats dict.
    """
    stats = {"checked": 0, "updated": 0, "resolved": 0, "errors": 0, "conflicts": 0}

    linked_preds = [
        p for p in data["predictions"]
        if p.get("market_link") and not p.get("market_link", {}).get("resolved")
    ]

    logger.info("Found %d predictions with active market links", len(linked_preds))

    for pred in linked_preds[:MAX_UPDATES_PER_RUN]:
        market_link = pred.get("market_link", {})
        market_id = market_link.get("market_id")
        if not market_id:
            continue

        stats["checked"] += 1

        try:
            market = get_market_price_by_id(market_id)
            if not market:
                logger.debug("Could not fetch market %s", market_id)
                stats["errors"] += 1
                continue

            # Get current price
            price = get_market_price(market)
            if price is not None:
                # Add to price history
                prices = pred.setdefault("market_prices", [])
                prices.append({
                    "ts": datetime.now().isoformat(),
                    "price": round(price, 4),
                })
                # Keep last 30 price points
                pred["market_prices"] = prices[-30:]
                stats["updated"] += 1

            # Check for resolution
            resolved, outcome = is_market_resolved(market)
            if resolved:
                logger.info("Market %s resolved: outcome=%s", market_id, outcome)
                pred["market_link"]["resolved"] = True
                pred["market_link"]["resolved_at"] = datetime.now().isoformat()
                pred["market_link"]["resolution_outcome"] = outcome

                if outcome is not None:
                    stats["resolved"] += 1
                    apply_market_resolution(pred, outcome, stats)

        except Exception as e:
            logger.error("Error updating market %s: %s", market_id, e)
            stats["errors"] += 1

        # Small delay to avoid rate limiting
        time.sleep(0.5)

    return stats


def apply_market_resolution(pred: dict, outcome: int, stats: dict) -> None:
    """Apply market resolution as ground truth.

    From DESIGN_STEALS.md:
    - Auto-resolve our prediction if no existing verdict
    - If existing verdict conflicts, log to market_conflicts.jsonl for review
    """
    market_verdict = "correct" if outcome == 1 else "wrong"
    our_verdict = pred.get("verdict")

    if our_verdict is None:
        # No existing verdict - apply market resolution
        pred["verdict"] = market_verdict
        pred["resolution_source"] = "polymarket"
        pred["test_status"] = "judged"
        logger.info("Applied market resolution: %s -> %s", pred.get("id"), market_verdict)

    elif our_verdict != market_verdict and our_verdict not in ("disputed", "expired"):
        # Conflict! Log for manual review
        log_market_conflict(pred, pred.get("market_link", {}), our_verdict, market_verdict)
        pred["market_conflict"] = True
        pred["market_conflict_at"] = datetime.now().isoformat()
        stats["conflicts"] += 1
        logger.warning(
            "CONFLICT: pred %s has verdict=%s but market resolved=%s",
            pred.get("id"), our_verdict, market_verdict
        )


def find_new_market_matches(data: dict, limit: int = 10) -> int:
    """Find market matches for predictions without links.

    Returns number of new links created.
    """
    # Get predictions that might match markets
    unlinked = [
        p for p in data["predictions"]
        if not p.get("market_link")
        and p.get("verdict") is None
        and p.get("test_status") not in ("expired", "removed")
    ]

    if not unlinked:
        return 0

    # Refresh market cache
    logger.info("Fetching Polymarket markets for matching...")
    markets = fetch_polymarket_markets()
    if not markets:
        logger.warning("No markets fetched")
        return 0

    linked = 0
    for pred in unlinked[:limit]:
        claim = pred.get("claim", "")
        if not claim:
            continue

        matches = match_claim_to_markets(claim, markets)
        if matches:
            best = matches[0]
            if best["match_method"] == "embedding_auto":
                link_prediction_to_market(pred, best, auto_link=True)
                if pred.get("market_link"):
                    linked += 1
                    logger.info(
                        "Linked pred %s to market [%.2f]: %s",
                        pred.get("id"), best["similarity"], best["market_question"][:60]
                    )

    return linked


def main():
    parser = argparse.ArgumentParser(description="Polymarket price polling worker")
    parser.add_argument("--match", action="store_true", help="Also find new market matches")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")
    args = parser.parse_args()

    logger.info("=== Market Price Worker started ===")
    write_heartbeat("started")

    if args.dry_run:
        # Dry run: load without lock, don't save
        data = load_data()
        stats = update_market_prices(data)
        if args.match:
            new_links = find_new_market_matches(data)
            stats["new_links"] = new_links
    else:
        # Normal run: use locked_data for atomic read-modify-write
        with locked_data() as data:
            stats = update_market_prices(data)
            if args.match:
                new_links = find_new_market_matches(data)
                stats["new_links"] = new_links
            # data is auto-saved on exit from locked_data

    logger.info(
        "Complete: checked=%d updated=%d resolved=%d errors=%d conflicts=%d",
        stats["checked"], stats["updated"], stats["resolved"],
        stats["errors"], stats["conflicts"]
    )
    write_heartbeat(f"done: {stats}")
    print("MARKET_WORKER_DONE", flush=True)


if __name__ == "__main__":
    main()
