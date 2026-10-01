"""
Schwab OAuth Helper - Manual code entry
Run this, open the URL, then paste the redirect URL.
"""
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

def exchange_code(config, code):
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
        print(f"[ERROR] HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
        return None

def main():
    config = load_config()
    auth_url = (
        f"https://api.schwabapi.com/v1/oauth/authorize"
        f"?response_type=code"
        f"&client_id={config['client_id']}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope=accounts+trading"
    )
    
    print("=" * 60)
    print("Schwab OAuth - Manual Mode")
    print("=" * 60)
    print()
    print("STEP 1: Open this URL in your browser (where you're logged into Schwab):")
    print()
    print(auth_url)
    print()
    print("STEP 2: Log in and authorize 'Aristotle Trading Agent'")
    print("STEP 3: Copy the FULL redirect URL from your browser's address bar")
    print()
    redirect_url = input("Paste the full redirect URL: ").strip()
    
    # Extract code
    if "code=" in redirect_url:
        code = urllib.parse.parse_qs(
            urllib.parse.urlparse(redirect_url).query
        ).get("code", [None])[0]
    else:
        code = redirect_url.strip() or None
    
    if not code:
        print("[ERROR] No code found in URL")
        return
    
    print(f"\n[..] Exchanging code...")
    tokens = exchange_code(config, code)
    
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
        print("[FAIL] Could not exchange code. Try again with a fresh URL.")

if __name__ == "__main__":
    main()
