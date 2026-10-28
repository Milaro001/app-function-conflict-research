"""Submission integrity: fixed recipient, chosen format and no duplicate sends."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import report_submission as m

THREAD='11111111-1111-4111-8111-111111111111'
REQUEST='22222222-2222-4222-8222-222222222222'
QUEUE='33333333-3333-4333-8333-333333333333'

class SubmissionIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.sent=[]
        (self.root/'report-data.json').write_text(json.dumps({'app':'抖音','issues':[{'id':'D1','decision_object':'评论状态'}]},ensure_ascii=False),encoding='utf-8')
        (self.root/'delivery-manifest.json').write_text(json.dumps({'bundle_id':'bundle'}),encoding='utf-8')
        def sender(thread,text):self.sent.append((thread,text));return QUEUE
        self.store=m.SubmissionStore(self.root,THREAD,sender,self.root/'private')
        self.payload={'request_id':REQUEST,'bundle_id':'bundle','issue_id':'D1','decision':{'g3':'adopt','delivery_format':'docx','reason':'保留状态说明'}}
    def tearDown(self):self.temp.cleanup()
    def test_selected_format_reaches_only_fixed_chat_and_repeat_does_not_send_again(self):
        first=self.store.submit(self.payload);second=self.store.submit(self.payload)
        self.assertTrue(first['message_queued']);self.assertTrue(second['replayed']);self.assertEqual(len(self.sent),1)
        self.assertEqual(self.sent[0][0],THREAD);self.assertIn('Word（.docx）',self.sent[0][1]);self.assertIn('保留状态说明',self.sent[0][1])
        self.assertFalse(json.loads((self.root/'private'/f'{REQUEST}.json').read_text(encoding='utf-8'))['external_approval'])
    def test_id_cannot_be_reused_for_a_different_task(self):
        self.store.submit(self.payload);self.payload['decision']['delivery_format']='pptx'
        with self.assertRaises(m.SubmissionConflict):self.store.submit(self.payload)
        self.assertEqual(len(self.sent),1)
    def test_outdated_report_and_bad_issue_cannot_start_work(self):
        self.payload['bundle_id']='old'
        with self.assertRaises(m.SubmissionConflict):self.store.submit(self.payload)
        self.payload['bundle_id']='bundle';self.payload['issue_id']='not-present'
        with self.assertRaises(m.InvalidSubmission):self.store.submit(self.payload)
        self.assertEqual(self.sent,[])
    def test_uncertain_acknowledgement_is_not_automatically_resent(self):
        count=[]
        def fail(thread,text):count.append(1);raise TimeoutError()
        self.store.sender=fail
        self.assertEqual(self.store.submit(self.payload)['status'],'unconfirmed')
        self.assertEqual(self.store.submit(self.payload)['status'],'unconfirmed');self.assertEqual(len(count),1)
    def test_hidden_format_does_not_change_a_collection_request(self):
        normalized=m.normalize_decision({'g3':'supplement','delivery_format':'pptx','platforms':['xhs'],'action_focus':'近30天'})
        self.assertIsNone(normalized['delivery_format']);self.assertEqual(normalized['platforms'],['xhs'])
    def test_cli_uses_arguments_and_requires_receipt_for_exact_thread(self):
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=f'Queued message {QUEUE} for thread {THREAD}.')) as run:
            self.assertEqual(m.queue_message('/path/codex',THREAD,'literal $()\n反馈'),QUEUE)
            self.assertEqual(run.call_args.args[0],['/path/codex','queue','--thread',THREAD,'--message','literal $()\n反馈'])
            self.assertNotIn('shell',run.call_args.kwargs)
    def test_malformed_actions_do_not_escape_validation(self):
        for d in [{'g3':{}},{'g3':'adopt','delivery_format':{}},{'g3':'supplement','platforms':[{}]}]:
            with self.assertRaises(m.InvalidSubmission):m.normalize_decision(d)

if __name__=='__main__':unittest.main()
