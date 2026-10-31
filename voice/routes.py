"""Browser-facing Sarvam voice endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from voice.sarvam import synthesize, transcribe

router = APIRouter(prefix="/api/voice")
MAX_AUDIO_BYTES = 10 * 1024 * 1024


class TTSIn(BaseModel):
    text: str = Field(min_length=1, max_length=2_500)
    language: str = "hi"  # PayTime contact code: hi or en (not Sarvam's BCP-47 format).


@router.get("/ping")
def ping():
    return {"ok": True}


@router.get("/test")
def voice_test_page():
    """Serve the isolated browser microphone/speaker check."""
    return FileResponse(Path(__file__).with_name("test.html"))


@router.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """Transcribe a short browser recording without retaining it on disk."""
    suffix = Path(audio.filename or "recording.webm").suffix or ".webm"
    if suffix.lower() not in {".wav", ".webm", ".mp3", ".m4a", ".mp4", ".ogg"}:
        raise HTTPException(415, "Upload WAV, WebM, MP3, M4A, MP4, or OGG audio.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
        temp_path = Path(temporary_file.name)
        try:
            remaining = MAX_AUDIO_BYTES + 1
            while chunk := await audio.read(min(1024 * 1024, remaining)):
                temporary_file.write(chunk)
                remaining -= len(chunk)
                if remaining == 0:
                    raise HTTPException(413, "Audio must be smaller than 10 MB.")
        finally:
            await audio.close()

    try:
        return {"text": transcribe(temp_path)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Speech transcription failed: {exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)


@router.post("/tts")
def text_to_speech(body: TTSIn):
    """Generate a WAV response suitable for immediate browser playback."""
    try:
        wav_audio = synthesize(body.text.strip(), body.language)
    except Exception as exc:
        raise HTTPException(502, f"Speech synthesis failed: {exc}") from exc
    return Response(content=wav_audio, media_type="audio/wav")
