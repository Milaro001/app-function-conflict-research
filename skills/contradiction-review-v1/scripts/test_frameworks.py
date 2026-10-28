import copy,unittest
from frameworks import validate_frameworks
class FrameworkBoundaries(unittest.TestCase):
    def fixture(self):
        return {'records':[{'evidence_id':'x:1','body':'取件码不显示','semantic_candidate':True}], 'issue_stats':[{'record_ids':['x:1']}], 'frameworks':{'service_quality':{'measurement_status':'not_conducted','source_url':'https://example.org/method','annotations':[{'evidence_id':'x:1','review_status':'model_first_pass','dimensions':[{'key':'reliability','anchor':'取件码不显示','reason':'材料涉及信息可用性。'}]}]}}}
    def test_exact_mapping_without_fabricated_rating(self):
        self.assertEqual(validate_frameworks(self.fixture())['service_records_checked'],1)
    def test_unavailable_score_and_missing_mapping_rejected(self):
        a=self.fixture();a['frameworks']['service_quality']['scores']=[3,2,1]
        with self.assertRaisesRegex(ValueError,'no measured'):validate_frameworks(a)
        a=self.fixture();a['frameworks']['service_quality']['annotations']=[]
        with self.assertRaisesRegex(ValueError,'all mapped'):validate_frameworks(a)
    def test_misattributed_quote_and_unsupported_dimension_rejected(self):
        a=self.fixture();a['frameworks']['service_quality']['annotations'][0]['dimensions'][0]['anchor']='不存在的观点'
        with self.assertRaisesRegex(ValueError,'exact source'):validate_frameworks(a)
        a=self.fixture();a['frameworks']['service_quality']['annotations'][0]['dimensions'][0]['key']='made_up'
        with self.assertRaisesRegex(ValueError,'service dimension'):validate_frameworks(a)
    def test_unsafe_source_and_seeded_rice_scores_rejected(self):
        a=self.fixture();a['frameworks']['rice']={'source_url':'javascript:alert(1)'}
        with self.assertRaisesRegex(ValueError,'URL'):validate_frameworks(a)
        a=self.fixture();a['frameworks']['rice']={'source_url':'https://example.org/method','scores':[10]}
        with self.assertRaisesRegex(ValueError,'invented scores'):validate_frameworks(a)
if __name__=='__main__':unittest.main()
