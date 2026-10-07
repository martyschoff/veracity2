# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Origin resweep (BUILD 2): regex-flag existing predictions containing reporting
language, LLM-judge each flagged prediction with its transcript_excerpt, and move
misattributed ones from data/predictions.json to data/guest_pool.json.

Coordination: waits for the attribution resweep (data/qa_results.json fully
covering data/qa_queue.json) to finish before writing; re-reads predictions.json
immediately before each write.
"""
import json
import re
import sys
import time
import urllib.request

REPO = "C:/Users/schof/veracity2"
PRED = f"{REPO}/data/predictions.json"
POOL = f"{REPO}/data/guest_pool.json"
QA_QUEUE = f"{REPO}/data/qa_queue.json"
QA_RESULTS = f"{REPO}/data/qa_results.json"

REPORT_RE = re.compile(
    r"according to|is saying|forecasts?\b|predicts that|paper says|the report\b|"
    r"report says|expects that|per the\b|\bsays that\b|\bforecast by\b|"
    r"\bprojects? that\b|\bconcludes that\b|\bper\b [A-Z]|\bquoted\b",
    re.IGNORECASE,
)

ENDPOINTS = [
    ("http://100.84.167.88:11434/v1/chat/completions", "qwen3:32b", None),
    ("http://127.0.0.1:18434/v1/chat/completions", "Qwen3.8-27B-UD-Q4_K_M", "OyISwmqwQMak4mEOtO3zajuzSY8clG73"),
    ("http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions", "qwen3-coder:30b-32k", None),
]

SYS = (
    "You are a claim-origin auditor. Each item is a prediction filed under a tracked "
    "individual, with claim and transcript excerpt. Decide: is this the tracked person's "
    "OWN prediction (first-person assertion), or a REPORTED/QUOTED third-party forecast "
    "(e.g. 'Anthropic is saying...', 'according to the CBO', inside quotes, a guest's view)?\n"
    'Reply ONLY JSON: {"results":[{"i":<idx>,"origin":"own"|"reported"|"quoted",'
    '"speaker":"<best-known third-party name, empty if own>","confidence":0-1,"reason":"short"}]}'
)


def llm(messages, timeout=420):
    last = None
    for url, model, key in ENDPOINTS:
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        body = {"model": model, "messages": messages, "max_tokens": 3000, "temperature": 0}
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            o = json.load(urllib.request.urlopen(req, timeout=timeout))
            m = o["choices"][0]["message"]
            c = m.get("content") or m.get("reasoning") or m.get("reasoning_content") or ""
            if c.strip():
                return c
        except Exception as e:
            last = e
            print(f"  endpoint fail {model}: {str(e)[:80]}", flush=True)
    raise RuntimeError(f"all endpoints failed: {last}")


def parse(out, idxs):
    s, e = out.find("{"), out.rfind("}")
    data = json.loads(out[s:e + 1])
    res = {}
    for r in data.get("results", []):
        try:
            i = int(r["i"])
        except (KeyError, ValueError, TypeError):
            continue
        if i in idxs:
            res[i] = r
    return res


def attribution_resweep_done() -> bool:
    try:
        q = json.load(open(QA_QUEUE, encoding="utf-8"))
        r = json.load(open(QA_RESULTS, encoding="utf-8"))
        ids = set(k for k in (q.keys() if isinstance(q, dict) else range(len(q))))
        done = set(v.get("id") for v in r.values())
        return len(done) >= len(ids)
    except Exception:
        return False


def person_total(preds, name):
    return sum(1 for p in preds if p.get("individual_name") == name)


def person_month(preds, name, month):
    return sum(1 for p in preds if p.get("individual_name") == name and (p.get("date") or "")[:7] == month)


def main():
    # Wait for the attribution resweep agent to finish before touching anything
    while not attribution_resweep_done():
        print("waiting for attribution resweep (qa_results vs qa_queue)...", flush=True)
        time.sleep(60)
    print("attribution resweep complete; starting origin resweep", flush=True)

    data = json.load(open(PRED, encoding="utf-8"))
    preds = data["predictions"]
    flagged = [p for p in preds
               if p.get("verdict") not in ("expired",)
               and REPORT_RE.search(p.get("claim", "") or "")]
    print(f"flagged {len(flagged)} of {len(preds)} by regex", flush=True)

    pool = json.load(open(POOL, encoding="utf-8")) if __import__("os").path.exists(POOL) else []
    removed = 0
    reviewed = 0
    BATCH = 10
    for b in range(0, len(flagged), BATCH):
        batch = flagged[b:b + BATCH]
        items = []
        for j, p in enumerate(batch):
            items.append(f'{j}. claim: {p.get("claim","")[:300]}\n   excerpt: {(p.get("transcript_excerpt") or "")[:500]}')
        user = "Items:\n" + "\n".join(items)
        try:
            out = llm([{"role": "system", "content": SYS}, {"role": "user", "content": user}])
            res = parse(out, set(range(len(batch))))
        except Exception as e:
            print(f"batch {b} failed: {e}", flush=True)
            reviewed += len(batch)
            continue
        for j, p in enumerate(batch):
            reviewed += 1
            r = res.get(j)
            if not r:
                continue
            origin = r.get("origin", "own")
            if origin == "own":
                continue
            # Excess rule: liberal for big rosters, conservative otherwise
            liberal = person_total(preds, p.get("individual_name", "")) > 100 or \
                person_month(preds, p.get("individual_name", ""), (p.get("date") or "")[:7]) > 10
            conf = float(r.get("confidence", 0) or 0)
            threshold = 0.5 if liberal else 0.8
            if conf < threshold:
                continue
            # Re-read immediately before write (clobber protection)
            fresh = json.load(open(PRED, encoding="utf-8"))
            ids = {q["id"] for q in fresh["predictions"]}
            if p["id"] not in ids:
                print(f"  {p['id']} already removed by another process", flush=True)
                continue
            fresh["predictions"] = [q for q in fresh["predictions"] if q["id"] != p["id"]]
            preds = fresh["predictions"]
            json.dump(fresh, open(PRED, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            pool.append({
                "speaker": r.get("speaker") or "unknown third party",
                "claim": p.get("claim"),
                "date": p.get("date"),
                "source_url": p.get("source_url"),
                "reason": f"origin resweep: {origin} (conf {conf}); {r.get('reason','')[:200]}",
            })
            json.dump(pool, open(POOL, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            removed += 1
            print(f"  REMOVED {p['id']} ({origin}, conf {conf}): {p.get('claim','')[:70]}", flush=True)
        print(f"progress: reviewed {reviewed}/{len(flagged)}, removed {removed}", flush=True)

    print(f"DONE: flagged_and_reviewed={reviewed} removed_to_pool={removed}", flush=True)


if __name__ == "__main__":
    main()
