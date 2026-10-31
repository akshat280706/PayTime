# Contract (prefix /api):
#   GET  /debts                        -> list with contact name + status
#   GET  /debts/{id}                   -> detail incl. contact_log
#   POST /debts/{id}/approve_escalation
#   POST /verify/screenshot  multipart image + debt_id
#                                      -> {matched, confidence, transaction}
#   POST /verify/check/{debt_id}       -> same shape, feed-only match
from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/ping")
def ping():
    return {"ok": True}
