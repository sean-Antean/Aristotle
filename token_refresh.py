"""
Token refresh utility for Schwab API
Run this before any API call to ensure valid tokens
"""

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


def load_tokens():
    """Load current tokens"""
    if not TOKENS_FILE.exists():
        return None
    with open(TOKENS_FILE) as f:
        return json.load(f)


def load_config():
    """Load configuration"""
    with open(CONFIG_FILE) as f:
        return json.load(f)


def is_token_expired(tokens):
    """Check if access token is expired or about to expire"""
    if 'expires_at' not in tokens:
        return True
    
    expires_at = datetime.fromisoformat(tokens['expires_at'])
    # Refresh if expires in less than 5 minutes
    return datetime.now() > (expires_at - timedelta(minutes=5))


def refresh_access_token():
    """Refresh the access token using refresh token"""
    tokens = load_tokens()
    if not tokens:
        print("No tokens found. Run schwab_auth.py first.")
        return None
    
    config = load_config()
    
    auth_string = base64.b64encode(
        f"{config['client_id']}:{config['client_secret']}".encode()
    ).decode()
    
    data = urllib.parse.urlencode({
        'grant_type': 'refresh_token',
        'refresh_token': tokens['refresh_token']
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
            new_tokens = json.loads(response.read())
            
            # Preserve refresh token if not returned
            if 'refresh_token' not in new_tokens:
                new_tokens['refresh_token'] = tokens['refresh_token']
            
            # Update expiration
            expires_in = new_tokens.get('expires_in', 1800)
            new_tokens['expires_at'] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            new_tokens['created_at'] = datetime.now().isoformat()
            
            # Save
            with open(TOKENS_FILE, 'w') as f:
                json.dump(new_tokens, f, indent=2)
            
            print("[REFRESH] Access token refreshed successfully")
            return new_tokens
            
    except urllib.error.HTTPError as e:
        print(f"[REFRESH ERROR] {e.code}: {e.read().decode()}")
        return None
    except Exception as e:
        print(f"[REFRESH ERROR] {e}")
        return None


def ensure_valid_token():
    """Ensure we have a valid access token, refreshing if needed"""
    tokens = load_tokens()
    
    if not tokens:
        print("[ERROR] No tokens found. Run: python schwab_auth.py")
        return None
    
    if is_token_expired(tokens):
        print("[INFO] Token expired or expiring soon. Refreshing...")
        return refresh_access_token()
    
    return tokens


if __name__ == '__main__':
    result = ensure_valid_token()
    if result:
        print(f"[OK] Token valid until: {result['expires_at']}")
    else:
        print("[FAIL] Could not ensure valid token")
