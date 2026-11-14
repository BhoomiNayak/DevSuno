"""Example D: hardcoded API key and password in source code.

Bug: credentials are written directly as string literals. Anyone who
reads this file — a teammate, a code reviewer, anyone with git access,
or anyone who finds the repo public — can read these credentials
immediately. The git history also records them permanently.

The fix: move all secrets to environment variables and read them at
runtime with os.getenv(). Store the actual values in .env (gitignored).

Demo question to speak (Hinglish):
  "bro is file mein koi security issue hai kya, password ya api key
   hardcode toh nahi kar diya"
"""
import hashlib
import hmac
import os


# Configuration — these are fine (not secrets)
DATABASE_HOST = "db.internal.company.com"
DATABASE_PORT = 5432
DATABASE_NAME = "users_production"

# Bug: credentials hardcoded as string literals
# (values below are intentionally fake — for demo purposes only)
DATABASE_PASSWORD = "Sup3rS3cur3Passw0rd!"   # <-- hardcoded password
JWT_SECRET        = "jwt-signing-key-2026"    # <-- hardcoded signing secret
API_KEY           = "gnani-api-key-demoonly"  # <-- hardcoded API key

# The fix looks like this:
# DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")
# JWT_SECRET        = os.getenv("JWT_SECRET")
# API_KEY           = os.getenv("API_KEY")


def create_jwt_token(user_id: int) -> str:
    payload = f"user_id={user_id}"
    sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256)
    return f"{payload}.{sig.hexdigest()}"


def get_db_connection():
    """Connect to the database using the hardcoded password."""
    import urllib.parse
    conn_str = (
        f"postgresql://admin:{DATABASE_PASSWORD}"
        f"@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
    )
    return conn_str  # password visible in connection string logs
