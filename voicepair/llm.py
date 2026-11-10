"""Reasoning step — the brain between Prisma and Timbre.

The product is a voice loop:
  Prisma (hear) → this module (find the bug) → Timbre (speak the fix)

Two backends, one slot
----------------------
local  (default, always available)
    Rule-based static analyser in ``local_debug.py``. Runs real checks on
    the code in front of it — missing None guard, off-by-one loop bound,
    hardcoded secret, bare ``except:``, unhandled exception patterns.
    Clearly labelled in every answer so the demo never misrepresents what
    answered. No API key, no network call, no latency.

evon   (optional, future-ready)
    Used only when ``EVON_API_URL`` is set in the environment, meaning
    Gnani has granted private Evon endpoint access. Posts an
    OpenAI-compatible chat-completions request to that URL with
    ``GNANI_API_KEY``. The slot is built; nothing else needs to change
    when access is granted.

    Evon v3.3 is NOT on the public Gnani API platform as of 10 Nov 2026.
    It is open-weight on Hugging Face and available via closed-beta
    private endpoint only. The demo runs correctly without it.

There is no third-party LLM backend. This project is built on Gnani's
speech APIs (Prisma + Timbre). The reasoning step is the honest local
analyser that the demo actually shows.

REVIEW_SYSTEM_PROMPT is exposed so ``cli.py`` can pass a review-specific
instruction string to the Evon backend when it is eventually available.
"""

from __future__ import annotations

import os

import requests

from . import local_debug

# System prompt for Evon (used when EVON_API_URL is set)
SYSTEM_PROMPT = (
    "You are a debugging copilot for a developer who speaks Hinglish. "
    "Answer in short, simple Hinglish-friendly English. Three parts only: "
    "1) What is wrong (one sentence). "
    "2) The fix (one or two sentences). "
    "3) One corrected line of code. Nothing else."
)

REVIEW_SYSTEM_PROMPT = (
    "You are a senior code reviewer. The developer describes what to look for "
    "in Hinglish. Analyse the git diff and reply in short, structured "
    "Hinglish-friendly English: 1) Issues found (security, unhandled "
    "exceptions, anti-patterns). 2) The most critical one to fix first. "
    "3) One corrected code snippet for the worst issue. Under 200 words."
)


def backend() -> str:
    """Return 'evon' if EVON_API_URL is set, otherwise 'local'."""
    return "evon" if os.getenv("EVON_API_URL", "").strip() else "local"


def _evon_answer(question: str, code: str,
                 system_prompt: str = SYSTEM_PROMPT) -> dict:
    """Call the Evon endpoint (only when EVON_API_URL is configured)."""
    base_url = os.getenv("EVON_API_URL", "").strip().rstrip("/")
    model = os.getenv("EVON_MODEL", "evon-v3.3").strip()
    key = os.getenv("GNANI_API_KEY", "").strip()
    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Question: {question}\n\nCode:\n```\n{code[:4000]}\n```",
            },
        ],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=90,
        )
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Could not reach Evon endpoint {url}: {exc}. "
            "Run with --llm local to use the local analyser."
        ) from exc
    if resp.status_code != 200:
        raise RuntimeError(
            f"Evon returned HTTP {resp.status_code}: {resp.text[:300]}. "
            "Evon access may not be granted for this key. "
            "Run with --llm local."
        )
    try:
        content = resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as exc:
        raise RuntimeError(
            f"Evon returned an unexpected response: {resp.text[:300]}"
        ) from exc
    return {
        "what_wrong": content,
        "fix": "",
        "corrected_line": "",
        "check": "evon",
        "backend": "evon",
        "raw": content,
    }


def debug_answer(question: str, code: str, llm: str = "auto",
                 system_prompt: str = SYSTEM_PROMPT) -> dict:
    """Return a structured debug answer dict.

    Parameters
    ----------
    question:
        Transcribed developer question (Hinglish).
    code:
        Source file content or git diff to analyse.
    llm:
        ``"auto"``  — evon if EVON_API_URL is set, otherwise local.
        ``"evon"``  — Evon only; fails loudly if unreachable.
        ``"local"`` — rule-based analyser, always available.
    system_prompt:
        Injected as the system role for Evon (ignored by local).
    """
    if llm == "evon":
        return _evon_answer(question, code, system_prompt)
    if llm == "local":
        return local_debug.analyse(question, code)
    if llm != "auto":
        raise ValueError(
            f"Unknown --llm value: {llm!r} (choose auto, evon, or local)"
        )
    if backend() == "evon":
        return _evon_answer(question, code, system_prompt)
    return local_debug.analyse(question, code)


def speakable_text(answer: dict) -> str:
    """Build the spoken string for Timbre TTS from an answer dict."""
    if answer.get("raw"):
        return answer["raw"][:600]

    parts: list[str] = []

    # Trace answers lead with location
    if answer.get("backend") == "local-trace" and answer.get("exception"):
        parts.append(f"{answer['exception']} mila {answer.get('location', '')} pe.")

    parts.append(answer.get("what_wrong", ""))
    parts.append(answer.get("fix", ""))

    if answer.get("corrected_line"):
        parts.append(f"Corrected line: {answer['corrected_line']}")

    return " ".join(p for p in parts if p)[:600]
