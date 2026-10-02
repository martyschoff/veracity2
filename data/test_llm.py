import httpx
import json

# Test local LLM
try:
    resp = httpx.post(
        "http://127.0.0.1:18434/v1/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": "Bearer OyISwmqwQMak4mEOtO3zajuzSY8clG73"},
        json={
            "model": "Qwen3.8-27B-UD-Q4_K_M",
            "messages": [{"role": "user", "content": "Say hello in 5 words."}],
            "max_tokens": 20
        },
        timeout=30
    )
    resp.raise_for_status()
    result = resp.json()
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"Local LLM OK: {content}")
except Exception as e:
    print(f"Local LLM FAILED: {e}")

# Test remote LLM
try:
    resp = httpx.post(
        "http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions",
        headers={"Content-Type": "application/json"},
        json={
            "model": "qwen3-coder:30b-32k",
            "messages": [{"role": "user", "content": "Say hello in 5 words."}],
            "max_tokens": 20
        },
        timeout=30
    )
    resp.raise_for_status()
    result = resp.json()
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(f"Remote LLM OK: {content}")
except Exception as e:
    print(f"Remote LLM FAILED: {e}")
