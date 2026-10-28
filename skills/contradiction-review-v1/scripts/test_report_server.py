"""HTTP handoff checks use injected sinks; no real clipboard or app changes."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
import report_server as m

class HandoffServerIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'report.html').write_text('<p>report</p>',encoding='utf-8')
        self.clipboard=[];self.opened=[]
        self.url='codex://threads/11111111-1111-4111-8111-111111111111'
        self.server=m.make_server(self.root,self.url.rsplit('/',1)[-1],0,self.clipboard.append,self.opened.append)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)
        self.token=json.load(urllib.request.urlopen(self.origin+'/api/session'))['token']
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def post(self,path,payload,origin=None):
        req=urllib.request.Request(self.origin+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':origin or self.origin})
        return json.load(urllib.request.urlopen(req))
    def test_copy_preserves_unicode_and_newlines_exactly(self):
        text='抖音反馈\n交付形式：PPT\n说明：保留“已读”场景。'
        self.assertTrue(self.post('/api/clipboard',{'token':self.token,'text':text})['copied'])
        self.assertEqual(self.clipboard,[text])
    def test_another_site_or_missing_token_cannot_change_the_clipboard(self):
        for payload,origin in [({'token':self.token,'text':'no'},'https://unrelated.example'),({'token':'wrong','text':'no'},self.origin)]:
            with self.assertRaises(urllib.error.HTTPError) as e:self.post('/api/clipboard',payload,origin)
            self.assertEqual(e.exception.code,403)
        self.assertEqual(self.clipboard,[])
    def test_return_opens_only_the_configured_chat_without_sending_a_message(self):
        result=self.post('/api/open-conversation',{'token':self.token,'url':'file:///not-allowed'})
        self.assertEqual(self.opened,[self.url]);self.assertFalse(result['message_sent'])

if __name__=='__main__':unittest.main()
