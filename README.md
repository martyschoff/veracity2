# Veracity2 — Predictions vs Reality Tracker

A web app that tracks predictions from named individuals (Zeihan, Doomberg, Diamandis) across categories (finance, energy, geopolitics, china, ai, ukraine), compares them against reality via an expert panel, and displays them in a grid where individuals are columns and their predictions are rows.

**Live site:** https://veracity2.surge.sh
**Repo:** https://github.com/martyschoff/veracity2

## Architecture

Static HTML site generated from JSON data by a Jinja2 render script. No backend in production — `render.py` reads `data/predictions.json`, renders `templates/index.html` into `surge_dist/index.html`, and the dist folder is deployed to Surge.sh.

A FastAPI app (`src/app.py`) also exists for local development with live API endpoints, but the production site is the static render.

## Project structure

```
veracity2/
├── src/
│   ├── models.py          # Individual + Prediction dataclasses
│   ├── store.py           # JSON file storage with dedup
│   ├── fetcher.py         # YouTube transcript fetcher (yt-dlp)
│   ├── extractor.py       # LLM-based prediction extraction
│   ├── app.py             # FastAPI app (local dev)
│   └── seed.py            # Seed script: fetch + extract + store
├── templates/
│   └── index.html         # Jinja2 template (the grid view)
├── data/
│   └── predictions.json   # All individuals + predictions
├── surge_dist/
│   ├── CNAME              # veracity2.surge.sh
│   └── index.html         # Rendered static output (deployed)
├── tests/                 # pytest tests
├── render.py              # Static render script (template → surge_dist)
├── fetch_all.py           # Batch fetcher script
└── docs/superpowers/plans/
    └── 2026-09-30-veracity2.md  # Original implementation plan
```

## Render pipeline

1. Edit `templates/index.html` (the Jinja2 template)
2. Run `render.py` to regenerate `surge_dist/index.html`
3. Deploy with Surge

```bash
# Python with Jinja2 is required
# Hermes-bundled Python: C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/python.exe

# Render
python render.py

# Deploy to Surge
SURGE_TOKEN=ea807c6f912951573c26c7fed2788f3f surge surge_dist/ veracity2.surge.sh
```

## Data model

`data/predictions.json` has two top-level arrays:

- **individuals**: people who make predictions (tracked) or sit on panels (panelists)
  - `name`, `handle`, `sources` (list of URLs), `categories` (list)
  - Tracked individuals: Peter Zeihan, Doomberg, Peter Diamandis
  - Panelists: everyone else (UnHerd, Jeff Snider, Ian Bremmer, etc.)
- **predictions**: extracted predictions
  - `id`, `individual_name`, `date`, `category`, `claim`, `source_url`, `transcript_excerpt`, `verdict` (null/correct/wrong), `created_at`

## UI layout

- **3 columns** (one per tracked individual), fixed order: Zeihan, Doomberg, Diamandis
- Each column header: avatar, name, purple category badge (hover shows panel tooltip with "PANEL" in orange), scorecard (total/correct/wrong counts)
- Below each header: top 5 outstanding predictions per person, stacked from the top
- Each prediction entry: date, condensed claim, orange source link (YouTube, Doomberg, etc.)
- **Click a column header** → full-screen overlay with all that person's predictions in a 4-column card grid
- **Settings button** (⚙) → dropdown (currently just light/dark mode toggle)
- Dark mode is default; light mode via CSS `[data-theme="light"]`

## Template filters (in render.py)

- `condense(claim)` — truncates long claims at ~120 chars with ellipsis at a sentence boundary
- `source_label(url)` — maps URLs to short labels (YouTube, Doomberg, Substack, White House, etc.)

## Adding panelists

Add to `data/predictions.json` → `individuals` array:

```json
{
  "name": "New Person",
  "handle": "newperson",
  "sources": ["https://youtube.com/@channel"],
  "categories": ["ai"]
}
```

Then re-render and deploy. Panelists appear in the category badge hover tooltips on the tracked individuals' columns.

## Cron jobs (planned, not yet set up)

```bash
hermes cron add --name "veracity2-morning" --schedule "0 8 * * *" \
  -q "Run the veracity2 cron job: cd ~/veracity2 && python -m src.cron"

hermes cron add --name "veracity2-evening" --schedule "0 20 * * *" \
  -q "Run the veracity2 cron job: cd ~/veracity2 && python -m src.cron"
```

## Git

```bash
git add -A && git commit -m "description" && git push origin master
```

## Environment

- **Machine:** AMD Ryzen AI MAX+ 395, 128GB RAM, Radeon 8060S, Windows 11
- **Python:** Hermes-bundled 3.14.7 at `C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/python.exe`
- **Surge:** account h4martylaptop@agentmail.to, token in env or memory
- **GitHub:** martyschoff/veracity2 (gh CLI authed)
