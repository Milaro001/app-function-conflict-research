"""Corpus identity, time and provenance checks using small isolated fixtures."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import sources as m


class SourceIntegrity(unittest.TestCase):
    def test_old_thread_recent_reply_does_not_make_other_comments_recent(self):
        asof=datetime(2026,10,26,tzinfo=timezone.utc)
        self.assertEqual(m.temporal_layer('2020-01-01T00:00:00+08:00',asof),'historical')
        self.assertEqual(m.temporal_layer('2026-10-20T00:00:00+08:00',asof),'recent_90d')
        self.assertEqual(m.temporal_layer('May 12',asof),'undated')
        self.assertEqual(m.temporal_layer('2027-01-01T00:00:00Z',asof),'future_or_clock_error')

    def test_identical_floors_in_different_v2ex_threads_do_not_merge(self):
        with tempfile.TemporaryDirectory() as d:
            for tid in (100,200):
                (Path(d)/f'v2ex-{tid}.json').write_text(json.dumps(dict(topic_id=tid,url='https://v2ex.com/t/'+str(tid),
                    title='网易云音乐',topic_body_with_supplements='题目',collection_date='2026-10-21',
                    posts=[dict(floor=1,text=f'内容{tid}',url='public',created_at_display='May 12')])) ,encoding='utf-8')
            rows,_=m.forum_rows(d,'v2ex')
            records,conflicts=m.annotate(rows,datetime.now(timezone.utc))
            self.assertEqual(len(records),4)
            self.assertFalse(conflicts)
            self.assertEqual(len({r['id'] for r in records if r['kind']=='comment'}),2)
            self.assertTrue(all(r['published_at'] is None for r in records))

    def test_repeated_text_keeps_source_records_but_has_one_text_group(self):
        rows=[dict(platform=p,kind='comment',id='1',body='这个入口 太乱',published_at=None) for p in ('xhs','bili')]
        records,conflicts=m.annotate(rows,datetime.now(timezone.utc))
        self.assertEqual(len(records),2)
        self.assertEqual(len({r['text_group'] for r in records}),1)
        self.assertEqual(sum(bool(r['duplicate_text_of']) for r in records),1)
        self.assertFalse(conflicts)

    def test_symbol_only_body_is_not_qualified_text(self):
        records,_=m.annotate([dict(platform='appbao',kind='comment',id='1',body='👍！！！',published_at=None)],datetime.now(timezone.utc))
        self.assertTrue(records[0]['nonempty_body'])
        self.assertFalse(records[0]['text_usable'])
        self.assertEqual(records[0]['semantic_status'],'not_reviewed')

    def test_latest_completed_pilot_selected_without_cross_app_or_auth_pollution(self):
        with tempfile.TemporaryDirectory() as d:
            for rid,app,mode,date,ids in [('old','网易云音乐','pilot','2026-10-20T00:00:00Z',['1']),
                ('new','网易云音乐','pilot','2026-10-21T00:00:00Z',['1','2']),
                ('other','其他App','pilot','2026-10-22T00:00:00Z',['3']),
                ('auth','网易云音乐','auth','2026-10-23T00:00:00Z',[])]:
                p=Path(d)/'runs'/rid;p.mkdir(parents=True)
                (p/'manifest.json').write_text(json.dumps(dict(run_id=rid,app=app,platform='bili',mode=mode,started_at=date,
                    finished_at=date,status='pilot_finished' if mode=='pilot' else 'authenticated')),encoding='utf-8')
                (p/'records.jsonl').write_text(''.join(json.dumps(dict(platform='bili',kind='comment',id=i,post_id='p',body=i))+'\n' for i in ids),encoding='utf-8')
            rows,meta=m.live_rows(d,'bili','网易云音乐')
            self.assertEqual({r['id'] for r in rows},{'1','2'})
            self.assertEqual(meta['run_id'],'new')
            self.assertTrue(all(r['provenance']['source_sha256'] for r in rows))

    def test_recent_sample_and_earlier_batches_are_merged_once(self):
        with tempfile.TemporaryDirectory() as d:
            for rid,mode,date,ids in [('p1','pilot','2026-10-20T00:00:00Z',['1','2']),
                ('r1','recent_sample','2026-10-21T00:00:00Z',['2','3']),
                ('disc','recent_discover','2026-10-22T00:00:00Z',['9'])]:
                p=Path(d)/'runs'/rid;p.mkdir(parents=True)
                (p/'manifest.json').write_text(json.dumps(dict(run_id=rid,app='菜鸟',platform='xhs',mode=mode,started_at=date,finished_at=date,status='done')),encoding='utf-8')
                (p/'records.jsonl').write_text(''.join(json.dumps(dict(platform='xhs',kind='comment',id=i,post_id='p',body=i))+'\n' for i in ids),encoding='utf-8')
            rows,meta=m.live_rows(d,'xhs','菜鸟')
            self.assertEqual(sorted(r['id'] for r in rows),['1','2','3'])
            self.assertEqual(meta['merged_run_ids'],['p1','r1'])

    def test_wrong_app_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'validation.json').write_text('{}',encoding='utf-8')
            (Path(d)/'comments.json').write_text(json.dumps([dict(app_name='其他App')]),encoding='utf-8')
            with self.assertRaises(ValueError):m.appbao_rows(d,'网易云音乐')


if __name__=='__main__':unittest.main()
