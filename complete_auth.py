import json
import base64
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "schwab_config.json"
TOKENS_FILE = CONFIG_DIR / "schwab_tokens.json"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

# The auth code from the callback URL
AUTH_CODE = "C0.b2F1dGgyLmNkYy5zY2h3YWIuY29t.jxyl3ZYsq8PQulicaii3Kpo_cGoSDPCVKYqF-t-s44I@"
REDIRECT_URI = "https://unlean-acrogynous-kera.ngrok-free.dev/callback"

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def exchange_code_for_tokens(config, code):
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
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            tokens = json.loads(response.read())
            
            expires_in = tokens.get('expires_in', 1800)
            tokens['expires_at'] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            tokens['created_at'] = datetime.now().isoformat()
            
            return tokens
    except urllib.error.HTTPError as e:
        print(f"[X] Token exchange failed: {e.code}")
        try:
            error_body = e.read()
            # Try to decode, handle gzip
            if e.headers.get('Content-Encoding') == 'gzip':
                import gzip
                error_body = gzip.decompress(error_body)
            print(f"   Response: {error_body.decode('utf-8', errors='replace')}")
        except:
            print(f"   Response: (could not decode)")
        return None
    except Exception as e:
        print(f"[X] Error: {e}")
        return None

def save_tokens(tokens):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)
    print(f"[SAVE] Tokens saved to: {TOKENS_FILE}")

def main():
    print("[LOCK] Completing Schwab OAuth (manual code)")
    print("=" * 60)
    
    config = load_config()
    print(f"Client ID: {config['client_id'][:10]}...")
    
    print("\n[REFRESH] Exchanging code for tokens...")
    tokens = exchange_code_for_tokens(config, AUTH_CODE)
    
    if tokens:
        save_tokens(tokens)
        
        print("\n" + "=" * 60)
        print("[OK] Authentication Complete!")
        print("=" * 60)
        print(f"\nAccess Token: {tokens['access_token'][:20]}...")
        print(f"Refresh Token: {tokens['refresh_token'][:20]}...")
        print(f"Expires: {tokens['expires_at']}")
        print(f"\nYou can now use the Schwab API!")
    else:
        print("\n[X] Failed to get tokens")

if __name__ == '__main__':
    main()
