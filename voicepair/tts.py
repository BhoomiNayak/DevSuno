"""Timbre v3.0 text-to-speech wrapper.

API base: https://api.vachana.ai
Auth:     X-API-Key-ID header (handled by gnani-vachana SDK)
Docs:     https://docs.gnani.ai/api/TTS/tts-inference
          https://docs.gnani.ai/api/TTS/tts-audio-tags

Key facts from the real docs
-----------------------------
Timbre v3.0 voices (13 total, each speaks all 10 languages):
  Avinash, Shivani, Lakshmi, Kalpana, Shubham, Prakash,
  Devansh, Yashraj, Chetana, Vasudha, Riyaa, Tarika, Harshad

  NOTE: Pranav and Nalini are Timbre v2.5-only voices. They do NOT
  work with timbre-v3.0.

Language codes for TTS (not the same as STT):
  hi-en  = Hinglish (code-mixed Hindi-English) ← correct for this project
  hi-IN  = Hindi
  en-IN  = Indian English
  auto   = auto-detect from script (safe for mixed text)

Audio expression tags (Timbre v3.0 only, 13 total):
  <laugh>  <giggle>  <sigh>  <exhales>  <sniffles>  <yawns>
  <coughs>  <clears throat>  <whispers>  <shouting>  <excited>
  <slow>  <pauses>

  Tag scope: each tag changes delivery from its position to the END of
  the text (or until the next tag). There is NO closing tag.

  IMPORTANT: tags are OPEN only. Do NOT write </sigh> or <sigh>…</sigh>.
  Write: "<sigh> Arre yaar, scores is None check missing hai."

  Unknown tags are stripped silently — the request still succeeds.
"""

from __future__ import annotations

from pathlib import Path

from gnani.tts import GnaniTTSClient
from gnani.tts.exceptions import GnaniTTSError

from .stt import require_api_key

MODEL = "timbre-v3.0"

# Default voice: Avinash (male, Timbre v3.0 — speaks all 10 languages)
# Alt voice:     Shivani (female, Timbre v3.0)
DEFAULT_VOICE = "Avinash"
ALT_VOICE = "Shivani"

# hi-en is the correct language code for Hinglish (code-mixed Hindi-English).
# Use "auto" if the text may be in any Indian language.
DEFAULT_LANGUAGE = "hi-IN"   # Hindi — SDK supports hi-IN, not hi-en

# ---------------------------------------------------------------------------
# Severity detection for expression tag injection
# ---------------------------------------------------------------------------

_SUCCESS_SIGNALS = {
    "passed", "success", "fixed", "correct", "works", "all tests",
    "no errors", "no issues", "great", "perfect", "done", "resolved",
    "shabash",
}
_CRITICAL_SIGNALS = {
    "crash", "exception", "traceback", "error", "fatal", "critical",
    "unhandled", "none", "null", "overflow", "leak", "vulnerability",
    "security", "injection", "undefined", "typeerror", "keyerror",
    "indexerror", "attributeerror", "stacktrace", "stack trace",
}
_WARNING_SIGNALS = {
    "warning", "suggest", "consider", "might", "could", "should",
    "potential", "possible", "careful", "note", "tip",
}


def _severity(text: str) -> str:
    """Return 'critical', 'success', 'warning', or 'neutral'."""
    lower = text.lower()
    # Check success first — explicit success label wins over incidental words
    if any(s in lower for s in _SUCCESS_SIGNALS):
        return "success"
    if any(s in lower for s in _CRITICAL_SIGNALS):
        return "critical"
    if any(s in lower for s in _WARNING_SIGNALS):
        return "warning"
    return "neutral"


def inject_expression_tag(text: str, answer: dict | None = None) -> str:
    """Prepend a Timbre v3.0 expression tag based on answer severity.

    Tags are OPEN only (no closing tag). The tag changes delivery from
    its position to the end of the text. We prepend it so the whole
    spoken text carries the right emotion.

    Mapping:
      critical  ->  "<sigh> Arre yaar, {text}"
      success   ->  "<excited> Shabash! {text}"
      warning   ->  "<slow> {text}"
      neutral   ->  text unchanged

    The ``<laugh>`` / ``<giggle>`` tags exist but sound odd for
    developer responses; <excited> is the correct "celebratory" tag.
    """
    # Explicit check-field override (highest priority)
    if answer:
        check_val = (answer.get("check") or "").lower()
        if any(s in check_val for s in _SUCCESS_SIGNALS):
            return f"<excited> Shabash! {text}"

    combined = text
    if answer:
        combined = " ".join(filter(None, [
            answer.get("what_wrong", ""),
            answer.get("fix", ""),
            answer.get("check", ""),
            text,
        ]))

    sev = _severity(combined)
    if sev == "critical":
        return f"<sigh> Arre yaar, {text}"
    if sev == "success":
        return f"<excited> Shabash! {text}"
    if sev == "warning":
        return f"<slow> {text}"
    return text


def speak(
    text: str,
    output_file: str | Path,
    voice: str = DEFAULT_VOICE,
    language: str = DEFAULT_LANGUAGE,
    answer: dict | None = None,
    expressive: bool = True,
) -> Path:
    """Synthesise ``text`` to ``output_file`` (WAV) using Timbre v3.0.

    Parameters
    ----------
    text:
        Plain spoken text. Expression tags are injected automatically
        unless ``expressive=False``.
    output_file:
        Destination WAV path.
    voice:
        Timbre v3.0 voice name. Default: ``Avinash`` (male).
        Use ``Shivani`` for a female voice.
    language:
        Language code. ``hi-en`` for Hinglish (default).
        ``auto`` if the text may be in any Indian language.
    answer:
        Full answer dict from ``llm.py`` — used to pick the right
        expression tag based on severity.
    expressive:
        ``False`` skips tag injection (plain neutral delivery).
    """
    require_api_key()
    tagged_text = inject_expression_tag(text, answer) if expressive else text
    client = GnaniTTSClient()
    try:
        client.synthesize(
            tagged_text,
            voice=voice,
            model=MODEL,
            language=language,
            output_file=str(output_file),
        )
    except GnaniTTSError as exc:
        raise RuntimeError(f"Timbre TTS failed: {exc}") from exc
    return Path(output_file)
