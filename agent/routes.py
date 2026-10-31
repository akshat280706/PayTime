# Contract (prefix /api/agent):
#   POST /intake          {text}               -> created debt record
#   POST /start_call      {debt_id}            -> {reply_text}
#   POST /turn            {debt_id, utterance} -> {reply_text, intent, outcome}
#   GET  /next_action/{debt_id}                -> {action, reason}
#   GET  /health                               -> {llm_live, model, last_error}
#
# /intake -> {created, debt?, contact_id, amount, confidence, candidates, debt_id}; created=false (no debt made)
#            when the name is ambiguous or no amount was found (pick from candidates and retry), or when that
#            contact already has an open/promised debt of the same amount (existing=true, debt = that debt).
# /turn   outcome -> {status, stage, next_action_at, promised_date, trigger_verification, needs_merchant}
#            trigger_verification=true means intent was claims_paid: the caller should run verify.
from contextlib import closing

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import conversation, llm, policy
from agent.intake import parse_intake
from agent.state import create_debt
from db import get_db

router = APIRouter(prefix="/api/agent")


class IntakeIn(BaseModel):
    text: str


class CallIn(BaseModel):
    debt_id: int


class TurnIn(BaseModel):
    debt_id: int
    utterance: str = ""


@router.get("/ping")
def ping():
    return {"ok": True}


@router.get("/health")
def health():
    llm.preflight()  # first call makes one tiny live request; later calls are free
    return {"llm_live": not llm.DEGRADED, "model": llm.MODEL, "last_error": llm.LAST_ERROR}


@router.post("/intake")
def intake(body: IntakeIn):
    parsed = parse_intake(body.text)
    if parsed["contact_id"] is None or parsed["amount"] is None:
        return {"created": False, **parsed}
    if parsed["debt_id"]:  # merchant re-asked about a debt that already exists
        with closing(get_db()) as db:
            debt = dict(db.execute("SELECT * FROM debts WHERE id=?", (parsed["debt_id"],)).fetchone())
        return {"created": False, "existing": True, "debt": debt, **parsed}
    return {"created": True, "debt": create_debt(parsed["contact_id"], parsed["amount"]), **parsed}


def _call(fn, *args):
    try:
        return fn(*args)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(409, str(e))


@router.post("/start_call")
def start_call(body: CallIn):
    return {"reply_text": _call(conversation.start_call, body.debt_id)}


@router.post("/turn")
def turn(body: TurnIn):
    return _call(conversation.turn, body.debt_id, body.utterance)


@router.get("/next_action/{debt_id}")
def next_action(debt_id: int):
    with closing(get_db()) as db:
        debt = db.execute("SELECT * FROM debts WHERE id=?", (debt_id,)).fetchone()
    if debt is None:
        raise HTTPException(404, f"debt {debt_id} not found")
    return policy.next_action(debt)
