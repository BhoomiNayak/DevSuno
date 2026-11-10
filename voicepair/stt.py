"""Prisma v3.0 speech-to-text wrapper.

API base: https://api.vachana.ai
Auth:     X-API-Key-ID header (handled by gnani-vachana SDK)
Docs:     https://docs.gnani.ai/api/STT/models/prisma-v3

Key facts from the real docs
-----------------------------
- language_code=indic-auto  lets the model detect from 10 Indian + English
- format=codemix            English words stay in Latin; numbers as words —
                            exactly what Hinglish developer speech needs
- keyterms                  up to 200 words/phrases; boosts recognition of
                            names, brands, tech jargon
- topic                     up to 1,600 chars; contextual sentence about the
                            recording — improves accuracy on uncommon words
- language_candidates       does NOT exist in the real API; language_code
                            accepts indic-auto or up to 4 comma-separated
                            codes (e.g. "hi-IN,en-IN,kn-IN")
- Prisma v3.0 covers: hi-IN, en-IN, kn-IN, ta-IN, te-IN, ml-IN, mr-IN,
                      pa-IN, bn-IN, gu-IN  (no as-IN / Urdu)
"""

from __future__ import annotations

import os
from pathlib import Path

from gnani.stt import GnaniSTTClient
from gnani.stt.exceptions import GnaniSTTError

from .context import BASE_KEYTERMS

MODEL = "prisma-v3.0"
# Comma-separated string accepted by the real API for multi-language hints.
# Covers Hindi/Hinglish, Indian English, and Kannada (brief requirement).
LANGUAGE_CODE = "indic-auto"
LANGUAGE_HINTS = "hi-IN,en-IN,kn-IN"   # passed as language_code when not using auto


class MissingApiKeyError(RuntimeError):
    """Raised when GNANI_API_KEY is not set."""


def require_api_key() -> str:
    key = os.getenv("GNANI_API_KEY", "").strip()
    if not key:
        raise MissingApiKeyError(
            "GNANI_API_KEY is not set. Create an API key at app.gnani.ai, "
            "then run: export GNANI_API_KEY=<your key>"
        )
    return key


def transcribe(audio_path: str | Path,
               keyterms: list[str] | None = None) -> dict:
    """Transcribe an audio file with Prisma v3.0.

    Parameters
    ----------
    audio_path:
        WAV/MP3/FLAC/OGG/M4A/AAC file, max 30 seconds.
    keyterms:
        Up to 200 words/phrases for recognition boosting.
        Build with ``voicepair.context.build_keyterms()``.
        Falls back to ``BASE_KEYTERMS`` when None.

    Returns
    -------
    dict
        ``{"transcript": "...", "detected_language_code": "hi-IN", ...}``
    """
    require_api_key()
    effective_keyterms = keyterms if keyterms is not None else BASE_KEYTERMS

    # Prisma v3.0 caps keyterms at 200; trim silently rather than 400-ing.
    effective_keyterms = effective_keyterms[:200]

    client = GnaniSTTClient()
    try:
        return client.transcribe(
            str(audio_path),
            language_code=LANGUAGE_CODE,          # indic-auto
            model=MODEL,
            format="codemix",                     # English words stay Latin
            keywords=effective_keyterms,
            topic=(
                "A developer is describing a software bug in Hinglish "
                "(Hindi-English code-mixed speech). The question involves "
                "code, variable names, and debugging terminology."
            ),
        )
    except GnaniSTTError as exc:
        raise RuntimeError(f"Prisma STT failed: {exc}") from exc
