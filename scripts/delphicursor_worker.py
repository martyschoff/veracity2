"""DelphiCursor worker: process predictions with delphicursor_status == 'queued'.

Runs Cursor (Opus) as an advisory adjudicator. Each claim gets:
- Isolated workspace directory
- Fixture file with Marty position REDACTED (blind judgment)
- 5-minute timeout, max 2 retries
- Verdict written to data/delphicursor_verdicts/

Mode A: Advisory. Marty's verdict is FINAL; DelphiCursor shown alongside for calibration.

Usage: python scripts/delphicursor_worker.py [--once]
       pythonw scripts/delphicursor_worker.py  # silent loop
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_lock import locked_data

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / 'data' / 'predictions.json'
WORKSPACE_DIR = BASE / 'data' / 'delphicursor_workspace'
VERDICTS_DIR = BASE / 'data' / 'delphicursor_verdicts'
LOGS_DIR = BASE / 'data' / 'delphicursor_logs'
FAILURES_LOG = BASE / 'data' / 'delphicursor_failures.jsonl'
DISAGREEMENTS_LOG = BASE / 'data' / 'delphicursor_disagreements.jsonl'
LOCK_FILE = BASE / 'data' / 'delphicursor.lock'
WORKER_LOG = BASE / 'data' / 'delphicursor_worker.log'

# Ensure directories exist
WORKSPACE_DIR.mkdir(exist_ok=True)
VERDICTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Timeouts
HARD_TIMEOUT = 300  # 5 minutes
SOFT_TIMEOUT = 180  # 3 minutes (warning only)
MAX_RETRIES = 2

# Cursor CLI path (Windows)
CURSOR_CLI = r'C:\Users\schof\AppData\Local\Programs\cursor\resources\app\bin\agent.cmd'


def log(msg: str):
    """Log to file and stdout."""
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(WORKER_LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def build_fixture(pred: dict, ind_data: dict) -> dict:
    """Build claim fixture with Marty position REDACTED."""
    # Extract time horizon from claim
    year_m = re.search(r'\b(20[2-9]\d)\b', pred.get('claim', ''))
    time_horizon = year_m.group(0) if year_m else 'ongoing'
    
    # Build swarm result string
    mc_result = pred.get('mc_result', '')
    mc_split = pred.get('mc_split')
    swarm_result = mc_result if mc_result else 'not_run'
    
    # Build delphi3080 info
    miro_status = pred.get('miro_status', 'not_run')
    miro_result = pred.get('miro_result', {})
    if isinstance(miro_result, dict):
        delphi_verdict = miro_result.get('verdict', 'unknown')
        delphi_summary = str(miro_result.get('summary', ''))[:200]
    else:
        delphi_verdict = str(miro_result)[:50]
        delphi_summary = ''
    
    # Build panel votes summary
    judgements = pred.get('judgements', [])
    if judgements:
        correct = sum(1 for j in judgements if j.get('verdict') == 'correct')
        incorrect = sum(1 for j in judgements if j.get('verdict') == 'incorrect')
        unclear = sum(1 for j in judgements if j.get('verdict') == 'unclear')
        total_weight = sum(j.get('weight', 1.0) for j in judgements)
        panel_summary = f"{correct} correct, {incorrect} incorrect, {unclear} unclear (total weight {total_weight:.1f})"
    else:
        panel_summary = "no panel votes"
    
    # Get predictor's weight
    predictor = pred.get('individual_name', '')
    predictor_weight = ind_data.get(predictor, {}).get('panel_weight', 1.0)
    
    fixture = {
        "claim_id": pred['id'],
        "statement": pred.get('claim', ''),
        "made_by": predictor,
        "made_on": pred.get('date', 'unknown'),
        "category": pred.get('category', 'other'),
        "time_horizon": time_horizon,
        "transcript_excerpt": (pred.get('transcript_excerpt') or pred.get('claim', ''))[:800],
        "source_url": pred.get('source_url', ''),
        "predictor_weight": predictor_weight,
        
        "adjudication_context": {
            "swarm_result": swarm_result,
            "swarm_split": mc_split,
            "delphi3080_verdict": delphi_verdict,
            "delphi3080_status": miro_status,
            "delphi3080_summary": delphi_summary,
            "panel_votes_summary": panel_summary
        },
        
        # CRITICAL: Marty's position is NEVER in the fixture
        "_redacted_note": "Marty verdict/note intentionally omitted for blind judgment"
    }
    
    return fixture


def build_prompt(current_date: str) -> str:
    """Build the system prompt for the agent."""
    return f"""You are an impartial adjudicator for a predictions-vs-reality tracker.

TASK: Judge whether the attached prediction has been proven CORRECT, INCORRECT,
or remains UNCLEAR as of today ({current_date}).

DEFINITIONS:
- CORRECT: The predicted event happened, OR for future-dated predictions,
  current evidence strongly indicates it is on track to happen.
- INCORRECT: The predicted event failed, its deadline passed unmet, OR current
  evidence strongly indicates it will not happen.
- UNCLEAR: Insufficient evidence exists to judge either way. Use this if you
  are genuinely uncertain — do not guess.

RULES:
1. You are judging the PREDICTION, not the predictor. Prior adjudicators
   disagreed — your job is to break the tie with superior reasoning.
2. For claims about verifiable public facts, you may browse to confirm. Cite
   your source if you do. Max 2 external URLs.
3. Do NOT default to "unclear" out of excessive caution. If you have a
   defensible position, commit to it.
4. Do NOT default to "correct" or "incorrect" out of false confidence. If the
   evidence is ambiguous, say UNCLEAR.
5. Predictions about the future that haven't happened yet are NOT automatically
   unclear — judge whether they are ON TRACK or OFF TRACK based on current
   evidence.
6. Confidence should reflect YOUR epistemic state, not the prediction's
   boldness.

You are running in an isolated workspace. The only files you should read are:
- claim_fixture.json (the prediction to judge)

The only file you should write is:
- verdict.json (your judgment)

Do NOT explore other directories. Do NOT read or modify any other files.

OUTPUT: Write a JSON file to verdict.json in your workspace:
{{
  "vote": "correct" | "incorrect" | "unclear",
  "confidence": 0-100,
  "reasoning": "2-3 sentences explaining your judgment",
  "sources_checked": ["url1", "url2"] or [],
  "dissent_note": "Why you disagree with swarm/delphi3080, if you do"
}}
"""


def validate_verdict(verdict: dict) -> tuple[bool, str]:
    """Validate verdict JSON against schema."""
    if not isinstance(verdict, dict):
        return False, "verdict is not a dict"
    
    vote = verdict.get('vote')
    if vote not in ('correct', 'incorrect', 'unclear'):
        return False, f"vote '{vote}' not in correct|incorrect|unclear"
    
    confidence = verdict.get('confidence')
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 100:
        return False, f"confidence {confidence} not in 0-100"
    
    reasoning = verdict.get('reasoning')
    if not reasoning or not isinstance(reasoning, str):
        return False, "reasoning missing or not string"
    
    return True, "valid"


def run_agent(workspace: Path, claim_id: str, attempt: int) -> tuple[bool, dict | None, str]:
    """Run the Cursor agent on a claim. Returns (success, verdict, error_msg)."""
    fixture_path = workspace / 'claim_fixture.json'
    verdict_path = workspace / 'verdict.json'
    log_path = LOGS_DIR / f"{claim_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_attempt{attempt}.log"
    
    # Build agent invocation command
    prompt = f"Read claim_fixture.json and write your judgment to verdict.json following the instructions in your system context."
    
    cmd = [
        CURSOR_CLI,
        '--trust',
        '--model', 'claude-sonnet-4-20250514',  # Use Sonnet 4 (Opus-class)
        '-p', prompt
    ]
    
    log(f"  Running agent (attempt {attempt}): {' '.join(cmd[:4])}...")
    
    try:
        # Read the system prompt and prepend to make it visible
        system_prompt = build_prompt(datetime.date.today().isoformat())
        
        # Write system prompt to workspace for agent to potentially read
        (workspace / 'system_prompt.txt').write_text(system_prompt, encoding='utf-8')
        
        # Modify prompt to include reading system prompt
        full_prompt = f"First read system_prompt.txt for your instructions, then read claim_fixture.json and write verdict.json."
        cmd[-1] = full_prompt
        
        # Run with timeout
        start = time.time()
        proc = subprocess.Popen(
            cmd,
            cwd=str(workspace),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=0x08000000 if sys.platform == 'win32' else 0  # CREATE_NO_WINDOW
        )
        
        # Monitor with soft/hard timeout
        output_lines = []
        soft_warned = False
        while proc.poll() is None:
            elapsed = time.time() - start
            
            if elapsed > SOFT_TIMEOUT and not soft_warned:
                log(f"  SOFT TIMEOUT ({SOFT_TIMEOUT}s) - still running...")
                soft_warned = True
            
            if elapsed > HARD_TIMEOUT:
                log(f"  HARD TIMEOUT ({HARD_TIMEOUT}s) - killing agent")
                proc.kill()
                proc.wait()
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(output_lines))
                return False, None, "timeout"
            
            # Read available output
            try:
                line = proc.stdout.readline()
                if line:
                    output_lines.append(line.rstrip())
            except Exception:
                pass
            
            time.sleep(0.5)
        
        # Collect remaining output
        remaining = proc.stdout.read()
        if remaining:
            output_lines.extend(remaining.split('\n'))
        
        # Save log
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        
        elapsed = time.time() - start
        log(f"  Agent finished in {elapsed:.1f}s (exit code {proc.returncode})")
        
        # Check for verdict file
        if not verdict_path.exists():
            return False, None, "no_verdict_file"
        
        # Parse verdict
        try:
            verdict = json.loads(verdict_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            return False, None, f"malformed_json: {e}"
        
        # Validate schema
        valid, err = validate_verdict(verdict)
        if not valid:
            return False, verdict, f"schema_violation: {err}"
        
        return True, verdict, ""
        
    except subprocess.TimeoutExpired:
        return False, None, "subprocess_timeout"
    except Exception as e:
        return False, None, f"exception: {type(e).__name__}: {e}"


def log_disagreement(pred: dict, verdict: dict):
    """Log when DelphiCursor disagrees with prior adjudicators."""
    opus_vote = verdict.get('vote')
    
    # Compare with swarm
    mc_result = pred.get('mc_result', '')
    swarm_direction = 'RIGHT' if 'RIGHT' in mc_result else 'WRONG' if 'WRONG' in mc_result else None
    swarm_agrees = (
        (swarm_direction == 'RIGHT' and opus_vote == 'correct') or
        (swarm_direction == 'WRONG' and opus_vote == 'incorrect')
    )
    
    # Compare with delphi3080
    miro_result = pred.get('miro_result', {})
    miro_verdict = miro_result.get('verdict', '') if isinstance(miro_result, dict) else ''
    
    # Compare with Marty
    marty_verdict = pred.get('marty_verdict')
    marty_agrees = (
        (marty_verdict == 'correct' and opus_vote == 'correct') or
        (marty_verdict == 'wrong' and opus_vote == 'incorrect')
    ) if marty_verdict else None
    
    # Only log if there's a disagreement
    if swarm_direction and not swarm_agrees:
        entry = {
            "claim_id": pred['id'],
            "timestamp": datetime.datetime.now().isoformat(),
            "delphicursor_vote": opus_vote,
            "delphicursor_confidence": verdict.get('confidence'),
            "swarm_said": mc_result,
            "delphi3080_said": miro_verdict or 'unknown',
            "marty_said": marty_verdict,
            "disagreed_with": ["swarm"] + (["marty"] if marty_agrees is False else [])
        }
        with open(DISAGREEMENTS_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')
        log(f"  Logged disagreement: Opus={opus_vote} vs Swarm={swarm_direction}")


def log_failure(pred: dict, error: str, attempts: int):
    """Log permanent failure."""
    entry = {
        "claim_id": pred['id'],
        "timestamp": datetime.datetime.now().isoformat(),
        "error": error,
        "attempts": attempts,
        "claim_excerpt": pred.get('claim', '')[:100]
    }
    with open(FAILURES_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')


def process_claim(pred: dict, ind_data: dict) -> bool:
    """Process a single claim. Returns True on success."""
    claim_id = pred['id']
    log(f"Processing: {claim_id}")
    log(f"  Claim: {pred.get('claim', '')[:80]}...")
    
    # Create isolated workspace
    workspace = WORKSPACE_DIR / claim_id
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    
    # Write fixture
    fixture = build_fixture(pred, ind_data)
    fixture_path = workspace / 'claim_fixture.json'
    fixture_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding='utf-8')
    
    # Try up to MAX_RETRIES times
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        success, verdict, error = run_agent(workspace, claim_id, attempt)
        
        if success:
            # Save verdict to permanent location
            verdict_path = VERDICTS_DIR / f"{claim_id}.json"
            verdict['judged_at'] = datetime.datetime.now().isoformat()
            verdict_path.write_text(json.dumps(verdict, indent=2), encoding='utf-8')
            
            # Log disagreements
            log_disagreement(pred, verdict)
            
            # Update prediction
            with locked_data() as data:
                idx = {p['id']: i for i, p in enumerate(data['predictions'])}
                if claim_id in idx:
                    target = data['predictions'][idx[claim_id]]
                    target['delphicursor_status'] = 'done'
                    target['delphicursor_result'] = {
                        'vote': verdict['vote'],
                        'confidence': verdict['confidence'],
                        'reasoning': verdict.get('reasoning', ''),
                        'sources_checked': verdict.get('sources_checked', []),
                        'dissent_note': verdict.get('dissent_note', ''),
                        'judged_at': verdict['judged_at']
                    }
            
            log(f"  SUCCESS: {verdict['vote']} (confidence {verdict['confidence']})")
            
            # Cleanup workspace
            shutil.rmtree(workspace, ignore_errors=True)
            return True
        
        last_error = error
        log(f"  Attempt {attempt} failed: {error}")
        
        if error == 'timeout':
            # Don't retry timeouts - claim is probably too hard
            break
        
        if attempt < MAX_RETRIES:
            log(f"  Retrying...")
            time.sleep(5)
    
    # Permanent failure
    log(f"  FAILED after {MAX_RETRIES} attempts: {last_error}")
    log_failure(pred, last_error, MAX_RETRIES)
    
    with locked_data() as data:
        idx = {p['id']: i for i, p in enumerate(data['predictions'])}
        if claim_id in idx:
            data['predictions'][idx[claim_id]]['delphicursor_status'] = 'failed_permanent'
    
    # Keep workspace for debugging
    return False


def acquire_lock() -> bool:
    """Try to acquire the global worker lock."""
    if LOCK_FILE.exists():
        try:
            lock_data = json.loads(LOCK_FILE.read_text())
            pid = lock_data.get('pid')
            # Check if process is still alive
            if sys.platform == 'win32':
                r = subprocess.run(['powershell', '-c', f'Get-Process -Id {pid} -ErrorAction SilentlyContinue'],
                                   capture_output=True)
                if r.returncode == 0:
                    log(f"Another worker (pid {pid}) is running. Exiting.")
                    return False
            else:
                try:
                    os.kill(pid, 0)
                    log(f"Another worker (pid {pid}) is running. Exiting.")
                    return False
                except OSError:
                    pass
        except Exception:
            pass
    
    # Write our lock
    LOCK_FILE.write_text(json.dumps({'pid': os.getpid(), 'started': datetime.datetime.now().isoformat()}))
    return True


def release_lock():
    """Release the global worker lock."""
    try:
        LOCK_FILE.unlink()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--once', action='store_true', help='Process one claim and exit')
    args = ap.parse_args()
    
    if not acquire_lock():
        return
    
    log("DelphiCursor worker started")
    
    try:
        while True:
            # Load data and find queued claims
            with open(DATA, encoding='utf-8') as f:
                data = json.load(f)
            
            ind_data = {i['name']: i for i in data.get('individuals', [])}
            
            queue = [p for p in data['predictions'] 
                     if p.get('delphicursor_status') in ('queued', 'urgent')]
            
            # Sort by priority (urgent first, then by queue time)
            queue.sort(key=lambda p: (0 if p.get('delphicursor_status') == 'urgent' else 1,
                                      p.get('delphicursor_queued_at', '9999')))
            
            if queue:
                pred = queue[0]
                log(f"Queue depth: {len(queue)}")
                process_claim(pred, ind_data)
                
                if args.once:
                    break
            else:
                if args.once:
                    log("Queue empty.")
                    break
                time.sleep(60)
                
    except KeyboardInterrupt:
        log("Interrupted.")
    except Exception as e:
        import traceback
        log(f"Worker error: {type(e).__name__}: {e}")
        log(traceback.format_exc()[-800:])
    finally:
        release_lock()
        log("Worker stopped.")


if __name__ == '__main__':
    main()
