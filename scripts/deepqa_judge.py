"""Deep QA judge: for thin-excerpt predictions with a fetched full transcript,
re-judge own-voice vs reported/quoted/third-party/past-fact.

Run only after deepqa_fetch shards are done. Single process, nimo128 primary,
tower1 gpt-oss:120b escalation for borderline removals.
State: data/deepqa_judge_state.json
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import call_llm  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
CACHE = Path(r"C:/Users/schof/AppData/Local/hermes/cache/web")
STATE = DATA / "deepqa_judge_state.json"

NIMO = {"url": "http://100.84.167.88:11434/v1/chat/completions", "key": None, "model": "qwen3:32b"}
TOWER = {"url": "http://tower1.tail5b3b50.ts.net:11434/v1/chat/completions", "key": None,
         "model": "gpt-oss:120b"}

SYSTEM = (
    "You are a strict QA judge for a prediction-tracking site. You are given:\n"
    "- PREDICTION stored on the site (claim + excerpt)\n"
    "- CONTEXT: a window of the FULL transcript/article from the same source.\n"
    "Decide the claim's ORIGIN and STATUS in the source text:\n"
    "- OWNS: the speaker asserts the forecast in their own voice (first-person or unhedged\n"
    "  narration from the speaker) -> KEEP\n"
    "- REPORTED: the speaker is relaying someone else's forecast/analysis (attributed or\n"
    "  clearly describing what others say/believe) -> REMOVE\n"
    "- QUOTED: inside quotes, read-aloud material, viewer/email questions, headlines -> REMOVE\n"
    "- PAST-FACT: the text only describes past or present events, no forward-looking claim -> REMOVE\n"
    "- NOT-FOUND: the claim can't be located or substantiated in the context -> REMOVE\n"
    "- KEEP-REVISED: the forecast exists in own voice but the stored claim misstates it;\n"
    "  give 'revised_claim' with corrected wording.\n"
    "Also return 'context_excerpt': the ~1-2 sentence passage from CONTEXT that grounds the\n"
    "prediction (verbatim), or empty string.\n"
    "Borderline? Set 'borderline': true and explain in 'reason'.\n"
    'Return ONLY JSON: {"origin": "...", "borderline": true/false, "reason": "...", '
    '"context_excerpt": "...", "revised_claim": ""}\n'
)

INVALID = {"REPORTED", "QUOTED", "PAST-FACT", "NOT-FOUND"}


def load_state():
    if STATE.exists():
        return json.load(open(STATE, encoding="utf-8"))
    return {"judged": {}, "counts": {}}


def find_context(text, claim, excerpt, win=3500):
    text_l = text.lower()
    # candidate anchor phrases: content words from claim
    words = re.findall(r"[a-z0-9$%']{4,}", claim.lower())
    words = [w for w in words if w not in
             {"will", "have", "this", "that", "with", "from", "they", "their", "there",
              "about", "going", "into", "over", "than", "then", "just", "also", "more",
              "much", "some", "been", "were", "because"}]
    best, best_score = 0, 0
    step = 400
    for pos in range(0, max(1, len(text_l) - 200), step):
        chunk = text_l[pos:pos + win]
        score = sum(1 for w in words if w in chunk)
        if score > best_score:
            best_score, best = score, pos
    if best_score == 0:
        return ""
    start = max(0, best - 200)
    return text[start:start + win + 200]


def parse_json(s):
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def main():
    preds = json.load(open(DATA / "predictions.json", encoding="utf-8"))["predictions"]
    st = load_state()
    targets = [p for p in preds if len(p.get("transcript_excerpt") or "") < 200]
    print(f"targets={len(targets)} already_judged={len(st['judged'])}", flush=True)
    for n, p in enumerate(targets):
        pid = p["id"]
        if pid in st["judged"]:
            continue
        m = re.search(r"v=([\w-]{11})", p.get("source_url") or "")
        if not m:
            st["judged"][pid] = {"status": "no_yt_id", "origin": "SKIP"}
            continue
        f = CACHE / f"ytdlp-{m.group(1)}.md"
        if not f.exists():
            st["judged"][pid] = {"status": "not_fetched", "origin": "SKIP"}
            continue
        md = f.read_text(encoding="utf-8", errors="replace")
        if "[no-track]" in md or "## Transcript" not in md:
            st["judged"][pid] = {"status": md.split("## Transcript")[1][:20] if "## Transcript" in md else "bad",
                                 "origin": "SKIP"}
            continue
        body = md.split("## Transcript", 1)[1][:60000]
        ctx = find_context(body, p["claim"], p.get("transcript_excerpt") or "")
        if not ctx or len(ctx) < 100:
            ctx = body[:3500]
            found = "no-match-used-head"
        else:
            found = "match"
        user = (f"PREDICTION claim: {p['claim']}\n"
                f"stored excerpt: {(p.get('transcript_excerpt') or '')[:400]}\n\n"
                f"CONTEXT:\n{ctx}")
        res = None
        for attempt in range(3):
            resp = call_llm(SYSTEM, user, max_tokens=2500, endpoints=[NIMO])
            res = parse_json(resp or "")
            if res and res.get("origin"):
                break
            time.sleep(4)
        if not res:
            st["judged"][pid] = {"status": "llm_fail", "origin": "SKIP", "found": found}
            continue
        entry = {"status": "judged", "found": found,
                 "origin": str(res.get("origin", "")).upper().strip(),
                 "borderline": bool(res.get("borderline")),
                 "reason": res.get("reason", ""),
                 "context_excerpt": res.get("context_excerpt", ""),
                 "revised_claim": res.get("revised_claim", "")}
        # escalation for removal decisions
        if entry["origin"] in INVALID or entry["borderline"]:
            resp2 = call_llm(SYSTEM, user + "\n\nNOTE: a first judge said "
                             f"{entry['origin']}. Decide independently; be conservative about "
                             "removal: only remove if you are CONFIDENT the claim is not owned.",
                             max_tokens=2500, endpoints=[TOWER])
            res2 = parse_json(resp2 or "")
            if res2 and res2.get("origin"):
                entry["escalated"] = True
                entry["tower_origin"] = str(res2.get("origin", "")).upper().strip()
                if entry["origin"] in INVALID and entry["tower_origin"] not in INVALID:
                    entry["origin"] = "OWNS"  # tower overrides removal
                    entry["reason"] += " | tower override: kept"
        st["judged"][pid] = entry
        st["counts"][entry["origin"]] = st["counts"].get(entry["origin"], 0) + 1
        if (n + 1) % 10 == 0:
            st["_saved_at"] = time.strftime("%H:%M:%S")
            STATE.write_text(json.dumps(st, indent=1), encoding="utf-8")
            print(f"{n+1}/{len(targets)} counts={st['counts']}", flush=True)
    STATE.write_text(json.dumps(st, indent=1), encoding="utf-8")
    print("JUDGE DONE", st["counts"], flush=True)


if __name__ == "__main__":
    main()
