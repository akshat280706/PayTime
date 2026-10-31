import os
import time

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is in requirements.txt; env vars still work without it
    pass

FALLBACK = not os.getenv("SARVAM_API_KEY")
if FALLBACK:
    print("\n" + "!" * 70
          + "\n!! SARVAM_API_KEY not set: agent is running on CANNED RESPONSES, NOT the LLM"
          + "\n" + "!" * 70 + "\n")


URL = "https://api.sarvam.ai/v1/chat/completions"
MODEL = os.getenv("SARVAM_MODEL") or "sarvam-105b-conversations"  # NOT sarvam-105b: 200 with empty content at our token cap
DEGRADED = FALLBACK  # True whenever replies are NOT coming from the LLM (no key, or the model is failing)
LAST_ERROR = "SARVAM_API_KEY not set" if FALLBACK else None
_checked = False
_calls = 0  # credits are shared with TTS/STT, so every HTTP request is counted and logged


def _banner(error):
    bar = "#" * 78
    print(f"\n{bar}\n{bar}\n##  LLM IS DOWN: THE AGENT IS ANSWERING WITH CANNED REPLIES, NOT SARVAM\n"
          f"##  model: {MODEL}\n##  error: {error}\n{bar}\n{bar}\n")


def _fail(e):
    global DEGRADED, LAST_ERROR
    err = f"{type(e).__name__}: {e}"
    if not DEGRADED or err != LAST_ERROR:  # shout on the live -> down transition, not on every retry
        _banner(err)
    DEGRADED, LAST_ERROR = True, err


def _call(system_prompt, messages, max_tokens=200):
    """One HTTP request, logged. Raises on any failure, including a 200 with empty content."""
    global _calls
    _calls += 1
    n, start, status, tokens = _calls, time.perf_counter(), "-", "-"
    try:
        r = requests.post(URL, headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]}, timeout=10, json={
            "model": MODEL, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system_prompt}, *messages]})
        status = r.status_code
        if not r.ok:
            raise requests.HTTPError(f"{r.status_code} {r.text[:300]}", response=r)
        data = r.json()
        tokens = (data.get("usage") or {}).get("total_tokens", "?")
        choice = data["choices"][0]
        text = choice["message"]["content"]
        if not text or not text.strip():
            raise ValueError("200 but empty content")
        text = text.strip()
        if choice.get("finish_reason") == "length":  # hit max_tokens: never speak a half sentence
            end = max(text.rfind(c) for c in "।.?!")
            if end <= 0:
                raise ValueError("reply truncated by max_tokens with no full sentence")
            print(f"[llm] call #{n} truncated by max_tokens, trimmed to the last full sentence")
            text = text[:end + 1]
        return text
    finally:
        print(f"[llm] call #{n} {MODEL} status={status} {time.perf_counter() - start:.2f}s tokens={tokens}")


def _call_retry(*args, **kwargs):
    """At most one retry, and not for a 4xx (other than 429): repeating a bad request only burns credits."""
    try:
        return _call(*args, **kwargs)
    except Exception as e:
        resp = getattr(e, "response", None)
        if resp is not None and 400 <= resp.status_code < 500 and resp.status_code != 429:
            raise
        print(f"[llm] retrying once after: {type(e).__name__}: {str(e)[:120]}")
        return _call(*args, **kwargs)


def preflight():
    """One tiny live call, once per process. Sets DEGRADED / LAST_ERROR; never raises."""
    global _checked, DEGRADED, LAST_ERROR
    if _checked or FALLBACK:
        return
    _checked = True
    try:
        _call_retry("Reply with the single word OK.", [{"role": "user", "content": "ping"}], max_tokens=16)
        DEGRADED, LAST_ERROR = False, None
    except Exception as e:
        _fail(e)


def complete(system_prompt, messages):
    """The only provider call. messages: [{"role": "user"|"assistant", "content": str}], first is user."""
    preflight()
    try:
        text = _call_retry(system_prompt, messages)
    except Exception as e:
        _fail(e)
        raise
    global DEGRADED, LAST_ERROR
    DEGRADED, LAST_ERROR = False, None  # a good call clears a past failure
    return text
