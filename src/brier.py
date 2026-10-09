# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Brier Ledger: track probability calibration over time.

Records per-source probability estimates at verdict time and computes Brier scores.
Enables reliability diagrams (calibration curves) per pundit.

Brier score: (probability - outcome)² where outcome ∈ {0, 1}
Lower is better. Perfect calibration = 0.

Usage:
    from src.brier import record_probabilities, finalize_brier, get_calibration_data
    
    # After MC/panel runs, record probabilities
    record_probabilities(pred_id, {"monte_carlo": 0.72, "miro": 0.68})
    
    # When outcome is known, finalize scores
    finalize_brier(pred_id, outcome=1)  # 1 = correct, 0 = wrong
    
    # Get calibration data for reliability diagrams
    data = get_calibration_data("Peter Zeihan")
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from data_lock import locked_data, locked_read

BASE = Path(__file__).resolve().parent.parent
CALIBRATION_DIR = BASE / "data" / "calibration"


def compute_brier(prob: float, outcome: int) -> float:
    """Compute Brier score: (probability - outcome)².
    
    Args:
        prob: Predicted probability (0.0 to 1.0)
        outcome: Actual outcome (1 = correct/happened, 0 = wrong/didn't happen)
    
    Returns:
        Brier score (0.0 = perfect, 1.0 = worst possible)
    """
    return round((prob - outcome) ** 2, 6)


def _extract_mc_probability(mc_result: str | None) -> float | None:
    """Extract probability from Monte Carlo result string.
    
    Examples:
        "RIGHT (72% of 40 decided, 10 unclear)" -> 0.72
        "WRONG (38% of 24 decided, 16 unclear)" -> 0.38
    """
    if not mc_result or not isinstance(mc_result, str):
        return None
    
    # Pattern: "RIGHT (72% of N decided, M unclear)" or "WRONG (38%...)"
    m = re.search(r"(RIGHT|WRONG)\s*\((\d+)%", mc_result)
    if not m:
        return None
    
    direction, pct = m.groups()
    pct_float = int(pct) / 100.0
    
    # RIGHT means pct_float is probability of correct
    # WRONG means pct_float is probability of correct (minority voted wrong)
    if direction == "RIGHT":
        return pct_float
    else:
        return pct_float  # Already percentage that voted "yes"/correct


def _extract_miro_probability(miro_result: dict | None) -> float | None:
    """Extract probability from MiroFish result.
    
    Miro returns: {"verdict": "supported"|"refuted"|"inconclusive", "confidence": 0.0-1.0}
    Maps to probability of claim being correct.
    """
    if not miro_result or not isinstance(miro_result, dict):
        return None
    
    verdict = miro_result.get("verdict")
    confidence = miro_result.get("confidence")
    
    if verdict is None or confidence is None:
        return None
    
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        return None
    
    if verdict == "supported":
        return conf  # High confidence supported = high prob correct
    elif verdict == "refuted":
        return 1.0 - conf  # High confidence refuted = low prob correct
    else:  # inconclusive
        return 0.5  # Inconclusive defaults to 50%


def _extract_delphicursor_probability(dc_result: dict | None) -> float | None:
    """Extract probability from DelphiCursor result.
    
    DC returns: {"vote": "correct"|"incorrect"|"unclear", "confidence": 0-100}
    Maps to probability of claim being correct.
    """
    if not dc_result or not isinstance(dc_result, dict):
        return None
    
    vote = dc_result.get("vote")
    confidence = dc_result.get("confidence")
    
    if vote is None or confidence is None:
        return None
    
    try:
        conf = float(confidence) / 100.0  # Convert 0-100 to 0.0-1.0
    except (TypeError, ValueError):
        return None
    
    if vote == "correct":
        return conf
    elif vote == "incorrect":
        return 1.0 - conf
    else:  # unclear
        return 0.5


def _extract_panel_probability(judgements: list | None) -> float | None:
    """Extract weighted probability from panel votes.
    
    Computes weighted average where:
    - correct = 1.0
    - incorrect = 0.0
    - unclear = 0.5
    """
    if not judgements or not isinstance(judgements, list):
        return None
    
    total_weight = 0.0
    weighted_sum = 0.0
    
    for j in judgements:
        v = j.get("verdict")
        w = j.get("weight", 1.0)
        
        if v == "correct":
            weighted_sum += w * 1.0
            total_weight += w
        elif v in ("incorrect", "wrong"):
            weighted_sum += w * 0.0
            total_weight += w
        elif v == "unclear":
            weighted_sum += w * 0.5
            total_weight += w
    
    if total_weight == 0:
        return None
    
    return round(weighted_sum / total_weight, 4)


def extract_all_probabilities(prediction: dict) -> dict[str, float]:
    """Extract all available probabilities from a prediction record.
    
    Returns dict with source names as keys and probabilities as values.
    Only includes sources that have valid data.
    """
    probs = {}
    
    mc_prob = _extract_mc_probability(prediction.get("mc_result"))
    if mc_prob is not None:
        probs["monte_carlo"] = mc_prob
    
    miro_prob = _extract_miro_probability(prediction.get("miro_result"))
    if miro_prob is not None:
        probs["miro"] = miro_prob
    
    dc_prob = _extract_delphicursor_probability(prediction.get("delphicursor_result"))
    if dc_prob is not None:
        probs["delphicursor"] = dc_prob
    
    panel_prob = _extract_panel_probability(prediction.get("judgements"))
    if panel_prob is not None:
        probs["panel_weighted"] = panel_prob
    
    # Future: polymarket price integration
    # if prediction.get("market_link", {}).get("price") is not None:
    #     probs["polymarket"] = prediction["market_link"]["price"]
    
    return probs


def record_probabilities(pred_id: str, source_probs: dict[str, float] | None = None) -> bool:
    """Record probability estimates in the brier_ledger for a prediction.
    
    If source_probs is None, extracts from existing prediction fields.
    Can be called multiple times to add new sources.
    
    Args:
        pred_id: Prediction ID
        source_probs: Dict of {source_name: probability} or None to auto-extract
        
    Returns:
        True if probabilities were recorded, False otherwise
    """
    with locked_data() as data:
        target = next((p for p in data["predictions"] if p.get("id") == pred_id), None)
        if not target:
            return False
        
        # Auto-extract if not provided
        if source_probs is None:
            source_probs = extract_all_probabilities(target)
        
        if not source_probs:
            return False
        
        # Initialize or update brier_ledger
        if "brier_ledger" not in target:
            target["brier_ledger"] = {
                "recorded_at": datetime.datetime.utcnow().isoformat() + "Z",
                "probabilities": {},
                "resolved_outcome": None,
                "brier_scores": {},
            }
        
        # Merge new probabilities (don't overwrite existing)
        existing_probs = target["brier_ledger"].get("probabilities", {})
        for source, prob in source_probs.items():
            if source not in existing_probs:
                existing_probs[source] = round(prob, 4)
        target["brier_ledger"]["probabilities"] = existing_probs
        
        return True


def finalize_brier(pred_id: str, outcome: int) -> dict | None:
    """Compute and store Brier scores for a resolved prediction.
    
    Args:
        pred_id: Prediction ID
        outcome: 1 = correct/happened, 0 = wrong/didn't happen
        
    Returns:
        Dict of {source: brier_score} or None if failed
    """
    if outcome not in (0, 1):
        raise ValueError(f"outcome must be 0 or 1, got {outcome}")
    
    with locked_data() as data:
        target = next((p for p in data["predictions"] if p.get("id") == pred_id), None)
        if not target:
            return None
        
        # Ensure brier_ledger exists with probabilities
        if "brier_ledger" not in target:
            # Try to record from existing data first
            probs = extract_all_probabilities(target)
            if not probs:
                return None
            target["brier_ledger"] = {
                "recorded_at": datetime.datetime.utcnow().isoformat() + "Z",
                "probabilities": probs,
                "resolved_outcome": None,
                "brier_scores": {},
            }
        
        ledger = target["brier_ledger"]
        probs = ledger.get("probabilities", {})
        
        if not probs:
            return None
        
        # Compute Brier scores for each source
        scores = {}
        for source, prob in probs.items():
            scores[source] = compute_brier(prob, outcome)
        
        ledger["resolved_outcome"] = outcome
        ledger["brier_scores"] = scores
        ledger["finalized_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        
        return scores


def get_calibration_data(pundit: str) -> list[tuple[float, int]]:
    """Get (probability, outcome) pairs for a pundit's resolved predictions.
    
    Args:
        pundit: Pundit name (individual_name field)
        
    Returns:
        List of (probability, outcome) tuples for reliability diagrams
    """
    results = []
    
    with locked_read() as data:
        for pred in data["predictions"]:
            if pred.get("individual_name") != pundit:
                continue
            
            ledger = pred.get("brier_ledger")
            if not ledger:
                continue
            
            outcome = ledger.get("resolved_outcome")
            if outcome is None:
                continue
            
            # Use panel_weighted as the primary probability for calibration
            # Fall back to other sources in order of reliability
            probs = ledger.get("probabilities", {})
            prob = probs.get("panel_weighted") or probs.get("monte_carlo") or \
                   probs.get("miro") or probs.get("delphicursor")
            
            if prob is not None:
                results.append((prob, outcome))
    
    return results


def compute_calibration_buckets(data: list[tuple[float, int]], n_buckets: int = 10) -> dict:
    """Compute calibration bucket statistics for reliability diagrams.
    
    Args:
        data: List of (probability, outcome) tuples
        n_buckets: Number of buckets (default 10 for deciles)
        
    Returns:
        Dict with bucket ranges as keys, stats as values
    """
    bucket_size = 1.0 / n_buckets
    buckets = {}
    
    for i in range(n_buckets):
        low = i * bucket_size
        high = (i + 1) * bucket_size
        key = f"{low:.1f}-{high:.1f}"
        
        # Filter data in this bucket
        in_bucket = [(p, o) for p, o in data if low <= p < high or (i == n_buckets - 1 and p == high)]
        
        if in_bucket:
            actual_rate = sum(o for _, o in in_bucket) / len(in_bucket)
            mean_pred = sum(p for p, _ in in_bucket) / len(in_bucket)
        else:
            actual_rate = None
            mean_pred = None
        
        buckets[key] = {
            "count": len(in_bucket),
            "actual_rate": round(actual_rate, 4) if actual_rate is not None else None,
            "mean_predicted": round(mean_pred, 4) if mean_pred is not None else None,
        }
    
    return buckets


def compute_mean_brier(data: list[tuple[float, int]]) -> float | None:
    """Compute mean Brier score from calibration data."""
    if not data:
        return None
    
    total = sum(compute_brier(p, o) for p, o in data)
    return round(total / len(data), 6)


def generate_pundit_calibration_file(pundit: str, slug: str | None = None) -> Path | None:
    """Generate calibration JSON file for a pundit.
    
    Args:
        pundit: Pundit name
        slug: Optional slug for filename (auto-generated if None)
        
    Returns:
        Path to generated file, or None if insufficient data
    """
    CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
    
    data = get_calibration_data(pundit)
    
    if len(data) < 5:  # Require at least 5 resolved predictions
        return None
    
    if slug is None:
        slug = pundit.lower().replace(" ", "-").replace("(", "").replace(")", "")
    
    calibration = {
        "pundit": pundit,
        "pundit_slug": slug,
        "total_resolved": len(data),
        "mean_brier": compute_mean_brier(data),
        "calibration_buckets": compute_calibration_buckets(data),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
    
    filepath = CALIBRATION_DIR / f"{slug}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2, ensure_ascii=False)
    
    return filepath


def generate_all_calibration_files() -> list[Path]:
    """Generate calibration files for all pundits with sufficient data.
    
    Returns:
        List of paths to generated files
    """
    generated = []
    
    with locked_read() as data:
        pundits = set(p.get("individual_name") for p in data["predictions"] if p.get("individual_name"))
    
    for pundit in pundits:
        filepath = generate_pundit_calibration_file(pundit)
        if filepath:
            generated.append(filepath)
    
    return generated


def backfill_brier_ledgers(dry_run: bool = True) -> dict:
    """Backfill brier_ledger for existing predictions with verdict data.
    
    Args:
        dry_run: If True, don't write changes, just report what would be done
        
    Returns:
        Stats dict with counts
    """
    stats = {"checked": 0, "backfilled": 0, "already_has_ledger": 0, "no_data": 0}
    
    with (locked_read() if dry_run else locked_data()) as data:
        for pred in data["predictions"]:
            stats["checked"] += 1
            
            if pred.get("brier_ledger"):
                stats["already_has_ledger"] += 1
                continue
            
            # Only backfill if prediction has a verdict
            verdict = pred.get("verdict") or pred.get("marty_verdict")
            if not verdict:
                continue
            
            probs = extract_all_probabilities(pred)
            if not probs:
                stats["no_data"] += 1
                continue
            
            # Map verdict to outcome
            if verdict in ("correct", "right"):
                outcome = 1
            elif verdict in ("wrong", "incorrect"):
                outcome = 0
            else:
                continue  # Unknown verdict format
            
            if not dry_run:
                pred["brier_ledger"] = {
                    "recorded_at": datetime.datetime.utcnow().isoformat() + "Z",
                    "probabilities": {k: round(v, 4) for k, v in probs.items()},
                    "resolved_outcome": outcome,
                    "brier_scores": {k: compute_brier(v, outcome) for k, v in probs.items()},
                    "backfilled": True,
                }
            
            stats["backfilled"] += 1
    
    return stats


# CLI interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Brier Ledger management")
    parser.add_argument("--backfill", action="store_true", help="Backfill brier_ledger for existing predictions")
    parser.add_argument("--dry-run", action="store_true", help="Don't write changes (with --backfill)")
    parser.add_argument("--calibrate", action="store_true", help="Generate calibration files for all pundits")
    parser.add_argument("--pundit", type=str, help="Generate calibration for specific pundit")
    parser.add_argument("--stats", action="store_true", help="Show Brier statistics")
    
    args = parser.parse_args()
    
    if args.backfill:
        print(f"Backfilling brier_ledgers (dry_run={args.dry_run})...")
        stats = backfill_brier_ledgers(dry_run=args.dry_run)
        print(f"  Checked: {stats['checked']}")
        print(f"  Already has ledger: {stats['already_has_ledger']}")
        print(f"  Backfilled: {stats['backfilled']}")
        print(f"  No data (skipped): {stats['no_data']}")
        if args.dry_run:
            print("  (dry run - no changes written)")
    
    elif args.calibrate:
        print("Generating calibration files...")
        files = generate_all_calibration_files()
        print(f"  Generated {len(files)} file(s)")
        for f in files:
            print(f"    {f}")
    
    elif args.pundit:
        print(f"Generating calibration for {args.pundit}...")
        filepath = generate_pundit_calibration_file(args.pundit)
        if filepath:
            print(f"  Generated: {filepath}")
        else:
            print("  Insufficient data (need at least 5 resolved predictions)")
    
    elif args.stats:
        print("Brier Ledger statistics:")
        with locked_read() as data:
            total = len(data["predictions"])
            with_ledger = sum(1 for p in data["predictions"] if p.get("brier_ledger"))
            resolved = sum(1 for p in data["predictions"] 
                          if p.get("brier_ledger", {}).get("resolved_outcome") is not None)
            backfilled = sum(1 for p in data["predictions"] 
                            if p.get("brier_ledger", {}).get("backfilled"))
        print(f"  Total predictions: {total}")
        print(f"  With brier_ledger: {with_ledger}")
        print(f"  Resolved (with outcome): {resolved}")
        print(f"  Backfilled: {backfilled}")
    
    else:
        parser.print_help()
