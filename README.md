# DevSuno — Voice-First Terminal Debugger for Indian Developers

> **Speak your bug in Hinglish. Hear the fix.**

Built for the **Gnani Great Indian AI Internship Challenge** by **Bhoomi Prashanth Nayak** (solo entry).

---

## The Problem

Indian developers debug out loud in Hinglish.

> *"bro null check kyun miss ho gaya"*
> *"ye loop last element pe crash kyun kar raha hai"*
> *"is function mein exception silently swallow ho rahi hai kya"*

Every coding tool only takes typed English. Nobody built a debugger that speaks your language — until now.

---

## What DevSuno Does

DevSuno is a voice-first terminal copilot. You speak about your code in Hinglish. It finds the bug. It speaks the fix back — with emotion.

```
You speak (Hinglish / Kannada / English — any mix)
        ↓
Gnani Prisma v3.0 STT
  indic-auto  ·  codemix format  ·  200 dynamic workspace keyterms
        ↓
Static analyser finds the bug in the code you pointed at
        ↓
Gnani Timbre v3.0 TTS
  Avinash voice  ·  hi-IN  ·  <sigh> on crashes  ·  <excited> on fixes
        ↓
Terminal panel + spoken answer
```

No browser. No chat window. Just your terminal, your voice, your language.

---

## Live Web Demo

Try it without installing anything — judges open the URL, pick a code snippet, type a question in Hinglish, hear Timbre speak the fix.

```bash
# Run locally
uvicorn server:app --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765
```

Deploy free to Render in 5 minutes using the included `render.yaml`.

---

## Gnani APIs Used

| API | How |
|---|---|
| **Prisma v3.0 REST STT** | Transcribes Hinglish questions from recorded or mic audio |
| **Prisma v3.0 Realtime WebSocket STT** | `--live` flag — words appear on screen as the developer speaks |
| **Timbre v3.0 REST TTS** | Speaks the fix with Avinash voice in `hi-IN` (Hinglish) |
| **Timbre v3.0 SSE Streaming TTS** | Audio starts playing in ~300ms via `--stream-tts` and `chat` mode |
| **Timbre expression tags** | `<sigh>` on critical bugs, `<excited>` on clean code |
| **indic-auto language detection** | Handles Hindi, Kannada, English, any mix automatically |
| **keyterms boosting (200 terms)** | Function names, class names, git filenames extracted from workspace |
| **topic hint** | Contextual sentence sent with every STT request for jargon accuracy |

---

## 7 Commands

```bash
# Continuous voice conversation — speak, hear fix, speak again
devsuno chat --file your_code.py

# One question, one spoken answer (voice, mic, or typed)
devsuno ask --record --seconds 8 --file your_code.py --play
devsuno ask --live --file your_code.py --stream-tts
devsuno ask --text "null check kyun miss ho gaya" --file main.py --play

# Find the bug AND write the fix into the file
devsuno ask --text "password hardcode ho gaya" --file auth.py --fix

# Scan entire directory — spoken audit report
devsuno scan --dir src/ --voice --play

# Watch for file saves — speaks the moment a bug is introduced
devsuno watch --dir src/ --voice

# Speak what to look for in uncommitted git changes
devsuno review --audio review.wav

# Pipe a crash — hear the root cause in Hinglish
python your_script.py 2>&1 | devsuno trace --voice --play
```

---

## 7 Bug Patterns Detected

| Check | What it catches |
|---|---|
| `hardcoded-secret` | Passwords, API keys, JWT tokens as string literals — finds ALL in one scan |
| `bare-except` | `except:` that swallows every error silently |
| `python-none-guard` | Parameter indexed or iterated with no None check |
| `unclosed-file` | `open()` called outside a `with` block |
| `mutable-default-arg` | `def foo(items=[])` — shared state across calls |
| `off-by-one-bound` | `i <= arr.length` reads one past the last element |
| `local-trace` | Stack trace root cause, library/framework frames stripped |

---

## Auto-Fix (`--fix`)

DevSuno writes the corrected code back to your file. Shows a colour diff, asks confirmation, backs up the original.

```diff
# Before
DATABASE_PASSWORD = "Sup3rS3cur3Passw0rd!"
JWT_SECRET        = "jwt-signing-key-2026"

# After  (devsuno ask --fix)
import os
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")
JWT_SECRET        = os.getenv("JWT_SECRET")
```

---

## Setup

**Requirements:** Python 3.10+, a free Gnani API key from [app.gnani.ai/voice/api-keys](https://app.gnani.ai/voice/api-keys)

```bash
git clone https://github.com/BhoomiNayak/DevSuno.git
cd DevSuno

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -r requirements.txt
pip install -e .

cp .env.example .env
# open .env and paste your GNANI_API_KEY
```

**Verify (no audio, zero API calls):**
```bash
python test_api.py
```

---

## Example Files

| File | Bug | Hinglish question |
|---|---|---|
| `examples/null_check.py` | Missing None guard | *"bro check karo is array me null check kyun miss ho gaya"* |
| `examples/off_by_one.js` | `i <= arr.length` | *"ye loop last element pe kyun undefined de raha hai"* |
| `examples/bare_except.py` | Silent `except:` | *"bro ye function kabhi error nahi deta lekin result galat aata hai"* |
| `examples/hardcoded_secret.py` | Hardcoded credentials | *"bro is code mein password hardcode toh nahi kar diya"* |
| `examples/unclosed_file.py` | File handle leak | *"bro ye file operations sahi se close ho rahi hain ya leak hai"* |
| `examples/mutable_default.py` | `def foo(cart=[])` | *"bro purana data kyun aa raha hai list khali honi chahiye thi"* |

---

## Project Structure

```
DevSuno/
├── voicepair/
│   ├── cli.py            7 subcommands + Rich terminal UI
│   ├── stt.py            Prisma v3.0 REST STT
│   ├── stt_realtime.py   Prisma v3.0 WebSocket STT  (--live)
│   ├── tts.py            Timbre v3.0 REST TTS + expression tags
│   ├── tts_stream.py     Timbre v3.0 SSE streaming TTS
│   ├── llm.py            Reasoning router (Evon when available, else local)
│   ├── local_debug.py    7 bug pattern checks + trace summariser
│   ├── fixer.py          Auto-write fixes to source files
│   ├── watcher.py        File-save watcher (watchdog)
│   ├── context.py        Dynamic workspace keyterm extractor
│   ├── record.py         Mic recording with ASCII waveform
│   └── __init__.py       Version + startup banner
├── examples/             6 buggy files with Hinglish questions
├── server.py             Web demo server (FastAPI)
├── render.yaml           One-click Render deployment
├── test_api.py           Pipeline test (no audio required)
├── pyproject.toml        Package config
├── requirements.txt
├── .env.example          Copy to .env, add GNANI_API_KEY
└── PITCH.md              One-page solution pitch
```

---

## Deploy Web Demo (free, 5 min)

1. Go to [render.com](https://render.com) → New Web Service
2. Connect `BhoomiNayak/DevSuno`
3. Render auto-detects `render.yaml`
4. Add env var: `GNANI_API_KEY` = your key
5. Deploy → public URL ready

---

## On the Reasoning Layer

The local static analyser runs real checks and finds real bugs in the 7 patterns above.

**Evon** (Gnani's own 30B model) is open-weight on Hugging Face and not on the public API platform as of November 2026. The slot is built — set `EVON_API_URL` in `.env` and Evon activates automatically with no other change.

---

## Real-World Impact

Millions of Indian developers think in Hinglish and type in English. DevSuno meets them in the language they actually use — in the terminal where they actually work.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built entirely on Gnani Prisma v3.0 STT + Gnani Timbre v3.0 TTS.*
*Because Indian developers deserve tools that speak their language.*
