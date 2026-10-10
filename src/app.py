# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""FastAPI web app serving the veracity2 grid view."""

from __future__ import annotations

import json
import os
from datetime import datetime

# shared lock for predictions.json (matches scripts/data_lock.py)
from filelock import FileLock
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.store import Store

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "predictions.json"
_DATA_LOCK = FileLock(str(BASE_DIR / "data" / "predictions.json.lock"), timeout=60)
TEMPLATES_DIR = BASE_DIR / "templates"

# Ensure data dir exists
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

# Initialize FastAPI
app = FastAPI(title="Veracity2 — Predictions vs Reality")

# Jinja2 environment (direct, not via Starlette's wrapper to avoid cache key issues)
_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)

# Category colors for badges
def _condense(claim):
    """Condense a long claim into a headline-style sentence (mirror of render.py)."""
    if not claim or len(claim) <= 120:
        return claim
    cutoff = claim[:140]
    for sep in ['. ', '! ', '? ']:
        idx = cutoff.rfind(sep)
        if idx > 60:
            return claim[:idx + 1]
    idx = cutoff.rfind(', ')
    if idx > 60:
        return claim[:idx] + '…'
    idx = claim[:130].rfind(' ')
    if idx > 60:
        return claim[:idx] + '…'
    return claim[:120] + '…'


def _source_label(url):
    if not url:
        return 'Source'
    u = url.lower()
    if 'youtube.com' in u or 'youtu.be' in u:
        return 'YouTube'
    if 'doomberg' in u:
        return 'Doomberg'
    return 'Source'


_jinja_env.filters['condense'] = _condense
_jinja_env.filters['source_label'] = _source_label

CATEGORY_COLORS: dict[str, str] = {
    "finance": "#10b981",
    "energy": "#f59e0b",
    "ukraine": "#3b82f6",
    "china": "#ef4444",
    "ai": "#8b5cf6",
    "geopolitics": "#6366f1",
    "other": "#6b7280",
}

# The 3 tracked individuals (in column order)
TRACKED_NAMES: list[str] = ["Peter Zeihan", "Doomberg", "Peter Diamandis", "Ian Bremmer", "David McAlvany"]


def get_store() -> Store:
    return Store(str(DATA_FILE))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the spreadsheet-style grid view."""
    store = get_store()
    raw = store.get_all_raw()
    individuals = raw.get("individuals", [])
    predictions = raw.get("predictions", [])

    # Split into tracked individuals (fixed order) and panelists
    tracked_individuals = []
    panelists = []
    for ind in individuals:
        if ind.get("name") in TRACKED_NAMES:
            tracked_individuals.append(ind)
        else:
            panelists.append(ind)

    # Sort tracked individuals by the fixed column order
    tracked_individuals.sort(key=lambda i: TRACKED_NAMES.index(i["name"]))

    # Compute counts per tracked individual
    for ind in tracked_individuals:
        ind_preds = [p for p in predictions if p.get("individual_name") == ind["name"]]
        ind["total_count"] = len(ind_preds)
        ind["correct_count"] = len([p for p in ind_preds if p.get("verdict") == "correct"])
        ind["wrong_count"] = len([p for p in ind_preds if p.get("verdict") == "wrong"])

    # Build panelists-by-category map for hover tooltips on category badges
    panelists_by_category: dict[str, list] = {}
    for p in panelists:
        w = p.get("panel_weight", 1.0)
        for cat in p.get("categories", []):
            panelists_by_category.setdefault(cat, []).append(
                {"name": p["name"], "w": w})
    for cat in panelists_by_category:
        panelists_by_category[cat].sort(key=lambda e: -e["w"])  # best on top

    # Filter to only predictions from tracked individuals with no verdict (outstanding)
    tracked_names_set = set(TRACKED_NAMES)
    outstanding = [
        p for p in predictions
        if p.get("individual_name") in tracked_names_set and p.get("verdict") is None
    ]
    outstanding = [p for p in predictions if not p.get("gate_status")]
    outstanding.sort(key=lambda p: p.get("date", ""), reverse=True)  # newest first

    # Top 5 most recent outstanding PER PERSON
    def _deeplink(p):
        u = p.get("source_url") or ""
        t = p.get("t_seconds")
        if t is not None and "youtube.com" in u and "t=" not in u:
            u += ("&" if "?" in u else "?") + "t=" + str(max(0, int(t) - 15))  # 15s lead-in
        elif t is None and "#" not in u and not u.lower().startswith("mailto"):
            anchor_src = (p.get("transcript_excerpt") or p.get("claim") or "")
            words = [w for w in anchor_src.split() if w][:10]
            if len(words) >= 4:
                u += "#:~:text=" + "%20".join(words)
        return u

    rows_by_person: dict[str, list] = {}
    all_preds_by_person: dict[str, list] = {}
    for ind in tracked_individuals:
        name = ind["name"]
        person_preds = [p for p in outstanding if p.get("individual_name") == name]
        for p in person_preds:
            p["source_url"] = _deeplink(p)
        rows_by_person[name] = person_preds  # QA workbench: show ALL, no top-5 cap
        all_person = [p for p in predictions if p.get("individual_name") == name]
        all_person.sort(key=lambda p: p.get("date", ""), reverse=True)  # newest first
        for p in all_person:
            p["source_url"] = _deeplink(p)
        all_preds_by_person[name] = all_person

    # Total tracked predictions count (for stats bar)
    total_tracked_preds = len([p for p in predictions if p.get("individual_name") in tracked_names_set])

    template = _jinja_env.get_template("index.html")
    html = template.render(
        tracked_individuals=tracked_individuals,
        panelists=panelists,
        panelists_by_category=panelists_by_category,
        rows_by_person=rows_by_person,
        all_preds_by_person=all_preds_by_person,
        total_tracked_preds=total_tracked_preds,
        category_colors=CATEGORY_COLORS,
    )
    return HTMLResponse(content=html)


@app.get("/api/predictions")
async def api_predictions(
    individual: str | None = Query(None),
    category: str | None = Query(None),
):
    """Return predictions as JSON, optionally filtered."""
    store = get_store()
    preds = store.get_all_raw().get("predictions", [])

    if individual:
        preds = [p for p in preds if p.get("individual_name", "").lower() == individual.lower()]
    if category:
        preds = [p for p in preds if p.get("category", "").lower() == category.lower()]

    preds.sort(key=lambda p: p.get("date", ""), reverse=True)
    return JSONResponse(content={"predictions": preds, "count": len(preds)})


@app.get("/api/individuals")
async def api_individuals():
    """Return all tracked individuals."""
    store = get_store()
    inds = store.get_all_raw().get("individuals", [])
    return JSONResponse(content={"individuals": inds, "count": len(inds)})


@app.get("/api/stats")
async def api_stats():
    """Return summary stats."""
    store = get_store()
    raw = store.get_all_raw()
    preds = raw.get("predictions", [])
    inds = raw.get("individuals", [])

    by_category: dict[str, int] = {}
    by_individual: dict[str, int] = {}
    for p in preds:
        cat = p.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1
        name = p.get("individual_name", "unknown")
        by_individual[name] = by_individual.get(name, 0) + 1

    return JSONResponse(
        content={
            "total_predictions": len(preds),
            "total_individuals": len(inds),
            "by_category": by_category,
            "by_individual": by_individual,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


# ---- User mark / critique writeback ----
MARKS_LOG = BASE_DIR / "data" / "user_marks.json"


def _apply_mark(pred_id: str, agrees: bool, note: str = "") -> bool:
    """Apply a Marty mark to predictions.json (locked read-modify-write + log)."""
    with _DATA_LOCK:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        hit = False
        for p in data["predictions"]:
            if p.get("id") == pred_id:
                p["marty_agrees"] = agrees
                p["marty_note"] = note or ("MartyPredicts: Right" if agrees else "MartyPredicts: Wrong")
                p["marty_at"] = datetime.now().date().isoformat()
                p["marty_verdict"] = "correct" if agrees else "wrong"  # Marty's vote is FINAL, independent of panels
                if p.get("mc_status") in (None, "none", "not_due", "done"):
                    p["mc_status"] = "queued"  # swarm runs for the record; never overrides Marty
                if p.get("miro_status") in (None, "none", "error", "not_due"):
                    p["miro_status"] = "queued"
                hit = True
                break
        if hit:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log = json.load(open(MARKS_LOG, encoding="utf-8")) if MARKS_LOG.exists() else []
            log.append({"id": pred_id, "agrees": agrees, "note": note,
                        "at": datetime.now().isoformat()})
            MARKS_LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return hit


def _apply_critique(pred_id: str, text: str) -> bool:
    with _DATA_LOCK:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        hit = False
        for p in data["predictions"]:
            if p.get("id") == pred_id:
                p.setdefault("critiques", []).append({"text": text, "at": datetime.now().isoformat()})
                hit = True
                break
        if hit:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    return hit


IMPLICIT_QUEUE = BASE_DIR / "data" / "implicit_queue.json"


def _resolve_implicit(qid: str, action: str):
    with _DATA_LOCK:
        q = json.load(open(IMPLICIT_QUEUE, encoding="utf-8")) if IMPLICIT_QUEUE.exists() else []
        entry = next((e for e in q if e["id"] == qid), None)
        if not entry:
            return False
        d = json.load(open(DATA_FILE, encoding="utf-8"))
        pred = next((p for p in d["predictions"] if p["id"] == qid), None)
        if action == "move":
            entry["status"] = "moved"
            if pred:
                pred["gate_status"] = "promoted"
                if entry.get("implicit_forecast"):
                    pred["claim"] = entry["implicit_forecast"]
                pred["origin"] = "implicit-forecast"
        elif action == "keep":
            entry["status"] = "kept"
            if pred:
                pred["gate_status"] = "kept"
        elif action == "delete":
            entry["status"] = "deleted"
            if pred:
                pred["removed"] = True
        IMPLICIT_QUEUE.write_text(json.dumps(q, indent=2), encoding="utf-8")
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
    return True


@app.post("/api/implicit")
async def api_implicit(request: Request):
    body = await request.json()
    ok = _resolve_implicit(body.get("id", ""), body.get("action", ""))
    return JSONResponse({"ok": ok})


@app.get("/api/monitor")
async def api_monitor():
    from src.monitor_data import gather
    return JSONResponse(gather())


@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page():
    html = _jinja_env.get_template("monitor.html").render()
    return HTMLResponse(content=html)


@app.get("/version.json")
async def version_json():
    vf = BASE_DIR / "data" / "version.json"
    return JSONResponse(json.load(open(vf, encoding="utf-8")))


@app.get("/api/implicit")
async def api_implicit_list():
    q = json.load(open(IMPLICIT_QUEUE, encoding="utf-8")) if IMPLICIT_QUEUE.exists() else []
    return JSONResponse({"entries": [e for e in q if e.get("status") == "pending"]})


@app.post("/api/marty")
async def api_marty(request: Request):
    body = await request.json()
    ok = _apply_mark(body.get("id", ""), bool(body.get("agrees")), body.get("note", ""))
    return JSONResponse({"ok": ok})


@app.post("/api/critique")
async def api_critique(request: Request):
    body = await request.json()
    ok = _apply_critique(body.get("id", ""), body.get("text", ""))
    return JSONResponse({"ok": ok})


# ---- Phase 4: Market Signals API (DESIGN_STEALS.md) ----

@app.get("/api/prediction/{pred_id}/market")
async def api_prediction_market(pred_id: str):
    """Return market link + price history for a prediction.
    
    Returns:
    - market_link: platform, market_id, market_question, match_confidence
    - market_prices: array of {ts, price} entries
    - current_price: most recent price
    - verification_url: link to verify on Polymarket
    """
    store = get_store()
    preds = store.get_all_raw().get("predictions", [])
    pred = next((p for p in preds if p.get("id") == pred_id), None)
    
    if not pred:
        return JSONResponse(status_code=404, content={"error": "Prediction not found"})
    
    market_link = pred.get("market_link")
    if not market_link:
        return JSONResponse(content={"linked": False, "message": "No market link"})
    
    prices = pred.get("market_prices", [])
    current_price = prices[-1]["price"] if prices else None
    
    return JSONResponse(content={
        "linked": True,
        "prediction_id": pred_id,
        "market_link": market_link,
        "market_prices": prices,
        "current_price": current_price,
        "price_count": len(prices),
        "verification_url": f"https://polymarket.com/event/{market_link.get('market_id', '')}",
    })


@app.post("/api/prediction/{pred_id}/market/link")
async def api_link_market(pred_id: str, request: Request):
    """Manually link a prediction to a Polymarket market.
    
    Body: {"market_id": "...", "market_question": "...", "confidence": 0.95}
    """
    try:
        from src.market_matcher import link_prediction_to_market
    except ImportError:
        return JSONResponse(status_code=500, content={"error": "Market matcher not available"})
    
    body = await request.json()
    market_id = body.get("market_id")
    if not market_id:
        return JSONResponse(status_code=400, content={"error": "market_id required"})
    
    with _DATA_LOCK:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        pred = next((p for p in data["predictions"] if p.get("id") == pred_id), None)
        if not pred:
            return JSONResponse(status_code=404, content={"error": "Prediction not found"})
        
        # Create market link manually
        pred["market_link"] = {
            "platform": "polymarket",
            "market_id": market_id,
            "market_question": body.get("market_question", ""),
            "match_confidence": body.get("confidence", 1.0),
            "match_method": "manual",
            "linked_at": datetime.now().isoformat(),
            "volume": body.get("volume", 0),
        }
        
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return JSONResponse(content={"ok": True, "market_link": pred["market_link"]})


@app.get("/api/markets/conflicts")
async def api_market_conflicts():
    """Return list of predictions where market resolution conflicts with our verdict."""
    conflicts_file = BASE_DIR / "data" / "market_conflicts.jsonl"
    conflicts = []
    
    if conflicts_file.exists():
        with open(conflicts_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        conflicts.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    
    return JSONResponse(content={"conflicts": conflicts, "count": len(conflicts)})


@app.get("/api/markets/review-queue")
async def api_market_review_queue():
    """Return pending market match reviews (similarity 0.75-0.85)."""
    try:
        from src.market_matcher import get_review_queue
        queue = get_review_queue()
        return JSONResponse(content={"queue": queue, "count": len(queue)})
    except ImportError:
        return JSONResponse(content={"queue": [], "count": 0, "error": "Market matcher not available"})


@app.post("/api/markets/review")
async def api_resolve_market_review(request: Request):
    """Resolve a market review queue item.
    
    Body: {"pred_id": "...", "action": "link"|"skip"}
    """
    try:
        from src.market_matcher import resolve_review, get_review_queue
    except ImportError:
        return JSONResponse(status_code=500, content={"error": "Market matcher not available"})
    
    body = await request.json()
    pred_id = body.get("pred_id")
    action = body.get("action")
    
    if not pred_id or action not in ("link", "skip"):
        return JSONResponse(status_code=400, content={"error": "pred_id and action (link/skip) required"})
    
    # If action is "link", we need to create the actual link
    if action == "link":
        # Get the queue item to find market details
        queue = get_review_queue()
        item = next((q for q in queue if q.get("pred_id") == pred_id), None)
        if item:
            with _DATA_LOCK:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                pred = next((p for p in data["predictions"] if p.get("id") == pred_id), None)
                if pred:
                    pred["market_link"] = {
                        "platform": "polymarket",
                        "market_id": item.get("market_id"),
                        "market_question": item.get("market_question", ""),
                        "match_confidence": item.get("similarity", 0.8),
                        "match_method": "manual_review",
                        "linked_at": datetime.now().isoformat(),
                        "volume": item.get("volume", 0),
                    }
                
                with open(DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
    
    ok = resolve_review(pred_id, action)
    return JSONResponse(content={"ok": ok})


@app.get("/api/markets/stats")
async def api_market_stats():
    """Return market integration statistics."""
    store = get_store()
    preds = store.get_all_raw().get("predictions", [])
    
    linked = [p for p in preds if p.get("market_link")]
    resolved_by_market = [p for p in preds if p.get("resolution_source") == "polymarket"]
    with_conflict = [p for p in preds if p.get("market_conflict")]
    
    return JSONResponse(content={
        "total_predictions": len(preds),
        "linked_to_market": len(linked),
        "resolved_by_market": len(resolved_by_market),
        "market_conflicts": len(with_conflict),
        "link_rate": round(len(linked) / len(preds) * 100, 1) if preds else 0,
    })
