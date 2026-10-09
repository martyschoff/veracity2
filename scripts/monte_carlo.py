# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Monte Carlo persona-swarm assessment (Phase 1).

For each prediction with mc_status == 'queued':
  - Generate N diverse personas (vary expertise, politics, region, optimism)
  - Each persona judges the claim in one short call: plausible/won't-happen + confidence
  - Aggregate: majority direction + spread -> mc_verdict like "NO (64% of 40)"
  - Write mc_status='done', mc_result on the prediction; render/deploy left to caller

Endpoints: nimo128 first (producer), local 27B fallback. Run after a Marty mark.
Usage: python scripts/monte_carlo.py [--n 40]
"""
import datetime
import json
import re
import sys
from pathlib import Path

import filelock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_lock import locked_data
from src.pipeline import PRODUCER_ENDPOINTS, call_llm

# Swarm vote endpoints: nimo128 + 3080 box 7B (parallel workers)
SWARM_ENDPOINTS = [
    *PRODUCER_ENDPOINTS,
    {"url": "http://100.120.21.39:11434/v1/chat/completions", "key": None, "model": "llama3.1:8b"},
    # 3080 pool: 7 instances, GPUs 1-7 (user released 2026-10-06). Full paths required -
    # call_llm posts to ep['url'] verbatim (the /v1-only form 404s).
    {"url": "http://100.124.236.23:11434/v1/chat/completions", "key": None, "model": "qwen3:8b"},  # GPU0 (qwen3:8b only; whisper not running on TJ1)
    {"url": "http://100.124.236.23:11435/v1/chat/completions", "key": None, "model": "qwen3:8b"},
    {"url": "http://100.124.236.23:11436/v1/chat/completions", "key": None, "model": "qwen3:8b"},
    {"url": "http://100.124.236.23:11437/v1/chat/completions", "key": None, "model": "qwen3:8b"},
    {"url": "http://100.124.236.23:11438/v1/chat/completions", "key": None, "model": "qwen3:8b"},
    {"url": "http://100.124.236.23:11439/v1/chat/completions", "key": None, "model": "qwen3:8b"},
    {"url": "http://100.124.236.23:11440/v1/chat/completions", "key": None, "model": "qwen3:8b"},
    {"url": "http://100.124.236.23:11441/v1/chat/completions", "key": None, "model": "qwen3:8b"},
]

N_DEFAULT = 40
DATA = Path(__file__).resolve().parent.parent / "data" / "predictions.json"
LOCK = DATA.with_suffix('.json.lock')

AXES = [
    ("expertise", ["an economist", "a geopolitical analyst", "an energy markets trader",
                   "an AI researcher", "a historian", "a retired intelligence officer",
                   "a commodities investor", "a policy bureaucrat", "a technology entrepreneur",
                   "an academic demographer"]),
    ("politics", ["hawkish conservative", "progressive", "libertarian", "centrist pragmatist",
                  "populist nationalist", "institutionalist"]),
    ("region", ["North America", "Europe", "East Asia", "South Asia", "Middle East",
                "Latin America", "Africa", "Russia/CIS"]),
    ("disposition", ["skeptical of hype", "techno-optimist", "catastrophe-minded",
                     "steady-state pragmatist", "contrarian"]),
]


def build_personas(n: int) -> list:
    """Deterministic-ish diverse persona grid."""
    import itertools
    combos = list(itertools.product(range(10), range(6), range(8), range(5)))
    step = max(1, len(combos) // n)
    personas = []
    for k in range(n):
        e, pol, r, d = combos[(k * step) % len(combos)]
        personas.append(f"{AXES[3][1][d]} {AXES[0][1][e]} from {AXES[2][1][r]}, "
                        f"politically {AXES[1][1][pol]}")
    return personas[:n]


def persona_vote(persona: str, claim: str, made_date: str) -> dict | None:
    system = (
        f"You are {persona}, asked to assess a prediction made on {made_date}. "
        "Judge it as of today. IMPORTANT: if the prediction's target date is still in the future, "
        "it has NOT failed merely because it has not happened yet - answer 'yes' if current evidence "
        "shows it is on track, 'unclear' if there is not enough evidence either way, and 'no' only if "
        "there is positive evidence it failed or its deadline has passed unmet. "
        "Answer ONLY JSON: {\"verdict\": \"yes\"|\"no\"|\"unclear\", \"confidence\": 0-100, "
        "\"reason\": \"max 20 words\"}. 'yes' = happened or on track. "
        "'no' = failed or will not happen. 'unclear' = undeterminable."
    )
    ep = SWARM_ENDPOINTS[hash(persona) % len(SWARM_ENDPOINTS)]
    raw = call_llm(system, f"Prediction: {claim}", max_tokens=300, endpoints=[ep])
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        if v.get("verdict") in ("yes", "no", "unclear"):
            return v
    except json.JSONDecodeError:
        pass
    return None


def run(n: int = N_DEFAULT):
    # Load + build queue using locked_data
    with locked_data() as data:
        today = datetime.date.today().isoformat()
        queue = []
        for p in data["predictions"]:
            if p.get("mc_status") != "queued":
                continue
            year_m = re.search(r"\b(20[2-9]\d)\b", p.get("claim", ""))
            due = (p.get("test_eligible_at") or (f"{year_m.group(1)}-12-31" if year_m else None))
            if due and due > today:
                p["mc_status"] = "not_due"
                p["mc_result"] = None
                continue
            queue.append(p)

    if not queue:
        print("Monte Carlo queue is empty.")
        return
    personas = build_personas(n)
    print(f"{len(queue)} prediction(s) queued; {len(personas)} personas each")
    for pred in queue:
        pred_id = pred.get("id")
        import concurrent.futures
        votes = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(persona_vote, persona, pred["claim"], pred.get("date", "unknown")): i
                    for i, persona in enumerate(personas)}
            for done, fut in enumerate(concurrent.futures.as_completed(futs), 1):
                v = fut.result()
                if v:
                    votes.append(v)
                if done % 10 == 0:
                    print(f"  {done}/{len(personas)} personas voted ({len(votes)} valid)", flush=True)
        yes = sum(1 for v in votes if v["verdict"] == "yes")
        no = sum(1 for v in votes if v["verdict"] == "no")
        unc = sum(1 for v in votes if v["verdict"] == "unclear")
        decided = yes + no
        if decided == 0:
            mc_status = "done"
            mc_result = "undetermined (all unclear)"
            split = 0
        else:
            pct_yes = round(100 * yes / decided)
            direction = "RIGHT" if pct_yes >= 50 else "WRONG"
            split = min(pct_yes, 100 - pct_yes)
            mc_status = "done"
            mc_result = f"{direction} ({pct_yes}% of {decided} decided, {unc} unclear)"

        # Use locked_data exclusively - no double locking
        with locked_data() as data:
            target = next((x for x in data["predictions"] if x.get("id") == pred_id), None)
            if target:
                target["mc_status"] = mc_status
                target["mc_result"] = mc_result
                if decided > 0:
                    target["mc_split"] = min(pct_yes, 100 - pct_yes)
                print(f"  => {target['claim'][:60]} : {mc_result}")
            else:
                print(f"  => TARGET GONE: {pred_id}", flush=True)
    print("Saved. Render+deploy to publish badges.")


if __name__ == "__main__":
    n = N_DEFAULT
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    run(n)
