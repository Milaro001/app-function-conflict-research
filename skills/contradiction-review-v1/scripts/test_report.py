"""Report evidence invariants; no collection or external network access."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import build_report as m


def example():
    data=json.loads((m.SKILL/'assets/report.example.json').read_text(encoding='utf-8'))
    from test_evidence_rules import screenshot_fixture
    data['presentation']={'hero':{'image':screenshot_fixture()}}
    return data


class ReportIntegrity(unittest.TestCase):
    def test_valid_report_produces_inspectable_offline_bundle_without_human_approval(self):
        data=example()
        with tempfile.TemporaryDirectory() as folder:
            manifest=m.build(data,folder)
            self.assertEqual(len(manifest['files']),4)
            self.assertEqual(manifest['human_review_status'],'unreviewed')
            receipt=json.loads((Path(folder)/'check-report.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['structural_checks']['exact_anchors_checked'],4)
            self.assertEqual(receipt['human_G2'],'unreviewed');self.assertEqual(receipt['human_G3'],'unreviewed')

    def test_misattributed_quote_and_missing_source_cannot_render(self):
        data=example();data['issues'][0]['anchors'][0]['anchor']='invented unsupported statement'
        with self.assertRaises(ValueError):m.render(data)
        data=example();data['evidence'][0]['source_url']=None
        with self.assertRaises(ValueError):m.render(data)

    def test_untrusted_comment_cannot_close_the_json_block_or_execute_a_link(self):
        data=example();danger='</script><script>window.PWNED=true</script>'
        data['evidence'][0]['body']+=danger
        html,_,_=m.render(data)
        self.assertNotIn(danger,html);self.assertIn('\\u003c/script\\u003e',html)
        data['evidence'][0]['source_url']='javascript:alert(1)'
        with self.assertRaises(ValueError):m.render(data)

    def test_missing_scope_count_is_unknown_and_cannot_satisfy_main_collection(self):
        data=example();self.assertIsNone(data['counts']['qualified_in_scope'])
        data['issues'][0]['main_collection_eligible']=True
        with self.assertRaises(ValueError):m.render(data)

    def test_recent_post_link_cannot_execute_a_source_instruction(self):
        data=example();data['sources'][0]['recent_posts']=[{'id':'bad','title':'source title','source_url':'javascript:alert(1)'}]
        with self.assertRaises(ValueError):m.render(data)
        data=example();data['counts']['qualified_in_scope']=1000
        with self.assertRaises(ValueError):m.render(data)

    def test_empty_evidence_creates_a_gap_report_not_an_invented_issue(self):
        data=example();data.update(issues=[],evidence=[]);data['counts']['raw_comments']=0
        _,checks,_=m.render(data)
        self.assertEqual(checks,{'issues':0,'evidence':0,'exact_anchors_checked':0,'issues_with_insight':0})

    def test_changing_original_evidence_changes_the_local_review_namespace(self):
        data=example();_,_,first=m.render(data);data['evidence'][0]['body']+=' revised snapshot'
        _,_,second=m.render(data)
        self.assertNotEqual(first,second)

    def test_journey_interpretation_cannot_quote_another_source_or_invent_an_anchor(self):
        data=example();eid=data['evidence'][0]['id'];body=data['evidence'][0]['body']
        stage={'key':'discover','label':'进入页面','user_action':'打开产品','touchpoint':'入口','backstage':'加载服务待核','feeling':-1,'evidence_ids':[eid],
               'feeling_basis':{'evidence_id':eid,'anchor':body[:20],'interpretation':'依据原话作定性解读，不是实测。'}}
        data['issues'][0]['insight']={'headline':'先确认入口问题','journey':{'stages':[stage,dict(stage,key='pay',label='完成任务')],'breakpoint':'pay'}}
        m.render(data)
        stage['feeling_basis']['anchor']='invented interpretation presented as a quote'
        with self.assertRaises(ValueError):m.render(data)
        stage['feeling_basis']['anchor']=body[:20];stage['feeling_basis']['evidence_id']='missing-source'
        with self.assertRaises(ValueError):m.render(data)

    def test_unknown_journey_is_a_visible_gap_not_a_fabricated_neutral_rating(self):
        data=example();eid=data['evidence'][0]['id']
        stage={'key':'discover','label':'进入页面','user_action':'打开产品','touchpoint':'入口','backstage':'加载服务待核','feeling':None,'evidence_ids':[eid]}
        data['issues'][0]['insight']={'headline':'感受仍需补证','journey':{'stages':[stage,dict(stage,key='pay',label='完成任务')],'breakpoint':'pay'}}
        _,checks,_=m.render(data)
        self.assertEqual(checks['presentation_inputs']['feeling_points_with_sources'],0)
        self.assertTrue(any(g.get('field')=='journey.feeling' for g in checks['presentation_gaps']))

    def test_handoff_configuration_cannot_execute_a_source_url_or_discard_review_choices(self):
        data=example();_,_,before=m.render(data)
        data['handoff']={'conversation_url':'codex://threads/11111111-1111-4111-8111-111111111111','local_bridge':True}
        html,_,after=m.render(data);self.assertEqual(before,after)
        self.assertNotIn('__HANDOFF_SCRIPT__',html)
        for url in ['javascript:alert(1)','codex://threads/new?prompt=send','https://unrelated.example']:
            data['handoff']['conversation_url']=url
            with self.assertRaises(ValueError):m.render(data)


if __name__=='__main__':unittest.main()
