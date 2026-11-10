# DevSuno — Audio-Native Terminal Copilot

> **Speak your bug in Hinglish. Hear the fix.**

DevSuno is a voice-first debugging copilot that lives in your terminal. Indian developers already debug out loud — *"bro null check kyun miss ho gaya"*, *"ye loop last element pe crash kyun kar raha hai"* — but every coding tool only takes typed English. DevSuno meets you in the language you actually think in.

Built for the **Gnani Great Indian AI Internship Challenge** by **Bhoomi Prashanth Nayak**.

---

## Demo

```
╭──────────────────────────────────────────────────────────────────────╮
│  ██████╗ ███████╗██╗   ██╗███████╗██╗   ██╗███╗   ██╗ ██████╗       │
│  ██╔══██╗██╔════╝██║   ██║██╔════╝██║   ██║████╗  ██║██╔═══██╗      │
│  ██║  ██║█████╗  ██║   ██║███████╗██║   ██║██╔██╗ ██║██║   ██║      │
│  ██║  ██║██╔══╝  ╚██╗ ██╔╝╚════██║██║   ██║██║╚██╗██║██║   ██║      │
│  ██████╔╝███████╗ ╚████╔╝ ███████║╚██████╔╝██║ ╚████║╚██████╔╝      │
│                                                                      │
│  🎙  Speak bugs in Hinglish. Gnani Prisma v3 STT + Timbre v3 TTS    │
│  v0.1.0  |  chat  ask  review  trace  |  Ctrl+C to exit             │
╰──────────────────────────────────────────────────────────────────────╯
```

---

## What It Does

You speak a debugging question naturally in Hinglish. DevSuno:

1. **Hears you** — Gnani Prisma v3.0 STT transcribes your Hinglish speech with `indic-auto` language detection and `codemix` output format
2. **Finds the bug** — a static analyser reads the code you pointed at and identifies the issue
3. **Speaks the fix** — Gnani Timbre v3.0 TTS speaks the answer back with expressive audio tags (`<sigh>` on crashes, `<excited>` on clean fixes)

No browser. No chat window. Just your terminal, your voice, your language.

---

## Architecture

```
┌─────────────────────────┐
│  Developer speaks       │
│  (Hinglish / Kannada /  │
│   English — any mix)    │
└────────────┬────────────┘
             │  mic audio (PCM)
             ▼
┌─────────────────────────┐
│  Gnani Prisma v3.0 STT  │
│  • indic-auto detection │
│  • codemix format       │
│  • 200 workspace        │
│    keyterms boosted     │
│  • REST or Realtime WS  │
└────────────┬────────────┘
             │  transcript (Hinglish)
             ▼
┌─────────────────────────┐
│  Local Static Analyser  │
│  • hardcoded secret     │
│  • bare except          │
│  • missing None guard   │
│  • unclosed file        │
│  • mutable default arg  │
│  • off-by-one loop      │
│  • stack trace reader   │
└────────────┬────────────┘
             │  structured answer
             ▼
┌─────────────────────────┐
│  Gnani Timbre v3.0 TTS  │
│  • Avinash voice        │
│  • hi-IN language       │
│  • expression tags      │
│    <sigh> / <excited>   │
│  • REST or SSE stream   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Terminal output        │
│  + spoken answer        │
│  (Rich panel + audio)   │
└─────────────────────────┘
```

---

## Features

| Feature | Description |
|---|---|
| **Hinglish STT** | Prisma v3.0 with `indic-auto` — handles Hindi, Kannada, English, and any mix |
| **Dynamic keyterms** | Extracts function names, class names, git filenames from your workspace and boosts them in Prisma |
| **Expressive TTS** | Timbre v3.0 expression tags: `<sigh>` on critical bugs, `<excited>` on successful fixes |
| **Realtime STT** | `--live` flag: words appear as you speak via Prisma WebSocket |
| **SSE streaming TTS** | Audio starts playing ~300ms after synthesis begins |
| **Conversational chat** | `devsuno chat` — continuous loop, no files saved, pure voice conversation |
| **6 bug patterns** | Hardcoded secrets, bare except, None guard, unclosed file, mutable default, off-by-one |
| **Stack trace reader** | `devsuno trace` — pipe stderr, hear the root cause in Hinglish |
| **Git diff review** | `devsuno review` — speak what to look for, hear issues in uncommitted changes |
| **Rich terminal UI** | Syntax-highlighted panels, spinners, answer cards |

---

## Commands

```bash
# Conversational mode — speak, hear fix, speak again. No files saved.
devsuno chat --file your_code.py

# One question about a file
devsuno ask --audio question.wav --file your_code.py --play

# Live realtime STT (words appear as you speak)
devsuno ask --live --file your_code.py --stream-tts

# Record from mic
devsuno ask --record --seconds 8 --file your_code.py --play

# Review uncommitted changes by voice
devsuno review --audio review.wav

# Pipe a crash and hear the root cause
python your_script.py 2>&1 | devsuno trace --voice --play
```

---

## Tech Stack

| Component | Technology |
|---|---|
| **Speech-to-Text** | Gnani Prisma v3.0 — `indic-auto`, `codemix`, keyterms, topic hint |
| **Text-to-Speech** | Gnani Timbre v3.0 — Avinash voice, `hi-IN`, audio expression tags |
| **Realtime STT** | `GnaniSTTStreamClient` WebSocket — live per-utterance transcripts |
| **Streaming TTS** | `GnaniTTSStreamClient` SSE — chunked audio playback |
| **SDK** | `gnani-vachana >= 0.9.0` |
| **Terminal UI** | `rich >= 13.0` — panels, spinners, syntax highlighting |
| **Audio I/O** | `sounddevice`, `soundfile`, `numpy` |
| **Language** | Python 3.10+ |

---

## Bug Patterns Detected

| Check | What it catches | Example |
|---|---|---|
| `hardcoded-secret` | passwords, API keys, tokens as string literals | `API_KEY = "sk-live-..."` |
| `bare-except` | `except:` that swallows every error silently | `except: return None` |
| `python-none-guard` | parameter indexed with no None check | `scores[0]` without `if scores is None` |
| `unclosed-file` | `open()` outside a `with` block | `f = open(path)` |
| `mutable-default-arg` | list/dict/set as default argument | `def foo(items=[])` |
| `off-by-one-bound` | `<= length` loop bound | `i <= arr.length` |
| `local-trace` | stack trace root cause, library noise stripped | any Python traceback |

---

## Setup

### Requirements

- Python 3.10+
- A Gnani API key — create one free at [app.gnani.ai/voice/api-keys](https://app.gnani.ai/voice/api-keys)
- Microphone (for `--record` and `--live` modes)

### Install

```bash
# Clone the repo
git clone https://github.com/<your-username>/devsuno.git
cd devsuno

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install the devsuno command
pip install -e .
```

### Configure

```bash
cp .env.example .env
```

Open `.env` and replace `PASTE_YOUR_GNANI_API_KEY_HERE` with your key:

```
GNANI_API_KEY=your_key_here
```

That's the only change needed. The key covers both Prisma STT and Timbre TTS.

### Verify

```bash
# Check everything works (no API calls)
python test_api.py

# Full pipeline test with a recorded audio file
python test_api.py --audio question.wav --file examples/null_check.py
```

---

## Example Files

Six buggy snippets — one per check family:

| File | Bug | Suggested Hinglish question |
|---|---|---|
| `examples/null_check.py` | Missing None guard on `scores` | *"bro check karo is array me null check kyun miss ho gaya"* |
| `examples/off_by_one.js` | `i <= arr.length` loop | *"ye loop last element pe kyun undefined de raha hai"* |
| `examples/bare_except.py` | Silent `except:` swallows errors | *"bro ye function kabhi error nahi deta lekin result galat aata hai"* |
| `examples/hardcoded_secret.py` | `DATABASE_PASSWORD = "..."` | *"bro is code mein password hardcode toh nahi kar diya"* |
| `examples/unclosed_file.py` | `f = open(...)` without `with` | *"bro ye file operations sahi se close ho rahi hain ya leak hai"* |
| `examples/mutable_default.py` | `def foo(cart=[])` | *"bro purana data kyun aa raha hai list khali honi chahiye thi"* |

---

## Project Structure

```
devsuno/
├── voicepair/
│   ├── cli.py           # CLI — chat, ask, review, trace subcommands + Rich UI
│   ├── stt.py           # Prisma v3.0 REST STT wrapper
│   ├── stt_realtime.py  # Prisma v3.0 Realtime WebSocket STT
│   ├── tts.py           # Timbre v3.0 REST TTS wrapper + expression tag injection
│   ├── tts_stream.py    # Timbre v3.0 SSE streaming TTS
│   ├── llm.py           # Reasoning router (Evon if available, else local)
│   ├── local_debug.py   # Static analyser + stack trace summariser
│   ├── context.py       # Dynamic workspace keyterm extractor
│   ├── record.py        # Mic recording with ASCII waveform (Rich)
│   └── __init__.py      # Version + startup banner
├── examples/
│   ├── null_check.py
│   ├── off_by_one.js
│   ├── bare_except.py
│   ├── hardcoded_secret.py
│   ├── unclosed_file.py
│   ├── mutable_default.py
│   └── README.md        # Suggested Hinglish questions for each example
├── test_api.py          # Pipeline test (stage by stage, no audio required)
├── pyproject.toml       # Package config — installs devsuno + voicepair commands
├── requirements.txt
├── .env.example         # Copy to .env, add your Gnani API key
└── .gitignore           # .env and out/ are gitignored
```

---

## A Note on the Reasoning Layer

The local static analyser is not a placeholder — it runs real checks and finds real bugs. The demo is built around the 6 patterns above.

**Evon** (Gnani's own 30B reasoning model) is not on the public API platform as of November 2026 — it's open-weight on Hugging Face and available via private endpoint only. The slot is built: set `EVON_API_URL` in `.env` and Evon takes over automatically with no other change.

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Built with ❤️ for the Gnani Great Indian AI Internship Challenge.*
*Gnani Prisma v3 STT + Timbre v3 TTS — because Indian developers deserve tools that speak their language.*
