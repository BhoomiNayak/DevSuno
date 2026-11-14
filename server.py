"""DevSuno web demo server.

Single FastAPI app that powers the web demo page.
No install needed for the judge — they open the URL, type a question,
pick a code snippet, click Get Fix, hear Timbre speak the answer.

Endpoints
---------
GET  /              Serves the demo HTML page
POST /api/fix       { question, code } → { answer, audio_b64 }
GET  /api/examples  → list of built-in example snippets

Deploy free on Render:
  - Build command : pip install -r requirements.txt
  - Start command : uvicorn server:app --host 0.0.0.0 --port $PORT
  - Env vars      : GNANI_API_KEY
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from pathlib import Path

logging.getLogger("gnani").setLevel(logging.WARNING)

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Add voicepair package to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from voicepair.local_debug import analyse
from voicepair.llm import speakable_text
from voicepair.tts import speak, inject_expression_tag, DEFAULT_VOICE

app = FastAPI(title="DevSuno Demo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class FixRequest(BaseModel):
    question: str
    code: str
    voice: str = DEFAULT_VOICE


class FixResponse(BaseModel):
    what_wrong: str
    fix: str
    corrected_line: str
    check: str
    backend: str
    audio_b64: str      # base64-encoded WAV — played directly in browser
    tagged_text: str    # what Timbre actually spoke (with expression tags)


# ---------------------------------------------------------------------------
# Built-in examples
# ---------------------------------------------------------------------------

_EXAMPLES = [
    {
        "id": "null_check",
        "label": "Missing None check (Python)",
        "question": "bro check karo is array me null check kyun miss ho gaya",
        "code": open(
            Path(__file__).parent / "examples/null_check.py",
            encoding="utf-8"
        ).read(),
    },
    {
        "id": "bare_except",
        "label": "Silent exception swallowing (Python)",
        "question": "bro ye function kabhi error nahi deta lekin result galat aata hai kya exception silently swallow ho rahi hai",
        "code": open(
            Path(__file__).parent / "examples/bare_except.py",
            encoding="utf-8"
        ).read(),
    },
    {
        "id": "hardcoded_secret",
        "label": "Hardcoded API key / password (Python)",
        "question": "bro is code mein password aur API key hardcode kar diya hai security issue hai kya",
        "code": open(
            Path(__file__).parent / "examples/hardcoded_secret.py",
            encoding="utf-8"
        ).read(),
    },
    {
        "id": "off_by_one",
        "label": "Off-by-one loop (JavaScript)",
        "question": "ye loop last element pe kyun undefined de raha hai",
        "code": open(
            Path(__file__).parent / "examples/off_by_one.js",
            encoding="utf-8"
        ).read(),
    },
    {
        "id": "unclosed_file",
        "label": "Unclosed file handle (Python)",
        "question": "bro ye file operations sahi se close ho rahi hain ya koi resource leak hai",
        "code": open(
            Path(__file__).parent / "examples/unclosed_file.py",
            encoding="utf-8"
        ).read(),
    },
    {
        "id": "mutable_default",
        "label": "Mutable default argument (Python)",
        "question": "bro purana data kyun aa raha hai list khali honi chahiye thi",
        "code": open(
            Path(__file__).parent / "examples/mutable_default.py",
            encoding="utf-8"
        ).read(),
    },
]


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/examples")
def get_examples():
    return [{"id": e["id"], "label": e["label"],
             "question": e["question"]} for e in _EXAMPLES]


@app.get("/api/example/{example_id}")
def get_example(example_id: str):
    for e in _EXAMPLES:
        if e["id"] == example_id:
            return e
    raise HTTPException(status_code=404, detail="Example not found")


@app.post("/api/fix", response_model=FixResponse)
def get_fix(req: FixRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")

    key = os.getenv("GNANI_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="GNANI_API_KEY not configured on this server"
        )

    # --- Analyse ---
    result = analyse(req.question, req.code[:4000])

    # --- TTS ---
    spoken = speakable_text(result)
    tagged = inject_expression_tag(spoken, result)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name

    try:
        speak(
            spoken,
            output_file=tmp_path,
            voice=req.voice,
            answer=result,
            expressive=True,
        )
        audio_bytes = Path(tmp_path).read_bytes()
        audio_b64 = base64.b64encode(audio_bytes).decode()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS failed: {exc}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return FixResponse(
        what_wrong=result.get("what_wrong", ""),
        fix=result.get("fix", ""),
        corrected_line=result.get("corrected_line", ""),
        check=result.get("check", ""),
        backend=result.get("backend", ""),
        audio_b64=audio_b64,
        tagged_text=tagged,
    )


# ---------------------------------------------------------------------------
# Demo HTML page
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def demo_page():
    return HTMLResponse(content=_HTML)


_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DevSuno — Voice Debugger for Indian Developers</title>
<style>
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --accent: #58a6ff;
    --green: #3fb950;
    --red: #f85149;
    --yellow: #d29922;
    --text: #e6edf3;
    --dim: #8b949e;
    --cyan: #39c5cf;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', system-ui, sans-serif;
    min-height: 100vh;
    padding: 2rem 1rem;
  }

  .container { max-width: 860px; margin: 0 auto; }

  /* Header */
  .header { text-align: center; margin-bottom: 2.5rem; }
  .logo {
    font-family: monospace;
    font-size: 1.1rem;
    color: var(--cyan);
    white-space: pre;
    line-height: 1.2;
    display: inline-block;
    margin-bottom: 1rem;
  }
  .tagline { color: var(--dim); font-size: 1.05rem; margin-bottom: 0.4rem; }
  .badges { display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; margin-top: 0.75rem; }
  .badge {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 0.2rem 0.75rem;
    font-size: 0.78rem;
    color: var(--dim);
  }
  .badge.gnani { border-color: var(--cyan); color: var(--cyan); }

  /* Card */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.25rem;
  }
  .card-title {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--dim);
    margin-bottom: 0.75rem;
  }

  /* Example selector */
  .example-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 0.6rem;
  }
  .example-btn {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    color: var(--text);
    font-size: 0.85rem;
    cursor: pointer;
    text-align: left;
    transition: border-color 0.15s, background 0.15s;
  }
  .example-btn:hover { border-color: var(--accent); background: #1c2230; }
  .example-btn.active { border-color: var(--cyan); background: #0d2137; color: var(--cyan); }

  /* Question input */
  .question-row { display: flex; gap: 0.75rem; align-items: flex-start; }
  .question-input {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    color: var(--text);
    font-size: 0.95rem;
    resize: vertical;
    min-height: 60px;
    font-family: inherit;
    transition: border-color 0.15s;
  }
  .question-input:focus { outline: none; border-color: var(--accent); }
  .question-input::placeholder { color: var(--dim); }

  /* Code area */
  .code-area {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    color: #a8b3cf;
    font-family: 'Cascadia Code', 'Fira Code', monospace;
    font-size: 0.82rem;
    width: 100%;
    min-height: 160px;
    resize: vertical;
    transition: border-color 0.15s;
  }
  .code-area:focus { outline: none; border-color: var(--accent); }

  /* Button */
  .btn {
    background: var(--accent);
    color: #0d1117;
    border: none;
    border-radius: 8px;
    padding: 0.75rem 1.75rem;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.1s;
    white-space: nowrap;
  }
  .btn:hover { opacity: 0.9; }
  .btn:active { transform: scale(0.97); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-row { display: flex; gap: 0.75rem; align-items: center; margin-top: 0.75rem; }

  /* Voice selector */
  .voice-select {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    color: var(--text);
    font-size: 0.85rem;
    cursor: pointer;
  }

  /* Spinner */
  .spinner {
    display: none;
    width: 20px; height: 20px;
    border: 2px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner.active { display: inline-block; }

  /* Answer panel */
  .answer-panel {
    display: none;
    border-left: 3px solid var(--green);
    padding-left: 1rem;
  }
  .answer-panel.visible { display: block; }
  .answer-panel.critical { border-left-color: var(--red); }

  .answer-row { margin-bottom: 0.75rem; }
  .answer-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--dim);
    margin-bottom: 0.2rem;
  }
  .answer-value { font-size: 0.95rem; line-height: 1.5; }
  .answer-code {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    font-family: monospace;
    font-size: 0.85rem;
    color: var(--cyan);
    white-space: pre-wrap;
  }
  .check-badge {
    display: inline-block;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 0.1rem 0.6rem;
    font-size: 0.75rem;
    color: var(--yellow);
    margin-top: 0.5rem;
  }
  .check-badge.critical { border-color: var(--red); color: var(--red); }

  /* Audio player */
  .audio-row {
    display: none;
    align-items: center;
    gap: 0.75rem;
    margin-top: 0.75rem;
  }
  .audio-row.visible { display: flex; }
  .play-btn {
    background: var(--green);
    color: #0d1117;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1.25rem;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
  }
  .play-btn:hover { opacity: 0.85; }
  .audio-label { color: var(--dim); font-size: 0.82rem; }

  /* Error */
  .error-box {
    display: none;
    background: #2d0f0f;
    border: 1px solid var(--red);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    color: var(--red);
    font-size: 0.88rem;
    margin-top: 0.75rem;
  }
  .error-box.visible { display: block; }

  /* How it works */
  .pipeline {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    color: var(--dim);
    font-size: 0.85rem;
    margin-top: 2rem;
  }
  .pipe-step {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.4rem 0.8rem;
    color: var(--text);
  }
  .pipe-step.gnani { border-color: var(--cyan); color: var(--cyan); }
  .pipe-arrow { color: var(--dim); }

  /* Footer */
  .footer {
    text-align: center;
    color: var(--dim);
    font-size: 0.8rem;
    margin-top: 2.5rem;
  }
  .footer a { color: var(--accent); text-decoration: none; }
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="logo">██████╗ ███████╗██╗   ██╗███████╗██╗   ██╗███╗   ██╗ ██████╗
██╔══██╗██╔════╝██║   ██║██╔════╝██║   ██║████╗  ██║██╔═══██╗
██║  ██║█████╗  ██║   ██║███████╗██║   ██║██╔██╗ ██║██║   ██║
██║  ██║██╔══╝  ╚██╗ ██╔╝╚════██║██║   ██║██║╚██╗██║██║   ██║
██████╔╝███████╗ ╚████╔╝ ███████║╚██████╔╝██║ ╚████║╚██████╔╝</div>
    <p class="tagline">🎙 Voice-first terminal debugger for Indian developers</p>
    <p style="color:var(--dim);font-size:0.88rem;">Type your bug description in Hinglish → hear the fix spoken back</p>
    <div class="badges">
      <span class="badge gnani">Gnani Prisma v3 STT</span>
      <span class="badge gnani">Gnani Timbre v3 TTS</span>
      <span class="badge">Hinglish + Kannada + English</span>
      <span class="badge">indic-auto detection</span>
    </div>
  </div>

  <!-- Step 1: Pick example -->
  <div class="card">
    <div class="card-title">Step 1 — Pick a buggy code snippet</div>
    <div class="example-grid" id="exampleGrid">
      <div style="color:var(--dim);font-size:0.85rem;">Loading examples…</div>
    </div>
  </div>

  <!-- Step 2: Question -->
  <div class="card">
    <div class="card-title">Step 2 — Describe the bug in Hinglish (or English)</div>
    <textarea
      class="question-input"
      id="questionInput"
      placeholder="bro check karo is array me null check kyun miss ho gaya…"
      rows="2"
    ></textarea>
  </div>

  <!-- Step 3: Code -->
  <div class="card">
    <div class="card-title">Step 3 — Code (auto-filled when you pick an example, or paste your own)</div>
    <textarea class="code-area" id="codeInput" placeholder="Paste your code here…"></textarea>
  </div>

  <!-- Get fix -->
  <div class="card">
    <div class="card-title">Step 4 — Get the fix</div>
    <div class="btn-row">
      <button class="btn" id="fixBtn" onclick="getFix()">🔍 Get Fix</button>
      <label style="color:var(--dim);font-size:0.85rem;">Voice:</label>
      <select class="voice-select" id="voiceSelect">
        <option value="Avinash">Avinash (male)</option>
        <option value="Shivani">Shivani (female)</option>
        <option value="Lakshmi">Lakshmi</option>
        <option value="Prakash">Prakash</option>
      </select>
      <div class="spinner" id="spinner"></div>
    </div>

    <div class="error-box" id="errorBox"></div>

    <!-- Answer -->
    <div class="answer-panel" id="answerPanel" style="margin-top:1.25rem;">
      <div class="answer-row">
        <div class="answer-label">What is wrong</div>
        <div class="answer-value" id="answerWhatWrong"></div>
      </div>
      <div class="answer-row">
        <div class="answer-label">The fix</div>
        <div class="answer-value" id="answerFix"></div>
      </div>
      <div class="answer-row" id="correctedRow">
        <div class="answer-label">Corrected line</div>
        <div class="answer-code" id="answerCorrected"></div>
      </div>
      <div>
        <span class="check-badge" id="checkBadge"></span>
        <span class="check-badge" style="border-color:var(--dim);color:var(--dim);margin-left:0.4rem;" id="backendBadge"></span>
      </div>

      <!-- Audio -->
      <div class="audio-row" id="audioRow">
        <button class="play-btn" id="playBtn" onclick="playAudio()">▶ Play spoken answer</button>
        <span class="audio-label" id="audioLabel"></span>
      </div>
    </div>
  </div>

  <!-- Pipeline -->
  <div class="pipeline">
    <span class="pipe-step">Your question (Hinglish)</span>
    <span class="pipe-arrow">→</span>
    <span class="pipe-step gnani">Gnani Prisma v3 STT</span>
    <span class="pipe-arrow">→</span>
    <span class="pipe-step">Static analyser</span>
    <span class="pipe-arrow">→</span>
    <span class="pipe-step gnani">Gnani Timbre v3 TTS</span>
    <span class="pipe-arrow">→</span>
    <span class="pipe-step">Spoken fix</span>
  </div>

  <div class="footer" style="margin-top:1.5rem;">
    Built for the <strong>Gnani Great Indian AI Internship Challenge</strong> by Bhoomi Prashanth Nayak &nbsp;·&nbsp;
    <a href="https://github.com/BhoomiNayak/DevSuno" target="_blank">GitHub</a>
  </div>

</div>

<script>
  let currentAudioB64 = null;
  let currentAudio = null;

  // Load examples on page load
  async function loadExamples() {
    try {
      const res = await fetch('/api/examples');
      const examples = await res.json();
      const grid = document.getElementById('exampleGrid');
      grid.innerHTML = '';
      examples.forEach(ex => {
        const btn = document.createElement('button');
        btn.className = 'example-btn';
        btn.textContent = ex.label;
        btn.onclick = () => selectExample(ex.id, btn);
        grid.appendChild(btn);
      });
    } catch (e) {
      document.getElementById('exampleGrid').innerHTML =
        '<span style="color:var(--dim)">Could not load examples.</span>';
    }
  }

  async function selectExample(id, btn) {
    // Mark active
    document.querySelectorAll('.example-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    // Fetch full example
    try {
      const res = await fetch(`/api/example/${id}`);
      const ex = await res.json();
      document.getElementById('questionInput').value = ex.question;
      document.getElementById('codeInput').value = ex.code;
    } catch (e) {}
  }

  async function getFix() {
    const question = document.getElementById('questionInput').value.trim();
    const code = document.getElementById('codeInput').value.trim();
    const voice = document.getElementById('voiceSelect').value;

    if (!question) {
      showError('Please enter a question.');
      return;
    }
    if (!code) {
      showError('Please paste some code or pick an example.');
      return;
    }

    // UI state
    setLoading(true);
    hideError();
    hideAnswer();

    try {
      const res = await fetch('/api/fix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, code, voice }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      showAnswer(data);

    } catch (e) {
      showError(e.message || 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  function showAnswer(data) {
    document.getElementById('answerWhatWrong').textContent = data.what_wrong;
    document.getElementById('answerFix').textContent = data.fix;

    const corrRow = document.getElementById('correctedRow');
    if (data.corrected_line) {
      document.getElementById('answerCorrected').textContent = data.corrected_line;
      corrRow.style.display = 'block';
    } else {
      corrRow.style.display = 'none';
    }

    const checkBadge = document.getElementById('checkBadge');
    checkBadge.textContent = data.check;
    checkBadge.className = 'check-badge' + (
      ['hardcoded-secret','bare-except'].includes(data.check) ? ' critical' : ''
    );

    document.getElementById('backendBadge').textContent = data.backend;

    // Audio
    currentAudioB64 = data.audio_b64;
    const audioRow = document.getElementById('audioRow');
    audioRow.classList.add('visible');
    document.getElementById('audioLabel').textContent =
      `Timbre v3 · ${document.getElementById('voiceSelect').value} voice`;

    const panel = document.getElementById('answerPanel');
    panel.classList.add('visible');
    panel.className = 'answer-panel visible' + (
      ['hardcoded-secret','bare-except'].includes(data.check) ? ' critical' : ''
    );

    // Auto-play
    playAudio();
  }

  function playAudio() {
    if (!currentAudioB64) return;
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    const wavBytes = Uint8Array.from(atob(currentAudioB64), c => c.charCodeAt(0));
    const blob = new Blob([wavBytes], { type: 'audio/wav' });
    const url = URL.createObjectURL(blob);
    currentAudio = new Audio(url);
    currentAudio.play();
    document.getElementById('playBtn').textContent = '⏸ Playing…';
    currentAudio.onended = () => {
      document.getElementById('playBtn').textContent = '▶ Play spoken answer';
    };
  }

  function hideAnswer() {
    document.getElementById('answerPanel').classList.remove('visible');
    document.getElementById('audioRow').classList.remove('visible');
    currentAudioB64 = null;
  }

  function setLoading(on) {
    document.getElementById('fixBtn').disabled = on;
    document.getElementById('spinner').classList.toggle('active', on);
  }

  function showError(msg) {
    const box = document.getElementById('errorBox');
    box.textContent = msg;
    box.classList.add('visible');
  }

  function hideError() {
    document.getElementById('errorBox').classList.remove('visible');
  }

  // Enter key on question submits
  document.addEventListener('DOMContentLoaded', () => {
    loadExamples();
    document.getElementById('questionInput').addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); getFix(); }
    });
  });
</script>
</body>
</html>
"""
