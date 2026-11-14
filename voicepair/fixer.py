"""Auto-fixer for DevSuno — writes corrected lines back to source files.

For each check type the fixer knows the exact transformation needed.
Where it can make a safe, targeted replacement it does so. Where the
fix requires human judgement (e.g. which specific exception to catch)
it shows a diff and asks for confirmation.

Fix strategies per check
-------------------------
hardcoded-secret       Replace  ``VAR = "value"``  with  ``VAR = os.getenv("VAR")``
                       Also prepends  ``import os``  if not already present.
                       Can fix ALL secrets in the file, not just the first.

python-none-guard      Insert  ``if param is None: return []``  as the first
                       line of the function body.

off-by-one-bound       Replace  ``<= arr.length``  with  ``< arr.length``
                       (JS) or  ``range(len(x)+1)``  with  ``range(len(x))``.

bare-except            Replace  ``except:``  or  ``except Exception:``
                       with  ``except Exception as e:``  + adds
                       ``logging.exception(e)``  if logging is imported,
                       else a ``# TODO: handle or re-raise``  comment.
                       Conservative — never silently drops the handler.

unclosed-file          Replace  ``f = open(...)``  with  ``with open(...) as f:``
                       and indents the following block. This is the most
                       complex transformation — previews diff and asks
                       for confirmation.

mutable-default-arg    Replace  ``def foo(x, items=[])``  with
                       ``def foo(x, items=None)``  and inserts the
                       ``if items is None: items = []``  guard as first
                       line of the function body.

Safe-write guarantee
--------------------
The original file is backed up to  ``<file>.devsuno.bak``  before any
write. The backup is deleted automatically on success. If anything goes
wrong, the original is restored from the backup.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_fix(
    filepath: str | Path,
    result: dict,
    confirm: bool = True,
    console=None,
) -> tuple[bool, str]:
    """Apply the fix for ``result`` to ``filepath``.

    Parameters
    ----------
    filepath:
        Source file to fix.
    result:
        Answer dict from ``local_debug.analyse()``.
    confirm:
        If True, show a diff and ask the user to confirm before writing.
        If False, write directly (useful for --force flag).
    console:
        Rich Console for coloured output.

    Returns
    -------
    (success: bool, message: str)
    """
    path = Path(filepath)
    if not path.exists():
        return False, f"File not found: {filepath}"

    check = result.get("check", "")
    original = path.read_text(encoding="utf-8", errors="replace")

    # Dispatch to the right fixer
    _fixers = {
        "hardcoded-secret":       _fix_hardcoded_secret,
        "python-none-guard":      _fix_none_guard,
        "off-by-one-bound":       _fix_off_by_one,
        "off-by-one-next-element":_fix_off_by_one,
        "bare-except":            _fix_bare_except,
        "unclosed-file":          _fix_unclosed_file,
        "mutable-default-arg":    _fix_mutable_default,
    }

    fixer = _fixers.get(check)
    if fixer is None:
        return False, (
            f"No automatic fix available for '{check}'. "
            f"Fix hint: {result.get('fix', '')}"
        )

    fixed = fixer(original, result)
    if fixed is None or fixed == original:
        return False, (
            "Could not locate the exact line to change automatically. "
            f"Fix hint: {result.get('fix', '')}"
        )

    # Show diff
    _print_diff(console, filepath, original, fixed)

    if confirm:
        try:
            answer = input("\nApply this fix? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer not in ("y", "yes"):
            return False, "Fix not applied — user declined."

    # Safe-write with backup
    backup = path.with_suffix(path.suffix + ".devsuno.bak")
    shutil.copy2(str(path), str(backup))
    try:
        path.write_text(fixed, encoding="utf-8")
        backup.unlink()
        return True, f"Fixed and saved: {filepath}"
    except Exception as exc:
        # Restore from backup
        shutil.copy2(str(backup), str(path))
        backup.unlink()
        return False, f"Write failed ({exc}), original restored."


# ---------------------------------------------------------------------------
# Individual fixers
# ---------------------------------------------------------------------------

def _ensure_import(code: str, module: str) -> str:
    """Prepend ``import <module>`` if not already present."""
    if re.search(rf"^import\s+{module}\b|^from\s+{module}\b", code, re.MULTILINE):
        return code
    return f"import {module}\n" + code


def _fix_hardcoded_secret(code: str, result: dict) -> str | None:
    """Replace ALL hardcoded secret assignments with os.getenv() calls."""
    from .local_debug import _SECRET_VAR_RE, _PLACEHOLDER_RE

    changed = False
    new_code = code

    for m in list(_SECRET_VAR_RE.finditer(code)):
        value = m.group("value")
        if _PLACEHOLDER_RE.match(value) or len(value) < 6:
            continue
        var = m.group("var")
        quote = m.group("quote")
        # Replace  VAR = "value"  with  VAR = os.getenv("VAR")
        old_assign = m.group(0)
        new_assign = f"{var} = os.getenv({quote}{var.upper()}{quote})"
        new_code = new_code.replace(old_assign, new_assign, 1)
        changed = True

    if not changed:
        return None

    new_code = _ensure_import(new_code, "os")
    return new_code


def _fix_none_guard(code: str, result: dict) -> str | None:
    """Insert ``if param is None: return []`` at the top of the function body."""
    # Find the parameter name from the corrected_line
    cl = result.get("corrected_line", "")
    m = re.match(r"if\s+(\w+)\s+is\s+None", cl)
    if not m:
        return None
    param = m.group(1)

    # Find the function that uses this parameter
    func_m = re.search(
        rf"def\s+\w+\s*\([^)]*\b{re.escape(param)}\b[^)]*\)[^:]*:\n",
        code,
    )
    if not func_m:
        return None

    # Find the first line of the function body
    body_start = func_m.end()
    # Determine the indentation of the first body line
    rest = code[body_start:]
    first_line_m = re.match(r"( +)\S", rest)
    if not first_line_m:
        return None
    indent = first_line_m.group(1)

    guard = f"{indent}if {param} is None:\n{indent}    return []\n"
    return code[:body_start] + guard + code[body_start:]


def _fix_off_by_one(code: str, result: dict) -> str | None:
    """Replace <= length with < length."""
    # JavaScript: i <= arr.length
    new_code = re.sub(
        r"(\w+)\s*<=\s*([\w.]+)\.length",
        lambda m: f"{m.group(1)} < {m.group(2)}.length",
        code,
    )
    # Python: range(len(x) + 1) → range(len(x))
    new_code = re.sub(
        r"range\(\s*len\((\w+)\)\s*\+\s*1\s*\)",
        lambda m: f"range(len({m.group(1)}))",
        new_code,
    )
    return new_code if new_code != code else None


def _fix_bare_except(code: str, result: dict) -> str | None:
    """Replace bare except: with except Exception as e: + comment."""
    has_logging = bool(re.search(r"^import logging|^from logging", code, re.MULTILINE))

    def _replace(m):
        indent = m.group(1) if m.group(1) else ""
        if has_logging:
            return (
                f"{indent}except Exception as e:\n"
                f"{indent}    logging.exception(e)"
            )
        return (
            f"{indent}except Exception as e:\n"
            f"{indent}    # TODO: handle or re-raise this exception\n"
            f"{indent}    raise"
        )

    # Match bare except: (with optional indentation)
    new_code = re.sub(
        r"^( *)except\s*(?:Exception\s*(?:as\s+\w+)?\s*)?:",
        _replace,
        code,
        flags=re.MULTILINE,
    )
    return new_code if new_code != code else None


def _fix_unclosed_file(code: str, result: dict) -> str | None:
    """Replace ``f = open(...)`` with ``with open(...) as f:`` + indent body."""
    # Match: varname = open(...)
    m = re.search(r"^( *)(\w+)\s*=\s*(open\s*\([^)]+\))", code, re.MULTILINE)
    if not m:
        return None

    indent = m.group(1)
    varname = m.group(2)
    open_call = m.group(3)
    line_start = m.start()
    line_end = code.find("\n", m.end())
    if line_end == -1:
        line_end = len(code)

    # Build the with statement
    with_line = f"{indent}with {open_call} as {varname}:\n"

    # Find and indent the following lines until we hit a blank line,
    # a dedent, or a close call
    rest = code[line_end + 1:]
    new_rest_lines = []
    for line in rest.splitlines(keepends=True):
        stripped = line.rstrip()
        # Stop indenting at: blank lines after content, dedented code, or .close()
        if stripped == "" or not stripped.startswith(indent + " "):
            # Check if it's the matching .close() — remove it
            if re.match(rf"\s*{re.escape(varname)}\s*\.\s*close\s*\(\s*\)", stripped):
                continue  # drop the explicit .close()
            new_rest_lines.append(line)
            continue
        new_rest_lines.append("    " + line)

    new_code = (
        code[:line_start]
        + with_line
        + "".join(new_rest_lines)
    )
    return new_code if new_code != code else None


def _fix_mutable_default(code: str, result: dict) -> str | None:
    """Replace mutable default arg with None + insert guard in function body."""
    cl = result.get("corrected_line", "")
    # Extract function name from corrected_line: def foo(..., param=None):
    func_m_cl = re.match(r"def\s+(\w+)\s*\(", cl)
    if not func_m_cl:
        return None
    func_name = func_m_cl.group(1)

    # Find the function in the code
    func_m = re.search(
        rf"def\s+{re.escape(func_name)}\s*\([^)]*\)[^:]*:", code, re.DOTALL
    )
    if not func_m:
        return None

    params_str = func_m.group(0)

    # Find parameters with mutable defaults in this function
    param_fixes: list[tuple[str, str, str]] = []  # (param, old_default, new_default)
    for pm in re.finditer(r"(\w+)\s*=\s*(\[\s*\]|\{\s*\}|set\s*\(\s*\))", params_str):
        param = pm.group(1)
        old_default = pm.group(2).strip()
        empty_val = (
            "[]" if old_default.startswith("[")
            else "{}" if old_default.startswith("{")
            else "set()"
        )
        param_fixes.append((param, old_default, empty_val))

    if not param_fixes:
        return None

    new_code = code
    # Replace defaults in signature
    for param, old_default, empty_val in param_fixes:
        new_code = re.sub(
            rf"\b{re.escape(param)}\s*=\s*{re.escape(old_default)}",
            f"{param}=None",
            new_code,
            count=1,
        )

    # Insert guards at top of function body
    func_m2 = re.search(
        rf"def\s+{re.escape(func_name)}\s*\([^)]*\)[^:]*:\n",
        new_code, re.DOTALL,
    )
    if not func_m2:
        return new_code  # signature fixed, guard insertion failed

    body_start = func_m2.end()
    rest = new_code[body_start:]
    first_m = re.match(r"( +)\S", rest)
    if not first_m:
        return new_code

    indent = first_m.group(1)
    guards = "".join(
        f"{indent}if {param} is None:\n{indent}    {param} = {empty_val}\n"
        for param, _, empty_val in param_fixes
    )
    return new_code[:body_start] + guards + new_code[body_start:]


# ---------------------------------------------------------------------------
# Diff display
# ---------------------------------------------------------------------------

def _print_diff(console, filepath, original: str, fixed: str) -> None:
    """Print a coloured unified diff between original and fixed."""
    import difflib

    orig_lines = original.splitlines(keepends=True)
    fix_lines = fixed.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines, fix_lines,
        fromfile=f"{filepath} (original)",
        tofile=f"{filepath} (fixed)",
        lineterm="",
    ))

    if not diff:
        return

    if console:
        try:
            from rich.syntax import Syntax
            from rich.panel import Panel
            diff_text = "".join(diff)
            syn = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
            console.print(Panel(syn, title="[bold cyan]Proposed fix[/bold cyan]",
                                border_style="cyan"))
            return
        except Exception:
            pass

    # Plain fallback
    for line in diff:
        line = line.rstrip()
        if line.startswith("+"):
            print(f"\033[32m{line}\033[0m")
        elif line.startswith("-"):
            print(f"\033[31m{line}\033[0m")
        else:
            print(line)
