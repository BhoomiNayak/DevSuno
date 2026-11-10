"""Terminal Voice-Pair: a voice-first, Hinglish code-switched debugging copilot.

Speak a debugging question in Hinglish, get a short structured fix back,
in text and spoken aloud. Built on Gnani's Prisma (STT) and Timbre (TTS)
speech APIs. The reasoning step uses Evon when Gnani API access to Evon
exists, and a labelled local fallback otherwise (see voicepair/llm.py).
"""

__version__ = "0.1.0"

# Suppress verbose INFO/DEBUG logs from the gnani-vachana SDK so they
# don't pollute the terminal UI during live STT and TTS operations.
import logging as _logging
_logging.getLogger("gnani").setLevel(_logging.WARNING)


def _print_banner() -> None:
    """Print the DevSuno startup banner. Called once from main()."""
    try:
        from rich.console import Console
        from rich.text import Text
        from rich.panel import Panel

        console = Console()
        banner = Text()
        banner.append("  ██████╗ ███████╗██╗   ██╗███████╗██╗   ██╗███╗   ██╗ ██████╗ \n", style="bold cyan")
        banner.append("  ██╔══██╗██╔════╝██║   ██║██╔════╝██║   ██║████╗  ██║██╔═══██╗\n", style="bold cyan")
        banner.append("  ██║  ██║█████╗  ██║   ██║███████╗██║   ██║██╔██╗ ██║██║   ██║\n", style="cyan")
        banner.append("  ██║  ██║██╔══╝  ╚██╗ ██╔╝╚════██║██║   ██║██║╚██╗██║██║   ██║\n", style="cyan")
        banner.append("  ██████╔╝███████╗ ╚████╔╝ ███████║╚██████╔╝██║ ╚████║╚██████╔╝\n", style="bold cyan")
        banner.append("  ╚═════╝ ╚══════╝  ╚═══╝  ╚══════╝ ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ \n", style="bold cyan")
        banner.append("\n")
        banner.append("  🎙  Speak bugs in Hinglish. ", style="bold white")
        banner.append("Gnani Prisma v3 STT", style="bold yellow")
        banner.append(" + ", style="dim")
        banner.append("Timbre v3 TTS", style="bold yellow")
        banner.append("\n")
        banner.append(f"  v{__version__}  |  ", style="dim")
        banner.append("chat  ask  review  trace", style="bold green")
        banner.append("  |  Ctrl+C to exit\n", style="dim")

        console.print(Panel(banner, border_style="cyan", padding=(0, 1)))
    except Exception:
        # Rich not available — plain fallback
        print(f"DevSuno v{__version__} — Speak bugs in Hinglish, hear the fix.")
        print("Commands: chat  ask  review  trace\n")

# Load GNANI_API_KEY (and optional EVON_API_URL) from a .env file in the
# project folder, so the key can be pasted into .env instead of exported.
# Silently ignored if python-dotenv is not installed.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass
