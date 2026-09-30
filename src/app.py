"""FastAPI web app serving the veracity2 grid view."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from src.store import Store

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "predictions.json"
TEMPLATES_DIR = BASE_DIR / "templates"

# Ensure data dir exists
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

# Initialize FastAPI
app = FastAPI(title="Veracity2 — Predictions vs Reality")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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


def get_store() -> Store:
    return Store(str(DATA_FILE))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the grid view."""
    store = get_store()
    raw = store.get_all_raw()
    individuals = raw.get("individuals", [])
    predictions = raw.get("predictions", [])

    # Sort predictions by date descending
    predictions.sort(key=lambda p: p.get("date", ""), reverse=True)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "individuals": individuals,
            "predictions": predictions,
            "category_colors": CATEGORY_COLORS,
        },
    )


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
