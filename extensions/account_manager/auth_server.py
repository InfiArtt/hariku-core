import threading
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

logger = logging.getLogger(__name__)

auth_code = None

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/callback':
            query = parse_qs(parsed_path.query)
            
            if 'error' in query:
                self.send_response(400)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(f"<h1>Login Failed</h1><p>Message: {query.get('error_description', [''])[0]}</p><p>Please close this window.</p>".encode('utf-8'))
                auth_code = "ERROR"
            elif 'code' in query:
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(b"<h1>Login Successful!</h1><p>You have successfully logged in. Please close this window and return to the Hariku application.</p>")
                auth_code = query['code'][0]
            else:
                self.send_response(400)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(b"<h1>Incomplete Parameters</h1><p>Please close this window.</p>")
                auth_code = "ERROR"
            
            # Beritahu server untuk berhenti setelah menangkap request
            threading.Thread(target=self.server.shutdown).start()

    def log_message(self, format, *args):
        # Mute logging to console
        pass

def wait_for_auth_code(port):
    global auth_code
    auth_code = None
    try:
        server = HTTPServer(('localhost', port), OAuthCallbackHandler)
        server.serve_forever()
        return auth_code
    except Exception as e:
        logger.error(f"Local auth server error: {e}")
        return None
