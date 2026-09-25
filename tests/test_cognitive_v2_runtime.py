"""Network-free router and bounded cognitive transport checks."""
from dataclasses import replace
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from dragonhydra.cognitive_v2.router import ModelRouter, RoutingInput, RoutingDecision, MODELS
from dragonhydra.cognitive_v2.adapter import (AdapterError, ProjectionFact, CognitiveProjection,
    CognitiveAnalysisRequest, QwenCognitiveEngine, QwenCognitiveAdapter, build_projection,
    parse_conclusions, _actor_result)
from dragonhydra.cognitive_v2.contracts import (CognitiveStateSnapshot, WorldState, MachineState,
    ProjectState, ModelState, MemoryState, UncertaintyMap, UncertaintyState, CapabilityState,
    ComponentState, Metric, StateLabel)
from dragonhydra.localai.contracts import canonical_bytes, content_hash
from dragonhydra.localai.gateway import AnalysisHandler
from dragonhydra.localai.runtime import MODEL_PROFILES, RUNTIME_ID

STAMP = '2026-09-26T00:00:00Z'
EXPIRES = '2026-09-26T00:02:00Z'


def frozen_snapshot():
    return CognitiveStateSnapshot(snapshot_id='synthetic-v2-snapshot', created_at=STAMP,
        as_of_at=STAMP, temporal_mode='SYNTHETIC', world_state=WorldState(as_of_at=STAMP),
        machine_state=MachineState(machine_snapshot_hash='a' * 64, observed_at=STAMP,
            available_at=STAMP, expires_at=EXPIRES, health='HEALTHY', components=(
                ComponentState(component_id='gpu-0', status='OK', metrics=(
                    Metric(name='memory_used_mib', value=512, unit='MiB'),),
                    labels=(StateLabel(name='name', value='Synthetic GPU'),)),
                ComponentState(component_id='event-start', status='OBSERVED',
                    reason_codes=('PROCESS_STARTED',), references=('event-start',)),)),
        project_state=ProjectState(project_id='DRAGONHYDRACHILD', branch='synthetic-branch',
            head='b' * 40, working_tree='CLEAN', observed_at=STAMP, available_at=STAMP,
            expires_at=EXPIRES), model_state=ModelState(), memory_state=MemoryState(),
        uncertainties=UncertaintyMap(items=(UncertaintyState(uncertainty_id='uncertainty-lineup',
            dimension='LINEUP', last_updated=STAMP, recommended_resolution='Request a validated lineup.',
            reason_codes=('LINEUP_CONTINUITY_UNKNOWN',)),)), capabilities=CapabilityState())


def output(ref='event-start', **updates):
    item = {'subject': 'PROCESS', 'position': 'PROCESS_STARTED', 'epistemic_state': 'HYPOTHESIS',
        'confidence': 'MEDIUM', 'references': [ref]}
    item.update(updates)
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'conclusions': [item]})}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 40}, 'timings': {'predicted_ms': 500.0}}


class CognitiveV2RouterTests(unittest.TestCase):
    def setUp(self):
        self.request = RoutingInput('SUMMARIZE_STATE', 2400, available_ram_mb=48000,
            available_vram_mb=5000, cpu_load_percent=20)
        self.router = ModelRouter()

    def test_fast_task_uses_4b(self):
        self.assertEqual(self.router.route(self.request).selected_model, MODELS[0])

    def test_deep_task_uses_30b_when_resources_allow(self):
        result = self.router.route(replace(self.request, task_kind='REVIEW_ARCHITECTURE'))
        self.assertEqual(result.selected_model, MODELS[1])
        self.assertIn('DEEP_TASK', result.reason_codes)

    def test_high_complexity_escalates_deliberately(self):
        self.assertEqual(self.router.route(replace(self.request, complexity_class='HIGH')).selected_model, MODELS[1])

    def test_latency_budget_prefers_fast_model(self):
        result = self.router.route(replace(self.request, task_kind='COMPARE_STATES', required_latency_ms=10000))
        self.assertEqual(result.selected_model, MODELS[0])
        self.assertIn('LATENCY_BUDGET_PREFERS_FAST_MODEL', result.reason_codes)

    def test_30b_unavailable_is_explicit(self):
        result = self.router.route(replace(self.request, task_kind='PLAN_RESEARCH', available_models=(MODELS[0],)))
        self.assertEqual(result.selected_model, MODELS[0])
        self.assertIn('DEEP_MODEL_UNAVAILABLE', result.reason_codes)

    def test_all_unavailable_is_blocked(self):
        result = self.router.route(replace(self.request, available_models=()))
        self.assertIsNone(result.selected_model)
        self.assertEqual(result.result_status, 'BLOCKED')

    def test_ram_floor_prevents_30b(self):
        result = self.router.route(replace(self.request, task_kind='PLAN_RESEARCH', available_ram_mb=12000))
        self.assertEqual(result.selected_model, MODELS[0])
        self.assertIn('DEEP_MODEL_RAM_INSUFFICIENT', result.reason_codes)

    def test_unknown_ram_prevents_deep_selection(self):
        result = self.router.route(replace(self.request, task_kind='PLAN_RESEARCH', available_ram_mb=None))
        self.assertEqual(result.selected_model, MODELS[0])
        self.assertIn('DEEP_MODEL_RAM_UNKNOWN', result.reason_codes)

    def test_cpu_fallback_is_proposal_not_process_launch(self):
        result = self.router.route(replace(self.request, available_vram_mb=0))
        self.assertEqual(result.selected_model, MODELS[0])
        self.assertIn('CPU_FALLBACK_REQUIRES_ENGINEERING_LAUNCH', result.reason_codes)

    def test_occupied_model_not_selected(self):
        result = self.router.route(replace(self.request, task_kind='COMPARE_STATES', occupied_models=(MODELS[1],)))
        self.assertEqual(result.selected_model, MODELS[0])

    def test_identical_input_hashes_identically(self):
        self.assertEqual(self.router.route(self.request), self.router.route(replace(self.request)))

    def test_routing_contracts_roundtrip(self):
        self.assertEqual(RoutingInput.from_dict(json.loads(canonical_bytes(self.request.to_dict()))), self.request)
        decision = self.router.route(self.request)
        self.assertEqual(RoutingDecision.from_dict(json.loads(canonical_bytes(decision.to_dict()))), decision)

    def test_changed_load_changes_routing_hash(self):
        self.assertNotEqual(self.router.route(self.request).routing_hash,
            self.router.route(replace(self.request, cpu_load_percent=30)).routing_hash)

    def test_unsupported_task_rejected(self):
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_TASK'):
            replace(self.request, task_kind='RUN_ARBITRARY_COMMAND')

    def test_oversized_context_rejected(self):
        with self.assertRaisesRegex(ValueError, 'REQUEST_TOO_LARGE'):
            replace(self.request, context_bytes=6501)

    def test_invalid_resource_state_rejected(self):
        for values in ({'cpu_load_percent': float('nan')}, {'available_ram_mb': -1},
                       {'available_models': ('untrusted-model',)}, {'context_bytes': True}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                replace(self.request, **values)


class CognitiveV2AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = frozen_snapshot()
        self.projection = build_projection(self.snapshot)
        self.request = CognitiveAnalysisRequest.create(self.projection, 'TRIAGE_CHANGES',
            MODELS[0], created_at=STAMP)
        self.runtime = Mock()
        self.runtime.identity = {'model_id': MODELS[0], 'model_hash': MODEL_PROFILES[MODELS[0]]['sha256'],
            'runtime_id': RUNTIME_ID, 'context_size': 4096}
        self.runtime.healthy.return_value = True
        self.runtime.url = 'http://127.0.0.1:8082'
        self.runtime.token = 'synthetic-private-authentication-value'
        with patch('dragonhydra.cognitive_v2.adapter.local_runtime_dir', return_value=self.root):
            self.engine = QwenCognitiveEngine(self.runtime, self.root, clock=lambda: STAMP)

    def run_output(self, value=None):
        with patch('dragonhydra.cognitive_v2.adapter.local_json', return_value=value or output()):
            return self.engine.analyze_request(self.request)

    def test_contract_roundtrip_and_identical_projection_hash(self):
        self.assertEqual(CognitiveAnalysisRequest.from_dict(self.request.to_dict()), self.request)
        self.assertEqual(CognitiveProjection.from_dict(self.projection.to_dict()).projection_hash, self.projection.projection_hash)
        self.assertEqual(build_projection(self.snapshot).projection_hash, self.projection.projection_hash)

    def test_changed_state_changes_projection_hash(self):
        changed = replace(self.snapshot, machine_state=replace(self.snapshot.machine_state, health='PARTIAL'))
        self.assertNotEqual(build_projection(changed).projection_hash, self.projection.projection_hash)

    def test_projection_retains_event_and_bounded_hardware_identity(self):
        values = [fact.value for fact in self.projection.facts]
        self.assertIn('PROCESS_STARTED', values)
        self.assertIn('Synthetic GPU', values)
        self.assertIn(512, values)

    def test_free_prose_is_not_model_context(self):
        changed = replace(self.snapshot, uncertainties=UncertaintyMap(items=(replace(
            self.snapshot.uncertainties.items[0], recommended_resolution='Read the official lineup after publication.'),)))
        self.assertNotIn('Read the official lineup', canonical_bytes(build_projection(changed).to_dict()).decode())

    def test_secret_or_path_facts_are_rejected(self):
        for key, value in [('password', 'protected'), ('label_name', 'api_key=protected'),
                           ('label_name', 'C:/LocalAI/Secrets'), ('label_name', 'text\ncommand')]:
            with self.subTest(value=value), self.assertRaises(AdapterError):
                ProjectionFact('reference-1', 'MACHINE_HEALTH', key, value)

    def test_plain_dict_cannot_bypass_typed_snapshot(self):
        with self.assertRaisesRegex(AdapterError, 'UNTRUSTED_CONTEXT'):
            build_projection(self.snapshot.to_dict())

    def test_projection_rejects_arbitrary_fields(self):
        raw = self.projection.to_dict()
        raw['shell'] = 'command'
        with self.assertRaises(AdapterError):
            CognitiveProjection.from_dict(raw)

    def test_projection_size_bounded_with_explicit_omission(self):
        components = tuple(ComponentState(component_id=f'service-{i}', status='OK',
            metrics=(Metric(name='load', value=i, unit='count'),)) for i in range(100))
        snapshot = replace(self.snapshot, machine_state=replace(self.snapshot.machine_state, components=components))
        projected = build_projection(snapshot)
        self.assertLessEqual(len(canonical_bytes(projected.to_dict())), 6500)
        self.assertGreater(projected.omitted_fact_count, 0)

    def test_owned_event_prioritized_ahead_of_component_noise(self):
        noise = tuple(ComponentState(component_id=f'gpu-{i}', status='UNKNOWN',
            reason_codes=('OPTIONAL_COMPONENT_UNAVAILABLE',)) for i in range(80))
        event = ComponentState(component_id='event-important', status='OBSERVED_EVENT',
            reason_codes=('PROCESS_STARTED',), labels=(StateLabel(name='entity_id', value='process.1234'),))
        snapshot = replace(self.snapshot, machine_state=replace(self.snapshot.machine_state,
            components=(*noise, event)), recent_events=('event-important',))
        projected = build_projection(snapshot)
        self.assertEqual(projected.facts[5].value, 'PROCESS_STARTED')
        self.assertEqual(projected.facts[6].value, 'process.1234')

    def test_gpu_event_identity_is_not_projected_as_process(self):
        event = ComponentState(component_id='event-gpu', status='OBSERVED_EVENT',
            reason_codes=('GPU_MEMORY_INCREASED',), labels=(StateLabel(name='entity_id', value='gpu.0'),))
        snapshot = replace(self.snapshot, machine_state=replace(self.snapshot.machine_state, components=(event,)),
            recent_events=('event-gpu',))
        facts = [fact for fact in build_projection(snapshot).facts if fact.reference == 'event-gpu' and fact.key != 'status']
        self.assertTrue(facts)
        self.assertTrue(all(fact.subject == 'GPU' for fact in facts))

    def test_input_hash_tampering_rejected(self):
        raw = self.request.to_dict(); raw['input_hash'] = 'd' * 64
        with self.assertRaises(AdapterError): CognitiveAnalysisRequest.from_dict(raw)

    def test_model_hash_mismatch_rejected(self):
        with self.assertRaisesRegex(AdapterError, 'MODEL_HASH_MISMATCH'):
            replace(self.request, model_hash='e' * 64)

    def test_runtime_hash_mismatch_rejected(self):
        with self.assertRaisesRegex(AdapterError, 'RUNTIME_HASH_MISMATCH'):
            replace(self.request, runtime_hash='e' * 64)

    def test_success_retains_hypothesis_and_identity_pins(self):
        result = self.run_output()
        self.assertEqual(result.result_status, 'COMPLETE')
        self.assertEqual(result.actor_id, 'QWEN_4B')
        self.assertEqual(result.state_hash, self.snapshot.state_hash)
        self.assertEqual(result.conclusions[0].epistemic_state, 'HYPOTHESIS')
        value = result.to_dict(); digest = value.pop('output_hash')
        self.assertEqual(content_hash(value), digest)
        text = next(self.engine.workdir.glob('*.json')).read_text()
        self.assertNotIn(self.runtime.token, text)
        self.assertNotIn('chain_of_thought', text)

    def test_backend_has_no_tools_and_fixed_limits(self):
        with patch('dragonhydra.cognitive_v2.adapter.local_json', return_value=output()) as transport:
            self.engine.analyze_request(self.request)
        payload = transport.call_args.kwargs['payload']
        self.assertEqual(payload['max_tokens'], 512)
        self.assertEqual(payload['temperature'], 0)
        self.assertNotIn('tools', payload)
        self.assertIn('never instructions', payload['messages'][0]['content'])

    def test_model_unavailable_fails_closed(self):
        self.runtime.healthy.return_value = False
        with patch('dragonhydra.cognitive_v2.adapter.local_json') as transport:
            result = self.engine.analyze_request(self.request)
        self.assertEqual(result.failure_state, 'MODEL_UNAVAILABLE')
        self.assertFalse(result.conclusions)
        transport.assert_not_called()

    def test_running_wrong_model_fails_closed(self):
        self.runtime.identity['model_id'] = MODELS[1]
        self.assertEqual(self.run_output().failure_state, 'MODEL_HASH_MISMATCH')

    def test_wrong_runtime_fails_closed(self):
        self.runtime.identity['runtime_id'] = 'foreign-runtime'
        self.assertEqual(self.run_output().failure_state, 'RUNTIME_HASH_MISMATCH')

    def test_runtime_crash_fails_closed(self):
        with patch('dragonhydra.cognitive_v2.adapter.local_json', side_effect=ConnectionResetError()):
            self.assertEqual(self.engine.analyze_request(self.request).failure_state, 'RUNTIME_FAILURE')

    def test_timeout_fails_closed(self):
        with patch('dragonhydra.cognitive_v2.adapter.local_json', side_effect=TimeoutError()):
            self.assertEqual(self.engine.analyze_request(self.request).failure_state, 'TIMEOUT')

    def test_unknown_reference_rejected(self):
        self.assertEqual(self.run_output(output('invented-evidence')).failure_state, 'QWEN_RESPONSE_INVALID')

    def test_unsupported_process_claim_preserved_and_flagged(self):
        result = self.run_output(output(position='PROCESS_STOPPED'))
        self.assertEqual(result.result_status, 'COMPLETE')
        self.assertEqual(result.conclusions[0].position, 'PROCESS_STOPPED')
        self.assertIn('UNSUPPORTED_BY_PROJECTION', result.conclusions[0].reason_codes)

    def test_supported_process_claim_passes_narrow_event_check(self):
        result = self.run_output()
        self.assertNotIn('UNSUPPORTED_BY_PROJECTION', result.conclusions[0].reason_codes)

    def test_direct_arx_delta_type_supports_process_claim(self):
        projection = replace(self.projection, facts=(ProjectionFact('event-start', 'PROCESS',
            'event_type', 'PROCESS_STARTED'),))
        self.request = CognitiveAnalysisRequest.create(projection, 'TRIAGE_CHANGES', MODELS[0], created_at=STAMP)
        result = self.run_output()
        self.assertEqual(result.result_status, 'COMPLETE')
        self.assertNotIn('UNSUPPORTED_BY_PROJECTION', result.conclusions[0].reason_codes)

    def test_observation_output_rejected(self):
        self.assertEqual(self.run_output(output(epistemic_state='OBSERVATION')).failure_state, 'QWEN_RESPONSE_INVALID')

    def test_arbitrary_action_output_rejected(self):
        self.assertEqual(self.run_output(output(position='RUN_ARBITRARY_COMMAND')).failure_state, 'QWEN_RESPONSE_INVALID')

    def test_hidden_reasoning_rejected_and_not_persisted(self):
        value = output(); value['choices'][0]['message']['reasoning_content'] = 'PRIVATE_TRACE_CANARY'
        self.assertEqual(self.run_output(value).failure_state, 'QWEN_RESPONSE_INVALID')
        self.assertNotIn('PRIVATE_TRACE_CANARY', next(self.engine.workdir.glob('*.json')).read_text())

    def test_tool_calls_rejected(self):
        value = output(); value['choices'][0]['message']['tool_calls'] = [{'name': 'shell'}]
        self.assertEqual(self.run_output(value).failure_state, 'QWEN_RESPONSE_INVALID')

    def test_truncated_output_rejected(self):
        value = output(); value['choices'][0]['finish_reason'] = 'length'
        self.assertEqual(self.run_output(value).failure_state, 'QWEN_RESPONSE_INVALID')

    def test_stale_input_requires_explicit_replay(self):
        self.engine.clock = lambda: '2026-09-26T00:04:00Z'
        self.request = CognitiveAnalysisRequest.create(self.projection, 'TRIAGE_CHANGES', MODELS[0],
            created_at='2026-09-26T00:04:00Z')
        self.assertEqual(self.run_output().failure_state, 'COGNITIVE_STATE_STALE')

    def test_expired_machine_rejected_even_with_recent_cursor(self):
        projection = replace(self.projection, machine_expires_at=STAMP)
        self.request = CognitiveAnalysisRequest.create(projection, 'TRIAGE_CHANGES', MODELS[0], created_at=STAMP)
        self.assertEqual(self.run_output().failure_state, 'MACHINE_STATE_STALE')

    def test_frozen_replay_is_explicit_and_receipted(self):
        self.engine.clock = lambda: '2026-09-26T00:04:00Z'
        self.request = CognitiveAnalysisRequest.create(self.projection, 'TRIAGE_CHANGES', MODELS[0],
            created_at='2026-09-26T00:04:00Z', replay_mode=True)
        self.assertEqual(self.run_output().result_status, 'COMPLETE')
        self.assertTrue(json.loads(next(self.engine.workdir.glob('*.json')).read_text())['request']['replay_mode'])

    def test_duplicate_request_never_repeats_inference(self):
        self.run_output()
        with patch('dragonhydra.cognitive_v2.adapter.local_json') as transport:
            result = self.engine.analyze_request(self.request)
        self.assertEqual(result.failure_state, 'REPLAY_REJECTED')
        transport.assert_not_called()

    def test_quota_rejects_before_model_call(self):
        self.engine.metrics['request_count'] = 128
        with patch('dragonhydra.cognitive_v2.adapter.local_json') as transport:
            result = self.engine.analyze_request(self.request)
        self.assertEqual(result.failure_state, 'REQUEST_QUOTA_REACHED')
        transport.assert_not_called()

    def test_audit_failure_cannot_claim_success(self):
        self.engine.workdir.rmdir(); self.engine.workdir.write_text('audit intentionally unavailable')
        self.assertEqual(self.run_output().failure_state, 'AUDIT_FAILURE')


class CognitiveV2HTTPTests(unittest.TestCase):
    def handler(self, *, headers=None, raw=b'{}'):
        handler = object.__new__(AnalysisHandler)
        handler.server = SimpleNamespace(server_address=('127.0.0.1', 8083), auth_token='a' * 64, engine=Mock())
        handler.client_address = ('127.0.0.1', 12345)
        handler.path = '/v2/analyze'
        handler.headers = Message()
        values = {'Host': '127.0.0.1:8083', 'Authorization': 'Bearer ' + 'a' * 64,
            'Content-Type': 'application/json', 'Content-Length': str(len(raw))}
        values.update(headers or {})
        for key, value in values.items(): handler.headers[key] = value
        handler.rfile = BytesIO(raw); handler._reply = Mock()
        return handler

    def test_v2_authentication_required(self):
        handler = self.handler(headers={'Authorization': 'Bearer ' + 'wrong'})
        handler.do_POST()
        self.assertEqual(handler._reply.call_args.args[0], 403)
        handler.server.engine.analyze_v2.assert_not_called()

    def test_v2_browser_origin_rejected(self):
        handler = self.handler(headers={'Origin': 'https://synthetic.example'})
        handler.do_POST()
        self.assertEqual(handler._reply.call_args.args[0], 403)

    def test_v2_oversize_rejected(self):
        handler = self.handler(headers={'Content-Length': '8193'})
        handler.do_POST()
        self.assertEqual(handler._reply.call_args.args[0], 413)

    def test_v2_invalid_schema_rejected(self):
        handler = self.handler(raw=b'{"command":"shell"}')
        handler.do_POST()
        self.assertEqual(handler._reply.call_args.args[0], 400)

    def test_v2_request_dispatches_only_to_bounded_engine(self):
        request = CognitiveAnalysisRequest.create(build_projection(frozen_snapshot()), 'TRIAGE_CHANGES', MODELS[0], created_at=STAMP)
        handler = self.handler(raw=canonical_bytes(request.to_dict()))
        handler.server.engine.analyze_v2.return_value = _actor_result(request, failure='MODEL_UNAVAILABLE')
        handler.do_POST()
        self.assertEqual(handler._reply.call_args.args[0], 200)
        self.assertEqual(handler.server.engine.analyze_v2.call_args.args[0], request)
        handler.server.engine.analyze.assert_not_called()


class CognitiveV2ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('dragonhydra.localai.client.PROJECT_RUNTIME', 'dragonhydra.cognitive_v2.adapter.PROJECT_RUNTIME'):
            patcher = patch(name, self.root)
            patcher.start(); self.addCleanup(patcher.stop)
        self.adapter = QwenCognitiveAdapter('http://127.0.0.1:8083', model_id=MODELS[0],
            token='synthetic-auth-value-never-saved-000', audit_dir=self.root / 'client')
        self.request = CognitiveAnalysisRequest.create(build_projection(frozen_snapshot()),
            'TRIAGE_CHANGES', MODELS[0], created_at=STAMP)
        conclusions = parse_conclusions(output()['choices'][0]['message']['content'], self.request)
        self.response = _actor_result(self.request, conclusions=conclusions)

    def run_payload(self, payload):
        with patch.object(self.adapter.client, '_exchange', return_value=payload):
            return self.adapter.analyze_request(self.request)

    def test_valid_response_is_bound_and_audited(self):
        result = self.run_payload(self.response.to_dict())
        self.assertEqual(result, self.response)
        receipt = next(self.adapter.audit_dir.glob('*.json')).read_text()
        self.assertNotIn(self.adapter.client._token, receipt)
        self.assertIn(self.request.projection.projection_hash, receipt)

    def test_response_hash_tampering_fails_closed(self):
        value = self.response.to_dict(); value['output_hash'] = '0' * 64
        self.assertEqual(self.run_payload(value).failure_state, 'QWEN_RESPONSE_INVALID')

    def test_response_model_mismatch_fails_closed(self):
        value = self.response.to_dict(); value['model_hash'] = '0' * 64
        self.assertEqual(self.run_payload(value).failure_state, 'MODEL_HASH_MISMATCH')

    def test_response_runtime_mismatch_fails_closed(self):
        value = self.response.to_dict(); value['runtime_hash'] = '0' * 64
        self.assertEqual(self.run_payload(value).failure_state, 'RUNTIME_HASH_MISMATCH')

    def test_codex_cannot_impersonate_qwen_response(self):
        value = self.response.to_dict(); value['actor_id'] = 'CODEX'
        self.assertEqual(self.run_payload(value).failure_state, 'QWEN_RESPONSE_INVALID')

    def test_missing_response_schema_fails_closed(self):
        self.assertEqual(self.run_payload({'unstructured': 'output'}).failure_state, 'QWEN_RESPONSE_INVALID')

    def test_transport_unavailable_is_not_mock_output(self):
        from dragonhydra.localai.contracts import ContractError
        with patch.object(self.adapter.client, '_exchange', side_effect=ContractError('LOCALAI_UNAVAILABLE')):
            result = self.adapter.analyze_request(self.request)
        self.assertEqual(result.failure_state, 'MODEL_UNAVAILABLE')
        self.assertFalse(result.conclusions)

    def test_transport_timeout_is_preserved(self):
        from dragonhydra.localai.contracts import ContractError
        with patch.object(self.adapter.client, '_exchange', side_effect=ContractError('TIMEOUT')):
            self.assertEqual(self.adapter.analyze_request(self.request).failure_state, 'TIMEOUT')

    def test_external_endpoint_denied(self):
        with self.assertRaises(ValueError):
            QwenCognitiveAdapter('http://192.0.2.1:8083', model_id=MODELS[0], token='x' * 64,
                audit_dir=self.root / 'client')

    def test_endpoint_embedded_credentials_denied(self):
        with self.assertRaises(ValueError):
            QwenCognitiveAdapter('http://' + 'user:synthetic' + '@127.0.0.1:8083', model_id=MODELS[0],
                token='x' * 64, audit_dir=self.root / 'client')

    def test_endpoint_path_or_query_cannot_select_action_route(self):
        for endpoint in ('http://127.0.0.1:8083/execute', 'http://127.0.0.1:8083?command=synthetic'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                QwenCognitiveAdapter(endpoint, model_id=MODELS[0], token='x' * 64,
                    audit_dir=self.root / 'client')

    def test_arbitrary_audit_destination_denied(self):
        with self.assertRaises(ValueError):
            QwenCognitiveAdapter('http://127.0.0.1:8083', model_id=MODELS[0], token='x' * 64,
                audit_dir=self.root.parent)

    def test_excessive_timeout_denied(self):
        with self.assertRaises(ValueError):
            QwenCognitiveAdapter('http://127.0.0.1:8083', model_id=MODELS[0], token='x' * 64,
                audit_dir=self.root / 'client', timeout_seconds=121)
