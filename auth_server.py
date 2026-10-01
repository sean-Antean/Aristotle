import http.server
import socketserver
import urllib.parse
import json
import base64
import urllib.request

PORT = 8000

class CallbackHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        if 'code' in query_params:
            code = query_params['code'][0]
            print(f'\\n[AUTH CODE RECEIVED]: {code}')
            
            # Exchange code for tokens
            client_id = '1wk8tMeDif8l8kK9YMXN4nCYpTlXGHlQDPCKZcgWlOGdMbNj'
            client_secret = 'bqAC2HWQ7GPQobUWqSpxPsCGWNKRcEcoFhDc8o8dNv8fjjl5OGJABVsSkyuA7wDh'
            credentials = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
            
            data = urllib.parse.urlencode({
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': f'http://localhost:{PORT}/callback'
            }).encode()
            
            req = urllib.request.Request(
                'https://api.schwabapi.com/v1/oauth/token',
                data=data,
                headers={
                    'Authorization': f'Basic {credentials}',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            )
            
            try:
                with urllib.request.urlopen(req) as response:
                    tokens = json.loads(response.read().decode())
                    print('\\n[SUCCESS] Tokens received!')
                    
                    # Save tokens
                    import datetime
                    tokens['created_at'] = datetime.datetime.now().isoformat()
                    tokens['expires_at'] = (datetime.datetime.now() + datetime.timedelta(seconds=tokens.get('expires_in', 1800))).isoformat()
                    
                    with open('schwab_tokens.json', 'w') as f:
                        json.dump(tokens, f, indent=2)
                    print('[SAVED] Tokens saved to schwab_tokens.json')
            except Exception as e:
                print(f'\\n[ERROR] {e}')
            
            # Send response to browser
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<h1>Authentication Successful!</h1><p>You can close this window.</p>')
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<h1>Error</h1><p>No code received.</p>')
    
    def log_message(self, format, *args):
        pass  # Suppress logs

print(f'Starting callback server on port {PORT}...')
print(f'Open this URL in your browser:')
print(f'https://api.schwabapi.com/v1/oauth/authorize?response_type=code&client_id=1wk8tMeDif8l8kK9YMXN4nCYpTlXGHlQDPCKZcgWlOGdMbNj&redirect_uri=http%3A%2F%2Flocalhost%3A{PORT}%2Fcallback&scope=accounts+trading')
print('\\nWaiting for callback...')

with socketserver.TCPServer(("", PORT), CallbackHandler) as httpd:
    httpd.handle_request()
