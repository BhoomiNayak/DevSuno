"""Local static analyser + stack trace summariser.

Runs genuine static checks on code supplied by the user. Every answer
names the check that fired so the CLI can display it honestly. Never
claims to be an AI or Evon.

Checks implemented (Python unless noted):
  1. python-none-guard      parameter indexed/iterated with no None check
  2. off-by-one-bound       ``<= length`` / ``<= arr.length`` loop bound
  3. off-by-one-next-element range(len(x)) + x[i+1] read past end
  4. bare-except            ``except:`` or ``except Exception:`` with no re-raise
  5. hardcoded-secret       password / api_key / token assigned a string literal
  6. unclosed-file          open() called outside a ``with`` block
  7. mutable-default-arg    list/dict/set literal as a function default argument

Also exposes ``summarise_trace()`` for ``devsuno trace --voice``.
"""

from __future__ import annotations

import re


def _python_none_check(code: str, question: str) -> dict | None:
    """Find a function parameter that is indexed or iterated with no None guard."""
    funcs = re.finditer(
        r"def\s+(\w+)\s*\(([^)]*)\)\s*:", code
    )
    for match in funcs:
        params = [p.strip().split(":")[0].split("=")[0].strip()
                  for p in match.group(2).split(",") if p.strip()]
        params = [p for p in params if p and p not in ("self", "cls")]
        body = code[match.end():]
        # Only look at this function's body (stop at the next top-level def).
        nxt = re.search(r"\ndef\s+\w+\s*\(", body)
        if nxt:
            body = body[:nxt.start()]
        for param in params:
            uses = re.findall(rf"\b{re.escape(param)}\s*\[", body) or \
                re.findall(rf"for\s+\w+\s+in\s+{re.escape(param)}\b", body) or \
                re.findall(rf"len\(\s*{re.escape(param)}\s*\)", body)
            if not uses:
                continue
            guards = re.findall(
                rf"if\s+{re.escape(param)}\s+is\s+(not\s+)?None", body
            ) or re.findall(rf"if\s+{re.escape(param)}\s*:", body)
            if guards:
                continue
            return {
                "what_wrong": (
                    f"'{param}' is indexed or iterated but the function never "
                    f"checks whether '{param}' is None first. "
                    f"If the caller passes None, this crashes."
                ),
                "fix": (
                    f"Guard at the top of the function: "
                    f"`if {param} is None: return []` (or raise a clear error). "
                    f"Then use '{param}' safely."
                ),
                "corrected_line": f"if {param} is None:\n    return []",
                "check": "python-none-guard",
            }
    return None


def _off_by_one(code: str, _question: str = "") -> dict | None:
    """Find `<= length` / `<= len(...)` loop bounds."""
    match = re.search(
        r"for\s*\(\s*[^;]*;\s*\w+\s*<=\s*([\w.]+)\.length\s*;", code
    ) or re.search(
        r"for\s+\w+\s+in\s+range\(\s*0\s*,\s*len\((\w+)\)\s*\+\s*1\s*\)", code
    )
    if match:
        name = match.group(1)
        return {
            "what_wrong": (
                f"The loop runs while the index is <= {name}'s length, so on the "
                f"last iteration it reads one past the final element, which does "
                f"not exist."
            ),
            "fix": f"Use a strict less-than bound: `i < {name}.length` (or `range(len({name}))`).",
            "corrected_line": f"i < {name}.length",
            "check": "off-by-one-bound",
        }
    # range(len(x)) with x[i + 1] inside.
    if re.search(r"range\(\s*len\((\w+)\)\s*\)", code) and re.search(
        r"\w+\[\s*\w+\s*\+\s*1\s*\]", code
    ):
        name = re.search(r"range\(\s*len\((\w+)\)\s*\)", code).group(1)
        return {
            "what_wrong": (
                f"The loop goes up to index len({name}) - 1, but the body reads "
                f"{name}[i + 1], which is out of bounds on the last iteration."
            ),
            "fix": f"Loop to `range(len({name}) - 1)` when you read the next element.",
            "corrected_line": f"range(len({name}) - 1)",
            "check": "off-by-one-next-element",
        }
    return None


def _bare_except(code: str, _question: str = "") -> dict | None:
    """Find a bare ``except:`` or ``except Exception:`` block with no re-raise.

    A catch-all that swallows every exception silently is one of the most
    common sources of hard-to-debug production bugs — errors disappear with
    no log, no message, and no crash to investigate.
    """
    # Match bare except: or except Exception [as e]:
    for m in re.finditer(
        r"except\s*(?:Exception\s*(?:as\s+\w+)?\s*)?:", code
    ):
        # Look at the except block body (next ~5 lines)
        block_start = m.end()
        block_text = code[block_start:block_start + 400]
        # Strip leading newline/indent
        lines = block_text.splitlines()
        body_lines = [l for l in lines[1:8] if l.strip()]

        # If the block re-raises or logs, it is intentional — skip it
        body = " ".join(body_lines).lower()
        intentional = any(kw in body for kw in (
            "raise", "logging", "logger", "log.", "traceback",
            "sys.exit", "print(", "sentry", "rollbar",
        ))
        if intentional:
            continue

        # Grab the offending except line for context
        except_line = code[m.start(): m.end()].strip()
        return {
            "what_wrong": (
                f"Found `{except_line}` that silently swallows every exception. "
                "If anything goes wrong inside this try block, the error "
                "disappears with no log and no crash — impossible to debug later."
            ),
            "fix": (
                "Either catch the specific exception you expect "
                "(e.g. `except ValueError:`), or add `raise` at the end of the "
                "block to re-raise, or at minimum log the error: "
                "`except Exception as e: logging.exception(e)`."
            ),
            "corrected_line": "except ValueError:  # catch only what you expect",
            "check": "bare-except",
        }
    return None


# Patterns that look like hardcoded secrets — variable name + string value.
# Covers common names; rejects obvious placeholder strings.
_SECRET_VAR_RE = re.compile(
    r"""(?xi)
    (?:^|\b)
    (?P<var>
        password | passwd | pwd | secret | api[_\-]?key | apikey |
        auth[_\-]?token | token | access[_\-]?key | private[_\-]?key |
        db[_\-]?pass(?:word)? | database[_\-]?password |
        aws[_\-]?secret | stripe[_\-]?key | sendgrid[_\-]?key
    )
    \s*=\s*
    (?P<quote>["\'])(?P<value>.{4,80})(?P=quote)
    """,
    re.IGNORECASE | re.MULTILINE,
)
# Values that are obviously placeholders — not real secrets
_PLACEHOLDER_RE = re.compile(
    r"(?i)^(your[-_]|<|PASTE|CHANGE|TODO|FIXME|xxx|test|example|placeholder|dummy|fake|replace)",
)


def _hardcoded_secret(code: str, _question: str = "") -> dict | None:
    """Find a password, API key, or token assigned as a string literal."""
    for m in _SECRET_VAR_RE.finditer(code):
        value = m.group("value")
        if _PLACEHOLDER_RE.match(value):
            continue
        # Skip very short values (likely test/debug values like "x" or "1")
        if len(value) < 6:
            continue
        var = m.group("var")
        masked = value[:4] + "*" * max(0, len(value) - 4)
        return {
            "what_wrong": (
                f"'{var}' is assigned a hardcoded string value "
                f"(`{masked}`) directly in source code. "
                "Anyone with access to this file — or the git history — "
                "can read this credential."
            ),
            "fix": (
                f"Move the value to an environment variable and read it at runtime: "
                f"`{var} = os.getenv('{var.upper()}')`. "
                "Add the real value to `.env` (never commit `.env`)."
            ),
            "corrected_line": f"{var} = os.getenv('{var.upper()}')",
            "check": "hardcoded-secret",
        }
    return None


def _unclosed_file(code: str, _question: str = "") -> dict | None:
    """Find ``open()`` calls that are not inside a ``with`` block.

    ``f = open(...)`` without ``with`` leaks the file descriptor if an
    exception is raised between open and close, or if the developer
    simply forgets to call ``.close()``.
    """
    for m in re.finditer(r"(\w+)\s*=\s*open\s*\(", code):
        var = m.group(1)
        # Walk backwards a few lines to check if this is inside a `with`
        preceding = code[max(0, m.start() - 200): m.start()]
        # Also check the line itself
        line_start = code.rfind("\n", 0, m.start()) + 1
        line = code[line_start: code.find("\n", m.start())].strip()

        # If the assignment is itself inside a `with open(` block, skip
        if "with open" in line or "with open" in preceding.splitlines()[-3:]:
            continue
        # If the line is `with ... as ...:`, skip
        if line.startswith("with "):
            continue

        return {
            "what_wrong": (
                f"`{var} = open(...)` opens a file without a `with` statement. "
                "If an exception is raised before `.close()`, the file handle "
                "leaks and the file may never be flushed or properly closed."
            ),
            "fix": (
                f"Use a context manager: `with open(...) as {var}:` — "
                "it closes the file automatically even if an exception occurs."
            ),
            "corrected_line": f"with open(...) as {var}:",
            "check": "unclosed-file",
        }
    return None


def _mutable_default_arg(code: str, _question: str = "") -> dict | None:
    """Find a list, dict, or set literal used as a function default argument.

    Python evaluates default arguments once at function definition time,
    not on each call. A mutable default is shared across all calls that
    don't pass the argument, so mutations persist between calls.
    """
    # Match: def foo(x, items=[], config={}, seen=set()):
    for func_m in re.finditer(r"def\s+(\w+)\s*\(([^)]*)\)[^:]*:", code, re.DOTALL):
        params_str = func_m.group(2)
        func_name = func_m.group(1)
        # Find parameters with mutable defaults
        for param_m in re.finditer(
            r"(\w+)\s*=\s*(\[\s*\]|\{\s*\}|set\s*\(\s*\))", params_str
        ):
            param = param_m.group(1)
            default = param_m.group(2).strip()
            default_type = (
                "list" if default.startswith("[")
                else "dict" if default.startswith("{")
                else "set"
            )
            none_default = "[]" if default_type == "list" else "{}" if default_type == "dict" else "set()"
            return {
                "what_wrong": (
                    f"`{func_name}` uses `{param}={default}` as a default argument. "
                    f"This {default_type} is created once and shared across every call "
                    "that doesn't pass a value — mutations in one call affect all future calls."
                ),
                "fix": (
                    f"Use `None` as the default and create a new {default_type} inside: "
                    f"`def {func_name}(..., {param}=None)` then "
                    f"`if {param} is None: {param} = {none_default}`."
                ),
                "corrected_line": f"def {func_name}(..., {param}=None):",
                "check": "mutable-default-arg",
            }
    return None


def analyse(question: str, code: str) -> dict:
    """Run all static checks in priority order. Returns the first match.

    Always reports which check fired via the ``backend`` and ``check`` keys
    so the CLI can display it honestly.

    Check order (most critical first):
      1. hardcoded-secret      — security, highest severity
      2. bare-except           — silent error swallowing
      3. python-none-guard     — crash on None input
      4. unclosed-file         — resource leak
      5. mutable-default-arg   — subtle state bug
      6. off-by-one-bound      — index out of range
    """
    for check_fn in (
        _hardcoded_secret,
        _bare_except,
        _python_none_check,
        _unclosed_file,
        _mutable_default_arg,
        _off_by_one,
    ):
        result = check_fn(code, question)
        if result:
            result["backend"] = "local-fallback"
            return result

    return {
        "what_wrong": (
            "No specific bug pattern matched the checks I ran "
            "(hardcoded secret, bare except, missing None guard, "
            "unclosed file, mutable default argument, off-by-one loop). "
            "The question was understood, but I cannot pinpoint the bug "
            "from this code alone."
        ),
        "fix": (
            "Add a small reproduction: print the inputs right before the "
            "failing line, then check the exact line and value in the traceback."
        ),
        "corrected_line": "",
        "check": "no-pattern-matched",
        "backend": "local-fallback",
    }

# ---------------------------------------------------------------------------
# Stack trace summariser  (used by ``devsuno trace --voice``)
# ---------------------------------------------------------------------------

# Library / framework path fragments treated as "noise" — not the user's bug.
_NOISE_PATHS = (
    "site-packages", "dist-packages",
    "lib/python", "lib\\python",
    "/usr/lib", "\\Python3",
    "importlib", "_bootstrap",
    "runpy.py", "threading.py", "asyncio",
    "uvicorn", "starlette", "fastapi",
    "django", "flask", "werkzeug",
    "sqlalchemy", "celery",
)

# Short Hinglish-friendly hints per exception type
_EXCEPTION_HINTS: dict[str, str] = {
    "TypeError": "wrong type diya gaya hai",
    "ValueError": "invalid value pass hui hai",
    "KeyError": "dict mein key exist nahi karti",
    "IndexError": "list ya array out of bounds hai",
    "AttributeError": "object mein ye attribute nahi hai",
    "NameError": "variable define nahi kiya gaya",
    "ImportError": "module import nahi hua",
    "ModuleNotFoundError": "module install nahi hai ya path galat hai",
    "FileNotFoundError": "file exist nahi karti",
    "ZeroDivisionError": "zero se divide kiya ja raha hai",
    "RecursionError": "infinite recursion ho rahi hai",
    "RuntimeError": "runtime pe unexpected error aaya",
    "NotImplementedError": "ye method implement nahi hua abhi",
    "PermissionError": "permission denied hai",
    "TimeoutError": "operation timeout ho gaya",
    "ConnectionError": "network connection fail hua",
    "MemoryError": "memory khatam ho gayi",
    "OverflowError": "number bohot bada ho gaya",
    "StopIteration": "iterator khatam ho gaya",
    "AssertionError": "assertion fail hua",
}


def _is_noise_frame(line: str) -> bool:
    """Return True if this traceback frame line is a library/framework frame."""
    return any(p in line for p in _NOISE_PATHS)


def _extract_exception_line(raw: str) -> tuple[str, str]:
    """Return (exception_type, message) from the last line of the traceback."""
    lines = [l.rstrip() for l in raw.splitlines() if l.strip()]
    for line in reversed(lines):
        m = re.match(r"^([A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Warning|Interrupt))\s*:(.*)", line)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        # bare exception with no colon (e.g. "KeyboardInterrupt")
        m2 = re.match(r"^([A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Warning|Interrupt))\s*$", line)
        if m2:
            return m2.group(1).strip(), ""
    return "Exception", ""


def _user_frames(raw: str) -> list[tuple[str, str, str]]:
    """Return list of (file, lineno, context_line) for user-code frames only."""
    frames: list[tuple[str, str, str]] = []
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'\s*File "(.+?)", line (\d+)', line)
        if m:
            filepath, lineno = m.group(1), m.group(2)
            context = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if not _is_noise_frame(filepath):
                frames.append((filepath, lineno, context))
        i += 1
    return frames


def summarise_trace(raw_trace: str) -> dict:
    """Parse a Python traceback and return a short spoken summary dict.

    Parameters
    ----------
    raw_trace:
        The full traceback string read from stdin / stderr.

    Returns
    -------
    dict with keys:
        ``what_wrong``   — one sentence root cause
        ``fix``          — one sentence actionable suggestion
        ``location``     — "file.py line N" of the innermost user frame
        ``exception``    — exception class name
        ``backend``      — always "local-trace"
    """
    if not raw_trace.strip():
        return {
            "what_wrong": "Koi traceback nahi mila stdin mein.",
            "fix": "Script ke output ko pipe karo: python script.py 2>&1 | devsuno trace --voice",
            "location": "",
            "exception": "",
            "backend": "local-trace",
        }

    exc_type, exc_msg = _extract_exception_line(raw_trace)
    user_frames = _user_frames(raw_trace)

    # Innermost user-code frame is the most useful location
    root_frame = user_frames[-1] if user_frames else ("", "", "")
    filepath, lineno, context_line = root_frame
    location = f"{filepath} line {lineno}" if filepath else "unknown location"

    # Build what_wrong sentence
    hint = _EXCEPTION_HINTS.get(exc_type, "unexpected error aaya")
    if exc_msg:
        what_wrong = (
            f"{exc_type} aaya hai: {hint}. "
            f"Error message hai: \"{exc_msg[:120]}\". "
            f"Root cause {location} pe hai."
        )
    else:
        what_wrong = (
            f"{exc_type} aaya hai: {hint}. "
            f"Root cause {location} pe hai."
        )

    if context_line:
        what_wrong += f" Problematic line: `{context_line[:80]}`."

    # Build fix sentence from exception type
    fix_map = {
        "TypeError": f"Check karo ki sahi type pass ho raha hai at {location}.",
        "ValueError": f"Input values validate karo before passing to this function.",
        "KeyError": f"dict.get() use karo instead of direct indexing, ya pehle key existence check karo.",
        "IndexError": f"Array bounds check karo — list length se pehle index access karo.",
        "AttributeError": f"Object type print karke confirm karo ki ye attribute exist karta hai.",
        "NameError": f"Variable '{exc_msg}' ko define karo ya import karo before use.",
        "ImportError": f"pip install se missing package install karo ya PYTHONPATH check karo.",
        "ModuleNotFoundError": f"pip install se missing package install karo ya spelling check karo.",
        "FileNotFoundError": f"File path double-check karo — relative path current directory se hai.",
        "ZeroDivisionError": f"Divisor ko zero se pehle check karo: `if divisor != 0` guard lagao.",
        "RecursionError": f"Base case add karo ya recursion depth check karo sys.setrecursionlimit().",
        "RuntimeError": f"Stack trace carefully padho — usually ek inner exception hoti hai.",
        "AssertionError": f"Assert statement ki condition check karo jo fail hui hai.",
    }
    fix = fix_map.get(exc_type, f"{location} pe code dobara check karo aur inputs print karke verify karo.")

    return {
        "what_wrong": what_wrong,
        "fix": fix,
        "location": location,
        "exception": exc_type,
        "backend": "local-trace",
    }
