# Voice setup

1. Copy `.env.example` to `.env` and set `SARVAM_API_KEY`.
2. Install dependencies: `python -m pip install -r requirements.txt`.
3. Run the TTS check: `python voice/sarvam.py`.
4. Record a short WAV or WebM clip, then run both checks:
   `python voice/sarvam.py --audio path/to/recording.webm`.

The script saves generated audio under `voice/cache/`, which is intentionally ignored by Git.

`synthesize()` accepts PayTime contact language codes (`hi`, `mr`, `ta`, or `en`).
It converts them to Sarvam's BCP-47 codes internally and uses the female `simran`
Bulbul v3 voice by default.
