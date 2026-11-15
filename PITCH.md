# DevSuno — Voice-First Terminal Debugger for Indian Developers

**Bhoomi Prashanth Nayak · Solo Entry · Gnani Great Indian AI Internship Challenge**

---

## The Problem

Indian developers debug out loud in Hinglish.

> *"bro null check kyun miss ho gaya"*
> *"ye loop last element pe crash kyun kar raha hai"*
> *"is function mein exception silently swallow ho rahi hai kya"*

Every coding tool only takes typed English. Nobody built a debugger that speaks your language — until now.

---

## What DevSuno Does

DevSuno is a voice-first terminal copilot. You speak about your code in Hinglish. It finds the bug. It speaks the fix back.

```
You speak (Hinglish)
      ↓
Gnani Prisma v3.0 STT — indic-auto, codemix, 200 dynamic keyterms
      ↓
Static analyser — finds the bug in the code you pointed at
      ↓
Gnani Timbre v3.0 TTS — Avinash voice, hi-IN, expression tags
      ↓
Terminal panel + spoken answer
```

No browser. No chat window. Just your terminal, your voice, your language.

---

## Gnani APIs Used

| API | How |
|---|---|
| **Prisma v3.0 REST STT** | Transcribes Hinglish questions from recorded or mic audio |
| **Prisma v3.0 Realtime WebSocket STT** | `--live` flag — words appear on screen as the developer speaks |
| **Timbre v3.0 REST TTS** | Speaks the fix with Avinash voice in hi-IN (Hinglish) |
| **Timbre v3.0 SSE Streaming TTS** | Audio starts playing in ~300ms via `--stream-tts` and `chat` mode |
| **Timbre expression tags** | `<sigh>` on critical bugs, `<excited>` on clean code — dynamic emotion |
| **indic-auto language detection** | Handles Hindi, Kannada, English, any mix automatically |
| **keyterms boosting (200 terms)** | Function names, class names, git filenames extracted from workspace |
| **topic hint** | Contextual sentence sent with every STT request for jargon accuracy |

---

## 7 Commands

| Command | What it does |
|---|---|
| `devsuno chat` | Continuous voice conversation — speak, hear fix, speak again |
| `devsuno ask` | One question → one spoken answer (voice, mic, or `--text`) |
| `devsuno scan` | Audits an entire directory, speaks a prioritised bug report |
| `devsuno watch` | Watches for file saves, speaks a warning the moment a bug is introduced |
| `devsuno review` | Speak what to look for in your git diff, hear the issues |
| `devsuno trace` | Pipe a stack trace, hear the 2-sentence root cause in Hinglish |
| `devsuno ask --fix` | Finds the bug AND writes the corrected code back to the file |

---

## 7 Bug Patterns Detected

Hardcoded secrets · Silent bare except · Missing None guard ·
Unclosed file handles · Mutable default arguments · Off-by-one loops ·
Stack trace root cause extraction

---

## Web Demo

**Live:** deployed on Render — judges open the URL, pick a code snippet,
type a question in Hinglish, hear Timbre speak the fix. No install needed.

**Local:** `uvicorn server:app --port 8765` → `http://localhost:8765`

---

## Real-World Impact

Millions of Indian developers think in Hinglish and type in English.
DevSuno meets them in the language they actually use — in the terminal
where they actually work.

**GitHub:** https://github.com/BhoomiNayak/DevSuno

---

*Built entirely on Gnani Prisma v3.0 STT + Timbre v3.0 TTS.*
*Evon slot is built-in — set `EVON_API_URL` and it activates automatically.*
