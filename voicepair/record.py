"""Microphone recording for --record mode.

Uses sounddevice (needs a mic and the PortAudio library). In environments
with no input device this fails with a clear message instead of hanging
or crashing; the --audio file path is the reliable way to demo.

Waveform visualisation
----------------------
While recording, a real-time ASCII amplitude bar is printed to the
terminal using Rich's Live display.  Each tick (every 50 ms) samples the
current chunk's RMS amplitude and renders a coloured bar:

  quiet   : dim green   ░░░░░░░░░░░░░░░░░░░
  moderate: bold yellow ████████████░░░░░░░
  loud    : bold red    ███████████████████

The visualisation falls back silently to a plain "Recording…" message
if Rich is not installed.
"""

from __future__ import annotations

import threading
import time
import wave
from pathlib import Path

SAMPLE_RATE = 16000
CHANNELS = 1
_CHUNK = int(SAMPLE_RATE * 0.05)   # 50 ms chunks for the waveform ticker
_BAR_WIDTH = 40                    # character width of the amplitude bar


class RecordError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# ASCII waveform helpers
# ---------------------------------------------------------------------------

def _rms(chunk) -> float:
    """Root-mean-square amplitude of a numpy int16 chunk, normalised 0–1."""
    try:
        import numpy as np
        return float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2))) / 32768.0
    except Exception:
        return 0.0


def _amplitude_bar(rms: float, width: int = _BAR_WIDTH) -> str:
    """Return a Rich-markup coloured amplitude bar string."""
    filled = int(rms * width * 4)   # scale up so quiet speech is visible
    filled = min(filled, width)
    empty = width - filled

    if rms < 0.05:
        colour = "dim green"
        bar_char = "░"
    elif rms < 0.20:
        colour = "bold yellow"
        bar_char = "█"
    else:
        colour = "bold red"
        bar_char = "█"

    bar = bar_char * filled + "░" * empty
    return f"[{colour}]{bar}[/{colour}]"


def _record_with_waveform(seconds: float, sd) -> "numpy.ndarray":
    """Record audio and display a live ASCII waveform via Rich."""
    import numpy as np

    try:
        from rich.live import Live
        from rich.text import Text
        from rich import get_console
        has_rich = True
    except ImportError:
        has_rich = False

    total_frames = int(seconds * SAMPLE_RATE)
    chunks: list = []
    lock = threading.Lock()
    done = threading.Event()

    def _callback(indata, frames, time_info, status):
        with lock:
            chunks.append(indata.copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=_CHUNK,
        callback=_callback,
    )

    if not has_rich:
        # Plain fallback
        with stream:
            print(f"🎙  Recording {seconds:g}s... speak now.", flush=True)
            time.sleep(seconds)
        return np.concatenate(chunks, axis=0)[:total_frames] if chunks else np.zeros((total_frames, 1), dtype="int16")

    # Rich live waveform display
    elapsed = 0.0
    tick = 0.05  # seconds per frame

    def _render(rms: float, elapsed: float) -> Text:
        bar = _amplitude_bar(rms)
        pct = min(elapsed / seconds, 1.0)
        filled_prog = int(pct * 20)
        progress = "▓" * filled_prog + "░" * (20 - filled_prog)
        t = Text.from_markup(
            f"[bold cyan]🎙  Recording[/bold cyan]  {bar}  "
            f"[dim]{elapsed:.1f}s / {seconds:g}s[/dim]  "
            f"[green]{progress}[/green]"
        )
        return t

    with stream:
        with Live(_render(0.0, 0.0), refresh_per_second=20, transient=True) as live:
            start = time.monotonic()
            while elapsed < seconds:
                time.sleep(tick)
                elapsed = time.monotonic() - start
                with lock:
                    last_chunk = chunks[-1] if chunks else None
                rms = _rms(last_chunk) if last_chunk is not None else 0.0
                live.update(_render(rms, elapsed))

    if not chunks:
        raise RecordError("No audio data captured from microphone.")
    audio = np.concatenate(chunks, axis=0)[:total_frames]
    return audio


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record(seconds: float, output_file: str | Path) -> Path:
    """Record ``seconds`` of audio from the default input device.

    Displays a real-time ASCII waveform while recording (requires Rich).
    Saves the result as a 16-bit mono WAV at 16 kHz.

    Raises ``RecordError`` with a clear message on any failure so the
    caller can suggest using ``--audio <file>`` instead.
    """
    try:
        import sounddevice as sd
    except Exception as exc:
        raise RecordError(
            "Microphone recording needs the 'sounddevice' package and the "
            f"PortAudio library. It is not available here ({exc}). "
            "Record the question on your phone instead and pass it with "
            "--audio <question.wav>."
        ) from exc
    try:
        import numpy  # noqa: F401
    except ImportError as exc:
        raise RecordError(
            "Microphone recording needs numpy. Install it, or pass a "
            "recorded file with --audio <question.wav>."
        ) from exc

    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise RecordError(f"Could not list audio devices: {exc}") from exc

    inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
    if not inputs:
        raise RecordError(
            "No microphone / input device found on this machine. "
            "Record the question on your phone instead and pass it with "
            "--audio <question.wav>."
        )

    try:
        audio = _record_with_waveform(seconds, sd)
    except RecordError:
        raise
    except Exception as exc:
        raise RecordError(f"Recording failed: {exc}") from exc

    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio.tobytes())
    return path
