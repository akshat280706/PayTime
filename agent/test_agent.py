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
print("ok")
