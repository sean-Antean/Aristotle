"""
Exchange a Schwab auth code for tokens.
Usage: python exchange_code.py <auth_code_or_full_url>
"""
import sys
import json
import base64
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "schwab_config.json"
TOKENS_FILE = Path(__file__).parent / "schwab_tokens.json"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
REDIRECT_URI = "https://unlean-acrogynous-kera.ngrok-free.dev/callback"

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def extract_code(url_or_code):
    if "code=" in url_or_code:
        q = urllib.parse.urlparse(url_or_code).query
        return urllib.parse.parse_qs(q).get("code", [None])[0]
    return url_or_code.strip() or None

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
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read())
            tokens["expires_at"] = (datetime.now() + timedelta(
                seconds=tokens.get("expires_in", 1800))).isoformat()
            tokens["created_at"] = datetime.now().isoformat()
            return tokens
    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python exchange_code.py <auth_code_or_full_redirect_url>")
        print()
        print("Paste the full redirect URL from Schwab, or just the code after ?code=")
        return
    
    config = load_config()
    code = extract_code(sys.argv[1])
    
    if not code:
        print("[ERROR] No code found")
        return
    
    print(f"[..] Exchanging code: {code[:30]}...")
    tokens = exchange(config, code)
    
    if tokens:
        with open(TOKENS_FILE, "w") as f:
            json.dump(tokens, f, indent=2)
        print("[OK] Tokens saved!")
        print(f"     Access:  {tokens['access_token'][:20]}...")
        print(f"     Refresh: {tokens['refresh_token'][:20]}...")
        print(f"     Expires: {tokens['expires_at']}")
        
        # Quick test
        print("\n[..] Testing account access...")
        try:
            import schwab_accounts as acc
            nums = acc.get_account_numbers()
            if nums:
                for n in nums:
                    print(f"     Linked: *{n['mask']}  {n['type']}")
                print("\n[OK] Ready! Run: python reconcile.py")
            else:
                print("[WARN] No accounts returned")
        except Exception as e:
            print(f"[WARN] Test failed: {e}")
    else:
        print("[FAIL] Could not exchange code. The code may have expired (valid ~30s).")
        print("       Get a fresh code by re-authorizing.")

if __name__ == "__main__":
    main()
