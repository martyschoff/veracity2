# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Retest the two Moonshots videos with debug raw logging."""
import json, sys
sys.path.insert(0, r"C:/Users/schof/veracity2")
from src.speaker_extract import identify_speakers, extract_attributed_predictions, allocate_roster, get_endpoint_used

OUT = "data/speaker_test"
results = []
for name in ["moonshots_susskind", "moonshots_housel"]:
    meta = json.load(open(f"{OUT}/{name}_meta.json", encoding="utf-8"))
    transcript = open(f"{OUT}/{name}.txt", encoding="utf-8").read()
    print(f"\n=== {name}")
    cast = identify_speakers(meta["title"], meta["description"], transcript)
    print("CAST:", json.dumps(cast))
    attributed = extract_attributed_predictions(
        meta["title"], meta["description"], transcript,
        video_url=f"https://www.youtube.com/watch?v={meta['id']}",
        upload_date=meta["upload_date"],
        channel_owner=meta.get("channel"),
        debug_raw_path=f"{OUT}/raw_{name}.log",
    )
    alloc = allocate_roster(attributed)
    print("PREDICTIONS:", json.dumps(attributed["predictions"], indent=1))
    print("UNATTRIBUTED:", attributed["unattributed"])
    print("ALLOCATION:", json.dumps(alloc, indent=1))
    results.append({"test": name, "cast": cast, "predictions": attributed["predictions"],
                    "unattributed": attributed["unattributed"], "allocation": alloc})

json.dump({"endpoint_used": get_endpoint_used(), "results": results},
          open(f"{OUT}/results_moonshots.json", "w", encoding="utf-8"), indent=1)
print("\nENDPOINT:", get_endpoint_used())
