"""Example E: file opened without a context manager.

Bug: f = open(...) without a `with` block. If an exception is raised
between open() and close(), the file descriptor leaks. On Linux this
eventually hits the open-file-descriptor limit (ulimit -n, default 1024).
Write operations may also not be flushed to disk if close() is never called.

The fix: always use `with open(...) as f:` — it closes and flushes
automatically, even if an exception is raised inside the block.

Demo question to speak (Hinglish):
  "bro ye file operations sahi se close ho rahi hain ya koi resource
   leak hai"
"""


def read_config(config_path: str) -> dict:
    """Read a JSON config file and return the parsed dict."""
    import json
    f = open(config_path, "r")          # <-- Bug: not in a with block
    data = json.load(f)
    f.close()                           # close() is called, but only if no exception
    return data                         # if json.load raises, f is never closed


def append_log(log_path: str, message: str) -> None:
    """Append a log message to a file."""
    log_file = open(log_path, "a")      # <-- Bug: same issue on write
    log_file.write(message + "\n")
    # Oops — forgot log_file.close()   # <-- Bug: missing close entirely
