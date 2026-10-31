import random
from contextlib import closing
from datetime import datetime, timedelta

from db import get_db
from agent.policy import TS, clamp_to_calling_hours


def add_payment(db, debt_id):
    """Stands in for Paytm's payment webhook: a successful transaction for this debt's amount, timestamped now.
    Payer handle = the contact's, else ramesh@paytm for debt 1, else <first name>@paytm."""
    row = db.execute("SELECT d.amount, c.name, c.payer_handle FROM debts d JOIN contacts c ON c.id=d.contact_id "
                     "WHERE d.id=?", (debt_id,)).fetchone()
    if not row:
        raise LookupError("Debt not found")
    handle = row["payer_handle"] or ("ramesh@paytm" if debt_id == 1 else row["name"].split()[0].lower() + "@paytm")
    ref = "".join(random.choices("0123456789", k=12))
    db.execute("INSERT INTO transactions (amount, ts, ref, payer_handle, status) VALUES (?,?,?,?,'SUCCESS')",
               (row["amount"], datetime.now().isoformat(timespec="seconds"), ref, handle))
    db.commit()
    return {"transaction_ref": ref, "amount": row["amount"], "payer_handle": handle}


def create_contact(name, language="hi"):
    with closing(get_db()) as db:
        cur = db.execute("INSERT INTO contacts (name, phone, language, payer_handle) VALUES (?, NULL, ?, NULL)",
                         (name, language))
        db.commit()
        return cur.lastrowid


def create_debt(contact_id, amount):
    now = datetime.now()
    with closing(get_db()) as db:
        cur = db.execute(
            "INSERT INTO debts (contact_id, amount, created_at, due_date, stage, status, next_action_at)"
            " VALUES (?,?,?,?,0,'open',?)",
            (contact_id, amount, now.strftime(TS), now.strftime(TS), now.strftime(TS)))
        db.commit()
        return dict(db.execute("SELECT * FROM debts WHERE id=?", (cur.lastrowid,)).fetchone())


def apply_outcome(debt_id, intent, extracted):
    """extracted: {promised_date?, transcript?}. Stage 1->2 is NOT done here, only approve_escalation does it."""
    now = datetime.now()
    extracted = extracted or {}
    with closing(get_db()) as db:
        debt = db.execute("SELECT * FROM debts WHERE id=?", (debt_id,)).fetchone()
        status, stage, nxt = debt["status"], debt["stage"], debt["next_action_at"]
        out = {"trigger_verification": False, "needs_merchant": False, "promised_date": None}

        db.execute("INSERT INTO contact_log (debt_id, ts, channel, stage, transcript, outcome) VALUES (?,?,?,?,?,?)",
                   (debt_id, now.strftime(TS), "call", stage, extracted.get("transcript", ""), intent))

        if status != "settled":  # a settled debt only gets logged
            if intent == "promise_to_pay":
                pd = extracted.get("promised_date") or (now + timedelta(days=3)).strftime("%Y-%m-%d")
                status, nxt, out["promised_date"] = "promised", f"{pd}T10:00:00", pd
                db.execute("INSERT INTO promises (debt_id, promised_date, made_at) VALUES (?,?,?)",
                           (debt_id, pd, now.strftime(TS)))
            elif intent == "claims_paid":
                out["trigger_verification"] = True
            elif intent == "dispute_amount":
                status, nxt = "disputed", None
            elif intent == "refuse":
                nxt, out["needs_merchant"] = None, True  # flagged via the 'refuse' log row, stage untouched
            elif intent == "wrong_number":
                status, nxt = "opted_out", None
            elif intent == "callback_later":
                nxt = clamp_to_calling_hours(now + timedelta(hours=2)).strftime(TS)
            elif intent == "no_answer":
                nxt = clamp_to_calling_hours(now + timedelta(hours=48)).strftime(TS)
                misses = db.execute("SELECT COUNT(*) FROM contact_log WHERE debt_id=? AND outcome='no_answer'",
                                    (debt_id,)).fetchone()[0]
                if stage == 0 and misses >= 2:
                    stage = 1  # the only automatic advance

        db.execute("UPDATE debts SET status=?, stage=?, next_action_at=? WHERE id=?", (status, stage, nxt, debt_id))
        db.commit()
    return {**out, "status": status, "stage": stage, "next_action_at": nxt}
