# Run from repo root: python -m agent.test_agent   (uses a throwaway copy of state.db)
import os, shutil, tempfile
from datetime import date

shutil.copy("state.db", tmp := tempfile.mkdtemp())
os.chdir(tmp)

from agent.intake import parse_amount, parse_intake
from agent.intents import classify, resolve_date
from agent import conversation, policy, routes

for text, amt in [("Sharma ji ko 400 ka reminder bhejo", 400), ("remind Patel 1200", 1200),
                  ("Patel ko paanch sau", 500), ("Patel ko 2 hazaar", 2000), ("शर्मा को ४०० का", 400),
                  ("Patel ko ढाई सौ", 250), ("Patel Rs.1,200", 1200), ("Patel ko bhej do", None)]:
    assert parse_amount(text) == amt, (text, parse_amount(text))
r = parse_intake("Sharma ji ko 400 ka reminder bhejo")
assert r["contact_id"] == 3 and r["amount"] == 400, r          # Amit Sharma
hi, en = parse_intake("रमेश को ८५० का रिमाइंडर भेजो"), parse_intake("Ramesh ko 850 ka reminder bhejo")
assert hi["contact_id"] == en["contact_id"] == 1 and hi["amount"] == en["amount"] == 850, (hi, en)
assert parse_intake("शर्मा जी को 400")["contact_id"] == 3
assert hi["debt_id"] == en["debt_id"] == 1                      # debt 1 is already open at 850: no duplicate
assert parse_intake("Ramesh ko 400")["debt_id"] is None
assert routes.intake(routes.IntakeIn(text="Ramesh ko 850"))["existing"] is True
assert routes.intake(routes.IntakeIn(text="Ramesh ko 400"))["created"] is True
assert parse_intake("Kumar ko 100")["contact_id"] is None      # Ramesh/Senthil Kumar: candidates, no guess
assert parse_intake("Zzqx ko 100")["candidates"] == []

mon = date(2026, 11, 2)  # a Monday
assert resolve_date("kal de dunga", mon) == "2026-11-03"
assert resolve_date("Tuesday ko", mon) == "2026-11-03"
assert resolve_date("agle hafte", mon) == "2026-11-09"
assert resolve_date("Monday", mon) == "2026-11-09"
assert classify("")["intent"] == "no_answer"
assert classify("galat number hai")["intent"] == "wrong_number"
assert classify("nahi dunga")["intent"] == "refuse"
assert classify("kal call karna")["intent"] == "callback_later"

conversation.start_call(1)
t = conversation.turn(1, "ye galat number hai")
assert t["outcome"]["status"] == "opted_out" and "850" not in t["reply_text"]
try:
    conversation.start_call(1)
    raise SystemExit("opted-out debt must not be contactable")
except PermissionError:
    pass
assert policy.next_action({"id": 1, "status": "opted_out", "stage": 0, "next_action_at": None})["action"] == "wait"
# "I paid": the ledger decides. certain/high settles, ambiguous goes to the merchant, no match asks for a screenshot
import sqlite3
from datetime import datetime
db = sqlite3.connect("state.db")
now = datetime.now().isoformat(timespec="seconds")
db.execute("INSERT INTO transactions VALUES (101,1200,?,'REFCERTAIN001','priya@paytm','SUCCESS')", (now,))      # debt 2, handle known
db.executemany("INSERT INTO transactions VALUES (?,300,?,?,NULL,'SUCCESS')",                                      # debt 3, two unknown payers
               [(102, now, "REFAMBIG0001"), (103, now, "REFAMBIG0002")])
db.commit()
for debt in (2, 3, 5):
    conversation.start_call(debt)
t = conversation.turn(2, "paisa bhej diya hai")
assert t["outcome"]["status"] == "settled" and t["outcome"]["verification"]["confidence"] == "certain", t
assert t["outcome"]["next_action_at"] is None and "1200" in t["reply_text"] and t["language"] == "mr"
again = conversation.turn(2, "paisa bhej diya hai")                       # a repeat claim on a settled debt
assert again["reply_text"] == t["reply_text"] and "verification" not in again["outcome"], again
t = conversation.turn(3, "paisa bhej diya hai")
assert t["outcome"]["status"] != "settled" and t["outcome"]["needs_merchant"] is True, t
assert t["outcome"]["verification"] == {"verified": False, "confidence": "ambiguous", "candidate_ref": "REFAMBIG0001"}
t = conversation.turn(5, "paisa bhej diya hai")
assert t["outcome"]["status"] == "open" and t["outcome"]["verification"]["verified"] is False, t
assert t["outcome"]["trigger_verification"] is True                        # screenshot path still open
assert routes.start_call(routes.CallIn(debt_id=1 + 3))["language"] in ("hi", "mr", "ta")

# a reply cut off by max_tokens is trimmed to its last full sentence, or rejected if it has none
import requests
from agent import llm
class FakeResp:
    ok, status_code = True, 200
    def __init__(self, text): self.text = text
    def json(self): return {"choices": [{"message": {"content": self.text}, "finish_reason": "length"}], "usage": {}}
real_post = requests.post
os.environ.setdefault("SARVAM_API_KEY", "x")
requests.post = lambda *a, **k: FakeResp("ठीक है, समझ गई। मैं इसे नोट कर लूँगी, कृपया ")
assert llm._call("s", []) == "ठीक है, समझ गई।"
requests.post = lambda *a, **k: FakeResp("कृपया ")
try:
    llm._call("s", [])
    raise SystemExit("expected ValueError")
except ValueError:
    pass
requests.post = real_post

# preflight: a failing model flips DEGRADED and /health, a later good call clears it
from agent import llm, routes
llm.FALLBACK, llm._checked = False, False
def boom(*a, **k): raise RuntimeError("404 model gone")
llm._call = boom
h = routes.health()
assert llm.DEGRADED and h == {"llm_live": False, "model": llm.MODEL, "last_error": "RuntimeError: 404 model gone"}, h
llm._call = lambda *a, **k: "ok"
assert llm.complete("s", [{"role": "user", "content": "x"}]) == "ok" and routes.health()["llm_live"] is True
print("ok")
