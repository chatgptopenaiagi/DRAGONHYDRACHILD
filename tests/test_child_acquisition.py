import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra.child.acquisition import collect_once, normalize, validate_records, fault_injection_report
from dragonhydra.config import PROJECT_ROOT
from dragonhydra.web.contracts import PipelineError
from dragonhydra.web.provenance import digest


class ChildAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.stamp = (self.now - timedelta(seconds=1)).isoformat()
        self.document = {'name':'English Premier League 2026/27','matches':[
            {'round':'Matchday 1','date':'2026-08-20','team1':'Arsenal FC','team2':'Liverpool FC','score':{'ft':[2,1]}}]}
        self.body = json.dumps(self.document).encode()
        self.snapshot = {'snapshot_id':'a'*32,'source_id':'openfootball','source_url':'https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json',
                         'observed_at':self.stamp,'retrieved_at':self.stamp,'available_at':self.stamp,
                         'content_hash':digest(self.body),'source_policy_version':'test/1'}

    def test_rescheduling_retains_identity_and_unverified_timezone(self):
        old=normalize(self.body,self.snapshot)[0]
        self.document['matches'][0]['date']='2026-10-20'
        new=normalize(json.dumps(self.document).encode(),self.snapshot)[0]
        self.assertEqual(old['fixture_id'],new['fixture_id'])
        self.assertIsNone(new['kickoff_utc'])
        self.assertEqual(validate_records([old],at=datetime.now(timezone.utc))['accepted'],1)

    def test_ambiguous_source_score_is_preserved_never_final(self):
        self.document['matches'][0]['score']=[0,0]
        row=normalize(json.dumps(self.document).encode(),self.snapshot)[0]
        self.assertEqual(row['score_state'],'UNKNOWN_FORMAT')
        self.assertIsNone(row['home_score'])
        self.assertNotEqual(row['status'],'REPORTED_FINAL')
        self.assertEqual(row['source_score'],[0,0])
        self.document['matches'][0]['score']={'ht':[1,0]}
        row=normalize(json.dumps(self.document).encode(),self.snapshot)[0]
        self.assertEqual(row['score_state'],'UNKNOWN_FORMAT')
        self.assertEqual(row['status'],'SCHEDULED')
        self.document['matches'][0]['team1']='Unreviewed New Club'
        with self.assertRaisesRegex(PipelineError,'ENTITY_UNRESOLVED'):
            normalize(json.dumps(self.document).encode(),self.snapshot)

    def test_fault_injection_and_provenance_controls(self):
        report=fault_injection_report()
        self.assertEqual((report['detected'],report['faults'],report['false_positives']),(7,7,0))
        row=normalize(self.body,self.snapshot)[0]
        for mutation in ({'source_url':'http://127.0.0.1/private'}, {'content_hash':'bad'}, {'epistemic_state':'PREDICTION'}):
            self.assertEqual(validate_records([{**row,**mutation}],at=datetime.now(timezone.utc))['accepted'],0)

    def test_duplicate_and_conflict_remain_distinct(self):
        row=normalize(self.body,self.snapshot)[0]
        result=validate_records([row,row,{**row,'home_score':3}],at=datetime.now(timezone.utc))
        self.assertIn('DUPLICATE',result['decisions'][1]['reason_codes'])
        self.assertIn('CONFLICTING_DATA',result['decisions'][2]['reason_codes'])

    def test_mock_capture_appends_and_rate_gate_prevents_second_fetch(self):
        (PROJECT_ROOT/'runtime/tmp').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            root=Path(folder);(root/'config').mkdir()
            (root/'config/child-entity-crosswalk.json').write_bytes((PROJECT_ROOT/'config/child-entity-crosswalk.json').read_bytes())
            source=json.loads((PROJECT_ROOT/'config/web_sources.json').read_text())
            (root/'config/web_sources.json').write_text(json.dumps(source))
            evidence={'retrieved_at':self.stamp,'content_hash':digest(self.body),'content_type':'application/json','source_id':'openfootball',
                      'source_url':self.snapshot['source_url'],'robots':{'robots_status':'ABSENT'}}
            with patch('dragonhydra.child.acquisition.fetch',return_value=(self.body,evidence)) as fetcher:
                first=collect_once(root=root,persist=False)
                self.assertEqual(first['status'],'COMPLETE')
                ledger=list((root/'runtime/child/acquisition').glob('*.json'))
                before=ledger[0].read_bytes()
                self.assertEqual(collect_once(root=root,persist=False)['status'],'NOT_DUE')
                self.assertEqual(fetcher.call_count,1)
                self.assertEqual(before,ledger[0].read_bytes())

    def test_policy_failure_is_recorded_before_network(self):
        (PROJECT_ROOT/'runtime/tmp').mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT/'runtime/tmp') as folder:
            root=Path(folder);(root/'config').mkdir()
            (root/'config/child-entity-crosswalk.json').write_bytes((PROJECT_ROOT/'config/child-entity-crosswalk.json').read_bytes())
            source=json.loads((PROJECT_ROOT/'config/web_sources.json').read_text());source['openfootball']['terms_status']='PROHIBITED'
            (root/'config/web_sources.json').write_text(json.dumps(source))
            with patch('dragonhydra.child.acquisition.fetch') as fetcher:
                result=collect_once(root=root,persist=False)
                fetcher.assert_not_called()
                self.assertEqual(result['reason'],'TERMS_BLOCKED')
                self.assertEqual(len(list((root/'runtime/child/acquisition').glob('*.json'))),1)


if __name__=='__main__':
    unittest.main()
