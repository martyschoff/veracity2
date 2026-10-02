import json
from pathlib import Path
from datetime import datetime

data_file = Path("data/predictions.json")
with open(data_file, "r") as f:
    data = json.load(f)

preds = data["predictions"]
total = len(preds)
statuses = {}
verdicts = {}
for p in preds:
    s = p.get("test_status", "unknown")
    statuses[s] = statuses.get(s, 0) + 1
    v = p.get("verdict")
    verdicts[v] = verdicts.get(v, 0) + 1

tested = sum(1 for p in preds if p.get("test_status") in ("pending", "eligible", "judged", "disputed"))
judged = sum(1 for p in preds if p.get("test_status") == "judged")
disputed = sum(1 for p in preds if p.get("test_status") == "disputed")
retired = sum(1 for p in preds if p.get("test_status") == "expired")
pending = sum(1 for p in preds if p.get("test_status") == "pending")

print(f"Total predictions: {total}")
print(f"Status counts: {json.dumps(statuses, indent=2)}")
print(f"Verdict counts: {json.dumps(verdicts, indent=2)}")
print(f"Tested/eligible: {tested}, Judged: {judged}, Disputed: {disputed}, Retired: {retired}, Pending: {pending}")
print(f"Data file modified: {datetime.fromtimestamp(data_file.stat().st_mtime)}")
