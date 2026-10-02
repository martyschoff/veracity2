"""Veracity2 daily update pipeline.

Stages:
1. FETCH    — new content since last run (YouTube videos, Substack articles)
2. EXTRACT  — predictions from new content (max 2 per source, no quotes, no past-dated)
3. TEST     — evaluate eligible predictions (fact-checker lookups first for objective,
              LLM assessment for subjective); 2 agreeing votes -> verdict
4. RETIRE   — expire predictions stuck in testing > 12 months
5. PUBLISH  — render + deploy

Run:  python -m src.pipeline
Cron: 8am/8pm Eastern
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "predictions.json"
PROGRESS_FILE = BASE_DIR / "data" / "pipeline_state.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline")

# ---- Configuration ----
LLM_ENDPOINTS = [
    # nimo128 (Ollama qwen3:32b on HermesMac) — preferred workhorse; offload here first
    {"url": "http://100.84.167.88:11434/v1/chat/completions",
     "key": None,
     "model": "qwen3:32b"},
    # local llama-server (Qwen3.8-27B, 64k ctx) — fallback
    {"url": "http://127.0.0.1:18434/v1/chat/completions",
     "key": "OyISwmqwQMak4mEOtO3zajuzSY8clG73",
     "model": "Qwen3.8-27B-UD-Q4_K_M"},
    # upthread64 (Mac Mini Ollama, qwen3-coder MoE) — second fallback
    {"url": "http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions",
     "key": None,
     "model": "qwen3-coder:30b-32k"},
]

TESTING_MONTHS_BEFORE_EXPIRY = 12
VOTES_NEEDED_FOR_VERDICT = 2.0  # sum of agreeing weights needed
AI_KEYWORD_RE = re.compile(r"\b(?:a\.?i\.?|artificial[\s-]+intelligence)\b", re.IGNORECASE)
AI_PANEL_WEIGHT = 0.5
QUANT_PROMPT = (
    "Only include predictions made by the AUTHOR in their own voice. "
    "Never extract predictions from quoted material, blockquotes, tweets, or statements "
    "attributed to other people - even if the author appears to endorse them. "
    "If a claim is inside quotation marks or attributed to someone else, exclude it. "
)


# ---- State helpers ----

def load_data() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_pipeline_state() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_fetch": None, "last_run": None}


def save_pipeline_state(state: dict) -> None:
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---- LLM helper ----

def call_llm(system: str, user: str, max_tokens: int = 2000) -> str | None:
    import httpx
    for ep in LLM_ENDPOINTS:
        headers = {"Content-Type": "application/json"}
        if ep.get("key"):
            headers["Authorization"] = f"Bearer {ep['key']}"
        try:
            resp = httpx.post(
                ep["url"],
                headers=headers,
                json={"model": ep["model"], "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ], "temperature": 0.3, "max_tokens": max(max_tokens, 1500)},
                timeout=120.0,
            )
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = (msg.get("content") or "").strip()
                if not content:
                    # Reasoning models may spend the budget on reasoning_content
                    content = ((msg.get("reasoning_content") or msg.get("reasoning") or "")).strip()
                if content:
                    return content
        except Exception as e:
            logger.debug("LLM endpoint %s failed: %s", ep["url"], e)
            continue
    return None


def strip_quotes(text: str) -> str:
    """Remove quoted material so the LLM never extracts predictions from quotes.

    Removes: markdown blockquotes (> ...), long quoted spans in "..." or curly
    quotes, and text attributed after an em-dash attribution line.
    """
    # Markdown blockquotes
    text = re.sub(r"^>.*$", "", text, flags=re.MULTILINE)
    # Long double-quoted spans (straight and curly) — keep short quotes (<80 chars)
    text = re.sub(r'["\u201c]([^"\u201d]{80,})["\u201d]', ' [quoted material omitted] ', text)
    return text


# ---- Stage 2: Extraction ----

def extract_predictions(text: str, source_url: str, author: str,
                        categories: list[str], source_date: str) -> list[dict]:
    """Extract up to 2 future predictions from stripped source text."""
    if not text or not text.strip():
        return []

    cats_str = ", ".join(categories)
    system = (
        "You are an analyst extracting predictions from content. "
        "Extract specific, testable predictions or forecasts made by the author. "
        f"Classify each prediction into one of these categories: {cats_str}. "
        "If a prediction doesn't fit any category, use 'other'. "
        "Return a JSON array of objects with keys: 'claim', 'category', 'excerpt'. "
        + QUANT_PROMPT +
        "Only include predictions about things that WILL happen in the future. "
        "Exclude statements of fact, past events, and claims referencing years already "
        "passed relative to the source date. "
        "Maximum 2 predictions per source. Prioritize measurable outcomes "
        "(dates, quantities, prices, election results). "
        "If no predictions found, return []."
    )
    raw = call_llm(system, f"Source from {author}, published {source_date}:\n\n{text[:8000]}")
    if not raw:
        return []

    items = []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        fence = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
        if fence:
            try:
                items = json.loads(fence.group(1).strip())
            except json.JSONDecodeError:
                pass
        if not items:
            arr = re.search(r"\[.*\]", raw, re.DOTALL)
            if arr:
                try:
                    items = json.loads(arr.group(0))
                except json.JSONDecodeError:
                    pass
    if not items:
        return []

    # Past-date guard
    upload_year = int(source_date[:4]) if source_date and len(source_date) >= 4 else datetime.now().year
    valid_cats = set(categories)

    preds = []
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    for i, item in enumerate(items[:2]):
        if not isinstance(item, dict):
            continue
        claim = (item.get("claim") or "").strip()
        if not claim:
            continue
        cat = (item.get("category") or "other").lower().strip()
        if cat not in valid_cats:
            cat = "other"
        years = re.findall(r"\b(20\d{2})\b", claim)
        if any(int(y) < upload_year for y in years):
            logger.info("  Skipping past-dated claim: %s", claim[:60])
            continue

        q_patterns = [r"\b\d{4}\b", r"\$", r"\d+%",
                      r"\d+,?\d*\s*(million|billion|thousand)",
                      r"\b(wins?|loses?|elected|enact|sign|ratif)\b",
                      r"\b(by|before|after|until|within)\s+\d"]
        is_quant = any(re.search(p, claim, re.I) for p in q_patterns)

        preds.append({
            "id": f"pred_{ts}_{i:03d}",
            "individual_name": author,
            "date": source_date,
            "category": cat,
            "claim": claim,
            "source_url": source_url,
            "transcript_excerpt": (item.get("excerpt") or "").strip(),
            "verdict": None,
            "created_at": datetime.now().isoformat(),
            "measurement_type": "quantitative" if is_quant else "subjective",
            "test_status": "pending",
            "testing_since": datetime.now().date().isoformat(),
            "judgements": [],
        })
    return preds


# ---- Stage 3: Testing ----

def compute_verdict(pred: dict) -> str | None:
    """Weighted verdict. 2.0 weight of agreeing votes (no opposition) -> verdict;
    both sides present -> disputed."""
    judgements = pred.get("judgements", [])
    if not judgements:
        return None

    correct_weight = sum(j.get("weight", 1.0) for j in judgements if j.get("verdict") == "correct")
    wrong_weight = sum(j.get("weight", 1.0) for j in judgements if j.get("verdict") == "wrong")

    if correct_weight >= VOTES_NEEDED_FOR_VERDICT and wrong_weight == 0:
        return "correct"
    if wrong_weight >= VOTES_NEEDED_FOR_VERDICT and correct_weight == 0:
        return "wrong"
    if correct_weight > 0 and wrong_weight > 0:
        return "disputed"
    return None  # not enough weight yet


def CounterVerdicts(judgements: list) -> dict:
    counts = {"correct": 0, "wrong": 0}
    for j in judgements:
        v = j.get("verdict")
        if v in counts:
            counts[v] += 1
    return counts


def fact_check_lookup(pred: dict) -> dict | None:
    """Look for a real fact-checker ruling on an objective prediction.

    Uses web search against the three fact-checker sources. Returns a judgement
    dict or None if nothing relevant found.
    """
    try:
        from hermes_tools import web_search
        claim = pred.get("claim", "")
        # Trim the claim for the search
        query = f"{claim[:80]} fact check"
        results = web_search(query=query, limit=5)
        for r in results.get("data", {}).get("web", []):
            url = r.get("url", "")
            title = (r.get("title") or "").lower()
            desc = (r.get("description") or "").lower()
            is_fc = any(d in url for d in
                        ["factcheck.org", "apnews.com", "factchecktools.google.com",
                         "politifact.com", "snopes.com", "reuters.com/fact-check"])
            if is_fc:
                # Ask the LLM whether this fact-check resolves the prediction
                system = (
                    "You are assessing whether a fact-check article resolves a prediction. "
                    "Answer with a JSON object: {\"verdict\": \"correct\"|\"wrong\"|\"unclear\", "
                    "\"reasoning\": \"one sentence\"}. The prediction is judged correct if "
                    "events unfolded as predicted, wrong if they did not. Use 'unclear' if "
                    "the fact-check does not address the prediction."
                )
                user = (f"Prediction: {claim}\n"
                        f"Fact-check article: {r.get('title')}\n{r.get('description')}")
                raw = call_llm(system, user, max_tokens=200)
                if raw:
                    try:
                        m = re.search(r"\{.*\}", raw, re.DOTALL)
                        if m:
                            parsed = json.loads(m.group(0))
                            v = parsed.get("verdict")
                            if v in ("correct", "wrong"):
                                return {
                                    "panelist": "Fact-checker lookup",
                                    "source_url": url,
                                    "verdict": v,
                                    "weight": 1.0,
                                    "reasoning": parsed.get("reasoning", ""),
                                    "judged_at": datetime.now().date().isoformat(),
                                }
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        logger.debug("Fact-check lookup failed for %s: %s", pred.get("id"), e)
    return None


def llm_assess(pred: dict) -> dict | None:
    """LLM assessment of a prediction against current evidence."""
    claim = pred.get("claim", "")
    is_quant = pred.get("measurement_type") == "quantitative"
    system = (
        "You are a panelist judging whether a prediction came true. "
        "Based on your knowledge, assess the prediction's outcome. "
        "Answer with JSON: {\"verdict\": \"correct\"|\"wrong\"|\"unclear\", "
        "\"reasoning\": \"one sentence with evidence\"}. "
        + ("For quantitative predictions, check the specific number/date/outcome. "
           if is_quant else
           "For subjective predictions, judge whether the overall direction/event occurred. ")
        + "Use 'unclear' if you genuinely cannot assess it or it hasn't resolved yet."
    )
    raw = call_llm(system, f"Prediction (made {pred.get('date')}): {claim}", max_tokens=200)
    if not raw:
        return None
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
            v = parsed.get("verdict")
            if v in ("correct", "wrong"):
                return {
                    "panelist": "LLM panelist",
                    "verdict": v,
                    "weight": 1.0,
                    "reasoning": parsed.get("reasoning", ""),
                    "judged_at": datetime.now().date().isoformat(),
                }
    except json.JSONDecodeError:
        pass
    return None


MAX_TESTS_PER_RUN = 20  # 2 runs/day = 40/day; clears the 227 backlog in ~6 days


def volume_liberal(pred: dict, data: dict) -> bool:
    """Excess rule (user directive): QA may toss liberally when a person has an
    abundance of predictions — total > 100, or > 10 in the same month."""
    person = pred.get("individual_name", "")
    total = sum(1 for p in data["predictions"] if p.get("individual_name") == person)
    if total > 100:
        return True
    month = (pred.get("date") or "")[:7]
    per_month = sum(1 for p in data["predictions"]
                    if p.get("individual_name") == person
                    and (p.get("date") or "")[:7] == month)
    return per_month > 10


def qa_approve(pred: dict, verdict: str) -> bool:
    """QA judge: a separate local-model pass reviews the judgement bundle.

    Standing process rule: one model judges another model's output. The judge
    uses a fresh persona, reviews claim + verdicts + reasonings, and returns
    True only if it endorses the verdict. Any failure of the QA call itself
    approves by default (QA must not hard-block the pipeline).
    """
    bundle = "\n".join(
        f"- [{j.get('panelist','?')}] {j.get('verdict')}: {j.get('reasoning','')[:200]}"
        for j in pred.get("judgements", [])
    )
    system = (
        "You are a QA judge reviewing another model's fact-check verdict. "
        "Review the prediction, the verdict, and each panelist's reasoning. "
        "Approve only if the verdict is supported by the reasoning and the "
        "reasoning is factually plausible and on-topic. "
        "Answer with JSON: {\"approve\": true|false, \"reason\": \"one sentence\"}."
    )
    user = (f"Prediction (made {pred.get('date')}): {pred.get('claim')}\n"
            f"Computed verdict: {verdict}\n\nJudgements:\n{bundle}")
    try:
        if volume_liberal(pred, load_data()):
            system += (" EXCESS MODE: this person has an abundance of predictions, "
                       "so be strict — reject verdicts with weak, vague, or thin "
                       "reasoning rather than approving borderline cases.")
        raw = call_llm(system, user, max_tokens=400)
        if not raw:
            return True  # QA unavailable -> do not block
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return bool(json.loads(m.group(0)).get("approve", True))
    except Exception as e:
        logger.debug("QA pass failed for %s: %s", pred.get("id"), e)
    return True


def run_test_stage(data: dict) -> dict:
    """Test eligible predictions (up to MAX_TESTS_PER_RUN per run)."""
    stats = {"tested": 0, "judged": 0, "disputed": 0, "errors": 0}
    today = datetime.now().date()
    tested_this_run = 0

    for pred in data["predictions"]:
        status = pred.get("test_status", "pending")
        if status not in ("pending", "eligible"):
            continue

        # Transition pending -> eligible: every un-judged prediction is testable
        # daily per the agreed lifecycle; expiry is handled by the retire stage.
        if status == "pending":
            pred["test_status"] = "eligible"
            if not pred.get("testing_since"):
                pred["testing_since"] = today.isoformat()
            status = "eligible"

        # Skip if already has a computed verdict
        if pred.get("verdict") in ("correct", "wrong"):
            pred["test_status"] = "judged"
            continue
        if pred.get("verdict") == "disputed":
            pred["test_status"] = "disputed"
            continue

        # Don't re-test more than once per day
        judgements = pred.get("judgements", [])
        if judgements and isinstance(judgements[-1], dict) and judgements[-1].get("judged_at") == today.isoformat():
            continue

        stats["tested"] += 1
        tested_this_run += 1

        author = pred.get("individual_name", "")

        # Objective: fact-checker lookup first
        if pred.get("measurement_type") == "quantitative":
            j = fact_check_lookup(pred)
            if j:
                judgements.append(j)
                pred["judgements"] = judgements

        # LLM assessment (fills gaps for both types; second vote)
        # RULE: a predictor cannot panel-vote on their own predictions —
        # skip LLM votes for LLM panelists? No: LLM panelist is not the author.
        # Exclusion applies to human panelists via set_marty_verdict and future
        # panel-vote ingestion: filter judgements where panelist == author.
        if len(judgements) < VOTES_NEEDED_FOR_VERDICT:
            j = llm_assess(pred)
            if j:
                judgements.append(j)
                pred["judgements"] = judgements

        # AI cross-panel: non-ai predictions mentioning AI get an AI-panel vote
        # at half weight (votes consolidate across panels).
        is_ai_cat = pred.get("category") == "ai"
        mentions_ai = bool(AI_KEYWORD_RE.search(pred.get("claim", "")))
        if mentions_ai and not is_ai_cat:
            has_ai_vote = any("AI panel" in j.get("panelist", "") for j in judgements)
            if not has_ai_vote:
                aj = llm_assess(pred)
                if aj:
                    aj["panelist"] = "LLM panelist (AI panel)"
                    aj["weight"] = AI_PANEL_WEIGHT
                    judgements.append(aj)
                    pred["judgements"] = judgements

        # Enforce no-self-voting: drop judgements attributed to the author
        judgements = [j for j in judgements
                      if j.get("panelist", "") != author]
        pred["judgements"] = judgements

        # Compute verdict
        verdict = compute_verdict(pred)
        if verdict in ("correct", "wrong"):
            # QA pass: a local-model judge reviews the judgement bundle before
            # it is finalized. Standing process rule (user directive): one model
            # judges another model's results.
            if not qa_approve(pred, verdict):
                pred["verdict"] = None
                pred["test_status"] = "eligible"  # back to queue for re-test
                stats["errors"] += 1
                logger.info("  QA REJECTED verdict for %s — sent back for re-test", pred["id"])
                continue
            pred["verdict"] = verdict
            pred["test_status"] = "judged"
            stats["judged"] += 1
            logger.info("  JUDGED %s: %s — %s", verdict.upper(), pred["id"], pred["claim"][:60])
        elif verdict == "disputed":
            pred["verdict"] = "disputed"
            pred["test_status"] = "disputed"
            stats["disputed"] += 1
            logger.info("  DISPUTED: %s — %s", pred["id"], pred["claim"][:60])

        # Batch limit: save remaining predictions for the next run
        if tested_this_run >= MAX_TESTS_PER_RUN:
            logger.info("  Batch limit reached (%d tested this run)", tested_this_run)
            break

    return stats


# ---- Stage 4: Retirement ----

def run_retire_stage(data: dict) -> int:
    """Expire predictions testing > 12 months without a verdict."""
    today = datetime.now().date()
    cutoff = today - timedelta(days=TESTING_MONTHS_BEFORE_EXPIRY * 30)
    retired = 0

    for pred in data["predictions"]:
        if pred.get("verdict") in ("correct", "wrong", "disputed"):
            continue
        since = pred.get("testing_since")
        if not since:
            continue
        try:
            if date.fromisoformat(since) < cutoff:
                pred["test_status"] = "expired"
                pred["verdict"] = "expired"
                retired += 1
                logger.info("  RETIRED (12mo no verdict): %s — %s", pred["id"], pred["claim"][:60])
        except ValueError:
            pass
    return retired


# ---- Marty notation ----

def set_marty_verdict(data: dict, pred_id: str, agrees: bool, note: str = "") -> bool:
    """Set Marty's advisory agreement flag on a prediction. Does not force verdict."""
    for pred in data["predictions"]:
        if pred.get("id") == pred_id:
            pred["marty_agrees"] = agrees
            pred["marty_note"] = note
            pred["marty_at"] = datetime.now().date().isoformat()
            return True
    return False


# ---- Main ----

def run(render_and_deploy: bool = True) -> dict:
    logger.info("=== Veracity2 pipeline run started ===")
    state = load_pipeline_state()
    data = load_data()

    # Stage 3: Test eligible predictions (runs every time)
    logger.info("--- Stage 3: Testing ---")
    test_stats = run_test_stage(data)

    # Stage 4: Retire stale predictions
    logger.info("--- Stage 4: Retirement ---")
    retired = run_retire_stage(data)

    # Save
    save_data(data)
    state["last_run"] = datetime.now().isoformat()
    save_pipeline_state(state)

    summary = {
        "tested": test_stats["tested"],
        "judged": test_stats["judged"],
        "disputed": test_stats["disputed"],
        "retired": retired,
    }
    logger.info("Pipeline run complete: %s", summary)

    # Stage 5: Publish
    if render_and_deploy:
        import subprocess
        py = r"C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/python.exe"
        subprocess.run([py, str(BASE_DIR / "render.py")], cwd=BASE_DIR, check=True)
        env = {"SURGE_TOKEN": "ea807c6f912951573c26c7fed2788f3f"}
        subprocess.run(["surge", str(BASE_DIR / "surge_dist"), "veracity2.surge.sh"],
                       cwd=BASE_DIR, check=True,
                       env={**__import__("os").environ, **env})
        logger.info("Deployed to veracity2.surge.sh")

    return summary


if __name__ == "__main__":
    run()
