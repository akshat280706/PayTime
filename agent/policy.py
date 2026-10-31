from contextlib import closing
from datetime import datetime, timedelta

from db import get_db

CLOSED = ("settled", "disputed", "opted_out")
TS = "%Y-%m-%dT%H:%M:%S"


def in_calling_hours(dt):
    return 9 <= dt.hour < 19


def clamp_to_calling_hours(dt):
    """Move dt to the next 9am if it falls outside 9am-7pm."""
    if dt.hour < 9:
        return dt.replace(hour=9, minute=0, second=0, microsecond=0)
    if dt.hour >= 19:
        return (dt + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return dt


def next_action(debt, now=None):
    """debt: row/dict with id, status, stage, next_action_at. -> {action, reason}.
    ponytail: fixed rules; keep the signature so a learned policy can replace the body."""
    now = now or datetime.now()
    d = dict(debt)
    wait = lambda reason: {"action": "wait", "reason": reason}
    if d["status"] in CLOSED:
        return wait(f"debt is {d['status']}, no contact allowed")
    if not in_calling_hours(now):
        return wait("outside calling hours (9am-7pm)")
    with closing(get_db()) as db:
        logs = db.execute("SELECT ts, outcome FROM contact_log WHERE debt_id=? ORDER BY ts, id",
                          (d["id"],)).fetchall()
    attempts = [l for l in logs if l["outcome"] != "callback_later"]  # callbacks are not contact attempts
    last = attempts[-1] if attempts else None
    if last and last["outcome"] == "refuse":
        return wait("debtor refused, waiting for merchant")
    nxt = d.get("next_action_at")
    if nxt and datetime.fromisoformat(nxt) > now:
        return wait(f"scheduled for {nxt}")
    if last and now - datetime.fromisoformat(last["ts"]) < timedelta(hours=48):
        return wait("last contact under 48h ago")
    ignored = 0
    for l in reversed(attempts):
        if l["outcome"] != "no_answer":
            break
        ignored += 1
    if ignored >= 2:
        return {"action": "call_firm", "reason": f"{ignored} ignored contacts, firmer tone"}
    if ignored == 1:
        return {"action": "sms", "reason": "1 ignored call, lighter nudge"}
    if d["stage"] >= 1:
        return {"action": "call_firm", "reason": f"stage {d['stage']}"}
    return {"action": "call_gentle", "reason": "stage 0"}


_rule_next_action = next_action


def next_action(debt, now=None):  # noqa: F811
    """The rule above decides whether contact is allowed at all (hours, status, 48h gap). If it allows contact,
    the learned policy picks the action; any failure (e.g. policy/params.npz missing) keeps the rule's answer."""
    result = _rule_next_action(debt, now)
    if result["action"] == "wait":
        return result
    try:
        from policy.infer import context_from_debt, learned_next_action
        return learned_next_action(context_from_debt(debt, now))
    except Exception:
        return result
