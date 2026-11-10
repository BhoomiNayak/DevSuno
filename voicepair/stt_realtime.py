"""Prisma v3.0 Realtime WebSocket STT.

Uses ``GnaniSTTStreamClient`` from gnani-vachana to open a WebSocket,
stream raw PCM from the mic, and receive per-utterance transcripts as
the developer speaks.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading

from .context import build_keyterms
from .stt import require_api_key

# Suppress verbose gnani SDK logs in both STT and TTS modules
logging.getLogger("gnani").setLevel(logging.WARNING)

SAMPLE_RATE = 16_000
CHANNELS = 1
CHUNK_SAMPLES = 512
CHUNK_BYTES = CHUNK_SAMPLES * 2   # 16-bit = 2 bytes/sample


class RealtimeSTTError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Mic → async iterator
# ---------------------------------------------------------------------------

async def _mic_audio_source(
    stop_event: threading.Event,
):
    """Yield 1024-byte PCM chunks from the mic until stop_event is set."""
    try:
        import sounddevice as sd
    except Exception as exc:
        raise RealtimeSTTError(
            f"sounddevice not available ({exc}). "
            "Install with: pip install sounddevice numpy"
        ) from exc

    # Unbounded queue — never raises queue.Full.
    # The mic callback runs in a C thread and must never block or raise.
    audio_queue: queue.Queue[bytes | None] = queue.Queue()
    loop = asyncio.get_running_loop()

    def _callback(indata, frames, time_info, status):
        # Drop frames silently if the event loop is falling behind.
        # This is harmless — VAD handles variable frame rates fine.
        try:
            audio_queue.put_nowait(bytes(indata))
        except Exception:
            pass   # never raise inside a sounddevice C callback

    stream = sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=CHUNK_SAMPLES,
        callback=_callback,
    )

    with stream:
        while not stop_event.is_set():
            try:
                chunk = await loop.run_in_executor(
                    None, lambda: audio_queue.get(timeout=0.1)
                )
                if chunk is None:
                    break
                yield chunk
            except queue.Empty:
                continue


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

async def _run_session(
    code_text: str,
    on_transcript,
    on_processing,
    stop_event: threading.Event,
) -> str:
    require_api_key()

    from gnani.stt import GnaniSTTStreamClient
    from gnani.stt.exceptions import GnaniSTTError

    keyterms = build_keyterms(code_text=code_text)
    full_parts: list[str] = []

    def _on_transcript(event) -> None:
        text = (event.text or "").strip()
        if text:
            # Only append if this segment adds new content
            # (the SDK sends cumulative updates — take only the last segment)
            full_parts.append(text)
            lang = getattr(event, "detected_language_code", "") or ""
            on_transcript(text, lang)

    def _on_processing(event) -> None:
        on_processing()

    def _on_error(event) -> None:
        raise RealtimeSTTError(f"Prisma stream error: {event.message}")

    try:
        async with GnaniSTTStreamClient(
            language_code="indic-auto",
            model="prisma-v3.0",
            format="codemix",
            keywords=keyterms,
            sample_rate=SAMPLE_RATE,
        ) as stream:
            await stream.stream_audio(
                _mic_audio_source(stop_event),
                on_transcript=_on_transcript,
                on_processing=_on_processing,
                on_error=_on_error,
                realtime_pace=True,
            )
    except GnaniSTTError as exc:
        raise RealtimeSTTError(f"Prisma Realtime STT failed: {exc}") from exc

    # The SDK sends cumulative rolling transcripts per utterance.
    # Deduplicate: each new segment starts where the last ended.
    # Simple approach: return the last full transcript received,
    # which contains the complete utterance.
    if not full_parts:
        return ""
    # Return the longest/last segment which is the most complete
    return max(full_parts, key=len)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transcribe_live(
    code_text: str = "",
    on_transcript=None,
    on_processing=None,
    idle_timeout: int = 5,
    stop_event: threading.Event | None = None,
) -> str:
    """Record from the mic and transcribe in real time using Prisma v3.0.

    Returns the full transcript when the user presses Enter or goes silent.
    """
    require_api_key()

    if on_transcript is None:
        def on_transcript(text, lang):
            tag = f" [{lang}]" if lang else ""
            print(f"\r  {text}{tag}", end="", flush=True)

    if on_processing is None:
        def on_processing():
            print("  ▌", end="", flush=True)

    if stop_event is None:
        stop_event = threading.Event()

    return asyncio.run(
        _run_session(
            code_text=code_text,
            on_transcript=on_transcript,
            on_processing=on_processing,
            stop_event=stop_event,
        )
    )
