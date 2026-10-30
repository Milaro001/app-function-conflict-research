"""Generated report sharing preserves evidence without a live author receiver."""
import json
from pathlib import Path
import re
import tempfile
import unittest
import build_report
from test_report import example
from export_offline_report import make_offline

class OfflineExport(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.source=self.root/'source';self.output=self.root/'new folder'/'离线报告'
        data=example();data['handoff']={'conversation_url':'codex://threads/11111111-1111-4111-8111-111111111111','local_bridge':True}
        build_report.build(data,self.source)
        self.original=(self.source/'report.html').read_bytes()
    def tearDown(self):self.temp.cleanup()
    def test_reader_export_preserves_all_research_and_never_targets_author_chat(self):
        result=make_offline(self.source,self.output)
        before=json.loads((self.source/'report-data.json').read_text())
        after=json.loads((self.output/'report-data.json').read_text())
        self.assertEqual({k:v for k,v in before.items() if k not in ('handoff','bundle_id')},{k:v for k,v in after.items() if k not in ('handoff','bundle_id')})
        self.assertEqual(after['handoff'],{'local_bridge':False})
        self.assertEqual((self.source/'report.html').read_bytes(),self.original)
        self.assertEqual((self.source/'evidence.csv').read_bytes(),(self.output/'evidence.csv').read_bytes())
        html=(self.output/'report.html').read_text()
        for text in ['codex://','fetch(','/api/submit','/api/session']:self.assertNotIn(text,html)
        self.assertIn('offline_reader_feedback',html);self.assertIn('automatically_submitted:false',html)
        self.assertNotIn("home.href='../打开这里.html'",html)
        self.assertEqual(result['browser_check'],'not run by this command; test file:// with network disabled')
    def test_optional_home_must_be_a_relative_package_link(self):
        make_offline(self.source,self.output,'../开始.html')
        self.assertIn('../开始.html',(self.output/'report.html').read_text())
        for target in ['javascript:alert(1)','https://example.com','file:///private/data','/Users/someone']:
            with self.assertRaises(ValueError):make_offline(self.source,self.output,target)
    def test_original_output_directory_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):make_offline(self.source,self.source)
        self.assertEqual((self.source/'report.html').read_bytes(),self.original)
    def test_incompatible_html_fails_before_writing_an_offline_copy(self):
        (self.source/'report.html').write_text('<p>not a generated report</p>')
        with self.assertRaises(ValueError):make_offline(self.source,self.output)
        self.assertFalse(self.output.exists())

if __name__=='__main__':unittest.main()
