import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dragonhydra.cognitive_v2.artifacts import ArtifactStore

class CognitiveArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.patch=patch('dragonhydra.cognitive_v2.artifacts.PROJECT_RUNTIME',self.root)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.store=ArtifactStore(self.root)
    def test_idempotent_content_addressed_roundtrip(self):
        payload={'actor_id':'SYSTEM','reason_codes':['NO_ACTION']}
        ref=self.store.put('receipts',payload)
        self.assertEqual(ref,self.store.put('receipts',payload))
        self.assertEqual(payload,self.store.get('receipts',ref))
        self.assertEqual(len(list(self.root.rglob('*.json'))),1)
    def test_tampering_fails_closed(self):
        ref=self.store.put('receipts',{'value':1})
        (self.root/'receipts'/(ref+'.json')).write_text('{"value":2}')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):self.store.get('receipts',ref)
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):self.store.put('receipts',{'value':1})
    def test_no_secret_or_hidden_reasoning_fields(self):
        for key in ('password','chain_of_thought','reasoning_content','raw_commandline','api_key'):
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'UNTRUSTED_CONTEXT'):
                self.store.put('actor_results',{'nested':[{key:'fake-test-value'}]})
        self.assertFalse(list(self.root.rglob('*.json')))
    def test_parent_and_localai_paths_are_outside_authority(self):
        for path in (self.root.parent/'DRAGONHYDRA',self.root/'..'/'LocalAI'):
            with self.assertRaises(ValueError):ArtifactStore(path)
    def test_immutable_storage_quota_does_not_delete_old_evidence(self):
        store=ArtifactStore(self.root,max_files=1)
        ref=store.put('receipts',{'first':True})
        with self.assertRaisesRegex(ValueError,'QUOTA'):store.put('receipts',{'second':True})
        self.assertEqual(store.get('receipts',ref),{'first':True})
    def test_missing_reference_and_path_injection_rejected(self):
        with self.assertRaisesRegex(ValueError,'MEMORY_REFERENCE_MISSING'):self.store.get('snapshots','a'*64)
        with self.assertRaises(ValueError):self.store.get('../predictions','a'*64)
        with self.assertRaises(ValueError):self.store.get('snapshots','../../secret')
    def test_oversized_artifact_rejected_before_write(self):
        with self.assertRaisesRegex(ValueError,'REQUEST_TOO_LARGE'):self.store.put('receipts',{'value':'x'*262145})
