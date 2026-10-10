# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""400-persona mega-swarm on the big3080 7-GPU pool (owner-cleared 2026-10-07).

Runs 400 personas on claims that already have a 40-persona swarm result.
Results go ONLY to data/swarm400_state.json (comparison store) - predictions.json
is never touched ("don't post to app").

Usage: python scripts/monte_carlo_400.py [--claims id1,id2,...]
"""
import concurrent.futures
import datetime
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import call_llm
from monte_carlo import build_personas, AXES

DATA = Path(__file__).resolve().parent.parent / "data" / "predictions.json"
OUT = Path(__file__).resolve().parent.parent / "data" / "swarm400_state.json"

# 7-GPU pool on big3080 (GPUs 1-7; GPU0 = whisper, never unloaded)
POOL = [{"url": f"http://100.124.236.23:{p}/v1/chat/completions", "key": None, "model": "qwen3:8b"}
        for p in (11500, 11435, 11436, 11437, 11438, 11439, 11440, 11441)]  # all 8 GPUs (owner cleared)


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
    ep = POOL[hash(persona) % len(POOL)]
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


def aggregate(votes: list) -> dict:
    yes = sum(1 for v in votes if v["verdict"] == "yes")
    no = sum(1 for v in votes if v["verdict"] == "no")
    unc = sum(1 for v in votes if v["verdict"] == "unclear")
    decided = yes + no
    if decided == 0:
        return {"result": "undetermined (all unclear)", "split": None, "yes": yes, "no": no, "unclear": unc, "n": len(votes)}
    pct_yes = round(100 * yes / decided)
    return {"result": f"{'RIGHT' if pct_yes >= 50 else 'WRONG'} ({pct_yes}% of {decided} decided, {unc} unclear)",
            "split": min(pct_yes, 100 - pct_yes), "yes": yes, "no": no, "unclear": unc, "n": len(votes)}


def main():
    claims_filter = None
    if "--claims" in sys.argv:
        ids = sys.argv[sys.argv.index("--claims") + 1].split(",")
        claims_filter = set(i.strip() for i in ids)
    data = json.load(open(DATA, encoding="utf-8"))
    targets = [p for p in data["predictions"]
               if p.get("mc_status") == "done" and p.get("mc_result")
               and (not claims_filter or p["id"] in claims_filter)]
    print(f"{len(targets)} claim(s) to mega-swarm at 400 personas", flush=True)
    state = json.load(open(OUT, encoding="utf-8")) if OUT.exists() else {"runs": {}}
    personas = build_personas(400)
    for pred in targets:
        pid = pred["id"]
        if pid in state["runs"] and state["runs"][pid].get("result400"):
            print(f"skip {pid} (already done)", flush=True)
            continue
        t0 = time.time()
        votes = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=42) as pool:
            futs = [pool.submit(persona_vote, persona, pred["claim"], pred.get("date", "unknown")) for persona in personas]
            for i, fut in enumerate(concurrent.futures.as_completed(futs), 1):
                v = fut.result()
                if v:
                    votes.append(v)
                if i % 50 == 0:
                    print(f"  {pid[-6:]}: {i}/400 voted ({len(votes)} valid)", flush=True)
        agg = aggregate(votes)
        dt = round(time.time() - t0, 1)
        state["runs"][pid] = {
            "claim": pred["claim"][:140], "date": pred.get("date"),
            "result40": pred.get("mc_result"), "split40": pred.get("mc_split"),
            "result400": agg["result"], "split400": agg["split"],
            "votes400": agg, "seconds": dt,
        }
        OUT.write_text(json.dumps(state, indent=1), encoding="utf-8")
        print(f"  => {pid[-6:]} 400: {agg['result']} ({dt}s) | 40 was: {pred.get('mc_result')}", flush=True)
    print("SWARM400_DONE", flush=True)


if __name__ == "__main__":
    main()
