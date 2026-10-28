"""Offline checks for the added sources, keyword plan and the condition-pending tier."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import appbao
import appstore
import collect
import keywords
import research_gate
import sources
import web_import


class KeywordPlan(unittest.TestCase):
    def test_feature_terms_first_and_bounded(self):
        plan=keywords.build('菜鸟',['取件码','寄件'],['快递100'])
        self.assertEqual(plan['platforms']['zhihu'][0],'菜鸟 取件码')
        self.assertTrue(all(len(v)<=12 for v in plan['platforms'].values()))
        self.assertIn('菜鸟 闪退 卡顿',plan['intents']['problem'])


class AppBao(unittest.TestCase):
    def test_collect_stops_at_since_and_writes_importable_folder(self):
        def fake_page(pkg,appid,start,sort,guid,size=10):
            if sort=='hot':return []
            base=1790000000-start*86400*40
            return [dict(user=dict(nickName='a*'),comment=dict(commentID=f'{start}{i}',content=f'评论{start}-{i}',createTime=base-i,
                mulDimensionScore=dict(total=3),replyNum='')) for i in range(10)]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(appbao,'page',fake_page), mock.patch.object(appbao.time,'sleep'):
            args=type('A',(),dict(app='菜鸟',pkg='com.x',appid='1',since='2026-05-01T00:00:00+00:00',max_pages=50,hot_pages=1,max_records=3000,delay=0,output=d))
            appbao.collect(args)
            v=json.loads((Path(d)/'validation.json').read_text(encoding='utf-8'))
            self.assertEqual(v['stop_reasons']['time'],'reached_since_date')
            rows,meta=sources.appbao_rows(d,'菜鸟')
            self.assertTrue(rows and all(r['client']=='android' and r['client_basis']=='store_listing' for r in rows))


class AppStore(unittest.TestCase):
    def test_feed_entries_keep_version_and_ios_label(self):
        entry=lambda i:{'id':{'label':str(i)},'content':{'label':'取件码不显示'},'im:rating':{'label':'2'},'im:version':{'label':'8.11.1'},
            'updated':{'label':'2026-10-20T10:00:00-07:00'},'title':{'label':'t'},'author':{'name':{'label':'u'}}}
        feeds={1:{'feed':{'entry':[entry(1),entry(2)]}},2:{'feed':{}}}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(appstore,'get',lambda url:feeds[int(url.split('page=')[1].split('/')[0])]), mock.patch.object(appstore.time,'sleep'):
            args=type('A',(),dict(app='菜鸟',track_id='9',country='cn',max_pages=10,sort=['mostrecent'],delay=0,output=d))
            appstore.collect(args)
            rows,_=sources.appstore_rows(d,'菜鸟')
            self.assertEqual(len(rows),2)
            self.assertEqual({r['client'] for r in rows},{'ios'})
            self.assertEqual(rows[0]['version'],'8.11.1')


class WebImport(unittest.TestCase):
    def test_rejects_missing_url_and_keeps_unknown_dates(self):
        rows=[dict(site='黑猫投诉',url='https://tousu.example/1',body='驿站不给取件码',published_at='2026-09-01'),
              dict(url='',body='x'),dict(url='https://a.example/2',body='  ')]
        records,errors=web_import.convert(rows,'菜鸟')
        self.assertEqual(len(records),1)
        self.assertIsNone(records[0]['published_at'])
        self.assertEqual([e['reason'] for e in errors],['needs_public_http_url','empty_body'])


class PendingTier(unittest.TestCase):
    def test_unknown_client_is_pending_not_strict_and_known_mismatch_is_neither(self):
        base=dict(code='P',body='',anchor='',source_platform='xhs',source_url='https://x',app='菜鸟',basis='self_report',
            context_dependency='none',review_status='model_first_pass',published_at='2026-09-01T00:00:00+00:00')
        rec=lambda i,client:dict(base,evidence_id=str(i),body=f'取件码{i}不显示',anchor=f'取件码{i}',client=client)
        data=dict(scope=dict(app='菜鸟',client='android',start='2025-10-27T00:00:00+00:00',end='2026-10-27T00:00:00+00:00',target_effective=3),
            records=[rec(1,'android'),rec(2,'unknown'),rec(3,'ios')])
        out=research_gate.evaluate(data)
        self.assertEqual(out['tiers']['strict_qualified'],1)
        self.assertEqual(out['tiers']['condition_pending'],1)
        self.assertEqual(out['missing_to_target_including_pending'],1)


class ZhihuNormalise(unittest.TestCase):
    def test_answer_and_reply_shape(self):
        post=collect.normalize_post('zhihu','42',dict(content_id='42',content_type='answer',title='如何评价菜鸟',content_text='取件码经常不显示',
            created_time=1790000000,comment_count=3,content_url='https://www.zhihu.com/question/1/answer/42'))
        self.assertEqual(post['source_url'],'https://www.zhihu.com/question/1/answer/42')
        ledger=type('L',(),dict(author=lambda self,v:'h'))()
        reply=collect.normalize_comment('zhihu','42',dict(comment_id='7',parent_comment_id='5',content='同感',publish_time=1790000100,creator_hash='x'),ledger,root='5')
        self.assertEqual((reply['level'],reply['root_id'],reply['reply_to_id']),(2,'5','5'))





class AutoSelect(unittest.TestCase):
    def test_requires_topic_dedupes_ads_and_rotates_keywords(self):
        import recent_sample
        item=lambda title,ts:{'title':title,'pubdate':ts}
        items={'1':{'item':item('菜鸟驿站猫猫',1790000000),'keywords':['k1'],'order':0},
               '2':{'item':item('菜鸟 取件码不显示',1790000100),'keywords':['k1'],'order':1},
               '3':{'item':item('菜鸟 取件码不显示',1790000200),'keywords':['k1'],'order':2},
               '4':{'item':item('菜鸟App寄件太慢',1780000000),'keywords':['k2'],'order':3},
               '5':{'item':item('游戏菜鸟上分',1790000300),'keywords':['k2'],'order':4}}
        picked=recent_sample.auto_select('菜鸟',items,5,None,('取件码','寄件','驿站'))
        self.assertEqual(set(picked),{'1','3','4'})
        self.assertEqual(picked.index('3'),0 if picked[0]!='4' else 1)

class LabelBatches(unittest.TestCase):
    def test_split_once_per_text_group_and_merge_validates_anchor(self):
        import label_batches,quantification,research_gate
        rows=[dict(platform='xhs',kind='post',id='p',post_id='p',title='菜鸟取件码',body='',text_usable=True,text_group='tp',evidence_id='xhs:post:p'),
              dict(platform='xhs',kind='comment',id='1',post_id='p',body='取件码不显示',text_usable=True,text_group='g1',evidence_id='xhs:comment:1',source_url='https://x.example/1',published_at='2026-09-01T00:00:00+00:00'),
              dict(platform='wb',kind='comment',id='2',post_id='q',body='取件码不显示',text_usable=True,text_group='g1',evidence_id='wb:comment:2',published_at='2026-09-02T00:00:00+00:00'),
              dict(platform='wb',kind='comment',id='3',post_id='q',body='哈哈',text_usable=True,text_group='g2',evidence_id='wb:comment:3',published_at='2026-09-02T00:00:00+00:00')]
        with tempfile.TemporaryDirectory() as d:
            corpus=Path(d)/'evidence.jsonl';corpus.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
            label_batches.split(type('A',(),dict(corpus=corpus,app='菜鸟',output=d,size=10,max_chars=600)))
            batch=[json.loads(x) for x in (Path(d)/'batches/batch-001.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(batch),2)
            first=next(x for x in batch if x['body']=='取件码不显示')['evidence_id']
            (Path(d)/'labels/batch-001.jsonl').write_text(json.dumps(dict(evidence_id=first,code='P',anchor='取件码不显示',feature='取件码显示',
                basis='self_report',context_dependency='none',journey_stage='pickup'),ensure_ascii=False)+'\n'+
                json.dumps(dict(evidence_id='wb:comment:3',code='P',anchor='不在原文'),ensure_ascii=False)+'\n',encoding='utf-8')
            label_batches.merge(type('A',(),dict(work=d,client='all',start='2025-10-27T00:00:00+00:00',end='2026-10-27T00:00:00+00:00',target=1)))
            gaps=json.loads((Path(d)/'label-gaps.json').read_text(encoding='utf-8'))
            self.assertEqual(gaps['rejected'],{'anchor_not_in_original':1})
            annotated=[json.loads(x) for x in (Path(d)/'annotated-corpus.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(sum(1 for r in annotated if r.get('annotation')),2)
            gate=research_gate.evaluate(json.loads((Path(d)/'research-gate-input.json').read_text(encoding='utf-8')))
            self.assertEqual(gate['effective_text_groups'],1)


if __name__=='__main__':unittest.main()
