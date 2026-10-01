"""
finish_auth.py - fast, robust Schwab OAuth code exchange for Aristotle
======================================================================
Schwab authorization codes expire in ~30 seconds. This helper removes all
manual latency: after you copy the redirect URL from the browser address bar,
just run `python finish_auth.py` and it reads the URL from your clipboard,
extracts the code, exchanges it for tokens, and verifies the connection.

Usage:
    python finish_auth.py                 # reads the URL from the clipboard
    python finish_auth.py "<full url>"    # or pass it explicitly
"""

import base64
import gzip
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from schwab_bridge import get_ssl_context

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "schwab_config.json"
TOKENS_FILE = CONFIG_DIR / "schwab_tokens.json"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
REDIRECT_URI = "https://unlean-acrogynous-kera.ngrok-free.dev/callback"


def get_clipboard():
    """Read the Windows clipboard via PowerShell."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip()
    except Exception as e:
        print(f"[WARN] Could not read clipboard: {e}")
        return ""


def extract_code(url_or_code):
    if "code=" in url_or_code:
        q = urllib.parse.urlparse(url_or_code).query
        return urllib.parse.parse_qs(q).get("code", [None])[0]
    return url_or_code.strip() or None


def _read_body(resp):
    raw = resp.read()
    if resp.headers.get("Content-Encoding", "").lower() == "gzip":
        raw = gzip.decompress(raw)
    return raw


def exchange(config, code):
    auth = base64.b64encode(
        f"{config['client_id']}:{config['client_secret']}".encode()
    ).decode()
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST", headers={
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(req, context=get_ssl_context()) as resp:
            tokens = json.loads(_read_body(resp))
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            body = gzip.decompress(body)
        except Exception:
            pass
        print(f"[ERROR] Token exchange failed: HTTP {e.code}")
        print(f"        {body.decode(errors='replace')[:300]}")
        return None

    tokens["expires_at"] = (datetime.now() + timedelta(
        seconds=tokens.get("expires_in", 1800))).isoformat()
    tokens["created_at"] = datetime.now().isoformat()
    return tokens


def main():
    if not CONFIG_FILE.exists():
        print("[ERROR] schwab_config.json not found.")
        return
    config = json.loads(CONFIG_FILE.read_text())

    src = sys.argv[1] if len(sys.argv) > 1 else get_clipboard()
    code = extract_code(src)
    if not code:
        print("[ERROR] No authorization code found in clipboard/argument.")
        print("        Copy the full redirect URL (with ?code=) and re-run.")
        return

    print(f"[..] Exchanging code {code[:18]}... via {TOKEN_URL}")
    tokens = exchange(config, code)
    if not tokens:
        print("[!!] Re-run the auth URL to get a FRESH code (they expire in ~30s).")
        return

    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))
    try:
        os.chmod(TOKENS_FILE, 0o600)
    except Exception:
        pass
    (CONFIG_DIR / "last_reauth.txt").write_text(datetime.now().isoformat())
    print("[OK] SUCCESS - tokens saved.")
    print(f"     access  {tokens['access_token'][:16]}...")
    print(f"     refresh {tokens['refresh_token'][:16]}...")
    print(f"     expires {tokens['expires_at']}")

    # Verify immediately with a read-only account call.
    print("\n[..] Verifying live account access...")
    try:
        import schwab_accounts as acc
        nums = acc.get_account_numbers()
        if nums:
            for n in nums:
                print(f"     linked: *{n['mask']}  {n['type']}")
            print("\n[OK] Live connection confirmed. Run:  python reconcile.py")
        else:
            print("[WARN] Tokens saved but no accounts returned - check app scope.")
    except Exception as e:
        print(f"[WARN] Verify call error: {e}")


if __name__ == "__main__":
    main()
