"""FastAPI web app serving the veracity2 grid view."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.store import Store

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "predictions.json"
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
TRACKED_NAMES: list[str] = ["Peter Zeihan", "Doomberg", "Peter Diamandis"]


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
    panelists_by_category: dict[str, list[str]] = {}
    for p in panelists:
        for cat in p.get("categories", []):
            panelists_by_category.setdefault(cat, []).append(p["name"])

    # Filter to only predictions from tracked individuals with no verdict (outstanding)
    tracked_names_set = set(TRACKED_NAMES)
    outstanding = [
        p for p in predictions
        if p.get("individual_name") in tracked_names_set and p.get("verdict") is None
    ]
    outstanding.sort(key=lambda p: p.get("date", ""), reverse=True)

    # Take top 5 most recent outstanding
    top5 = outstanding[:5]

    # Total tracked predictions count (for stats bar)
    total_tracked_preds = len([p for p in predictions if p.get("individual_name") in tracked_names_set])

    template = _jinja_env.get_template("index.html")
    html = template.render(
        tracked_individuals=tracked_individuals,
        panelists=panelists,
        panelists_by_category=panelists_by_category,
        rows=top5,
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
