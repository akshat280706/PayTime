from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import numpy as np

from db import get_db
from policy.bandit import LinUCB, features
from policy.simulator import ACTIONS, HORIZON

PARAMS = Path(__file__).parent / "params.npz"
DEFAULT_SPEND = 2600.0  # midpoint of the simulated 200-5000 range: the app has no monthly_spend data
_model = None  # ponytail: loaded once per process, restart the server after retraining


def _load():
    global _model
    if _model is None:
        if not PARAMS.exists():
            raise FileNotFoundError(f"{PARAMS} not found: run `python -m policy.train` from the repo root first")
        _model = LinUCB.load(PARAMS)
    return _model


def learned_next_action(debt_context):
    """debt_context: the 7 fields from policy.simulator.Debtor.context(). -> {action, reason}, greedy."""
    values = _load().values(features({"monthly_spend": DEFAULT_SPEND, **debt_context}))
    best, second = np.argsort(-values)[:2]
    since = debt_context["days_since_last_contact"]
    history = (f"{debt_context['contacts_so_far']} contact(s) so far, last {since} day(s) ago"
               if debt_context["contacts_so_far"] else "no contact yet")
    return {"action": ACTIONS[best],
            "reason": f"Learned policy (trained on simulated debtors): {ACTIONS[best]} has the highest estimated "
                      f"value, Rs {values[best]:.0f} vs {ACTIONS[second]} Rs {values[second]:.0f}. {history}."}


def context_from_debt(debt, now=None):
    """Build the bandit context for a row of the debts table from contact_log and promises."""
    now = now or datetime.now()
    d = dict(debt)
    with closing(get_db()) as db:
        logs = db.execute("SELECT ts, outcome FROM contact_log WHERE debt_id=? AND outcome!='callback_later'"
                          " ORDER BY ts, id", (d["id"],)).fetchall()
        promises = db.execute("SELECT promised_date, kept FROM promises WHERE debt_id=?", (d["id"],)).fetchall()
    last = logs[-1]["outcome"] if logs else None
    if last == "no_answer":
        outcome = "no_answer"
    elif last == "promise_to_pay":
        broken = any(not p["kept"] and p["promised_date"] < now.date().isoformat() for p in promises)
        outcome = "broken" if broken else "promise"
    else:
        outcome = "engaged" if last else "none"
    since = (now - datetime.fromisoformat(logs[-1]["ts"])).days if logs else HORIZON
    return {"days_overdue": max(0, (now.date() - datetime.fromisoformat(d["due_date"]).date()).days),
            "amount": d["amount"], "contacts_so_far": len(logs), "promises_made": len(promises),
            "promises_kept": sum(p["kept"] for p in promises),
            "days_since_last_contact": min(since, HORIZON), "last_outcome": outcome}
