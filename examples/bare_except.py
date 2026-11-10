"""Example C: bare except that swallows every error silently.

Bug: the except block catches everything — including KeyboardInterrupt,
SystemExit, MemoryError — and returns None with no log, no message, and
no crash. If the database call fails, the caller gets None back and has
no idea why. The bug is completely invisible at runtime.

The fix: catch the specific exception you expect, or at minimum log the
error and re-raise.

Demo question to speak (Hinglish):
  "bro ye function kabhi bhi error nahi deta lekin result bhi galat aata hai
   kya koi exception silently swallow ho rahi hai"
"""
import json
import urllib.request


def fetch_user_data(user_id: int) -> dict | None:
    """Fetch user profile from the internal API."""
    try:
        url = f"https://api.internal/users/{user_id}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read())
    except:                           # <-- Bug: bare except swallows everything
        return None                   #     errors disappear silently


def process_order(user_id: int, items: list) -> str:
    """Process a purchase order for a user."""
    try:
        total = sum(item["price"] for item in items)
        discount = total * 0.1
        return f"Order total: {total - discount:.2f}"
    except Exception:                 # <-- Bug: same problem, specific to Exception
        return "Order failed"         #     but no log, no re-raise, caller doesn't know why
