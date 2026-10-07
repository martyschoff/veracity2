"""DelphiCursor check: verify setup and show status.

Usage: python scripts/delphicursor_check.py
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / 'data' / 'predictions.json'
VERDICTS_DIR = BASE / 'data' / 'delphicursor_verdicts'
LOGS_DIR = BASE / 'data' / 'delphicursor_logs'
FAILURES_LOG = BASE / 'data' / 'delphicursor_failures.jsonl'
DISAGREEMENTS_LOG = BASE / 'data' / 'delphicursor_disagreements.jsonl'

def main():
    print("DelphiCursor Status Check")
    print("=" * 40)
    
    # Check directories
    print("\n📁 Directories:")
    for d in [VERDICTS_DIR, LOGS_DIR]:
        exists = "✓" if d.exists() else "✗"
        print(f"  {exists} {d.name}/")
    
    # Load predictions
    with open(DATA, encoding='utf-8') as f:
        data = json.load(f)
    
    predictions = data.get('predictions', [])
    
    # Count statuses
    statuses = {}
    for p in predictions:
        st = p.get('delphicursor_status', 'none')
        statuses[st] = statuses.get(st, 0) + 1
    
    print("\n📊 DelphiCursor Statuses:")
    for st, count in sorted(statuses.items()):
        print(f"  {st}: {count}")
    
    # Count verdicts
    verdicts = {'correct': 0, 'incorrect': 0, 'unclear': 0}
    has_result = 0
    for p in predictions:
        if p.get('delphicursor_result'):
            has_result += 1
            vote = p['delphicursor_result'].get('vote')
            if vote in verdicts:
                verdicts[vote] += 1
    
    print(f"\n🔮 DelphiCursor Results: {has_result} predictions")
    if has_result:
        for v, c in verdicts.items():
            print(f"  {v}: {c}")
    
    # Check verdict files
    verdict_files = list(VERDICTS_DIR.glob('*.json')) if VERDICTS_DIR.exists() else []
    print(f"\n📄 Verdict files: {len(verdict_files)}")
    
    # Check logs
    log_files = list(LOGS_DIR.glob('*.log')) if LOGS_DIR.exists() else []
    print(f"📜 Log files: {len(log_files)}")
    
    # Check failures
    if FAILURES_LOG.exists():
        failures = FAILURES_LOG.read_text().strip().split('\n')
        failures = [f for f in failures if f]
        print(f"⚠️  Failures logged: {len(failures)}")
    else:
        print("⚠️  No failure log yet")
    
    # Check disagreements
    if DISAGREEMENTS_LOG.exists():
        disagreements = DISAGREEMENTS_LOG.read_text().strip().split('\n')
        disagreements = [d for d in disagreements if d]
        print(f"🔀 Disagreements logged: {len(disagreements)}")
    else:
        print("🔀 No disagreements logged yet")
    
    # Show recent verdicts
    recent = []
    for p in predictions:
        if p.get('delphicursor_result'):
            recent.append((
                p.get('delphicursor_result', {}).get('judged_at', ''),
                p['id'],
                p.get('delphicursor_result', {}).get('vote', ''),
                p.get('claim', '')[:50]
            ))
    recent.sort(reverse=True)
    
    if recent:
        print("\n🕐 Recent DelphiCursor Verdicts:")
        for ts, pid, vote, claim in recent[:5]:
            print(f"  [{vote}] {claim}...")
    
    print("\n" + "=" * 40)
    print("To queue eligible claims:")
    print("  python scripts/delphicursor_queue.py")
    print("To process queue:")
    print("  python scripts/delphicursor_worker.py --once")


if __name__ == '__main__':
    main()
