"""Workspace context extractor.

Builds dynamic keyterms for Prisma STT from the actual workspace so
that project-specific identifiers (function names, class names, variable
names, imported module names, git-tracked filenames) are recognised
correctly instead of being mangled by a generic speech model.

Why this matters: Prisma is Hinglish-aware, but it still guesses on
unknown technical tokens. If your code has ``FastAPI``, ``PostgreSQL``,
``process_scores``, or ``sumAll``, passing those as keyterms steers the
transcript towards the correct spelling so the reasoning layer gets
clean input.

The extractor is intentionally lightweight (pure-stdlib regex + git):
no AST import, no third-party deps, no crashes if a file is binary or
the directory is not a git repo.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# --- Base vocabulary always boosted (dev jargon common in Hinglish) ----
BASE_KEYTERMS: list[str] = [
    # Python builtins & common patterns
    "null", "None", "True", "False", "async", "await",
    "try", "except", "raise", "return", "yield",
    # Common bug vocabulary
    "null pointer", "off by one", "index error", "type error",
    "undefined", "traceback", "stack trace", "exception",
    # API / framework names likely to appear
    "FastAPI", "Django", "Flask", "SQLAlchemy", "PostgreSQL", "Redis",
    "JWT", "OAuth", "async def", "await",
    # Git workflow words
    "commit", "diff", "PR", "pull request", "merge", "branch",
    "refactor", "revert",
    # Code review / debugging words common in Hinglish
    "bug", "fix", "issue", "crash", "leak", "injection",
    "array", "list", "dict", "loop", "function", "class",
]

# Tokens to filter out — too short or too generic to help
_MIN_TERM_LEN = 3
_STOP_WORDS = {
    "and", "the", "for", "in", "is", "it", "to", "of",
    "not", "or", "if", "def", "var", "let", "new",
    "true", "false", "null", "this", "self", "cls",
}

# Regex patterns that pick up identifiers from source code
_IDENTIFIER_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")

# Patterns to pull specific Python / JS constructs
_PY_DEF_RE = re.compile(r"(?:def|class)\s+([A-Za-z_]\w+)")
_PY_IMPORT_RE = re.compile(r"(?:import|from)\s+([A-Za-z_][\w.]+)")
_JS_FUNC_RE = re.compile(r"(?:function|const|let|var)\s+([A-Za-z_]\w+)")


def _extract_identifiers(source: str) -> set[str]:
    """Return meaningful identifiers found in source text."""
    tokens: set[str] = set()
    for pat in (_PY_DEF_RE, _PY_IMPORT_RE, _JS_FUNC_RE):
        for m in pat.finditer(source):
            tokens.add(m.group(1))
    for m in _IDENTIFIER_RE.finditer(source):
        tokens.add(m.group(1))
    return tokens


def _git_filenames(cwd: Path) -> list[str]:
    """Return basenames (without extension) of files tracked by git."""
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True,
            cwd=str(cwd), timeout=10,
        )
        if out.returncode != 0:
            return []
        names = []
        for line in out.stdout.splitlines():
            stem = Path(line.strip()).stem
            if len(stem) >= _MIN_TERM_LEN:
                names.append(stem)
        return names
    except Exception:
        return []


def _filter(tokens: set[str]) -> list[str]:
    """Strip stop-words, short tokens, and duplicates; return sorted list."""
    seen: set[str] = set()
    result: list[str] = []
    for t in sorted(tokens):
        lower = t.lower()
        if lower in _STOP_WORDS:
            continue
        if len(t) < _MIN_TERM_LEN:
            continue
        if lower in seen:
            continue
        seen.add(lower)
        result.append(t)
    return result


def build_keyterms(
    code_text: str | None = None,
    extra_files: list[Path] | None = None,
    cwd: Path | None = None,
) -> list[str]:
    """Build the keyterm list to pass to Prisma STT.

    Parameters
    ----------
    code_text:
        Source code the user is asking about (the content of ``--file``
        or the git diff). Identifiers are extracted from this.
    extra_files:
        Additional source files to scan (e.g. neighbouring modules).
        Skipped if unreadable or binary.
    cwd:
        Working directory for ``git ls-files``. Defaults to ``Path.cwd()``.

    Returns
    -------
    list[str]
        Merged, deduplicated keyterms: base vocabulary + workspace
        identifiers + git filenames, capped at 100 items (Prisma limit).
    """
    tokens: set[str] = set()

    # Workspace identifiers from the target file / diff
    if code_text:
        tokens.update(_extract_identifiers(code_text))

    # Identifiers from additional nearby files
    for path in (extra_files or []):
        try:
            tokens.update(_extract_identifiers(path.read_text(errors="replace")))
        except Exception:
            pass

    # Git-tracked filenames (so e.g. "auth_service" is recognised)
    tokens.update(_git_filenames(cwd or Path.cwd()))

    # Merge base vocab + workspace tokens, deduplicate, sort
    all_terms = BASE_KEYTERMS[:]
    for t in _filter(tokens):
        if t not in all_terms:
            all_terms.append(t)

    # Prisma accepts up to 100 keyterms; always keep the base set first
    return all_terms[:100]
