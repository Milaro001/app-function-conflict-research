"""Loopback report preview with explicit user-click submission to one chat."""
import sys
import argparse
import hmac
import json
import re
import secrets
import shutil
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from report_submission import SubmissionStore,InvalidSubmission,SubmissionConflict,queue_message

THREAD_ID=re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$')

def write_clipboard(text):
    subprocess.run(['/usr/bin/pbcopy'],input=text.encode('utf-8'),check=True,timeout=5)

def open_conversation(url):
    subprocess.run(['/usr/bin/open',url],check=True,timeout=5,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def make_server(directory,thread_id,port=4191,clipboard_writer=write_clipboard,conversation_opener=open_conversation,queue_sender=None,state_dir=None):
    if not THREAD_ID.fullmatch(thread_id):raise ValueError('invalid configured thread ID')
    directory=Path(directory).resolve()
    if not (directory/'report.html').is_file():raise ValueError('report.html is required')
    token=secrets.token_urlsafe(32)
    conversation_url='codex://threads/'+thread_id
    submissions=SubmissionStore(directory,thread_id,queue_sender,state_dir) if queue_sender else None
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw):super().__init__(*a,directory=str(directory),**kw)
        def log_message(self,*args):pass  # no feedback text or tokens in logs
        def allowed_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def respond(self,code,value):
            body=json.dumps(value,ensure_ascii=False).encode()
            self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if not self.allowed_host():self.respond(403,{'error':'invalid_host'});return
            if self.path=='/api/session':
                self.respond(200,{'token':token,'conversation_url':conversation_url,'clipboard_available':True,'opens_existing_chat':True,'sends_message':bool(submissions),'submit_available':bool(submissions)});return
            super().do_GET()
        def do_POST(self):
            if not self.allowed_host():self.respond(403,{'error':'invalid_host'});return
            allowed_origin={'http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)}
            if self.headers.get('Origin') not in allowed_origin:self.respond(403,{'error':'invalid_origin'});return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':self.respond(415,{'error':'json_required'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 1<=length<=262144:raise ValueError()
                payload=json.loads(self.rfile.read(length))
                if not isinstance(payload,dict) or not isinstance(payload.get('token'),str):raise ValueError()
            except (ValueError,UnicodeError):self.respond(400,{'error':'invalid_request'});return
            if not hmac.compare_digest(payload['token'],token):self.respond(403,{'error':'invalid_token'});return
            try:
                if self.path=='/api/submit':
                    if submissions is None:self.respond(409,{'error':'direct_submit_unavailable'});return
                    try:result=submissions.submit(payload)
                    except InvalidSubmission as e:self.respond(400,{'error':str(e)});return
                    except SubmissionConflict as e:self.respond(409,{'error':str(e)});return
                    except (OSError,ValueError):self.respond(503,{'error':'report_unavailable'});return
                    self.respond(200 if result['message_queued'] else 202,result);return
                if self.path=='/api/clipboard':
                    text=payload.get('text')
                    if not isinstance(text,str) or not text.strip() or len(text)>100000:self.respond(400,{'error':'invalid_text'});return
                    clipboard_writer(text);self.respond(200,{'copied':True,'method':'local_clipboard'});return
                if self.path=='/api/open-conversation':
                    # The caller cannot supply an arbitrary URL or command.
                    conversation_opener(conversation_url)
                    self.respond(200,{'open_requested':True,'conversation_url':conversation_url,'message_sent':False});return
                self.respond(404,{'error':'unknown_action'})
            except (OSError,subprocess.SubprocessError):self.respond(503,{'error':'local_action_unavailable'})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--thread-id',required=True)
    parser.add_argument('--port',type=int,default=4191)
    parser.add_argument('--codex',type=Path,default=shutil.which('codex'))
    args=parser.parse_args()
    sender=(lambda thread,text:queue_message(args.codex,thread,text)) if args.codex and args.codex.is_file() else None
    server=make_server(args.directory,args.thread_id,args.port,queue_sender=sender)
    print(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/report.html','conversation_url':'codex://threads/'+args.thread_id,'sends_messages_on_user_click':bool(sender)}),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__ == '__main__':
    # Windows consoles often use GBK; never crash on characters they cannot show.
    for _s in (sys.stdout,sys.stderr):
        if hasattr(_s,'reconfigure'):_s.reconfigure(errors='backslashreplace')
    main()
