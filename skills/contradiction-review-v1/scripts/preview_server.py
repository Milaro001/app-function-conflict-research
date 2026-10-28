"""Host-neutral loopback preview. No message queue, clipboard, or external actions."""
import sys
import argparse,json
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
class ReadOnlyHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.headers.get('Host') not in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}:
            self.send_error(403);return
        if self.path.startswith('/api/'):
            self.send_error(404);return
        super().do_GET()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--port',type=int,default=4192);a=p.parse_args()
    directory=a.directory.resolve()
    if not (directory/'report.html').is_file():p.error('report.html is required')
    server=ThreadingHTTPServer(('127.0.0.1',a.port),partial(ReadOnlyHandler,directory=str(directory)))
    print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/report.html','direct_submit':False}),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
