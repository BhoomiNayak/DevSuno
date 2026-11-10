#!/usr/bin/env python3
"""Live pipeline test for Terminal Voice-Pair.

Usage:
    python test_api.py                    # env + local-analysis checks only
    python test_api.py --audio question.wav [--file examples/null_check.py]

Without GNANI_API_KEY it exits with a clear message (no traceback).
Without --audio it does NOT call any Gnani API: it checks the key, the
SDK imports, and the local debug analysis on the bundled examples.
With --audio it runs the full pipeline: Prisma STT -> reasoning ->
Timbre TTS, and reports each stage.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Load GNANI_API_KEY from a .env file in the project folder (see .env.example).
try:
    from dotenv import load_dotenv

    load_dotenv(HERE / ".env")
except Exception:
    pass


def fail(message: str, code: int = 1) -> int:
    print(f"FAIL: {message}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the Voice-Pair pipeline.")
    parser.add_argument("--audio", help="Recorded Hinglish question to run through the full pipeline.")
    parser.add_argument("--file", default="examples/null_check.py", help="Code file for context.")
    parser.add_argument("--out", default="out/test_answer.wav", help="Where to save the spoken test answer.")
    args = parser.parse_args()

    key = os.getenv("GNANI_API_KEY", "").strip()
    if not key:
        return fail(
            "GNANI_API_KEY is not set. Create an API key at app.gnani.ai, "
            "then paste it into the .env file (copy .env.example to .env) "
            "or run: export GNANI_API_KEY=<your key>. No API calls were made."
        )
    print("[ok] GNANI_API_KEY is set.")

    try:
        from gnani.stt import GnaniSTTClient  # noqa: F401
        from gnani.tts import GnaniTTSClient  # noqa: F401
        from voicepair import llm, stt, tts  # noqa: F401
    except ImportError as exc:
        return fail(f"Import failed: {exc}")

    print("[ok] gnani-vachana SDK and voicepair package import cleanly.")
    print(f"[info] Reasoning backend: {llm.backend()} "
          f"({'Evon via EVON_API_URL' if llm.backend() == 'evon' else 'local fallback; Evon is not on the public API platform'})")

    # Stage 0: local analysis works on the bundled examples (no API call).
    from voicepair import local_debug
    from voicepair.context import build_keyterms
    from voicepair.tts import inject_expression_tag

    code = Path(args.file).read_text(errors="replace")
    answer = local_debug.analyse("is array me null check kyun miss ho gaya", code)
    print(f"[ok] Local debug analysis on {args.file}: check={answer['check']}, "
          f"backend={answer['backend']}")
    print(f"     What is wrong: {answer['what_wrong'][:120]}")

    # Stage 0b: dynamic keyterms extraction
    keyterms = build_keyterms(code_text=code)
    print(f"[ok] Dynamic keyterms built: {len(keyterms)} terms "
          f"(sample: {keyterms[:6]})")

    # Stage 0c: Timbre v3 expression tag injection
    critical_text = "null pointer crash ho gaya"
    tagged = inject_expression_tag(critical_text, answer)
    print(f"[ok] Expression tag injection: {tagged[:80]}")

    # Stage 0d: stack trace summariser
    sample_trace = (
        "Traceback (most recent call last):\n"
        '  File "examples/null_check.py", line 12, in process_scores\n'
        "    total = scores[0]\n"
        "TypeError: 'NoneType' object is not subscriptable\n"
    )
    trace_answer = local_debug.summarise_trace(sample_trace)
    print(f"[ok] Trace summariser: exception={trace_answer['exception']}, "
          f"location={trace_answer['location']}")
    print(f"     Root cause: {trace_answer['what_wrong'][:100]}")

    if not args.audio:
        print("\nNo --audio given, so no Gnani API calls were made.")
        print("For the full live test, record a question and run:")
        print(f"  python test_api.py --audio <question.wav> --file {args.file}")
        return 0

    audio = Path(args.audio)
    if not audio.exists():
        return fail(f"Audio file not found: {audio}")

    print(f"\n[1/3] Prisma STT on {audio} (dynamic keyterms) ...")
    try:
        from voicepair.context import build_keyterms as _bk
        result = stt.transcribe(audio, keyterms=_bk(code_text=code))
    except Exception as exc:
        return fail(f"STT failed: {exc}")
    transcript = (result.get("transcript") or "").strip()
    print(f"[ok] Transcript: {transcript!r} "
          f"(detected: {result.get('detected_language_code', '?')})")
    if not transcript:
        return fail("Prisma returned an empty transcript.")

    print("[2/3] Reasoning ...")
    try:
        answer = llm.debug_answer(transcript, code)
    except Exception as exc:
        return fail(f"Reasoning failed: {exc}")
    print(f"[ok] Backend: {answer['backend']}")
    print(f"     What is wrong: {answer['what_wrong'][:200]}")

    print("[3/3] Timbre v3 TTS (with expression tag injection) ...")
    try:
        out = tts.speak(llm.speakable_text(answer), args.out, answer=answer)
    except Exception as exc:
        return fail(f"TTS failed: {exc}")
    print(f"[ok] Spoken answer saved: {out} ({out.stat().st_size} bytes)")

    print("\nALL STAGES PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
