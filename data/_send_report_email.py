import json, urllib.request, datetime
key = "am_us_inbox_815c96b569d38aa68e9c41bc1a51a5fe16086de96fe26ba8ac6d0fce99100e61"
md = """# Seer Score Daily Report — Fri Oct 9, 2026 09:03 ET

All three workers (MiroFish, swarm, DelphiCursor) restarted early Oct 9 after crashing overnight on the predictions.json structure clobber (fix committed c8e6739). Harvest daemon v2 active (heartbeat 09:02:36).

## Per-person verdict states (correct/wrong/expired/tbd) — 1,267 predictions
| Person | Total | Correct | Wrong | Expired | TBD | Decided score |
|---|---|---|---|---|---|---|
| Peter Zeihan | 779 | 99 | 9 | 12 | 659 | 91.7% |
| Doomberg | 110 | 31 | 2 | 0 | 77 | 93.9% |
| Peter Diamandis | 110 | 1 | 0 | 0 | 109 | 100% |
| Ian Bremmer | 225 | 71 | 40 | 0 | 114 | 64.0% |
| David McAlvany | 38 | 14 | 6 | 0 | 18 | 70.0% |

Global: 216 correct / 57 wrong / 12 expired / 982 tbd. Marty marks: 8 (3 correct / 5 wrong). Authoritative overrides: 1 (Bremmer "Mamdani wins NYC mayor" → correct).

## Queues
- mc_status: 7 done, 1 queued, 6 not_due
- miro_status: 9 done, 1 queued
- gate/implicit: 307 queued; qa_queue 1,435; deepqa ids missing 539; test eligible 243 (17 expired)

## In-flight jobs & ETAs
- **MiroFish**: RUNNING (nimo128 via proxy). 1 queued + 1 in-flight (pred_1790961078_13 Japan rates). Rate ~13.5 min/claim (~4.4 preds/hr). **ETA ~27 min.**
- **Swarm worker (40-persona MC)**: RUNNING, pass on 2 queued started 05:55. Rate ~12 min/claim (avg 700-912 s over 5 runs). **ETA ~25 min.**
- **DelphiCursor (Opus)**: RUNNING, queue depth 1. Rate ~1 min/claim (~60 claims/hr). **ETA ~2-3 min.**
- **Harvest daemon v2**: ACTIVE, all 7 queue sources completed as of 08:32 (Roubini 15 processed/+4 kept; McAlvany +1 Rickards; others 0). Rate when active ~82 articles/hr (~15 per 11 min). **ETA: queue drained — idle until next cycle.**
- DeepQA / classify workers: stopped since Oct 7-8 — no ETA (need relaunch).

## Swarm results (5 runs, 40 vs 400 personas)
- China chips >28nm: WRONG (38% of 40 / 43% of 400)
- US loses chip supply chains 4-6yr: WRONG (0% / 0%)
- Green transition 10x nickel: WRONG (33% / 32%)
- Russia-Ukraine shifts toward Ukraine: RIGHT (100% / 100% of 185)
- pred_1790961078_15: WRONG (0% / 5%)
400 agreed with 40 in 5/5 runs; unclear balloons at 400.

## Git
HEAD 35aaeea (harvest daemon v2). Modified: harvest_heartbeat.txt. Recent: cf9a8dd swarm sync, c8e6739 structure-clobber restore.

Dashboard: C:/Users/schof/veracity2/data/report_daily.html
"""
msg = {
    "from": "Seer Score Bot <seerscore@agentmail.to>",
    "to": ["h4martylaptop@agentmail.to"],
    "subject": "Seer Score Daily Report + ETAs",
    "text": md,
    "html": "<pre style=\"font-family:Consolas,monospace;font-size:12px\">" + md.replace("&","&amp;").replace("<","&lt;") + "</pre>",
}
req = urllib.request.Request(
    "https://api.agentmail.to/v0/emails",
    data=json.dumps(msg).encode(),
    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    method="POST")
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(r.status, r.read().decode()[:500])
except Exception as e:
    print("ERR", e)
    try:
        print(e.read().decode()[:500])
    except Exception:
        pass
