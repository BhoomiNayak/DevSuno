# Terminal Voice-Pair

## The complete project brief

**One line:** A voice-first debugging copilot that lives in the terminal. You speak a bug in Hinglish, it speaks the fix back.

**Built for:** The Great Indian AI Internship Challenge (Gnani AI) — submission closes Tuesday 10 November 2026, 11:59pm IST.

**Built by:** Bhoomi Prashanth Nayak (solo entry).

---

## 1. The problem

Developers already debug out loud. In India that thinking-out-loud is
Hinglish: "bro check karo is array me null check kyun miss ho gaya",
"ye loop kabhi khatam kyun nahi ho raha". But every coding assistant
only takes typed English. There is no way to talk to your code the way
you already talk about it, in the language you actually think in, without
leaving the terminal.

## 2. The idea

Terminal Voice-Pair brings voice into the developer's own workflow.
No chat window, no web form. One command in the terminal:

1. You speak a debugging question naturally, in Hinglish or code-mixed
   English ("bro check karo is array me null check kyun miss ho gaya").
2. The tool shows the transcript, looks at the code you pointed it at,
   and works out what is wrong.
3. The fix comes back twice: as text in the terminal, and spoken aloud.

## 3. How it works

```
you speak (Hinglish)
    |
    v
Prisma STT  — transcribes code-mixed speech (prisma-v3.0, indic-auto, codemix)
    |
    v
transcript + your code (a file, or git diff)
    |
    v
Reasoning  — finds the bug and writes the fix
    |
    v
Timbre TTS — speaks the fix (timbre-v2.5, hi-IN, voice Pranav)
    |
    v
terminal text + out/answer.wav
```

**Prisma STT** (`gnani-vachana` SDK) is built for Indian languages and
code-mixed speech: English technical words stay in Latin script, and the
transcript keeps the Hinglish shape of the question. Audio is limited to
30 seconds per request, which fits a debugging question.

**Timbre TTS** (`timbre-v2.5`, language `hi-IN`, voice `Pranav`) speaks
the fix back in natural Hinglish, so the answer is heard, not just read.

## 4. The reasoning layer — an honest note

This is the part to be straight about. **Evon v3.3 is not on the Gnani
API platform as of 10 November 2026.** Gnani lists Evon as a closed beta
(waitlist, first 1,000 builders from 12 October 2026) with open weights
on Hugging Face by request only, `docs.gnani.ai` lists no LLM endpoint,
and the `gnani-vachana` SDK ships only STT and TTS clients. There is no
documented Evon endpoint a programme API key can call today.

So the reasoning step has two backends, and the CLI always prints which
one answered:

- **local (default):** a small rule-based advisor that runs real static
  checks on the supplied code — a missing None guard, an off-by-one
  loop bound (`i <= arr.length`), an index running past the end — and
  says exactly which checks it ran. The demo pipeline runs end to end
  with real Prisma and Timbre calls and this labelled fallback.
- **evon:** used only if `EVON_API_URL` is set, i.e. Gnani has granted
  Evon API access. It posts an OpenAI-compatible chat-completions
  request to that URL with the API key, and a 404/401 fails loudly with
  "Evon API access may not be granted".

The demo never presents a local answer as Evon's.

## 5. What is inside the project

```
Terminal-Voice-Pair/
  voicepair/
    cli.py          - the terminal command: voicepair ask
    stt.py          - Prisma STT (gnani-vachana)
    tts.py          - Timbre TTS (gnani-vachana)
    llm.py          - reasoning router: evon if granted, else local
    local_debug.py  - labelled static checks (None guard, off-by-one)
    record.py       - mic recording (optional; needs a mic)
  examples/
    null_check.py   - Python: list used with no None check
    off_by_one.js   - JavaScript: loop runs one step too far
    README.md       - suggested Hinglish questions for each example
  requirements.txt  - gnani-vachana, requests, python-dotenv (+ mic extras)
  test_api.py       - live pipeline test, stage by stage
  .env.example      - copy to .env, paste one API key
  README.md         - install + run instructions
```

All demo code is synthetic. No real personal data anywhere.

## 6. The demo (60 seconds)

| Time | What happens | What you see and hear |
|------|--------------|-----------------------|
| 0–10s | The buggy file is on screen. Bhoomi speaks: "bro check karo is array me null check kyun miss ho gaya" | Terminal, voice question |
| 10–20s | Prisma transcribes the Hinglish question | Transcript appears in the terminal |
| 20–40s | Reasoning finds the missing None guard and writes the fix | The fix in text: what is wrong, the exact change, one corrected line |
| 40–60s | Timbre speaks the fix back | Spoken answer, saved to out/answer.wav |

The whole demo runs on real Gnani API calls for speech in and speech
out, with the reasoning backend labelled on screen.

## 7. Why this fits the challenge

- **Hinglish and code-mixed voice:** the core of the product. The
  question is spoken in Hinglish, the transcript keeps the code-mix,
  and the spoken answer comes back in Hinglish.
- **Creativity and best solo project:** voice debugging inside the
  terminal, where developers actually work, instead of another chatbot.
- **Best 60-second demo:** one terminal, one buggy file, one spoken
  question, one spoken fix. Nothing to explain that the demo does not
  show by itself.
- **Real-world impact:** millions of Indian developers think in
  Hinglish and type in English. Meeting them in their own language
  lowers the barrier to getting help with their code.

## 8. How to run it

```bash
# 1. Unzip, create a virtual environment, install
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Add your API key (the only edit needed)
cp .env.example .env
# open .env, replace PASTE_YOUR_GNANI_API_KEY_HERE with your key
# from https://app.gnani.ai/voice/api-keys

# 3. Record a question on your phone (8 seconds is plenty),
#    save it as question.wav in the project folder

# 4. Run it — missing None check
python -m voicepair ask --audio question.wav --file examples/null_check.py

# 5. Or the off-by-one loop
python -m voicepair ask --audio question.wav --file examples/off_by_one.js

# 6. Or point it at your own git diff
python -m voicepair ask --audio question.wav --diff

# 7. Test the pipeline stage by stage
python test_api.py --audio question.wav --file examples/null_check.py
```

Output: the transcript, the fix in text, the reasoning backend that
answered, and the spoken answer saved to `out/answer.wav`.

## 9. What is verified, and what is not yet

**Verified (10 Nov 2026):**

- The CLI runs: `voicepair --help` and `voicepair ask --help` work.
- The key flow works: with no key it exits with a clear message; with
  a key in `.env` it picks the key up and passes every local check.
- The local reasoning is correct on both examples: the missing None
  guard is found in `null_check.py`, the off-by-one bound is found in
  `off_by_one.js`.
- A missing audio file fails cleanly with a clear error, not a crash.
- No real Gnani API calls have been made yet — no key has been supplied.

**Not yet verified:**

- The live end-to-end run: a real recorded Hinglish question through
  Prisma STT, reasoning, and Timbre TTS, with a real key. That is the
  last technical step, and it happens on Bhoomi's machine with her key.
- The 60-second demo recording itself.

## 10. Limits, stated plainly

- Prisma caps audio at 30 seconds per request; a debugging question
  fits, a long explanation does not.
- Mic recording (`--record`) needs a microphone and the PortAudio
  library; recording on a phone and passing `--audio` is the reliable
  route.
- The local reasoning fallback only catches the check families it
  implements (None guard, off-by-one, index past the end). It is a
  labelled fallback, not a general debugger, and the CLI says so.
- Evon is not callable with the programme key today (see section 4).
  If Gnani grants Evon access, set `EVON_API_URL` and the Evon backend
  takes over.

## 11. Submission checklist (for Bhoomi)

- [ ] API key created at app.gnani.ai and pasted into `.env`
- [ ] Live test run with a real recorded question (`python test_api.py --audio ...`)
- [ ] 60-second demo recorded (real voice, real API calls)
- [ ] Demo posted on LinkedIn / X in the afternoon with #GnaniAI and
      #GreatIndianAIInternshipChallenge
- [ ] Submission sent by 11:59pm IST on 10 Nov 2026, with the video, a
      short write-up, and the post link
