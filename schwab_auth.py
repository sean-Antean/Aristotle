"""
Schwab OAuth Authentication
One-time setup to get access/refresh tokens

Usage:
    python schwab_auth.py
"""

import json
import base64
import urllib.parse
import urllib.request
import webbrowser
import http.server
import socketserver
import threading
import os
from pathlib import Path
from datetime import datetime, timedelta

CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "schwab_config.json"
TOKENS_FILE = CONFIG_DIR / "schwab_tokens.json"

# OAuth settings
AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
REDIRECT_PORT = 3000
# Use the HTTPS ngrok URL registered in Schwab Developer Portal
REDIRECT_URI = "https://unlean-acrogynous-kera.ngrok-free.dev/callback"

# Global to store auth code
auth_code = None


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    """Handle OAuth callback"""
    
    def do_GET(self):
        global auth_code
        
        if '/callback' in self.path:
            # Parse query parameters
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            if 'code' in params:
                auth_code = params['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"""
                    <html>
                    <body style="font-family: Arial; text-align: center; padding: 50px;">
                        <h1 style="color: green;">[OK] Authentication Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                    </body>
                    </html>
                """)
            elif 'error' in params:
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(f"""
                    <html>
                    <body style="font-family: Arial; text-align: center; padding: 50px;">
                        <h1 style="color: red;">[X] Authentication Failed</h1>
                        <p>Error: {params['error'][0]}</p>
                    </body>
                    </html>
                """.encode())
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass


def load_config():
    """Load configuration"""
    if not CONFIG_FILE.exists():
        print("[X] Configuration not found. Run setup first.")
        return None
    
    with open(CONFIG_FILE) as f:
        return json.load(f)


def start_callback_server():
    """Start local server to receive OAuth callback"""
    with socketserver.TCPServer(("", REDIRECT_PORT), OAuthHandler) as httpd:
        print(f"[WEB] Callback server started on port {REDIRECT_PORT}")
        httpd.handle_request()  # Handle one request
        httpd.server_close()


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
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        method='POST'
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            tokens = json.loads(response.read())
            
            # Add expiration time
            expires_in = tokens.get('expires_in', 1800)
            tokens['expires_at'] = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
            tokens['created_at'] = datetime.now().isoformat()
            
            return tokens
    except urllib.error.HTTPError as e:
        print(f"[X] Token exchange failed: {e.code}")
        print(f"   Response: {e.read().decode()}")
        return None
    except Exception as e:
        print(f"[X] Error: {e}")
        return None


def save_tokens(tokens):
    """Save tokens securely"""
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)
    
    # Set restrictive permissions
    os.chmod(TOKENS_FILE, 0o600)
    
    print(f"\n[SAVE] Tokens saved to: {TOKENS_FILE}")


def main():
    print("[LOCK] Schwab OAuth Authentication")
    print("=" * 60)
    
    # Load configuration
    config = load_config()
    if not config:
        print("\n[WRENCH2] Setup required first!")
        print("Run: python schwab_bridge.py --setup")
        return
    
    print(f"\nClient ID: {config['client_id'][:10]}...")
    print(f"Account: ****-{config.get('account_number', '????')}")
    
    # Build authorization URL
    auth_url = get_authorization_url(config)
    
    print(f"\n[PHONE] Opening browser for authorization...")
    print(f"   URL: {auth_url[:80]}...")
    
    # Start callback server in background
    server_thread = threading.Thread(target=start_callback_server)
    server_thread.daemon = True
    server_thread.start()
    
    # Open browser
    webbrowser.open(auth_url)
    
    print("\n[WAIT] Waiting for authorization...")
    print("   (Login to Schwab and authorize the app)")
    
    # Wait for callback
    import time
    timeout = 120  # 2 minutes
    elapsed = 0
    
    while auth_code is None and elapsed < timeout:
        time.sleep(1)
        elapsed += 1
        if elapsed % 10 == 0:
            print(f"   ...waiting ({elapsed}s)")
    
    if auth_code is None:
        print("\n[X] Timeout waiting for authorization")
        print("   Please try again")
        return
    
    print(f"\n[OK] Authorization code received!")
    
    # Exchange for tokens
    print("\n[REFRESH] Exchanging code for tokens...")
    tokens = exchange_code_for_tokens(config, auth_code)
    
    if tokens:
        save_tokens(tokens)
        
        print("\n" + "=" * 60)
        print("[OK] Authentication Complete!")
        print("=" * 60)
        print(f"\nAccess Token: {tokens['access_token'][:20]}...")
        print(f"Refresh Token: {tokens['refresh_token'][:20]}...")
        print(f"Expires: {tokens['expires_at']}")
        print(f"\nYou can now use the Schwab API!")
        print("\nExample:")
        print("  python schwab_bridge.py --quotes TSLL,NVDL")
        print("  python schwab_bridge.py --analyze TSLL")
    else:
        print("\n[X] Failed to get tokens")


if __name__ == '__main__':
    main()
