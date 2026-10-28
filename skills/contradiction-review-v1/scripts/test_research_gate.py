import unittest
import research_gate as m


def sample(body='日推屏蔽后还重复推荐',rid='1',**changes):
    row=dict(evidence_id=rid,body=body,anchor=body,code='P',app='网易云音乐',client='android',
        source_platform='xhs',source_url='https://www.xiaohongshu.com/explore/example',
        published_at='2026-10-01T00:00:00+08:00',context_dependency='none',basis='self_report',
        review_status='model_first_pass',human_review_status='unreviewed',issue_ids=['recommendation-control'])
    row.update(changes);return row


def run_rows(rows,**scope):
    chosen=dict(app='网易云音乐',client='android',start='2025-10-26T00:00:00+08:00',end='2026-10-26T23:59:59+08:00',target_effective=1)
    chosen.update(scope);return m.evaluate(dict(scope=chosen,records=rows),{'can_expand':False})


class ResearchGateIntegrity(unittest.TestCase):
    def test_emotion_and_event_do_not_erase_concrete_problem(self):
        r=run_rows([sample('气死我了，但日推屏蔽后还重复推荐',emotion='high',event_signal='context_only')])
        self.assertTrue(r['data_quantity_met'])
        self.assertEqual(r['problem_request_groups'],1)

    def test_value_is_usable_but_not_a_problem_request(self):
        row=sample('喜欢一起听歌功能',code='V',basis='direct_preference')
        self.assertTrue(run_rows([row])['data_quantity_met'])
        r=run_rows([row],target_kind='problem_request')
        self.assertFalse(r['data_quantity_met']);self.assertEqual(r['value_preference_groups'],1)

    def test_unknown_and_different_clients_never_become_android(self):
        r=run_rows([sample(rid='1',client='unknown'),sample(rid='2',client='macos')])
        self.assertEqual(r['effective_text_groups'],0)
        self.assertEqual(r['excluded_records'],{'client_unknown':1,'different_client':1})

    def test_old_and_unknown_dates_never_complete_recent_target(self):
        r=run_rows([sample(rid='1',published_at='2020-01-01T00:00:00Z'),sample(rid='2',published_at=None)])
        self.assertFalse(r['data_quantity_met']);self.assertEqual(r['missing_to_target'],1)

    def test_recent_observation_survives_old_duplicate_before_dedup(self):
        r=run_rows([sample(rid='1',published_at='2020-01-01T00:00:00Z'),sample(rid='2'),sample(rid='3')])
        self.assertEqual(r['effective_text_groups'],1)
        self.assertEqual(r['duplicate_text_observations'],1)

    def test_missing_context_and_nonexperience_are_not_qualified(self):
        r=run_rows([sample(rid='1',context_dependency='unresolved'),sample(rid='2',basis='hearsay')])
        self.assertEqual(r['effective_text_groups'],0)

    def test_duplicate_text_cannot_inflate_issue_gate(self):
        r=run_rows([sample(rid=str(i)) for i in range(120)])
        issue=r['issues']['recommendation-control']
        self.assertEqual(issue['related_feedback_groups'],1)
        self.assertFalse(issue['collection_threshold_met'])

    def test_quantity_does_not_pass_human_conflict_or_collection_gate(self):
        r=run_rows([sample()])
        self.assertTrue(r['data_quantity_met']);self.assertFalse(r['collection_technical_gate'])
        self.assertEqual(r['human_gate_status'],'not_assessed');self.assertEqual(r['conflict_status'],'not_assessed')

    def test_invalid_anchor_and_motive_label_are_rejected(self):
        for changes in ({'anchor':'原文没有这句话'},{'code':'revenge_user'}):
            with self.assertRaises(ValueError):run_rows([sample(**changes)])

    def test_inconsistent_same_text_labels_need_adjudication(self):
        with self.assertRaises(ValueError):run_rows([sample(rid='1'),sample(rid='2',code='V')])

    def test_different_app_disabled_source_and_missing_provenance_do_not_count(self):
        r=run_rows([sample(rid='1',app='QQ音乐'),sample(rid='2',source_platform='maimai'),sample(rid='3',source_url=None)])
        self.assertEqual(r['effective_text_groups'],0)
        self.assertEqual(sum(r['excluded_records'].values()),3)

    def test_newly_enabled_sources_use_same_semantic_scope_gate(self):
        for platform in ('wb','douyin','zhihu'):
            self.assertTrue(run_rows([sample(source_platform=platform)])['data_quantity_met'])
            self.assertFalse(run_rows([sample(source_platform=platform,context_dependency='unresolved')])['data_quantity_met'])

    def test_named_version_is_not_satisfied_by_unknown_or_another_version(self):
        r=run_rows([sample(rid='1'),sample(rid='2',version='8.0')],version='9.0')
        self.assertEqual(r['excluded_records'],{'version_unknown':1,'different_version':1})

    def test_selected_payment_condition_requires_observed_matching_label(self):
        r=run_rows([sample(rid='1'),sample(rid='2',payment='free'),sample(rid='3',payment='paid')],payment='paid')
        self.assertEqual(r['effective_text_groups'],1)
        self.assertEqual(r['excluded_records'],{'payment_unknown':1,'different_payment_condition':1})

    def test_focused_issue_does_not_count_other_app_problems(self):
        r=run_rows([sample()],issue_ids=['community-entry'])
        self.assertFalse(r['data_quantity_met']);self.assertEqual(r['excluded_records'],{'issue_outside_scope':1})


if __name__=='__main__':unittest.main()
