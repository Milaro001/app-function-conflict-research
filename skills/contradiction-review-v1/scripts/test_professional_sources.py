"""Professional article identity, selection, count separation and report-link checks."""
import copy
import json
import tempfile
import unittest
import io
import contextlib
import sys
import time
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import professional_sources as m
import quantification
import build_report
import collect_all
from test_report import example

class ProfessionalSources(unittest.TestCase):
    def test_four_sites_are_first_round_and_have_no_article_quota(self):
        p=m.make_plan('学习通',['作业提交'],['雨课堂'])
        self.assertEqual({s['id'] for s in p['sites']},{'woshipm','uisdc','ui_cn','zcool'})
        self.assertIsNone(p['article_target']);self.assertIsNone(p['minimum_per_site'])
        self.assertFalse(p['counts_as_user_feedback'])
        self.assertTrue(all('学习通' in s['queries'][0]['query'] for s in p['sites']))
        self.assertTrue(all(s['secondary_queries'] for s in p['sites']))

    def test_search_links_are_real_article_urls_not_navigation_or_other_hosts(self):
        html='<a href="https://www.woshipm.com/pd/123.html">学习通分析</a><a href="https://evil.example/pd/1.html">学习通</a><a href="/about">关于</a>'
        rows=m.discover(html,'https://www.woshipm.com/',m.SITES['woshipm'])
        self.assertEqual([r['url'] for r in rows],['https://www.woshipm.com/pd/123.html'])
        self.assertFalse(m.allowed('https://woshipm.com.evil.example/pd/1.html',m.SITES['woshipm']))

    def test_parser_separates_article_body_and_metadata_from_scripts_navigation(self):
        p=m.Page();p.feed('<title>文章</title><meta name="author" content="某作者"><nav>菜单</nav><div class="article--content"><p>保存失败需要给出重试入口。</p><script>secret()</script><p>这是具体流程。</p></div>')
        r=p.article();self.assertIn('保存失败',r['body']);self.assertNotIn('菜单',r['body']);self.assertNotIn('secret',r['body']);self.assertEqual(r['author'],'某作者')
        p=m.Page();p.feed('<nav>只有导航</nav>');self.assertEqual(p.article()['body'],'')

    def test_denied_source_is_stopped_not_retried_or_relabeled_no_results(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m.Fetcher,'get',side_effect=m.FetchError('access_denied')) as fetch:
            spec=m.make_plan('学习通',sites=['woshipm'])['sites'][0]
            meta,rows=m.collect_site(spec,'学习通',Path(d),3,8)
            self.assertEqual(fetch.call_count,1);self.assertEqual(meta['status'],'access_denied');self.assertEqual(rows,[])

    def test_footer_articles_and_creator_agreement_are_not_fetched_as_product_research(self):
        html='<a href="/it/123.html">创作者协议</a><a href="/pd/124.html">其他产品的首页推荐</a>'
        with tempfile.TemporaryDirectory() as d,patch.object(m.Fetcher,'get',return_value=(html,'https://www.woshipm.com/')) as fetch:
            spec=m.make_plan('学习通',sites=['woshipm'])['sites'][0]
            meta,rows=m.collect_site(spec,'学习通',Path(d),1,8)
            self.assertEqual(fetch.call_count,1);self.assertEqual(rows,[]);self.assertEqual(meta['status'],'needs_host_search')

    def make_run(self,root):
        run=root/'professional'/'run';run.mkdir(parents=True)
        record=dict(id='pro1',platform='web',kind='post',app='学习通',site='人人都是产品经理',title='流程分析',body='保存失败需要重试。\u2028原文后半段。',source_url='https://www.woshipm.com/pd/123.html',material_role='professional_reference_candidate')
        m.jsonlines(run/'records.jsonl',[record]);m.write(run/'manifest.json',dict(app='学习通',bodies_obtained=1,selected_articles=0,sites=[]))
        return run,record

    def test_unreviewed_articles_never_enter_corpus_and_zero_selected_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run,_=self.make_run(root)
            self.assertEqual(m.merged(root,'学习通')[0],[])
            self.assertEqual(m.review(run,[dict(id='pro1',decision='exclude',rationale='对象不符')]),[])
            self.assertEqual(m.merged(root,'学习通')[0],[])
            self.assertEqual(m.merged(root,'其他App')[1]['status'],'not_run')

    def test_selection_keeps_exact_excerpt_and_never_becomes_comment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run,record=self.make_run(root)
            decision=dict(id='pro1',decision='include',rationale='同一保存失败任务',app_relation='same_task',viewpoint='提供重试反馈',excerpt='保存失败需要重试。',limitations='旧版本案例，仍需本轮验证')
            selected=m.review(run,[decision]);self.assertEqual(selected[0]['kind'],'post');self.assertEqual(selected[0]['body'],decision['excerpt'])
            self.assertNotIn('后半段',selected[0]['body'])
            self.assertEqual(m.merged(root,'学习通')[1]['selected_articles'],1)
            scope=dict(app='学习通',client='android',start='2025-01-01T00:00:00Z',end='2026-10-29T00:00:00Z')
            self.assertEqual(quantification.derive(selected,{},scope)['metrics']['raw_comment_ids'],0)
            decision['excerpt']='不是原文'
            with self.assertRaises(ValueError):m.review(run,[decision])

    def test_unicode_line_separators_do_not_break_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            run,record=self.make_run(Path(d))
            self.assertEqual(len((run/'records.jsonl').read_text().splitlines()),1)
            self.assertEqual(m.readlines(run/'records.jsonl')[0]['body'],record['body'])

class ProfessionalReport(unittest.TestCase):
    def fixture(self):
        data=example();eid='web:post:pro1';body='保存失败需要重试。'
        data['evidence'].append(dict(id=eid,platform='web',kind='post',material_role='professional_reference',body=body,source_url='https://www.woshipm.com/pd/123.html'))
        data['professional_references']=[dict(id='pro1',evidence_id=eid,title='流程分析',site='人人都是产品经理',anchor=body,app_relation='same_task',viewpoint='给失败后的重试入口',quality_reason='同任务的具体改法',limitations='测试示例，非本轮研究发现',counts_as_user_feedback=False)]
        data['issues'][0]['options'][0]['reference_links']=[dict(reference_id='pro1',user_evidence_ids=[data['evidence'][0]['id']],takeaway='参考显式重试',adaptation='按当前任务改写提示',boundary='需要本轮验证')]
        return data
    def test_reference_can_render_with_separate_counts(self):
        d=self.fixture();before=copy.deepcopy(d['counts']);html,_,_=build_report.render(d)
        self.assertEqual(d['counts'],before);self.assertIn('drawProfessionalLinks',html)
    def test_unknown_reference_and_article_as_user_feedback_are_rejected(self):
        for mutation in ['unknown','article','counts','anchor','boundary']:
            d=self.fixture();link=d['issues'][0]['options'][0]['reference_links'][0]
            if mutation=='unknown':link['reference_id']='missing'
            elif mutation=='article':link['user_evidence_ids']=[d['professional_references'][0]['evidence_id']]
            elif mutation=='counts':d['professional_references'][0]['counts_as_user_feedback']=True
            elif mutation=='anchor':d['professional_references'][0]['anchor']='伪造'
            else:link['boundary']=''
            with self.assertRaises(ValueError):build_report.render(d)

class CollectionOrder(unittest.TestCase):
    def test_professional_discovery_launches_first_and_article_count_is_not_comments(self):
        calls=[]
        with tempfile.TemporaryDirectory() as d:
            def launch(name,cmd,logs):
                calls.append((name,cmd));path=logs/(name+'.log')
                result={'status':'professional_review_pending','bodies_obtained':2,'selected_articles':0} if name=='professional' else {'comments':5}
                path.write_text(json.dumps(result));log=path.open('a')
                return dict(name=name,path=path,log=log,started=time.monotonic(),proc=SimpleNamespace(poll=lambda:0,returncode=0))
            with patch.object(collect_all,'cfg',return_value={'python':sys.executable,'output':d}),patch.object(collect_all,'launch',side_effect=launch),patch.object(collect_all.subprocess,'run',return_value=SimpleNamespace(stdout='{}')),patch.object(sys,'argv',['collect_all.py','--app','学习通','--feature','作业','--platforms','appbao']),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(collect_all.main(),0)
            self.assertEqual([x[0] for x in calls],['professional','appbao'])
            summary=json.loads(next((Path(d)/'collect-all').glob('*/collection-summary.json')).read_text())
            pro=next(r for r in summary['sources'] if r['source']=='professional')
            self.assertEqual(pro['comments'],0);self.assertEqual(pro['posts'],2)
            self.assertIsNone(summary['professional_reference_policy']['article_target'])

if __name__=='__main__':unittest.main()
