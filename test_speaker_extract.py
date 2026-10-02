"""Validation run for speaker attribution — writes ONLY to data/speaker_test/."""
import json
import sys

sys.path.insert(0, r"C:/Users/schof/veracity2")
from src.speaker_extract import (
    call_llm, extract_attributed_predictions, allocate_roster,
    identify_speakers, get_endpoint_used,
)

OUT = "data/speaker_test"
VIDS = [
    ("moonshots_susskind", "Daniel Susskind", False),
    ("moonshots_housel", "Morgan Housel", False),
    ("zeihan_solo", "Peter Zeihan", True),
]

# sanity: endpoint alive
print("PING:", call_llm([{"role": "user", "content": "say OK"}]))

results = []
for name, guest, solo in VIDS:
    meta = json.load(open(f"{OUT}/{name}_meta.json", encoding="utf-8"))
    transcript = open(f"{OUT}/{name}.txt", encoding="utf-8").read()
    print(f"\n=== {name}: {meta['title']} ({meta['upload_date']}) len={len(transcript)}")
    cast = identify_speakers(meta["title"], meta["description"], transcript)
    print("CAST:", json.dumps(cast, indent=1))
    attributed = extract_attributed_predictions(
        meta["title"], meta["description"], transcript,
        video_url=f"https://www.youtube.com/watch?v={meta['id']}",
        upload_date=meta["upload_date"],
        channel_owner=meta.get("channel"),
    )
    alloc = allocate_roster(attributed)
    print("PREDICTIONS:", json.dumps(attributed["predictions"], indent=1))
    print("UNATTRIBUTED:", len(attributed["unattributed"]))
    print("ROSTER:", json.dumps(alloc, indent=1))
    results.append({
        "test": name, "title": meta["title"], "upload_date": meta["upload_date"],
        "cast": cast, "predictions": attributed["predictions"],
        "unattributed_count": len(attributed["unattributed"]),
        "allocation": alloc,
    })

json.dump({"endpoint_used": get_endpoint_used(), "results": results},
          open(f"{OUT}/results.json", "w", encoding="utf-8"), indent=1)
print("\nENDPOINT USED:", get_endpoint_used())
