"""
Schwab OAuth Authentication - Manual Code Entry
Use this if automatic browser callback doesn't work

Usage:
    python schwab_auth_manual.py
"""

import json
import base64
import urllib.parse
import urllib.request
import os
from pathlib import Path
from datetime import datetime, timedelta

# Reuse the OS-trust-store SSL context (handles antivirus/proxy TLS interception)
from schwab_bridge import get_ssl_context

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "schwab_config.json"
TOKENS_FILE = CONFIG_DIR / "schwab_tokens.json"

# OAuth settings
AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
REDIRECT_PORT = 3000
# Use the HTTPS ngrok URL registered in Schwab Developer Portal
REDIRECT_URI = "https://unlean-acrogynous-kera.ngrok-free.dev/callback"


def load_config():
    """Load configuration"""
    if not CONFIG_FILE.exists():
        print("Configuration not found. Run setup first.")
        print("Run: python schwab_bridge.py --setup")
        return None
    
    with open(CONFIG_FILE) as f:
        return json.load(f)


def get_authorization_url(config):
    """Build OAuth authorization URL"""
    params = {
        'response_type': 'code',
        'client_id': config['client_id'],
        'redirect_uri': REDIRECT_URI,
        'scope': 'accounts trading'
    }
    
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(config, code):
    """Exchange authorization code for access/refresh tokens"""
    auth_string = base64.b64encode(
        f"{config['client_id']}:{config['client_secret']}".encode()
    ).decode()
    
    data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }).encode()
    
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            'Authorization': f'Basic {auth_string}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept-Encoding': 'identity',
        },
        method='POST'
    )

    def _read(resp):
        raw = resp.read()
        if resp.headers.get('Content-Encoding', '').lower() == 'gzip':
            import gzip as _gz
            raw = _gz.decompress(raw)
        return raw

    try:
        with urllib.request.urlopen(req, context=get_ssl_context()) as response:
            tokens = json.loads(_read(response))
            expires_in = tokens.get('expires_in', 1800)
            tokens['expires_at'] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            tokens['created_at'] = datetime.now().isoformat()
            return tokens
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            import gzip as _gz
            body = _gz.decompress(body)
        except Exception:
            pass
        print(f"Token exchange failed: {e.code}: {body.decode(errors='replace')[:300]}")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def save_tokens(tokens):
    """Save tokens securely"""
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)
    
    # Set restrictive permissions
    os.chmod(TOKENS_FILE, 0o600)

    (CONFIG_DIR / "last_reauth.txt").write_text(datetime.now().isoformat())
    print(f"Tokens saved to: {TOKENS_FILE}")


def main():
    print("=" * 60)
    print("Schwab OAuth Authentication - Manual Mode")
    print("=" * 60)
    
    # Load configuration
    config = load_config()
    if not config:
        return
    
    print(f"\nClient ID: {config['client_id'][:10]}...")
    print(f"Account: ****-{config.get('account_number', '????')}")
    
    # Show authorization URL
    auth_url = get_authorization_url(config)
    print(f"\n{'='*60}")
    print("STEP 1: Open this URL in your browser (where you're logged into Schwab):")
    print(f"{'='*60}")
    print(f"\n{auth_url}\n")
    
    print("STEP 2: Log in and authorize 'Aristotle Trading Agent'")
    print("STEP 3: You'll be redirected to a localhost URL that won't load")
    print("STEP 4: Copy the FULL redirect URL from your browser's address bar")
    print("STEP 5: Paste it below")
    print(f"{'='*60}\n")
    
    # Get redirect URL from user
    redirect_url = input("Paste the full redirect URL (or just the code): ").strip()
    
    # Extract code from URL or use directly
    if 'code=' in redirect_url:
        # Extract code from URL
        parsed = urllib.parse.urlparse(redirect_url)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get('code', [None])[0]
    else:
        # Assume user pasted just the code
        code = redirect_url
    
    if not code:
        print("Could not find authorization code. Please try again.")
        return
    
    print(f"\nAuthorization code received: {code[:20]}...")
    
    # Exchange for tokens
    print("\nExchanging code for tokens...")
    tokens = exchange_code_for_tokens(config, code)
    
    if tokens:
        save_tokens(tokens)
        
        print("\n" + "=" * 60)
        print("Authentication Complete!")
        print("=" * 60)
        print(f"\nAccess Token: {tokens['access_token'][:20]}...")
        print(f"Refresh Token: {tokens['refresh_token'][:20]}...")
        print(f"Expires: {tokens['expires_at']}")
        print(f"\nYou can now use the Schwab API!")
        print("\nExample:")
        print("  python schwab_bridge.py --quotes TSLL,NVDL")
        print("  python schwab_bridge.py --analyze TSLL")
    else:
        print("\nFailed to get tokens")


if __name__ == '__main__':
    main()
