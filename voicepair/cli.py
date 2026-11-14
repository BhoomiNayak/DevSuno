"""Terminal Voice-Pair / DevSuno CLI.

Subcommands
-----------
ask      Original flow: audio -> Prisma STT -> reasoning -> Timbre TTS.
         Add --live to use Prisma Realtime WebSocket STT instead of a WAV file.
review   Voice Git Diff reviewer: speak what to look for, hear the issues.
         Add --live for realtime mic transcription.
trace    Audio Stack Trace Reader: pipe stderr, hear the root cause.

All output uses Rich for colours, spinners, syntax-highlighted code, and
panels so the demo looks great on any modern terminal.

Streaming modes
---------------
--live      Prisma Realtime WebSocket STT: words appear as you speak.
            Press Enter to stop recording. Requires sounddevice + numpy.
            Default (no --live): batch WAV file upload via Prisma REST.

--stream-tts  Timbre SSE streaming: audio plays as chunks arrive (~300 ms
              first-audio instead of waiting for the full synthesis).
              Default (no --stream-tts): full WAV file, then play.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
from pathlib import Path

from . import __version__, llm, record, stt, tts
from .context import build_keyterms
from .local_debug import summarise_trace
from .stt import MissingApiKeyError

MAX_CODE_CHARS = 4000

# ---------------------------------------------------------------------------
# Rich helpers — imported lazily so the CLI still works without Rich
# (falls back to plain print when Rich is absent).
# ---------------------------------------------------------------------------

def _get_console():
    try:
        from rich.console import Console
        return Console()
    except ImportError:
        return None


def _print(console, *args, **kwargs):
    if console:
        console.print(*args, **kwargs)
    else:
        # Strip Rich markup tags for plain fallback
        import re
        text = " ".join(str(a) for a in args)
        text = re.sub(r"\[/?[^\]]*\]", "", text)
        print(text)


def _spinner(console, message: str):
    """Return a Rich spinner context-manager or a no-op context."""
    try:
        from rich.status import Status
        return Status(message, console=console, spinner="dots")
    except ImportError:
        import contextlib
        @contextlib.contextmanager
        def _noop():
            print(message)
            yield
        return _noop()


def _rule(console, title: str = ""):
    if console:
        console.rule(title)
    else:
        print(f"\n{'─' * 60}  {title}")


def _syntax_panel(console, code: str, language: str, title: str):
    """Print a syntax-highlighted panel; plain print fallback."""
    if not console:
        print(f"\n── {title} ──\n{code}\n")
        return
    try:
        from rich.panel import Panel
        from rich.syntax import Syntax
        syn = Syntax(code.strip(), language, theme="monokai",
                     line_numbers=False, word_wrap=True)
        console.print(Panel(syn, title=f"[bold]{title}[/bold]",
                            border_style="cyan"))
    except Exception:
        console.print(code)


def _answer_panel(console, answer: dict):
    """Render the structured answer dict as a Rich panel."""
    if not console:
        print(f"\n--- Answer ---")
        print(f"What is wrong : {answer['what_wrong']}")
        if answer.get("fix"):
            print(f"The fix       : {answer['fix']}")
        if answer.get("corrected_line"):
            print(f"Corrected line: {answer['corrected_line']}")
        print(f"Backend       : {answer['backend']}")
        return
    try:
        from rich.panel import Panel
        from rich.table import Table
        from rich.syntax import Syntax
        from rich.text import Text

        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold yellow", no_wrap=True)
        table.add_column()
        table.add_row("What is wrong", answer["what_wrong"])
        if answer.get("fix"):
            table.add_row("The fix", answer["fix"])
        if answer.get("corrected_line"):
            lang = "python" if "\n" not in answer["corrected_line"] else "python"
            syn = Syntax(answer["corrected_line"], lang, theme="monokai",
                         line_numbers=False)
            table.add_row("Corrected line", syn)
        table.add_row(
            "Backend",
            Text(answer["backend"], style="dim"),
        )
        console.print(Panel(table, title="[bold green]DevSuno Answer[/bold green]",
                            border_style="green"))
    except Exception:
        console.print(answer)


def _trace_panel(console, answer: dict):
    """Render a trace summary as a Rich panel."""
    if not console:
        print(f"\n--- Trace Summary ---")
        print(f"Exception : {answer['exception']}")
        print(f"Location  : {answer['location']}")
        print(f"Root cause: {answer['what_wrong']}")
        print(f"Fix hint  : {answer['fix']}")
        return
    try:
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold red", no_wrap=True)
        table.add_column()
        table.add_row("Exception", Text(answer["exception"], style="bold red"))
        table.add_row("Location", Text(answer["location"], style="yellow"))
        table.add_row("Root cause", answer["what_wrong"])
        table.add_row("Fix hint", answer["fix"])
        console.print(Panel(table, title="[bold red]Trace Summary[/bold red]",
                            border_style="red"))
    except Exception:
        console.print(answer)


# ---------------------------------------------------------------------------
# Shared workflow helpers
# ---------------------------------------------------------------------------

def _read_file_context(file_arg: str) -> tuple[str, str]:
    path = Path(file_arg)
    if not path.exists():
        raise SystemExit(f"Code file not found: {path}")
    text = path.read_text(errors="replace")[:MAX_CODE_CHARS]
    return text, f"file {path}"


def _read_git_diff(cwd: Path | None = None) -> tuple[str, str]:
    try:
        out = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True,
            cwd=str(cwd or Path.cwd()), timeout=30,
        )
    except Exception as exc:
        raise SystemExit(f"Could not run git diff: {exc}")
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit(
            "git diff is empty or this is not a git repo. "
            "Make sure you have uncommitted changes, or use "
            "--file <code-file> instead."
        )
    return out.stdout[:MAX_CODE_CHARS], "git diff"


def _get_audio_path(args, console) -> Path:
    audio_path = Path(args.audio) if getattr(args, "audio", None) else None
    if getattr(args, "record", False):
        _print(console,
               "[bold green]🎙  Preparing microphone...[/bold green]")
        try:
            audio_path = record.record(
                args.seconds,
                getattr(args, "record_out", "out/question.wav"),
            )
        except record.RecordError as exc:
            raise SystemExit(f"Error: {exc}")
        _print(console,
               f"[green]✓[/green] Saved recording: [cyan]{audio_path}[/cyan]")
    if audio_path is None or not audio_path.exists():
        raise SystemExit(f"Error: audio file not found: {audio_path}")
    return audio_path


def _play_if_possible(path: Path, console) -> None:
    try:
        import soundfile as sf
        import sounddevice as sd
        data, rate = sf.read(str(path), dtype="int16")
        sd.play(data, samplerate=rate)
        sd.wait()
    except Exception as exc:
        _print(console,
               f"[dim](Tip: play the answer with any audio player: {path})[/dim]")


def _transcribe(audio_path: Path, code: str, console) -> tuple[str, str]:
    keyterms = build_keyterms(code_text=code)
    _print(console,
           f"[dim]  keyterms: {len(keyterms)} workspace terms loaded[/dim]")
    result = stt.transcribe(audio_path, keyterms=keyterms)
    transcript = (result.get("transcript") or "").strip()
    detected = result.get("detected_language_code", "")
    if not transcript:
        raise SystemExit("Error: Prisma returned an empty transcript.")
    return transcript, detected


def _live_transcribe(code: str, console) -> tuple[str, str]:
    """Prisma Realtime WebSocket STT — words appear as the developer speaks."""
    from .stt_realtime import transcribe_live, RealtimeSTTError

    stop_event = threading.Event()
    segments: list[str] = []
    last_lang: list[str] = [""]

    def _on_transcript(text: str, lang: str) -> None:
        segments.append(text)
        last_lang[0] = lang or last_lang[0]
        full = " ".join(segments)
        _print(console,
               f"\r[bold yellow]You said:[/bold yellow] {full}  ", end="")

    def _on_processing() -> None:
        _print(console, "[dim]▌[/dim]", end="")

    def _wait_for_enter() -> None:
        try:
            input()
        except Exception:
            pass
        stop_event.set()

    _print(console,
           "\n[bold green]🎙  Live[/bold green] — speak now "
           "[dim](press Enter to stop)[/dim]")
    t = threading.Thread(target=_wait_for_enter, daemon=True)
    t.start()

    try:
        full = transcribe_live(
            code_text=code,
            on_transcript=_on_transcript,
            on_processing=_on_processing,
            idle_timeout=5,
            stop_event=stop_event,
        )
    except RealtimeSTTError as exc:
        raise SystemExit(f"Realtime STT error: {exc}")

    print()
    if not full.strip():
        raise SystemExit("Error: no speech detected.")
    return full.strip(), last_lang[0]


def _save_and_speak(answer: dict, out_path: Path, voice: str,
                    play: bool, console, expressive: bool = True,
                    stream_tts: bool = False) -> None:
    """Synthesise answer. ``stream_tts=True`` uses Timbre SSE streaming."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    spoken = llm.speakable_text(answer)

    if stream_tts:
        from .tts_stream import speak_streaming
        _print(console,
               f"[cyan]Timbre v3 SSE stream[/cyan] → {out_path} "
               "[dim](playing as chunks arrive…)[/dim]")
        try:
            speak_streaming(
                spoken, out_path,
                voice=voice, answer=answer, expressive=expressive,
                play=play,
            )
            _print(console,
                   f"[green]✓[/green] Spoken answer saved: "
                   f"[cyan]{out_path}[/cyan]")
            return
        except Exception as exc:
            _print(console,
                   f"[yellow]SSE stream failed ({exc}), "
                   f"falling back to REST TTS…[/yellow]")

    with _spinner(console,
                  f"[cyan]Timbre v3 TTS[/cyan] synthesising → {out_path}…"):
        tts.speak(spoken, out_path, voice=voice,
                  answer=answer, expressive=expressive)
    _print(console,
           f"[green]✓[/green] Spoken answer saved: [cyan]{out_path}[/cyan]")
    if play:
        _print(console, "[cyan]▶  Playing…[/cyan]")
        _play_if_possible(out_path, console)


# ---------------------------------------------------------------------------
# ask
# ---------------------------------------------------------------------------

def cmd_ask(args) -> int:
    console = _get_console()

    # --text skips Prisma STT entirely — no API key needed for STT
    if not getattr(args, "text", None):
        try:
            stt.require_api_key()
        except MissingApiKeyError as exc:
            _print(console, f"[bold red]Error:[/bold red] {exc}")
            return 2

    _rule(console, "[bold cyan]DevSuno — ask[/bold cyan]")

    # Code context
    if args.file and args.diff:
        raise SystemExit("Pass only one of --file and --diff, not both.")
    if args.file:
        code, context_desc = _read_file_context(args.file)
        # Show the code file in a syntax panel
        lang = Path(args.file).suffix.lstrip(".") or "text"
        _syntax_panel(console, code, lang, f"Code context: {args.file}")
    elif args.diff:
        code, context_desc = _read_git_diff()
        _syntax_panel(console, code, "diff", "Code context: git diff")
    else:
        raise SystemExit("Provide code context: --file <code-file> or --diff.")

    # STT — typed text, live WebSocket, or batch WAV
    if getattr(args, "text", None):
        transcript = args.text.strip()
        detected = ""
        _print(console,
               f"\n[bold yellow]Question:[/bold yellow] {transcript}")
        _print(console, "[dim]  (typed input — Prisma STT skipped)[/dim]")
    elif getattr(args, "live", False):
        try:
            transcript, detected = _live_transcribe(code, console)
        except SystemExit:
            raise
        except Exception as exc:
            _print(console, f"[bold red]Live STT Error:[/bold red] {exc}")
            return 1
    else:
        audio_path = _get_audio_path(args, console)
        with _spinner(console,
                      f"[cyan]Prisma STT[/cyan] transcribing {audio_path}…"):
            try:
                transcript, detected = _transcribe(audio_path, code, console)
            except Exception as exc:
                _print(console, f"[bold red]STT Error:[/bold red] {exc}")
                return 1

    _print(console, f"\n[bold yellow]You said:[/bold yellow] {transcript}")
    if detected:
        _print(console, f"[dim]  detected language: {detected}[/dim]")

    # Reasoning
    backend_name = llm.backend() if args.llm == "auto" else args.llm
    with _spinner(console,
                  f"[cyan]Reasoning[/cyan] ({backend_name})…"):
        try:
            answer = llm.debug_answer(transcript, code, llm=args.llm)
        except Exception as exc:
            _print(console, f"[bold red]Reasoning Error:[/bold red] {exc}")
            return 1

    _answer_panel(console, answer)

    # --- Auto-fix -----------------------------------------------------------
    if getattr(args, "fix", False) or getattr(args, "force_fix", False):
        if args.file and answer.get("check") != "no-pattern-matched":
            from .fixer import apply_fix
            _print(console, "\n[bold cyan]Auto-fix[/bold cyan]")
            confirm = not getattr(args, "force_fix", False)
            ok, msg = apply_fix(
                args.file, answer,
                confirm=confirm,
                console=console,
            )
            if ok:
                _print(console, f"[bold green]✓[/bold green] {msg}")
                # Speak the fix confirmation
                answer["what_wrong"] = msg
                answer["check"] = "success"
            else:
                _print(console, f"[yellow]{msg}[/yellow]")

    # TTS
    _save_and_speak(answer, Path(args.out), args.voice, args.play,
                    console, stream_tts=getattr(args, "stream_tts", False))
    return 0


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------

_REVIEW_SYSTEM_PROMPT = llm.REVIEW_SYSTEM_PROMPT


def cmd_review(args) -> int:
    console = _get_console()

    try:
        stt.require_api_key()
    except MissingApiKeyError as exc:
        _print(console, f"[bold red]Error:[/bold red] {exc}")
        return 2

    _rule(console, "[bold magenta]DevSuno — review[/bold magenta]")

    # Diff context
    if getattr(args, "diff_file", None):
        diff_path = Path(args.diff_file)
        if not diff_path.exists():
            raise SystemExit(f"Diff file not found: {diff_path}")
        diff_text = diff_path.read_text(errors="replace")[:MAX_CODE_CHARS]
        context_desc = f"diff file {diff_path}"
    else:
        diff_text, context_desc = _read_git_diff()

    _syntax_panel(console, diff_text, "diff",
                  f"Code context: {context_desc}")

    # STT — live WebSocket or batch WAV
    if getattr(args, "live", False):
        try:
            transcript, detected = _live_transcribe(diff_text, console)
        except SystemExit:
            raise
        except Exception as exc:
            _print(console, f"[bold red]Live STT Error:[/bold red] {exc}")
            return 1
    else:
        audio_path = _get_audio_path(args, console)
        with _spinner(console,
                      f"[cyan]Prisma STT[/cyan] transcribing review intent…"):
            try:
                transcript, detected = _transcribe(audio_path, diff_text,
                                                   console)
            except Exception as exc:
                _print(console, f"[bold red]STT Error:[/bold red] {exc}")
                return 1

    _print(console, f"\n[bold yellow]You said:[/bold yellow] {transcript}")
    if detected:
        _print(console, f"[dim]  detected language: {detected}[/dim]")

    # Reasoning — pass the review-specific system prompt
    backend_name = llm.backend() if args.llm == "auto" else args.llm
    with _spinner(console,
                  f"[cyan]Reviewing diff[/cyan] with {backend_name}…"):
        try:
            answer = llm.debug_answer(
                transcript, diff_text,
                llm=args.llm,
                system_prompt=_REVIEW_SYSTEM_PROMPT,
            )
            if answer.get("check") == "no-pattern-matched":
                answer["what_wrong"] = (
                    "Local static checks ne koi specific pattern nahi pakda. "
                    "Diff manually review karo for security issues and "
                    "unhandled exceptions. "
                    "(Set EVON_API_URL if Gnani grants Evon access for deeper analysis.)"
                )
                answer["check"] = "review-no-pattern"
            answer["backend"] = answer.get("backend", "local") + " (review)"
        except Exception as exc:
            _print(console, f"[bold red]Review Error:[/bold red] {exc}")
            return 1

    _answer_panel(console, answer)

    _save_and_speak(answer, Path(args.out), args.voice, args.play,
                    console, stream_tts=getattr(args, "stream_tts", False))
    return 0


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------

def cmd_trace(args) -> int:
    console = _get_console()
    _rule(console, "[bold red]DevSuno — trace[/bold red]")

    # Read traceback
    if getattr(args, "trace_file", None):
        tfile = Path(args.trace_file)
        if not tfile.exists():
            raise SystemExit(f"Trace file not found: {tfile}")
        raw_trace = tfile.read_text(errors="replace")
    elif not sys.stdin.isatty():
        raw_trace = sys.stdin.read()
    else:
        _print(console,
               "[yellow]Usage:[/yellow] "
               "python script.py 2>&1 | devsuno trace --voice\n"
               "Or:    devsuno trace --trace-file traceback.txt --voice")
        return 2

    if not raw_trace.strip():
        raise SystemExit("Error: empty traceback received on stdin.")

    # Show raw trace in a panel
    _syntax_panel(console, raw_trace[:2000], "pytb", "Raw Traceback")

    with _spinner(console, "[cyan]Parsing stack trace…[/cyan]"):
        answer = summarise_trace(raw_trace)

    _trace_panel(console, answer)

    if not args.voice:
        _print(console,
               "[dim](Pass --voice to hear this summary spoken aloud)[/dim]")
        return 0

    try:
        stt.require_api_key()
    except MissingApiKeyError as exc:
        _print(console,
               f"[bold red]Error:[/bold red] {exc} (--voice requires GNANI_API_KEY)")
        return 2

    out_path = Path(args.out)
    _save_and_speak(answer, out_path, args.voice_name, args.play,
                    console, expressive=True)
    return 0




# ---------------------------------------------------------------------------
# chat  — conversational loop, no files saved
# ---------------------------------------------------------------------------

def cmd_chat(args) -> int:
    """Continuous voice conversation loop.

    Speak -> Prisma hears -> analyser finds bug -> Timbre speaks back.
    No WAV files saved. Pure conversation. Ctrl+C to exit.
    """
    console = _get_console()

    try:
        stt.require_api_key()
    except MissingApiKeyError as exc:
        _print(console, f"[bold red]Error:[/bold red] {exc}")
        return 2

    # Resolve code context once — stays loaded for the whole session
    if getattr(args, "file", None):
        code, context_desc = _read_file_context(args.file)
        lang = Path(args.file).suffix.lstrip(".") or "text"
        _syntax_panel(console, code, lang, f"Loaded: {args.file}")
    elif getattr(args, "diff", False):
        code, context_desc = _read_git_diff()
        _syntax_panel(console, code, "diff", "Loaded: git diff")
    else:
        code, context_desc = "", "no code context"

    _rule(console, "[bold cyan]DevSuno Chat[/bold cyan]")
    _print(console,
           f"[dim]Context: {context_desc} | "
           f"Voice: {args.voice} | "
           "Ctrl+C to exit[/dim]\n")

    turn = 0
    try:
        while True:
            turn += 1
            _print(console,
                   f"[bold green]🎙  [{turn}] Speak now…[/bold green] "
                   "[dim](press Enter to stop)[/dim]")

            # --- STT: Prisma Realtime -------------------------------------
            stop_event = threading.Event()
            segments = []
            last_lang = [""]

            def _on_t(text, lang):
                # SDK sends cumulative rolling transcript — replace, don't append
                segments.clear()
                segments.append(text)
                last_lang[0] = lang or last_lang[0]
                _print(console,
                       f"\r  [yellow]{text}[/yellow]  ", end="")

            def _on_p():
                _print(console, "[dim]▌[/dim]", end="")

            def _wait_enter():
                try:
                    input()
                except Exception:
                    pass
                stop_event.set()

            et = threading.Thread(target=_wait_enter, daemon=True)
            et.start()

            try:
                from .stt_realtime import transcribe_live, RealtimeSTTError
                transcript = transcribe_live(
                    code_text=code,
                    on_transcript=_on_t,
                    on_processing=_on_p,
                    idle_timeout=4,
                    stop_event=stop_event,
                )
            except RealtimeSTTError as exc:
                _print(console, f"\n[red]STT error: {exc}[/red]")
                continue

            print()
            if not transcript.strip():
                _print(console, "[dim]  (no speech detected, try again)[/dim]\n")
                continue

            if last_lang[0]:
                _print(console, f"[dim]  detected: {last_lang[0]}[/dim]")

            # --- Reasoning ------------------------------------------------
            try:
                answer = llm.debug_answer(transcript, code, llm="auto")
            except Exception as exc:
                _print(console, f"[red]Reasoning error: {exc}[/red]\n")
                continue

            # --- Print answer panel ---------------------------------------
            _answer_panel(console, answer)

            # --- TTS: Timbre SSE, no file saved ---------------------------
            spoken = llm.speakable_text(answer)
            _print(console, "[cyan]🔊  Speaking…[/cyan]", end="")
            try:
                from .tts_stream import speak_ephemeral
                speak_ephemeral(spoken, voice=args.voice,
                                answer=answer, expressive=True)
            except Exception as exc:
                import tempfile, os as _os
                _print(console,
                       f" [dim](streaming unavailable: {exc}, using REST)[/dim]")
                try:
                    with tempfile.NamedTemporaryFile(suffix=".wav",
                                                    delete=False) as tmp:
                        tmp_path = tmp.name
                    tts.speak(spoken, tmp_path, voice=args.voice,
                              answer=answer, expressive=True)
                    _play_if_possible(Path(tmp_path), console)
                    _os.unlink(tmp_path)
                except Exception as e2:
                    _print(console, f"[red]TTS failed: {e2}[/red]")

            print()
            _print(console, "")

    except KeyboardInterrupt:
        _print(console, "\n\n[dim]Chat ended. Bye![/dim]")
        return 0


# ---------------------------------------------------------------------------
# watch  — real-time file-save watcher
# ---------------------------------------------------------------------------

def cmd_watch(args) -> int:
    """Watch a directory and speak bug warnings the moment a file is saved."""
    console = _get_console()

    if args.voice:
        try:
            stt.require_api_key()
        except MissingApiKeyError as exc:
            _print(console,
                   f"[bold red]Error:[/bold red] {exc} (--voice requires GNANI_API_KEY)")
            return 2

    _rule(console, "[bold green]DevSuno — watch[/bold green]")

    from .watcher import run_watch
    run_watch(
        watch_dir=args.dir,
        voice=args.voice,
        voice_name=args.voice_name,
        speak_clean=args.speak_clean,
    )
    return 0


# ---------------------------------------------------------------------------
# scan  — whole-directory static analysis with spoken summary
# ---------------------------------------------------------------------------

def cmd_scan(args) -> int:
    """Scan an entire directory for bugs and speak a prioritised report."""
    console = _get_console()

    from .local_debug import scan_directory, scan_summary_text

    root = Path(args.dir).resolve()
    if not root.is_dir():
        _print(console, f"[bold red]Error:[/bold red] Not a directory: {root}")
        return 2

    _rule(console, "[bold yellow]DevSuno — scan[/bold yellow]")
    _print(console,
           f"[dim]Scanning [cyan]{root}[/cyan] "
           f"(max {args.max_files} files)…[/dim]")

    # --- Scan ---------------------------------------------------------------
    with _spinner(console, "[yellow]Scanning files…[/yellow]"):
        findings = scan_directory(root, max_files=args.max_files)

    # --- Results table ------------------------------------------------------
    if not findings:
        _print(console,
               "\n[bold green]✓ Clean![/bold green] "
               "No issues found across all scanned files.")
    else:
        try:
            from rich.table import Table
            from rich.panel import Panel
            from rich.text import Text

            # Severity colour map
            _colours = {
                "hardcoded-secret":       "bold red",
                "bare-except":            "red",
                "python-none-guard":      "yellow",
                "unclosed-file":          "yellow",
                "mutable-default-arg":    "dim yellow",
                "off-by-one-bound":       "cyan",
                "off-by-one-next-element":"cyan",
            }

            table = Table(
                title=f"[bold yellow]{len(findings)} issue(s) found in "
                      f"{root.name}[/bold yellow]",
                show_header=True,
                header_style="bold white",
                border_style="yellow",
                show_lines=True,
            )
            table.add_column("#",         style="dim",        width=3)
            table.add_column("File",      style="cyan",       no_wrap=True)
            table.add_column("Check",     style="bold",       width=22)
            table.add_column("What is wrong", no_wrap=False,  min_width=30)

            for i, f in enumerate(findings, 1):
                colour = _colours.get(f["check"], "white")
                table.add_row(
                    str(i),
                    f["file"],
                    Text(f["check"], style=colour),
                    f["what_wrong"][:90] + ("…" if len(f["what_wrong"]) > 90 else ""),
                )
            console.print(table)
        except Exception:
            # Plain fallback
            for i, f in enumerate(findings, 1):
                print(f"[{i}] {f['file']:40} {f['check']:25} {f['what_wrong'][:60]}")

        # Detailed panel for the most critical finding
        worst = findings[0]
        _print(console, "")
        try:
            from rich.panel import Panel
            from rich.table import Table
            t = Table.grid(padding=(0, 1))
            t.add_column(style="bold red", no_wrap=True)
            t.add_column()
            t.add_row("Most critical", f"[cyan]{worst['file']}[/cyan]")
            t.add_row("Check", worst["check"])
            t.add_row("What is wrong", worst["what_wrong"])
            t.add_row("Fix", worst["fix"])
            if worst.get("corrected_line"):
                t.add_row("Corrected line", worst["corrected_line"])
            console.print(Panel(
                t,
                title="[bold red]Top Priority Fix[/bold red]",
                border_style="red",
            ))
        except Exception:
            print(f"Top fix: {worst['what_wrong']}")

    # --- Auto-fix top finding -----------------------------------------------
    if findings and (getattr(args, "fix", False) or getattr(args, "force_fix", False)):
        worst = findings[0]
        fix_path = root / worst["file"]
        if fix_path.exists():
            from .fixer import apply_fix
            _print(console, "\n[bold cyan]Auto-fix — top priority finding[/bold cyan]")
            confirm = not getattr(args, "force_fix", False)
            ok, msg = apply_fix(
                fix_path, worst,
                confirm=confirm,
                console=console,
            )
            if ok:
                _print(console, f"[bold green]✓[/bold green] {msg}")
            else:
                _print(console, f"[yellow]{msg}[/yellow]")

    # --- Spoken summary (Timbre TTS) ----------------------------------------
    if args.voice:
        try:
            stt.require_api_key()
        except MissingApiKeyError as exc:
            _print(console,
                   f"[bold red]Error:[/bold red] {exc} (--voice requires GNANI_API_KEY)")
            return 2

        summary_text = scan_summary_text(findings, root_name=root.name)
        _print(console,
               f"\n[cyan]🔊  Speaking scan summary…[/cyan]")

        # Build a fake answer dict so expression tags work
        answer = {
            "what_wrong": summary_text,
            "fix": "",
            "check": "hardcoded-secret" if findings and findings[0]["check"] == "hardcoded-secret" else (
                "success" if not findings else "bare-except"
            ),
            "backend": "local-fallback",
        }

        out_path = Path(args.out)
        _save_and_speak(
            answer, out_path, args.voice_name,
            play=args.play, console=console,
            expressive=True, stream_tts=False,
        )

    return 0 if not findings else 1   # exit 1 so CI pipelines can act on findings


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="devsuno",
        description=(
            "DevSuno — Audio-native terminal copilot. "
            "Speak bugs in Hinglish, get fixes spoken back. "
            "Powered by Gnani Prisma v3 STT + Timbre v3 TTS."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  devsuno chat --file main.py          # conversational mode\n"
            "  devsuno ask --audio q.wav --file main.py\n"
            "  devsuno ask --live --file main.py --stream-tts\n"
            "  devsuno ask --record --diff\n"
            "  devsuno review --live\n"
            "  devsuno review --audio review.wav\n"
            "  python app.py 2>&1 | devsuno trace --voice\n"
            "\nBackends (--llm):\n"
            "  auto    evon if EVON_API_URL is set, otherwise local  (default)\n"
            "  evon    requires EVON_API_URL (Gnani private endpoint)\n"
            "  local   rule-based static analyser, no API key needed\n"
        ),
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    _llm_choices = ["auto", "evon", "local"]

    # -- chat ----------------------------------------------------------------
    chat = sub.add_parser(
        "chat",
        help=(
            "Conversational mode — speak, hear the fix, speak again. "
            "No files saved. Ctrl+C to exit."
        ),
    )
    chat.add_argument("--file",
                      help="Code file to discuss (stays loaded all session).")
    chat.add_argument("--diff", action="store_true",
                      help="Use current git diff as context.")
    chat.add_argument("--voice", default=tts.DEFAULT_VOICE,
                      help=f"Timbre voice (default {tts.DEFAULT_VOICE}).")
    chat.set_defaults(func=cmd_chat)

    # -- ask -----------------------------------------------------------------
    ask = sub.add_parser("ask",
                         help="Ask a debugging question by voice.")
    ask.add_argument("--audio",
                     help="Recorded question file (WAV/MP3/FLAC, max 30s).")
    ask.add_argument("--text", default=None,
                     help="Type your question instead of speaking — skips Prisma STT. "
                          "Still calls Timbre TTS for the spoken answer. "
                          "Example: --text \"null check kyun miss ho gaya\"")
    ask.add_argument("--record", action="store_true",
                     help="Record from the microphone.")
    ask.add_argument("--seconds", type=float, default=8,
                     help="Seconds to record (default 8).")
    ask.add_argument("--record-out", default="out/question.wav",
                     dest="record_out")
    ask.add_argument("--file", help="Code file the question is about.")
    ask.add_argument("--diff", action="store_true",
                     help="Use current git diff as code context.")
    ask.add_argument("--llm", choices=_llm_choices, default="auto",
                     help="Reasoning backend (default auto).")
    ask.add_argument("--voice", default=tts.DEFAULT_VOICE,
                     help=f"Timbre voice (default {tts.DEFAULT_VOICE}, "
                          f"alt: {tts.ALT_VOICE}).")
    ask.add_argument("--out", default="out/answer.wav",
                     help="Spoken answer output path.")
    ask.add_argument("--live", action="store_true",
                     help="Prisma Realtime WebSocket STT: words appear as you speak. "
                          "Press Enter to stop. Requires sounddevice + numpy.")
    ask.add_argument("--stream-tts", action="store_true", dest="stream_tts",
                     help="Timbre SSE streaming: audio plays as chunks arrive.")
    ask.add_argument("--play", action="store_true",
                     help="Play the spoken answer after saving.")
    ask.add_argument("--fix", action="store_true",
                     help="Auto-write the fix to the source file. Shows a diff "
                          "and asks for confirmation before writing.")
    ask.add_argument("--force-fix", action="store_true", dest="force_fix",
                     help="Apply --fix without asking for confirmation.")
    ask.set_defaults(func=cmd_ask)

    # -- review --------------------------------------------------------------
    review = sub.add_parser("review",
                             help="Voice Git Diff reviewer.")
    review.add_argument("--audio",
                        help="Recorded review intent in Hinglish.")
    review.add_argument("--record", action="store_true",
                        help="Record review intent from microphone.")
    review.add_argument("--seconds", type=float, default=8)
    review.add_argument("--record-out", default="out/question.wav",
                        dest="record_out")
    review.add_argument("--diff-file", dest="diff_file",
                        help="Path to a saved diff. Omit to run git diff.")
    review.add_argument("--llm", choices=_llm_choices, default="auto",
                        help="Reasoning backend (default auto).")
    review.add_argument("--voice", default=tts.DEFAULT_VOICE)
    review.add_argument("--out", default="out/review.wav")
    review.add_argument("--live", action="store_true",
                        help="Prisma Realtime WebSocket STT for review intent.")
    review.add_argument("--stream-tts", action="store_true", dest="stream_tts",
                        help="Timbre SSE streaming TTS.")
    review.add_argument("--play", action="store_true")
    review.set_defaults(func=cmd_review)

    # -- trace ---------------------------------------------------------------
    trace = sub.add_parser(
        "trace",
        help=(
            "Audio Stack Trace Reader. "
            "Usage: python script.py 2>&1 | devsuno trace --voice"
        ),
    )
    trace.add_argument("--voice", action="store_true",
                       help="Speak the root-cause summary via Timbre TTS.")
    trace.add_argument("--trace-file", dest="trace_file",
                       help="Read traceback from file instead of stdin.")
    trace.add_argument("--voice-name", default=tts.DEFAULT_VOICE,
                       dest="voice_name",
                       help=f"Timbre voice (default {tts.DEFAULT_VOICE}).")
    trace.add_argument("--out", default="out/trace.wav")
    trace.add_argument("--play", action="store_true")
    trace.set_defaults(func=cmd_trace)

    # -- scan ----------------------------------------------------------------
    scan = sub.add_parser(
        "scan",
        help=(
            "Scan an entire directory for bugs. "
            "Produces a prioritised Rich table + optional spoken summary."
        ),
    )
    scan.add_argument(
        "--dir", default=".",
        help="Directory to scan (default: current directory).",
    )
    scan.add_argument(
        "--max-files", type=int, default=200, dest="max_files",
        help="Maximum files to scan (default 200).",
    )
    scan.add_argument(
        "--voice", action="store_true",
        help="Speak the scan summary via Timbre TTS after scanning.",
    )
    scan.add_argument(
        "--voice-name", default=tts.DEFAULT_VOICE, dest="voice_name",
        help=f"Timbre voice for --voice output (default {tts.DEFAULT_VOICE}).",
    )
    scan.add_argument(
        "--out", default="out/scan_summary.wav",
        help="Spoken summary output path.",
    )
    scan.add_argument(
        "--play", action="store_true",
        help="Play the spoken summary after saving.",
    )
    scan.add_argument(
        "--fix", action="store_true",
        help="Auto-fix the top-priority finding. Shows diff + asks confirmation.",
    )
    scan.add_argument(
        "--force-fix", action="store_true", dest="force_fix",
        help="Apply --fix without asking for confirmation.",
    )
    scan.set_defaults(func=cmd_scan)

    # -- watch ---------------------------------------------------------------
    watch = sub.add_parser(
        "watch",
        help=(
            "Watch a directory for file saves. Speaks a bug warning the "
            "moment a buggy save is detected. Ctrl+C to stop."
        ),
    )
    watch.add_argument(
        "--dir", default=".",
        help="Directory to watch (default: current directory).",
    )
    watch.add_argument(
        "--voice", action="store_true",
        help="Speak bug warnings via Timbre TTS on every buggy save.",
    )
    watch.add_argument(
        "--voice-name", default=tts.DEFAULT_VOICE, dest="voice_name",
        help=f"Timbre voice (default {tts.DEFAULT_VOICE}).",
    )
    watch.add_argument(
        "--speak-clean", action="store_true", dest="speak_clean",
        help="Also speak a 'clean' message when a saved file has no issues.",
    )
    watch.set_defaults(func=cmd_watch)

    return parser


def main(argv=None) -> int:
    from . import _print_banner
    _print_banner()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
