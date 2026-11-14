"""File-save watcher for ``devsuno watch``.

Uses watchdog to monitor a directory for file saves. The moment a
source file is saved, it runs the static analyser on it. If a bug is
found, Timbre TTS speaks the warning immediately — before the developer
even looks up from their editor.

Behaviour
---------
- Watches .py / .js / .ts / .jsx / .tsx files only.
- Debounces: a file must be stable for 0.5 s before analysis runs
  (avoids double-firing on editor auto-save).
- If the same bug was already reported for the same file in the last
  60 s, it stays silent (avoids repeating on every keystroke-save).
- Ctrl+C exits cleanly.

Terminal output
---------------
Every event (save, bug found, clean) is printed with Rich so the watch
mode looks good on screen during the demo.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

# Suppress gnani SDK logs during watch mode
logging.getLogger("gnani").setLevel(logging.WARNING)

_WATCH_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}
_DEBOUNCE_SECONDS = 0.5      # wait this long after last save event
_COOLDOWN_SECONDS = 60.0     # don't re-report same bug in same file


class _BugCache:
    """Remember recently reported (file, check) pairs to avoid spam."""

    def __init__(self, ttl: float = _COOLDOWN_SECONDS):
        self._ttl = ttl
        self._seen: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def should_report(self, filepath: str, check: str) -> bool:
        key = (filepath, check)
        now = time.monotonic()
        with self._lock:
            last = self._seen.get(key, 0.0)
            if now - last < self._ttl:
                return False
            self._seen[key] = now
            return True

    def clear(self, filepath: str) -> None:
        with self._lock:
            keys = [k for k in self._seen if k[0] == filepath]
            for k in keys:
                del self._seen[k]


class _DebounceTimer:
    """Call a function once after a quiet period."""

    def __init__(self, delay: float, fn):
        self._delay = delay
        self._fn = fn
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def trigger(self, *args, **kwargs):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                self._delay, self._fn, args=args, kwargs=kwargs
            )
            self._timer.daemon = True
            self._timer.start()


def _get_console():
    try:
        from rich.console import Console
        return Console()
    except ImportError:
        return None


def _cprint(console, *args, **kwargs):
    if console:
        console.print(*args, **kwargs)
    else:
        import re
        text = " ".join(str(a) for a in args)
        print(re.sub(r"\[/?[^\]]*\]", "", text))


def run_watch(
    watch_dir: str | Path,
    voice: bool = False,
    voice_name: str = "Avinash",
    speak_clean: bool = False,
) -> None:
    """Start the file-save watcher. Blocks until Ctrl+C.

    Parameters
    ----------
    watch_dir:
        Directory to watch recursively.
    voice:
        Speak bug warnings via Timbre TTS when a bug is found.
    voice_name:
        Timbre voice to use.
    speak_clean:
        Also speak a "clean" message when a saved file has no issues.
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    from .local_debug import analyse

    root = Path(watch_dir).resolve()
    console = _get_console()
    cache = _BugCache()

    # TTS helper — only imported if voice=True
    def _speak(text: str, answer: dict | None = None) -> None:
        if not voice:
            return
        try:
            from .tts_stream import speak_ephemeral
            speak_ephemeral(text, voice=voice_name,
                            answer=answer, expressive=True)
        except Exception:
            try:
                import tempfile, os as _os
                from .tts import speak as _speak_rest
                from .tts import inject_expression_tag
                tagged = inject_expression_tag(text, answer) if answer else text
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as tmp:
                    tmp_path = tmp.name
                _speak_rest(tagged, tmp_path, voice=voice_name, expressive=False)
                import soundfile as sf
                import sounddevice as sd
                data, rate = sf.read(tmp_path, dtype="int16")
                sd.play(data, samplerate=rate)
                sd.wait()
                _os.unlink(tmp_path)
            except Exception:
                pass   # voice failed silently — text output still works

    def _on_save(filepath: str) -> None:
        path = Path(filepath)
        if path.suffix.lower() not in _WATCH_EXTENSIONS:
            return
        try:
            code = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        rel = str(path.relative_to(root)) if path.is_relative_to(root) else filepath
        result = analyse("watch", code)

        if result["check"] == "no-pattern-matched":
            cache.clear(filepath)
            if speak_clean:
                _cprint(console,
                        f"[green]✓[/green] [dim]{rel}[/dim] — clean")
                _speak(f"{rel} clean hai, koi issue nahi.")
            return

        if not cache.should_report(filepath, result["check"]):
            return  # already reported recently, stay silent

        # Print warning panel
        try:
            from rich.panel import Panel
            from rich.table import Table
            from rich.text import Text

            _colours = {
                "hardcoded-secret": "bold red",
                "bare-except": "red",
                "python-none-guard": "yellow",
                "unclosed-file": "yellow",
                "mutable-default-arg": "dim yellow",
                "off-by-one-bound": "cyan",
            }
            colour = _colours.get(result["check"], "white")

            t = Table.grid(padding=(0, 1))
            t.add_column(style="bold", no_wrap=True)
            t.add_column()
            t.add_row("File",   Text(rel, style="cyan"))
            t.add_row("Check",  Text(result["check"], style=colour))
            t.add_row("Bug",    result["what_wrong"][:120])
            t.add_row("Fix",    result["fix"][:120])
            if result.get("corrected_line"):
                t.add_row("Line",   result["corrected_line"][:60])

            console.print(Panel(
                t,
                title=f"[{colour}]⚠  Bug detected on save[/{colour}]",
                border_style=colour.replace("bold ", ""),
            ))
        except Exception:
            _cprint(console,
                    f"[red]⚠  {rel}[/red] — {result['check']}: "
                    f"{result['what_wrong'][:80]}")

        # Speak the warning
        spoken = (
            f"{rel.split('/')[-1]} mein {result['check'].replace('-', ' ')} "
            f"mila. {result['what_wrong'][:100]}"
        )
        _speak(spoken, answer=result)

    # Debounce per file path
    _debouncers: dict[str, _DebounceTimer] = {}
    _debouncers_lock = threading.Lock()

    class _Handler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return
            fp = str(event.src_path)
            if Path(fp).suffix.lower() not in _WATCH_EXTENSIONS:
                return
            with _debouncers_lock:
                if fp not in _debouncers:
                    _debouncers[fp] = _DebounceTimer(_DEBOUNCE_SECONDS, _on_save)
                _debouncers[fp].trigger(fp)

        on_created = on_modified   # treat new files the same as saves

    observer = Observer()
    observer.schedule(_Handler(), str(root), recursive=True)
    observer.start()

    _cprint(console, "")
    try:
        from rich.panel import Panel
        from rich.text import Text
        t = Text()
        t.append(f"  Watching  ", style="dim")
        t.append(str(root), style="bold cyan")
        t.append(f"\n  Extensions: {', '.join(sorted(_WATCH_EXTENSIONS))}", style="dim")
        t.append(f"\n  Voice:  {'on (' + voice_name + ')' if voice else 'off (pass --voice to enable)'}", style="dim")
        t.append(f"\n  Ctrl+C  to stop\n", style="dim")
        console.print(Panel(t, title="[bold green]DevSuno Watch[/bold green]",
                            border_style="green"))
    except Exception:
        _cprint(console,
                f"Watching {root} — Ctrl+C to stop")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        _cprint(console, "\n[dim]Watch stopped.[/dim]")
