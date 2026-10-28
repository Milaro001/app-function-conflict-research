"""A failed search page must not discard the preceding page or leak tokens."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import recent_sample as m


class RecentSearchIntegrity(unittest.IsolatedAsyncioTestCase):
    async def test_time_order_and_partial_discovery_survive_failure(self):
        import vendor_loader;vendor_loader.prepare(m.c.CFG['mediacrawler'])
        calls=[]
        async def search(keyword,**kw):
            calls.append((keyword,kw))
            if kw['page']==2:raise m.c.CollectionStop('access_denied')
            return {'result':[{'aid':1,'title':'App使用体验','pubdate':1700000000,'xsec_token':'private-access-marker'}]}
        async def call(kind,fn,**kw):return await fn()
        with tempfile.TemporaryDirectory() as d:
            previous=m.c.RUNTIME;m.c.RUNTIME=Path(d)/'private'
            try:
                dest=Path(d)/'public';dest.mkdir()
                ledger=SimpleNamespace(run_id='test',path=dest,manifest={'search_pages':[]},event=lambda kind,**kw:dict(kind=kind,**kw),flush=lambda:None)
                owner=SimpleNamespace(platform='bili',call=call,client=SimpleNamespace(search_video_by_keyword=search),ledger=ledger)
                with self.assertRaises(m.c.CollectionStop):await m.discover(owner,['App 功能','App 改版'],2)
                self.assertEqual(calls[0][1]['order'].value,'pubdate')
                self.assertEqual(len(calls),2)
                self.assertEqual(json.loads((dest/'candidates.json').read_text(encoding='utf-8'))[0]['id'],'1')
                self.assertNotIn('private-access-marker',(dest/'candidates.json').read_text(encoding='utf-8'))
                self.assertIn('private-access-marker',(m.c.RUNTIME/'search-candidates/test.json').read_text(encoding='utf-8'))
            finally:m.c.RUNTIME=previous

if __name__=='__main__':unittest.main()
