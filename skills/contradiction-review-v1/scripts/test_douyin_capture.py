"""Bounded browser-response parsing and context invariants, using no network."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import collect
from douyin_capture import BrowserCapture, response_kind, search_items, decode_payloads


class Response:
    def __init__(self,path,data,status=200):
        self.url='https://www.douyin.com'+path;self.data=data;self.status=status
    async def json(self):return self.data


class DouyinIntegrity(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=collect.RUNTIME,collect.OUTPUT
        collect.RUNTIME=Path(self.tmp.name)/'runtime';collect.OUTPUT=Path(self.tmp.name)/'out'
        self.ledger=collect.Ledger('douyin','test','pilot',run_id='isolated')
        self.owner=collect.Collector(SimpleNamespace(platform='douyin',max_records=2,keyword='test',interactive=False),self.ledger)
        self.capture=BrowserCapture(self.owner);self.capture.selected.add('p')
        self.capture.search_started=True
    def tearDown(self):
        self.ledger.db.close();collect.RUNTIME,collect.OUTPUT=self.old;self.tmp.cleanup()

    def test_response_whitelist_does_not_capture_other_sites_or_profile_data(self):
        self.assertIsNone(response_kind('https://evil.example/aweme/v1/web/comment/list/'))
        self.assertEqual(response_kind('https://www.douyin.com/aweme/v1/web/comment/list/reply/'),'reply_page')
        self.assertEqual(response_kind('https://www-hj.douyin.com/aweme/v1/web/comment/list/'),'main_page')
        self.assertIsNone(response_kind('https://www.douyin.com/aweme/v1/web/familiar/'))

    def test_search_extracts_only_video_items(self):
        rows=search_items({'data':[{'user_info':{'uid':'private'}},{'aweme_info':{'aweme_id':'1','desc':'test'}}]})
        self.assertEqual([r['aweme_id'] for r in rows],['1'])

    def test_utf8_stream_frames_preserve_data_and_ignore_ack(self):
        values=[{'status_code':0,'data':[{'aweme_info':{'aweme_id':'1','desc':'中文'}}]},{'ack':1},{'data':[],'has_more':1}]
        chunks=[json.dumps(d,ensure_ascii=False).encode('utf-8') for d in values]
        wire=b''.join(hex(len(b))[2:].encode()+b'\r\n'+b+b'\r\n' for b in chunks)+b'0\r\n\r\n'
        self.assertEqual(decode_payloads(wire.decode()),values)
        self.assertEqual(decode_payloads('{"data":[]}'),[{'data':[]}])

    def test_truncated_stream_is_not_an_empty_success(self):
        for text in ('ff\r\n{}\r\n0\r\n','2\r\n{}\r\n'):
            with self.assertRaises(ValueError):decode_payloads(text)

    async def test_verification_payload_never_counts_as_source_end(self):
        await self.capture.consume(Response('/aweme/v1/web/general/search/stream/',
            {'status_code':0,'data':[],'has_more':0,'search_nil_info':{'search_nil_type':'verify_check'}}))
        self.assertTrue(self.capture.verification_signal)
        self.assertFalse(self.ledger.manifest['search_pages'])

    async def test_background_verification_returns_without_opening_or_waiting(self):
        self.capture.verification_signal=True
        with self.assertRaisesRegex(collect.CollectionStop,'needs_interactive_verification'):
            await self.capture.wait_verification()

    async def test_unrelated_cached_search_cannot_enter_current_query(self):
        await self.capture.consume(Response('/aweme/v1/web/general/search/stream/?keyword=other',
            {'status_code':0,'data':[{'aweme_info':{'aweme_id':'1','desc':'unrelated'}}]}))
        self.assertFalse(self.capture.items);self.assertFalse(self.ledger.manifest['search_pages'])

    async def test_missing_has_more_cannot_confirm_end(self):
        await self.capture.consume(Response('/aweme/v1/web/comment/list/?aweme_id=p&cursor=0',
            {'status_code':0,'comments':[{'cid':'1','text':'text','create_time':1700000000,'user':{'uid':'private'}}]}))
        stream=self.capture.streams[('main_page','p',None)]
        self.assertFalse(stream['end']);self.assertEqual(self.ledger.export()['main_comments'],1)
        self.assertNotIn('private',(self.ledger.path/'records.jsonl').read_text(encoding='utf-8'))

    async def test_reply_root_and_direct_target_remain_separate(self):
        await self.capture.consume(Response('/aweme/v1/web/comment/list/reply/?item_id=p&comment_id=root&cursor=0',
            {'status_code':0,'has_more':0,'comments':[{'cid':'r','reply_id':'root','reply_to_reply_id':'missing','text':'reply'}]}))
        counts=self.ledger.export();row=json.loads((self.ledger.path/'records.jsonl').read_text(encoding='utf-8'))
        self.assertEqual((row['root_id'],row['reply_to_id']),('root','missing'))
        self.assertEqual(counts['missing_reply_targets'],['r']);self.assertEqual(counts['missing_roots'],['r'])

    async def test_unselected_recommendation_comments_do_not_enter_sample(self):
        await self.capture.consume(Response('/aweme/v1/web/comment/list/?aweme_id=other',
            {'comments':[{'cid':'1','text':'unrelated'}],'has_more':0}))
        self.assertEqual(self.ledger.export()['records'],0)

    async def test_denied_response_stops_without_recording_or_retrying(self):
        await self.capture.consume(Response('/aweme/v1/web/comment/list/?aweme_id=p',{'secret':'private'},403))
        with self.assertRaises(collect.CollectionStop):await self.capture.settle()
        self.assertEqual(self.ledger.export()['records'],0)

    async def test_global_record_cap_is_preserved_mid_page(self):
        await self.capture.consume(Response('/aweme/v1/web/comment/list/?aweme_id=p',
            {'comments':[{'cid':str(i),'text':str(i)} for i in range(1,6)],'has_more':0}))
        self.assertEqual(self.ledger.export()['unique_comment_ids'],2)
        self.assertEqual(self.capture.failure,'record_limit_reached')
        self.assertFalse(self.capture.streams[('main_page','p',None)]['end'])


if __name__=='__main__':unittest.main()
