"""Monte Carlo persona-swarm assessment (Phase 1).

For each prediction with mc_status == 'queued':
  - Generate N diverse personas (vary expertise, politics, region, optimism)
  - Each persona judges the claim in one short call: plausible/won't-happen + confidence
  - Aggregate: majority direction + spread -> mc_verdict like "NO (64% of 40)"
  - Write mc_status='done', mc_result on the prediction; render/deploy left to caller

Endpoints: nimo128 first (producer), local 27B fallback. Run after a Marty mark.
Usage: python scripts/monte_carlo.py [--n 40]
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import PRODUCER_ENDPOINTS, call_llm, load_data, save_data

N_DEFAULT = 40
DATA = Path(__file__).resolve().parent.parent / "data" / "predictions.json"

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
        "Judge it as of today: has it come true, is it on track, or will it fail? "
        "Answer ONLY JSON: {\"verdict\": \"yes\"|\"no\"|\"unclear\", \"confidence\": 0-100, "
        "\"reason\": \"max 20 words\"}. 'yes' = the prediction happened or is on track to happen. "
        "'no' = it failed or will not happen. 'unclear' = genuinely undeterminable."
    )
    raw = call_llm(system, f"Prediction: {claim}", max_tokens=200, endpoints=PRODUCER_ENDPOINTS)
    if not raw:
        return None
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
    data = load_data()
    queue = [p for p in data["predictions"] if p.get("mc_status") == "queued"]
    if not queue:
        print("Monte Carlo queue is empty.")
        return
    personas = build_personas(n)
    print(f"{len(queue)} prediction(s) queued; {len(personas)} personas each")
    for pred in queue:
        votes = []
        for i, persona in enumerate(personas):
            v = persona_vote(persona, pred["claim"], pred.get("date", "unknown"))
            if v:
                votes.append(v)
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(personas)} personas voted ({len(votes)} valid)")
        yes = sum(1 for v in votes if v["verdict"] == "yes")
        no = sum(1 for v in votes if v["verdict"] == "no")
        unc = sum(1 for v in votes if v["verdict"] == "unclear")
        decided = yes + no
        if decided == 0:
            pred["mc_status"] = "done"
            pred["mc_result"] = "undetermined (all unclear)"
            continue
        pct_yes = round(100 * yes / decided)
        direction = "YES" if pct_yes >= 50 else "NO"
        split = min(pct_yes, 100 - pct_yes)
        pred["mc_status"] = "done"
        pred["mc_result"] = f"{direction} ({pct_yes}% of {decided} decided, {unc} unclear)"
        pred["mc_split"] = split  # low = contested; phase-2 candidates
        print(f"  => {pred['claim'][:60]} : {pred['mc_result']}")
    save_data(data)
    print("Saved. Render+deploy to publish badges.")


if __name__ == "__main__":
    n = N_DEFAULT
    if "--n" in sys.argv:
        n = int(sys.argv[sys.argv.index("--n") + 1])
    run(n)
