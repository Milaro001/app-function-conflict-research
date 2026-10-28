"""Local integrity checks; no network and no semantic-accuracy claims."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('collection',Path(__file__).with_name('collect.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeAuthor:
    def author(self,value):
        return 'anonymous' if value else None


class CollectionIntegrity(unittest.TestCase):
    def test_weibo_self_root_is_a_main_comment_not_its_own_child(self):
        row=m.normalize_comment('wb','p',{'id':'10','rootid':'10','text':'specific feedback'},FakeAuthor())
        self.assertEqual(row['level'],1);self.assertIsNone(row['parent_id'])
        self.assertEqual(row['root_id'],'10')
        child=m.normalize_comment('wb','p',{'id':'11','rootid':'10','text':'reply'},FakeAuthor(),root='10')
        self.assertEqual(child['level'],2);self.assertEqual(child['root_id'],'10')
    def test_weibo_nested_cards_and_html_do_not_lose_post_text(self):
        posts=m.weibo_cards([{'card_group':[{'mblog':{'id':'1','text':'改版<br>太乱<img alt="[哭]" src="x">','created_at':'Wed May 01 12:00:00 +0800 2024'}}]}])
        post=m.normalize_post('wb','1',posts[0])
        self.assertEqual(post['body'],'改版\n太乱[哭]')
        self.assertEqual(post['published_at'],'2024-05-01T04:00:00+00:00')
        self.assertNotIn('user',post)

    def test_weibo_preview_reply_is_not_invented_as_direct_reply(self):
        item=m.normalize_comment('wb','p',{'id':12,'rootid':10,'text':'<a>回复</a>：入口在哪'},FakeAuthor(),root='10')
        self.assertEqual(item['level'],2)
        self.assertEqual(item['root_id'],'10')
        self.assertIsNone(item['reply_to_id'])
        self.assertEqual(item['parent_relation'],'root_container')

    def test_nested_bili_details_preserve_original_post_context(self):
        post=m.normalize_post('bili','20',{'View':{'title':'网易云音乐改版','desc':'演示播放器入口','bvid':'BV-demo','pubdate':1700000000,'stat':{'reply':56}}})
        self.assertEqual(post['title'],'网易云音乐改版')
        self.assertEqual(post['body'],'演示播放器入口')
        self.assertEqual(post['declared_comments'],56)
        self.assertTrue(post['published_at'])

    def test_empty_post_context_is_not_reported_as_complete(self):
        with self.assertRaises(ValueError):m.normalize_post('bili','20',{})
        with self.assertRaises(ValueError):m.normalize_post('xhs','20',{})

    def test_bili_reply_keeps_root_and_direct_target_separate(self):
        raw={'rpid':13,'root':10,'parent':12,'content':{'message':'回复上一条'},'member':{'mid':123},'ctime':1700000000}
        item=m.normalize_comment('bili','20',raw,FakeAuthor(),root='10')
        self.assertEqual((item['root_id'],item['parent_id'],item['level']),('10','12',2))
        self.assertNotIn('member',item)

    def test_xhs_container_root_survives_missing_reply_target(self):
        item=m.normalize_comment('xhs','p',{'id':'r','content':'这个呢'},FakeAuthor(),root='main')
        self.assertEqual(item['root_id'],'main')
        self.assertEqual(item['parent_relation'],'root_container')
        self.assertIsNone(item['reply_to_id'])

    def test_missing_id_cannot_silently_merge_comments(self):
        with self.assertRaises(ValueError):m.normalize_comment('xhs','p',{'content':'text'},FakeAuthor())

    def test_duplicate_records_and_context_gaps_are_visible(self):
        with tempfile.TemporaryDirectory() as d:
            old_runtime,old_output=m.RUNTIME,m.OUTPUT
            m.RUNTIME,m.OUTPUT=Path(d)/'private',Path(d)/'out'
            try:
                ledger=m.Ledger('xhs','网易云音乐','test',run_id='integrity')
                item=m.normalize_comment('xhs','p',{'id':'r','content':'回复','target_comment':{'id':'missing-target'}},ledger,root='missing-root')
                self.assertTrue(ledger.save(item));self.assertFalse(ledger.save(item))
                counts=ledger.export()
                self.assertEqual(counts['unique_comment_ids'],1)
                self.assertEqual(counts['missing_roots'],['r'])
                self.assertEqual(counts['missing_reply_targets'],['r'])
                ledger.db.close()
            finally:m.RUNTIME,m.OUTPUT=old_runtime,old_output

    def test_exception_outputs_do_not_export_secret_body(self):
        self.assertEqual(m.safe_error(Exception('HTTP 403 Cookie=do-not-export')),'access_denied')
        self.assertEqual(m.safe_error(TimeoutError('private response body')),'network_error')

    def test_gate_cannot_pass_an_unrun_platform(self):
        with tempfile.TemporaryDirectory() as d:
            old=m.OUTPUT;m.OUTPUT=Path(d)
            try:
                m.gate()
                result=json.loads((Path(d)/'expansion-gate.json').read_text(encoding='utf-8'))
                self.assertFalse(result['can_expand'])
                self.assertFalse(result['platforms']['xhs']['passed'])
            finally:m.OUTPUT=old


    def test_gate_judges_each_platform_and_counts_recent_samples(self):
        with tempfile.TemporaryDirectory() as d:
            old=m.OUTPUT,m.CFG.get('source_scope');m.OUTPUT=Path(d)
            m.CFG['source_scope']=dict(core_social=['xhs','zhihu'],enabled_support_social=['wb'],local_adapter_pending=['zhihu'])
            try:
                run=Path(d)/'runs'/'r1';run.mkdir(parents=True)
                (run/'manifest.json').write_text(json.dumps(dict(platform='xhs',mode='recent_sample',status='recent_sample_finished',
                    started_at='2026-10-27T00:00:00Z',finished_at='2026-10-27T00:05:00Z',browser_profile='p',errors=[],
                    auth_checks=[dict(round='initial',status='authenticated',profile_reused=True)],counts=dict(posts=3),
                    threads=[dict(kind='main',stop_reason='source_end_confirmed'),dict(kind='reply',stop_reason='embedded_preview_only')])),encoding='utf-8')
                m.gate()
                r=json.loads((Path(d)/'expansion-gate.json').read_text(encoding='utf-8'))
                self.assertEqual(r['ready_platforms'],['xhs'])
                self.assertIn('replies_preview_only_source_limit',r['platforms']['xhs']['warnings'])
                self.assertEqual(r['platforms']['zhihu']['status'],'adapter_pending')
                self.assertEqual(r['platforms']['wb']['status'],'not_run')
                self.assertTrue(r['can_expand_any']);self.assertFalse(r['can_expand'])
            finally:
                m.OUTPUT=old[0];m.CFG['source_scope']=old[1]


if __name__=='__main__':unittest.main()
