"""Synthetic schema fixtures only; never source screenshots or research evidence."""
import base64,copy,hashlib,unittest
from frameworks import validate_hero_image
from sampling_plan import plan,years_before

def screenshot_fixture():
    raw=b'\xff\xd8\xff\xe0TEST_ONLY_SCHEMA_FIXTURE\xff\xd9'
    return dict(kind='website_screenshot',source_url='https://example.org/product',author='Synthetic unit-test fixture',
                captured_at='2026-10-28T18:00:00+08:00',alt='test fixture',caption='Synthetic fixture, never delivered',usage_note='Synthetic metadata for contract tests only',
                data='data:image/jpeg;base64,'+base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest())

class EvidenceRules(unittest.TestCase):
    def test_missing_and_generated_cover_rejected(self):
        with self.assertRaises(ValueError):validate_hero_image(None,required=True)
        a=screenshot_fixture();a['kind']='generated_illustration'
        with self.assertRaises(ValueError):validate_hero_image(a,required=True)
    def test_capture_provenance_and_hash_are_required(self):
        self.assertTrue(validate_hero_image(screenshot_fixture(),required=True))
        for key in ['source_url','captured_at','usage_note','sha256']:
            a=screenshot_fixture();a.pop(key)
            with self.assertRaises(ValueError,msg=key):validate_hero_image(a,required=True)
        a=screenshot_fixture();a['data']+='AAAA'
        with self.assertRaises(ValueError):validate_hero_image(a,required=True)
    def test_user_and_report_screenshots_keep_real_provenance(self):
        for kind in ['user_screenshot','report_screenshot']:
            a=screenshot_fixture();a['kind']=kind
            self.assertTrue(validate_hero_image(a,required=True))
            a.pop('source_url')
            with self.assertRaises(ValueError):validate_hero_image(a,required=True)
    def test_gallery_checks_every_image_in_legacy_and_quantified_reports(self):
        from frameworks import validate_hero_gallery
        from test_report import example
        from build_report import validate
        gallery=[screenshot_fixture(),screenshot_fixture()]
        self.assertEqual(len(validate_hero_gallery({'images':gallery})),2)
        data=example();data['presentation']['hero']['images']=copy.deepcopy(gallery);validate(data)
        data['presentation']['hero']['images'][1]['sha256']='invalid'
        with self.assertRaisesRegex(ValueError,'hash mismatch'):validate(data)
        with self.assertRaisesRegex(ValueError,'at most four'):validate_hero_gallery({'images':gallery*3})
        gallery[1]['source_url']='javascript:alert(1)'
        with self.assertRaisesRegex(ValueError,'URL'):validate_hero_gallery({'images':gallery})
    def test_raw_band_keeps_actual_count_and_effective_gate_separate(self):
        from sampling_plan import raw_collection_plan
        for n in [1499,1734,2000,2389,2501]:
            p=raw_collection_plan(n)
            self.assertEqual(p['actual'],n);self.assertFalse(p['hard_cap']);self.assertFalse(p['truncate_to_target']);self.assertFalse(p['randomize_target'])
        d=self.sample(999);d['metrics']['raw_comment_ids']=2389
        p=plan(d)
        self.assertFalse(p['minimum_met']);self.assertEqual(p['raw_collection']['actual'],2389)
        self.assertNotEqual(p['action'],'complete')
    def test_same_quote_semantic_similarity_needs_reason(self):
        from test_report import example
        from build_report import validate
        d=example();eid=d['evidence'][0]['id'];anchor=d['evidence'][0]['body'][:20]
        st=dict(key='track',label='查看',user_action='查看状态',touchpoint='状态页',backstage='待核',feeling=-1,evidence_ids=[eid],
                feeling_basis=dict(evidence_id=eid,anchor=anchor,interpretation='合成测试的匹配说明',match_type='semantic_similar'))
        d['issues'][0]['insight']=dict(headline='合成测试',journey=dict(stages=[st,dict(st,key='send')],breakpoint='send'))
        with self.assertRaisesRegex(ValueError,'match_reason'):validate(d)
        st['feeling_basis']['match_reason']='原话谈相近的任务，不表示实测此步骤。';validate(d)
        st['quote_matches']=[dict(evidence_id=eid,match_type='semantic_similar',anchor='测试造出的原文并不存在',match_reason='测试相似关系')]
        with self.assertRaisesRegex(ValueError,'anchor'):validate(d)
        st['quote_matches']={}
        with self.assertRaisesRegex(ValueError,'must be a list'):validate(d)
    def sample(self,n):
        return dict(scope=dict(app='测试',start='2025-10-28T00:00:00+08:00',end='2026-10-28T23:59:59+08:00'),metrics=dict(qualified_groups=n,text_groups=4000,window_groups=n))
    def test_years_expand_in_order_and_minimum_stays_effective(self):
        for year in (1,2,3):
            p=plan(self.sample(999),year,True)
            self.assertEqual(p['action'],'expand_window');self.assertEqual(p['next_years'],year+1)
        self.assertEqual(plan(self.sample(999),4,True)['action'],'stop_with_gap')
        self.assertEqual(plan(self.sample(1000),2,True)['action'],'complete_minimum_with_preferred_gap')
        self.assertEqual(plan(self.sample(2000),1)['action'],'complete')
    def test_calendar_leap_day_and_blocked_source(self):
        self.assertTrue(years_before('2024-02-29T23:59:59+08:00',1).startswith('2023-02-28'))
        d=self.sample(30);d['all_available_paths_blocked']=True
        self.assertEqual(plan(d,1,True)['action'],'stop_with_gap')
    def test_zero_qualified_does_not_invent_a_retention_budget(self):
        d=self.sample(0);d['metrics']['window_groups']=120
        self.assertIsNone(plan(d)['budget']);self.assertIn('condition_check',plan(d))

if __name__=='__main__':unittest.main()
