# Run from repo root: python -m verify.test_matcher
import sqlite3
from datetime import datetime, timedelta

from verify.matcher import match_feed_transaction, settle_debt

now = datetime.now()
iso = lambda d: d.isoformat(timespec="seconds")


def world(handle, txns, created_days_ago=10):
    db = sqlite3.connect(":memory:")
    db.executescript(open("schema.sql").read())
    db.execute("INSERT INTO contacts VALUES (1,'Ramesh','+91','hi',?)", (handle,))
    db.execute("INSERT INTO debts (id,contact_id,amount,created_at,due_date) VALUES (1,1,850,?,?)",
               (iso(now - timedelta(days=created_days_ago)),) * 2)
    for i, (amt, days_ago, payer) in enumerate(txns, 1):
        db.execute("INSERT INTO transactions VALUES (?,?,?,?,?,'SUCCESS')",
                   (i, amt, iso(now - timedelta(days=days_ago)), f"REF{i:09d}", payer))
    return db


def level(db):
    m = match_feed_transaction(db, debt_id=1)
    return m and m["confidence"]


assert level(world("ramesh@paytm", [(850, 0, "ramesh@paytm")])) == "certain"     # known handle matches
assert level(world(None, [(850, 0, "ramesh@paytm")])) == "high"                  # handle unknown, in window
assert level(world(None, [(850, 40, "x@paytm")])) == "ambiguous"                 # before the debt existed
assert level(world("ramesh@paytm", [(850, 0, "stranger@paytm")])) is None        # known payer differs: skipped
assert level(world(None, [(851, 0, "ramesh@paytm")])) is None                    # amount must be exact
assert level(world(None, [(850, 0, "a@paytm"), (850, 1, "b@paytm")])) == "ambiguous"  # two possible payers

db = world(None, [(850, 0, "ramesh@paytm")])
m = match_feed_transaction(db, debt_id=1)
assert settle_debt(db, 1, m["transaction"]) == "ramesh@paytm"                    # first payment teaches the handle
assert db.execute("SELECT payer_handle FROM contacts").fetchone()[0] == "ramesh@paytm"
assert db.execute("SELECT status FROM debts").fetchone()[0] == "settled"
print("ok")
