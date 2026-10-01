import json
import urllib.parse

with open('schwab_config.json') as f:
    config = json.load(f)

params = {
    'response_type': 'code',
    'client_id': config['client_id'],
    'redirect_uri': 'https://unlean-acrogynous-kera.ngrok-free.dev/callback',
    'scope': 'accounts trading'
}

auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?{urllib.parse.urlencode(params)}"
print(auth_url)
