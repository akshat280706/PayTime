"""Small, reusable Sarvam STT/TTS wrapper plus a safe connection smoke test."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from sarvamai import SarvamAI


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TTS_TEXT = "Namaste. This is an automated reminder from PayTime."
LANGUAGE_CODES = {
    "en": "en-IN",
    "hi": "hi-IN",
}
DEFAULT_SPEAKER = "simran"  # Female Bulbul v3 voice; works across supported languages.
CACHE_DIR = ROOT / "voice" / "cache"


def sarvam_language_code(language: str) -> str:
    """Convert PayTime's compact contact language code to Sarvam's BCP-47 code."""
    normalized = language.strip().lower()
    return LANGUAGE_CODES.get(normalized, language)


def get_client() -> SarvamAI:
    """Return an authenticated client without ever printing the API key."""
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "SARVAM_API_KEY is missing. Copy .env.example to .env and add your key."
        )
    return SarvamAI(api_subscription_key=api_key)


def synthesize(text: str, language: str = "hi") -> bytes:
    """Turn text into WAV audio bytes, reusing cached audio to conserve credits."""
    language_code = sarvam_language_code(language)
    cache_key = hashlib.sha256(
        f"bulbul:v3\0{DEFAULT_SPEAKER}\0{language_code}\0{text}".encode("utf-8")
    ).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.wav"
    if cache_path.exists():
        return cache_path.read_bytes()

    response = get_client().text_to_speech.convert(
        text=text,
        language_code=language_code,
        model="bulbul:v3",
        speaker=DEFAULT_SPEAKER,
        output_audio_codec="wav",
    )
    audio = base64.b64decode(response.audios[0])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(audio)
    return audio


def transcribe(audio_path: Path) -> str:
    """Transcribe a short recording using Sarvam Saaras."""
    with audio_path.open("rb") as audio_file:
        response = get_client().speech_to_text.transcribe(
            file=audio_file,
            model="saaras:v4",
            mode="transcribe",
        )
    return response.transcript


def run_smoke_test(audio_path: Path | None, output_path: Path) -> None:
    """Make one TTS request and, when supplied, one STT request."""
    audio = synthesize(DEFAULT_TTS_TEXT)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)
    print(f"TTS OK: wrote {output_path}")

    if audio_path is None:
        print("STT pending: record a short WAV/WebM file and pass --audio PATH.")
        return
    print(f"STT OK: {transcribe(audio_path)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify PayTime's Sarvam voice setup.")
    parser.add_argument("--audio", type=Path, help="Short recording to transcribe (WAV or WebM).")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "voice" / "cache" / "smoke-test.wav",
        help="Where to save the generated TTS WAV.",
    )
    args = parser.parse_args()
    run_smoke_test(args.audio, args.output)
