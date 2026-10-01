"""
Simple callback server for Schwab OAuth.
Run this first, then open the auth URL in your browser.
"""
import http.server
import socketserver
import urllib.parse
import json
from pathlib import Path

PORT = 3000
auth_code = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        if '/callback' in self.path:
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            if 'code' in params:
                auth_code = params['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b"""
                    <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: green;">[OK] Auth Successful!</h1>
                    <p>You can close this window. Check Telegram for next steps.</p>
                    </body></html>
                """)
                print(f"\n[OK] Got auth code: {auth_code[:30]}...")
                print("Copy this code and paste it in Telegram if needed.")
            elif 'error' in params:
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(f"""
                    <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: red;">Error: {params['error'][0]}</h1>
                    </body></html>
                """.encode())
            else:
                self.send_response(200)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        print(f"[SERVER] {args[0]}")

def main():
    print(f"[*] Starting callback server on port {PORT}...")
    print(f"[*] Open the Schwab auth URL in your browser now.")
    print(f"[*] After auth, this server will capture the code.")
    print()
    
    with socketserver.TCPServer(("", PORT), CallbackHandler) as httpd:
        httpd.timeout = 120  # 2 minute timeout
        start_time = __import__('time').time()
        while auth_code is None and (__import__('time').time() - start_time) < 120:
            httpd.handle_request()
        
        if auth_code:
            print(f"\n[OK] Auth code captured!")
            # Save to file for easy retrieval
            code_file = Path(__file__).parent / "auth_code.txt"
            code_file.write_text(auth_code)
            print(f"[SAVE] Code saved to auth_code.txt")
        else:
            print("\n[TIMEOUT] No auth code received within 2 minutes.")

if __name__ == "__main__":
    main()
