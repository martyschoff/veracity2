"""Combined backfill driver: fetch (yt-dlp android_vr) + extract (LLM) for next N videos.

Usage: python run_batch.py <channel> <count> [--merge] [--deploy]
"""
import sys, json, os, subprocess

ROOT = r"C:/Users/schof/veracity2"
sys.path.insert(0, ROOT)


def next_ids(channel, count):
    preds = json.load(open(os.path.join(ROOT, "data/predictions.json")))
    urls = set(p["source_url"] for p in preds["predictions"])
    state = json.load(open(os.path.join(ROOT, "backfill_state.json")))["processed"]
    q = json.load(open(os.path.join(ROOT, "work_queue.json")))[channel]
    out = []
    for v in q:
        if len(out) >= count:
            break
        vid = v["id"]
        if vid in state or f"https://www.youtube.com/watch?v={vid}" in urls:
            continue
        out.append(vid)
    return out


def main():
    channel = sys.argv[1]
    count = int(sys.argv[2])
    ids = next_ids(channel, count)
    print(f"[batch] {channel}: {len(ids)} videos to fetch", flush=True)
    if ids:
        # fetch via yt-dlp
        r = subprocess.run([sys.executable, "fetch_captions2.py"] + ids,
                           capture_output=True, text=True, cwd=ROOT)
        for line in r.stdout.splitlines():
            if " OK " in line or " FAIL" in line or " ERR" in line:
                print("  fetch:", line.split("\r")[-1], flush=True)
        if r.returncode != 0:
            print("  fetch rc", r.returncode, r.stderr[-500:], flush=True)
    # extract
    r = subprocess.run([sys.executable, "backfill3.py", "process", channel] + ids,
                       capture_output=True, text=True, cwd=ROOT)
    print("\n".join(l for l in r.stdout.splitlines() if "HTTP Request" not in l)[-3000:], flush=True)
    if "--merge" in sys.argv:
        r = subprocess.run([sys.executable, "backfill3.py", "merge"], capture_output=True, text=True, cwd=ROOT)
        print(r.stdout, flush=True)
    if "--deploy" in sys.argv:
        env = dict(os.environ, SURGE_TOKEN="ea807c6f912951573c26c7fed2788f3f")
        subprocess.run([sys.executable, "render.py"], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["surge", "surge_dist/", "veracity2.surge.sh"], cwd=ROOT, check=True, env=env,
                       capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=ROOT)
        subprocess.run(["git", "commit", "-qm", "backfill: automated batch"], cwd=ROOT)
        subprocess.run(["git", "push", "-q"], cwd=ROOT)
        print("[deploy] done", flush=True)


if __name__ == "__main__":
    main()
