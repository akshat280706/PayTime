# Contract (prefix /api/voice):
#   POST /stt    multipart audio       -> {text}
#   POST /tts    {text, language}      -> audio/wav bytes
from fastapi import APIRouter

router = APIRouter(prefix="/api/voice")


@router.get("/ping")
def ping():
    return {"ok": True}
