"""Example D: hardcoded API key and password in source code.

Bug: credentials are written directly as string literals. Anyone who
reads this file — a teammate, a code reviewer, anyone with git access,
or anyone who finds the repo public — can steal these credentials and
use them immediately.

The git history also permanently records them even after deletion.

The fix: move all secrets to environment variables and read them at
runtime with os.getenv(). Store the actual values in .env (gitignored).

Demo question to speak (Hinglish):
  "bro is file mein koi security issue hai kya, password ya api key
   hardcode toh nahi kar diya"
"""
import hashlib
import hmac


# Configuration
DATABASE_HOST = "db.internal.company.com"
DATABASE_PORT = 5432
DATABASE_NAME = "users_production"

# Bug: real credentials hardcoded as string literals
DATABASE_PASSWORD = "Sup3rS3cur3Passw0rd!"       # <-- hardcoded password
STRIPE_API_KEY    = "sk_live_EXAMPLE_FAKE_KEY_DO_NOT_USE"  # <-- fake key (demo only)
JWT_SECRET        = "myverysecretjwtsigningkey123"       # <-- signing secret
SENDGRID_API_KEY  = "SG.EXAMPLE_FAKE_KEY_DO_NOT_USE"    # <-- fake key (demo only)


def create_jwt_token(user_id: int) -> str:
    payload = f"user_id={user_id}"
    sig = hmac.new(JWT_SECRET.encode(), payload.encode(), hashlib.sha256)
    return f"{payload}.{sig.hexdigest()}"


def charge_customer(amount_paise: int, card_token: str) -> dict:
    """Charge a customer via Stripe."""
    import urllib.request, json
    headers = {
        "Authorization": f"Bearer {STRIPE_API_KEY}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # ... rest of the charge logic
    return {"status": "charged", "amount": amount_paise}
