# Contract (prefix /api/agent):
#   POST /intake          {text}               -> created debt record
#   POST /start_call      {debt_id}            -> {reply_text}
#   POST /turn            {debt_id, utterance} -> {reply_text, intent, outcome}
#   GET  /next_action/{debt_id}                -> {action, reason}
from fastapi import APIRouter

router = APIRouter(prefix="/api/agent")


@router.get("/ping")
def ping():
    return {"ok": True}
