"""Timbre v3.0 SSE streaming TTS.

Uses ``GnaniTTSStreamClient`` from gnani-vachana to stream audio chunks
via Server-Sent Events as they are generated, then plays them immediately
via sounddevice. The first audio arrives ~300 ms after synthesis starts
instead of waiting for the full file.

Comparison with REST TTS
------------------------
  REST:    synthesise entire file → save → play (2–4 s delay)
  SSE:     chunks arrive as generated → play each chunk → done  (~300 ms)

The function also saves the complete audio to ``output_file`` as a WAV
so the existing ``--out`` and ``--play`` paths still work.

Audio format received
---------------------
  Container : WAV (default, 16-bit PCM) — matches sounddevice expectation
  Rate      : 16 000 Hz  (telephony-quality, low latency)
  Channels  : 1 (mono)
  Encoding  : linear_pcm

We request 16 kHz so each chunk is small and playback starts quickly.
48 kHz is higher quality but means larger chunks and longer first-audio
latency.

Dependencies
------------
  sounddevice  — real-time chunk playback  (optional; falls back to file)
  soundfile    — write WAV header          (optional; same)
  gnani-vachana ≥ 0.9.0  — GnaniTTSStreamClient
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

from .stt import require_api_key
from .tts import DEFAULT_LANGUAGE, DEFAULT_VOICE, MODEL, inject_expression_tag

# 16 kHz for small chunks and fast first-audio; still clear for speech
_STREAM_SAMPLE_RATE = 16_000
_STREAM_CHANNELS = 1
_STREAM_WIDTH = 2        # 16-bit = 2 bytes per sample


def speak_streaming(
    text: str,
    output_file: str | Path,
    voice: str = DEFAULT_VOICE,
    language: str = DEFAULT_LANGUAGE,
    answer: dict | None = None,
    expressive: bool = True,
    play: bool = True,
) -> Path:
    """Synthesise ``text`` via Timbre v3.0 SSE streaming.

    Chunks are played through the speaker as they arrive (if ``play=True``
    and sounddevice is available). The full audio is also written to
    ``output_file`` as a WAV file.

    Parameters
    ----------
    text:
        Plain text to speak. Expression tags are injected automatically
        unless ``expressive=False``.
    output_file:
        Destination WAV path.
    voice:
        Timbre v3.0 voice name. Default: ``Avinash``.
    language:
        Language code. ``hi-en`` for Hinglish.
    answer:
        Answer dict from ``llm.py`` — drives expression tag selection.
    expressive:
        ``False`` skips tag injection.
    play:
        Stream audio to the speaker as chunks arrive.

    Returns
    -------
    Path
        Path to the saved WAV file.
    """
    require_api_key()

    tagged_text = inject_expression_tag(text, answer) if expressive else text

    from gnani.tts import GnaniTTSStreamClient, AudioConfig
    from gnani.tts.exceptions import GnaniTTSError

    # Collect all raw PCM bytes from the SSE stream
    all_pcm: list[bytes] = []

    # Set up real-time playback if sounddevice is available
    sd = _try_import_sounddevice()

    audio_cfg = AudioConfig(
        sample_rate=_STREAM_SAMPLE_RATE,
        num_channels=_STREAM_CHANNELS,
        sample_width=_STREAM_WIDTH,
        encoding="linear_pcm",
        container="raw",   # raw PCM — no WAV header per chunk
    )

    try:
        client = GnaniTTSStreamClient()
        for chunk in client.synthesize_stream(
            tagged_text,
            voice=voice,
            model=MODEL,
            language=language,
            audio_config=audio_cfg,
        ):
            if chunk:
                all_pcm.append(chunk)
                if play and sd is not None:
                    _play_pcm_chunk(chunk, sd)

    except GnaniTTSError as exc:
        raise RuntimeError(f"Timbre SSE streaming failed: {exc}") from exc

    # Write collected PCM to a proper WAV file
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(out_path, b"".join(all_pcm))
    return out_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_import_sounddevice():
    """Return the sounddevice module or None if unavailable."""
    try:
        import sounddevice as sd
        return sd
    except Exception:
        return None


def _play_pcm_chunk(pcm_bytes: bytes, sd) -> None:
    """Play a raw PCM chunk immediately via sounddevice (non-blocking)."""
    try:
        import numpy as np
        samples = np.frombuffer(pcm_bytes, dtype="<i2")  # little-endian int16
        sd.play(samples, samplerate=_STREAM_SAMPLE_RATE, blocking=True)
    except Exception:
        pass   # never fatal — the full file is still saved


def _write_wav(path: Path, pcm: bytes) -> None:
    """Write raw PCM bytes to a 16-bit mono WAV file."""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(_STREAM_CHANNELS)
        wf.setsampwidth(_STREAM_WIDTH)
        wf.setframerate(_STREAM_SAMPLE_RATE)
        wf.writeframes(pcm)


def speak_ephemeral(
    text: str,
    voice: str = DEFAULT_VOICE,
    language: str = DEFAULT_LANGUAGE,
    answer: dict | None = None,
    expressive: bool = True,
) -> None:
    """Synthesise ``text`` and play it immediately — no file saved.

    Collects all SSE chunks (low latency start), builds a complete WAV
    in memory, plays it via soundfile+sounddevice. Falls back to REST
    TTS if streaming fails.
    """
    require_api_key()
    tagged_text = inject_expression_tag(text, answer) if expressive else text

    from gnani.tts import GnaniTTSStreamClient, AudioConfig, GnaniTTSClient
    from gnani.tts.exceptions import GnaniTTSError

    # Use WAV container so each chunk is self-describing and playback
    # is unambiguous regardless of sample rate.
    audio_cfg = AudioConfig(
        sample_rate=48_000,
        num_channels=1,
        sample_width=2,
        encoding="linear_pcm",
        container="wav",
    )

    all_chunks: list[bytes] = []
    try:
        client = GnaniTTSStreamClient()
        for chunk in client.synthesize_stream(
            tagged_text,
            voice=voice,
            model=MODEL,
            language=language,
            audio_config=audio_cfg,
        ):
            if chunk:
                all_chunks.append(chunk)
    except GnaniTTSError as exc:
        raise RuntimeError(f"Timbre streaming failed: {exc}") from exc

    if not all_chunks:
        return

    # Play the complete audio using soundfile (handles WAV header correctly)
    _play_wav_bytes(b"".join(all_chunks))


def _play_wav_bytes(wav_bytes: bytes) -> None:
    """Play WAV audio from an in-memory bytes buffer."""
    try:
        import io
        import soundfile as sf
        import sounddevice as sd
        data, rate = sf.read(io.BytesIO(wav_bytes), dtype="int16")
        sd.play(data, samplerate=rate)
        sd.wait()
    except Exception as exc:
        # Last-resort: write to temp file and play
        try:
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp = f.name
            import soundfile as sf2
            import sounddevice as sd2
            data, rate = sf2.read(tmp, dtype="int16")
            sd2.play(data, samplerate=rate)
            sd2.wait()
            os.unlink(tmp)
        except Exception:
            pass  # TTS worked, playback just not available
