"""reauth_url.py - print the Schwab authorization URL for the Telegram re-auth flow.
==================================================================================
Step 1 of the phone-friendly weekly re-auth. Aristotle runs this and sends the URL
to the user on Telegram. The user taps it, logs into Schwab, authorizes, lands on a
page that FAILS to load (the offline ngrok callback - expected), copies the FULL
address-bar URL, and pastes it back into the chat. Aristotle then runs
`finish_auth.py "<that url>"` (step 2) to exchange it.

Pure Python, no LLM, no secrets printed (only the public client_id in the URL).
"""
import json
import urllib.parse
from pathlib import Path

from finish_auth import REDIRECT_URI  # single source of truth for the callback

CONFIG_DIR = Path(__file__).parent
AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"

cfg = json.loads((CONFIG_DIR / "schwab_config.json").read_text())
params = {
    "response_type": "code",
    "client_id": cfg["client_id"],
    "redirect_uri": REDIRECT_URI,
    "scope": "accounts trading",
}
url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

print("SCHWAB RE-AUTH (step 1 of 2)")
print("1. Tap the link below and log into Schwab.")
print("2. Approve 'Aristotle'. You'll land on a page that FAILS to load - that's normal.")
print("3. Copy the ENTIRE address-bar URL from that failed page.")
print("4. Paste it back to me here and I'll finish the re-auth.")
print("")
print(url)
