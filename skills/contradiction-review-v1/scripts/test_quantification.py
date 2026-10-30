import copy
import unittest
from quantification import derive, validate_analytics

SCOPE={'app':'示例App','client':'android','start':'2026-01-01T00:00:00+00:00',
       'end':'2026-10-26T16:00:00+00:00','recent_start':'2026-07-28T00:00:00+00:00'}

def row(id,body='视频一直卡住',code='P',basis='self_report',client='unknown',when='2026-07-28T08:00:00+00:00'):
    return dict(kind='comment',id=id,evidence_id='xhs:comment:'+id,platform='xhs',app='示例App',
        body=body,published_at=when,client=client,source_url='https://example.com/post',post_id='p',
        annotation=dict(code=code,basis=basis,anchor=body,context_dependency='none'))

class QuantificationIntegrity(unittest.TestCase):
    def test_missing_labels_are_not_silently_classified(self):
        r=row('1');r['annotation']={}
        with self.assertRaises(ValueError):derive([r],{},SCOPE)
    def test_ids_and_text_groups_have_different_denominators(self):
        a=derive([row('1'),row('2'),row('3','喜欢这个推荐',code='V',basis='direct_preference')],{},SCOPE)
        self.assertEqual(a['metrics']['raw_comment_ids'],3)
        self.assertEqual(a['metrics']['text_groups'],2)
        self.assertEqual(a['metrics']['semantic_groups'],2)
        self.assertEqual(sum(x['value'] for x in a['source_counts']),3)
        self.assertEqual(a['metrics']['qualified_groups'],0)

    def test_self_report_is_not_client_verification(self):
        a=derive([row('1'),row('2','另一个症状',client='android'),row('3','听说很卡',basis='hearsay')],{},SCOPE)
        self.assertEqual(a['metrics']['pv_groups'],3)
        self.assertEqual(a['metrics']['semantic_groups'],2)
        self.assertEqual(a['metrics']['qualified_groups'],1)

    def test_context_variant_not_forced_into_one_category(self):
        a=derive([row('1','同问',code='C',basis='unknown'),row('2','同问',code='U',basis='unknown')],{},SCOPE)
        self.assertEqual(next(x['value'] for x in a['code_counts'] if x['code']=='context_variant'),1)
        self.assertEqual(a['metrics']['semantic_groups'],0)

    def test_explicit_calendar_window_and_unknown_dates_are_preserved(self):
        a=derive([row('1'),row('2','另一条',when=None)],{},SCOPE)
        self.assertEqual(next(x['value'] for x in a['time_counts'] if x['key']=='recent90'),1)
        self.assertEqual(next(x['value'] for x in a['time_counts'] if x['key']=='unknown'),1)

    def test_tampered_chart_count_and_denominator_are_rejected(self):
        a=derive([row('1')],{},SCOPE)
        report={'counts':{'raw_comments':1,'screened_feedback':1,'qualified_in_scope':0},'issues':[],'evidence':[]}
        validate_analytics(a,report)
        bad=copy.deepcopy(a);bad['source_counts'][0]['value']=2
        with self.assertRaises(ValueError):validate_analytics(bad,report)
        bad=copy.deepcopy(a);bad['metrics']['retention_denominator']=99
        with self.assertRaises(ValueError):validate_analytics(bad,report)

    def stance_fixture(self):
        a=derive([row('1','查件方便，但广告遮挡',code='P')],{'I1':{'candidate_ids':['xhs:comment:1']}},SCOPE)
        report={'counts':{'raw_comments':1,'screened_feedback':1,'qualified_in_scope':0},'issues':[{'id':'I1'}],'evidence':[]}
        a['issue_stances']={'I1':[dict(evidence_id='xhs:comment:1',stance='negative',target='广告干扰',anchors=[dict(direction='negative',text='广告遮挡')],note='针对广告评价，不把查件好评迁移到广告。',review_status='model_first_pass')]}
        return a,report

    def test_stance_is_independent_of_function_code(self):
        a,report=self.stance_fixture()
        self.assertEqual(validate_analytics(a,report)['stance_records_checked'],1)
        a['issue_stances']['I1'][0].update(stance='positive',target='查件',anchors=[dict(direction='positive',text='查件方便')])
        validate_analytics(a,report)  # P can contain praise of another explicit target.

    def test_missing_stance_mapping_is_a_blocking_gap(self):
        a,report=self.stance_fixture();a.pop('issue_stances')
        with self.assertRaisesRegex(ValueError,'issue_stances is required'):validate_analytics(a,report)

    def test_stance_cannot_drop_or_duplicate_a_mapped_record(self):
        a,report=self.stance_fixture();a['issue_stances']['I1']=[]
        with self.assertRaisesRegex(ValueError,'stance IDs'):validate_analytics(a,report)
        a,report=self.stance_fixture();a['issue_stances']['I1']*=2
        with self.assertRaisesRegex(ValueError,'stance IDs'):validate_analytics(a,report)

    def test_stance_anchor_must_be_exact_and_directional(self):
        a,report=self.stance_fixture();a['issue_stances']['I1'][0]['anchors'][0]['text']='原文不存在'
        with self.assertRaisesRegex(ValueError,'stance anchor'):validate_analytics(a,report)
        a,report=self.stance_fixture();a['issue_stances']['I1'][0]['stance']='mixed'
        with self.assertRaisesRegex(ValueError,'directional'):validate_analytics(a,report)
        a['issue_stances']['I1'][0]['anchors'].append(dict(direction='positive',text='查件方便'))
        validate_analytics(a,report)

if __name__=='__main__':unittest.main()
