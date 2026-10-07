# Veracity2 — Predictions vs Reality Tracker

A web app that tracks predictions from named individuals (Zeihan, Doomberg, Diamandis, Bremmer) across categories (finance, energy, geopolitics, china, ai, ukraine), compares them against reality via an expert panel, and displays them in a grid where individuals are columns and their predictions are rows.

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
├── fetch_bremmer.py       # Bremmer Quick Take fetcher (Quick Takes only)
├── fix_dates.py           # One-off script to fix past-dated predictions
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
  - Tracked individuals (4 columns): Peter Zeihan, Doomberg, Peter Diamandis, Ian Bremmer
  - Panelists: everyone else — UnHerd, Jeff Snider, Andrew Ross Sorkin, Dan Ives, Scott Bessent, David McAlvany, Kevin Orrick, Mustafa Suleyman, Jensen Huang, Alex Karp, Alex Ziskind, Jamison Greer, etc.
- **predictions**: extracted predictions
  - `id`, `individual_name`, `date`, `category`, `claim`, `source_url`, `transcript_excerpt`, `verdict` (null/correct/wrong), `created_at`, `measurement_type` (quantitative/subjective)

## Prediction rules

- **Max 2 predictions per source** (video/article), prioritized by measurability (dates, quantities, timeframes score higher)
- **No past-dated predictions** — if a claim references a year already passed relative to the source date, it's excluded
- **measurement_type tag**: `quantitative` (objectively verifiable — election results, price targets, production numbers) or `subjective` (matters of degree — "relations will worsen")
- **Bremmer: Quick Takes only** — `fetch_bremmer.py` filters to "Quick Take", "Ian Explains", and "Ask Ian" videos from GZERO Media

## UI layout

- **4 columns** (one per tracked individual), fixed order: Zeihan, Doomberg, Diamandis, Bremmer
- Each column header: avatar, name, purple category badge (hover shows panel tooltip with "PANEL" in orange), scorecard (total/correct/wrong counts)
- **Objective/Subjective toggle buttons** — green when on, red when off. Default: objective only. Both off = empty columns. Counts update live.
- Below each header: top 5 predictions per person (after filter), stacked from the top
- Each prediction entry: date, clickable orange claim text with ↗ (opens source URL), "Panel Judgement: TBD" box
- **Click a column header (name)** → full-screen overlay with all that person's predictions in a 4-column card grid
- **Click 👍 or 👎** → detail view filtered to only correct or wrong predictions
- **Settings button** (⚙) → dropdown with light/dark mode toggle
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

## Local model

- **llama-server** running on port 18434 with API key (check config or process command line)
- Models available: Qwen3.8-27B-UD-Q4_K_M (default), Qwen3.6-35B-A3B-UD-Q4_K_M, Qwen3-32B-Q5_K_M
- Model files at `C:/Users/schof/AppData/Local/hermes/models/`
- Config: `hermes config set providers.llamacpp.base_url http://127.0.0.1:18434/v1`
- Fallback: HermesMac Ollama at `upthread64.tail5b3b50.ts.net:11434` (qwen3-coder:30b-32k)

## Current data coverage

| Person | Predictions | Earliest | Latest |
|---|---|---|---|
| Peter Zeihan | 18 | Sep 18, 2026 | Sep 30, 2026 |
| Doomberg | 35 | Apr 30, 2024 | Sep 29, 2026 |
| Peter Diamandis | 5 | Nov 8, 2024 | Sep 13, 2026 |
| Ian Bremmer | 10 | Sep 18, 2026 | Sep 30, 2026 |

Backfill to Apr 30, 2024 is planned but paused (~4-6 hours estimated at local model speed).

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
- **Surge:** account h4martylaptop@agentmail.to, token ea807c6f912951573c26c7fed2788f3f
- **GitHub:** martyschoff/veracity2 (gh CLI authed)
- **HermesMac remote gateway:** 100.84.167.88:9119 (Tailscale), Ollama at port 11434

---

## Copyright & License

Copyright (c) 2026 Martin Schoffstall. Released under the MIT License — see [LICENSE](LICENSE).
All rights in the underlying prediction corpus and grading methodology are reserved by the author.
