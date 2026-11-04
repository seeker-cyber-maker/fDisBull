"""Controller-level dependency/capture integration without target bindings."""

import json
from pathlib import Path

import pytest

from test_z_controller import make_controller, SOURCE


def request(controller, verb, **params):
    reply = controller.handle({'verb': verb, 'params': params})
    assert reply['ok'], reply
    return reply['result']


def add(controller, id, **params):
    return request(controller, 'work-queue', op='add', id=id, **params)


@pytest.fixture
def capture_stub(monkeypatch):
    from fdisbull import z_call_contract as module
    calls = []

    def capture_native_call(ctx, name, callsite, code_selector, *, trigger=None,
                            continuation_steps=0, execute=True):
        calls.append(('capture', name))
        if trigger:
            trigger()
        contract = {'name': name, 'callsite': callsite, 'code_selector': code_selector,
                    'phase': 'complete', 'status': 'returned' if execute else 'inputs_observed',
                    'entry_conditions': {'code_selector': code_selector,
                                         'registers': {'general': {'eax': '0x1234'}},
                                         'stack': {'hex': '00' * 1024}},
                    'arguments': [{'register': 'EAX', 'value': 0x1234,
                                   'pointer_hypothesis': {'c_string': 'TEST1'}}],
                    'continuation': [{'instruction': {'address': callsite + 5, 'mnemonic': 'mov'},
                                      'after_registers': {'general': {'eax': '0x0'}}}]
                                    if continuation_steps else []}
        if execute:
            contract['return_registers'] = {'general': {'eax': '0x0'}}
        ctx.state.setdefault('native_call_contracts', {})[name] = contract
        return contract

    def invoke_captured_call(ctx, contract, *, args=None):
        calls.append(('invoke', contract['name']))
        return {'name': contract['name'], 'args': args, 'ui_input': False}

    monkeypatch.setattr(module, 'capture_native_call', capture_native_call)
    monkeypatch.setattr(module, 'invoke_captured_call', invoke_captured_call)
    return module, calls


def test_work_queue_persists_task_and_artifact_facts_across_controller_restart(tmp_path):
    controller, _, _, _ = make_controller(tmp_path, SOURCE)
    add(controller, 'parse', requires=['file'], produces=['rows'],
        operation={'verb': 'step', 'params': {'amount': 2}})
    request(controller, 'work-queue', op='publish', key='file', value=False,
            evidence='inventory.json')
    controller.close()

    restarted, _, _, _ = make_controller(tmp_path, SOURCE)
    status = request(restarted, 'work-queue')
    assert status['ready'] == ['parse'] and status['fact_keys'] == ['file']
    assert status['path'] == str(tmp_path / 'work.z.json')
    result = request(restarted, 'run-work', id='parse')
    assert result['status'] == 'awaiting_outputs' and result['result'] == {'count': 2}
    restarted.close()


def test_capture_operation_publishes_observed_facts_and_unlocks_next_work(tmp_path, capture_stub):
    controller, _, _, _ = make_controller(tmp_path, SOURCE)
    add(controller, 'capture', requires=['scene'], produces=['native-call:save'],
        operation={'verb': 'capture-native-call', 'params': {
            'name': 'save', 'callsite': 0x1000, 'code_selector': 8,
            'trigger': {'verb': 'step', 'params': {'amount': 3}}, 'continuation_steps': 2}})
    add(controller, 'inspect-buffer', requires=['native-call:save'],
        operation={'verb': 'step'})
    request(controller, 'work-queue', op='publish', key='scene', value='menu', evidence='frame-1')
    result = request(controller, 'run-work', id='capture')
    assert result['status'] == 'completed'
    assert result['queue']['ready'] == ['inspect-buffer']
    assert controller.ctx.state['count'] == 3
    raw = json.loads(Path(result['result']['path']).read_text())
    assert raw['entry_conditions']['registers']['general']['eax'] == '0x1234'
    assert 'registers' not in result['result']['entry_conditions']
    assert 'stack' not in result['result']['entry_conditions']
    assert 'after_registers' not in result['result']['continuation'][0]
    assert result['result']['arguments'][0]['c_string'] == 'TEST1'
    assert set(result['queue']['fact_keys']) == {
        'scene', 'native-entry:save', 'native-call:save', 'native-continuation:save'}
    assert capture_stub[1] == [('capture', 'save')]
    controller.close()


def test_successful_effect_awaiting_outputs_is_not_run_again(tmp_path):
    controller, _, _, _ = make_controller(tmp_path, SOURCE)
    add(controller, 'save', produces=['saved'], operation={'verb': 'step'})
    result = request(controller, 'run-work', id='save')
    assert result['status'] == 'awaiting_outputs'
    again = controller.handle({'verb': 'run-work', 'params': {'id': 'save'}})
    assert not again['ok'] and 'not ready' in again['error']['message']
    assert controller.ctx.state['count'] == 1
    assert request(controller, 'run-work')['status'] == 'no_ready_work'
    request(controller, 'work-queue', op='publish', key='saved', value={'path': 'slot'},
            evidence='save-event')
    request(controller, 'work-queue', op='complete', id='save')
    assert request(controller, 'work-queue')['task_counts'] == {'completed': 1}
    assert controller.ctx.state['count'] == 1
    controller.close()


@pytest.mark.parametrize('raise_after_effect', [False, True])
def test_changing_input_during_operation_requires_review_without_repeating_effect(
        tmp_path, raise_after_effect):
    source = SOURCE + '''
def change_input(ctx, raise_after_effect=False):
    ctx.state['effect_count'] = ctx.state.get('effect_count', 0) + 1
    ctx.work_queue('publish', key='source', value=2, evidence='changed-source')
    if raise_after_effect:
        raise RuntimeError('failure after input changed')
    return {'effect_count': ctx.state['effect_count']}
ACTIONS['change-input'] = {'handler': change_input}
'''
    controller, _, _, _ = make_controller(tmp_path, source)
    request(controller, 'work-queue', op='publish', key='source', value=1, evidence='original-source')
    add(controller, 'write', requires=['source'], produces=['saved'], operation={
        'verb': 'change-input', 'params': {'raise_after_effect': raise_after_effect}}, priority=10)
    add(controller, 'independent', operation={'verb': 'step'})
    reply = controller.handle({'verb': 'run-work', 'params': {'id': 'write'}})
    if raise_after_effect:
        assert not reply['ok'] and 'failure after input changed' in reply['error']['message']
    else:
        assert reply['ok'], reply
        assert reply['result']['status'] == 'needs_review'
    assert controller.ctx.state['effect_count'] == 1
    status = request(controller, 'work-queue')
    assert status['ready'] == ['independent']
    assert next(task for task in status['tasks'] if task['id'] == 'write')['status'] == 'failed'
    repeated = controller.handle({'verb': 'run-work', 'params': {'id': 'write'}})
    assert not repeated['ok'] and 'not ready' in repeated['error']['message']
    assert controller.ctx.state['effect_count'] == 1
    assert request(controller, 'run-work')['id'] == 'independent'
    assert controller.ctx.state['effect_count'] == 1
    assert request(controller, 'run-work')['status'] == 'no_ready_work'
    controller.close()


def test_operation_failure_retains_partial_fact_and_other_ready_work(tmp_path):
    source = SOURCE + '''
def blocked(ctx):
    ctx.work_queue('publish', key='filename', value='actors.dat', evidence='file-event')
    raise RuntimeError('scene continuation unavailable')
ACTIONS['blocked'] = {'handler': blocked}
'''
    controller, _, _, _ = make_controller(tmp_path, source)
    add(controller, 'capture', produces=['filename', 'continuation'],
        operation={'verb': 'blocked'}, priority=10)
    add(controller, 'parse', requires=['filename'], operation={'verb': 'step'})
    add(controller, 'independent', operation={'verb': 'step'})
    failed = controller.handle({'verb': 'run-work', 'params': {'id': 'capture'}})
    assert not failed['ok'] and 'continuation unavailable' in failed['error']['message']
    status = request(controller, 'work-queue')
    assert status['ready'] == ['independent', 'parse']
    assert status['fact_keys'] == ['filename']
    assert status['task_counts'] == {'failed': 1, 'pending': 2}
    assert request(controller, 'run-work', id='parse')['status'] == 'completed'
    assert request(controller, 'work-queue')['task_counts']['failed'] == 1
    controller.close()


def test_partial_capture_only_unlocks_the_observed_entry(tmp_path, capture_stub):
    controller, _, _, _ = make_controller(tmp_path, SOURCE)
    add(controller, 'entry-consumer', requires=['native-entry:read'])
    add(controller, 'return-consumer', requires=['native-call:read'])
    add(controller, 'continuation-consumer', requires=['native-continuation:read'])
    result = request(controller, 'capture-native-call', name='read', callsite=0x1000,
                     code_selector=8, execute=False)
    assert result['phase'] == 'complete' and result['status'] == 'inputs_observed'
    status = request(controller, 'work-queue')
    assert status['ready'] == ['entry-consumer']
    assert status['fact_keys'] == ['native-entry:read']
    controller.close()


def test_replay_uses_saved_contract_and_publishes_replay_fact(tmp_path, capture_stub):
    controller, _, _, _ = make_controller(tmp_path, SOURCE)
    captured = request(controller, 'capture-native-call', name='save', callsite=0x1000, code_selector=8)
    add(controller, 'inspect-save', requires=['native-replay:save'])
    result = request(controller, 'invoke-captured-call', contract=captured['path'],
                     args={'eax': 7})
    assert result['ui_input'] is False and result['args'] == {'eax': 7}
    assert Path(result['path']).exists()
    assert request(controller, 'work-queue')['ready'] == ['inspect-save']
    assert capture_stub[1] == [('capture', 'save'), ('invoke', 'save')]
    controller.close()


@pytest.mark.parametrize('observed_entry', [False, True])
def test_failed_capture_persists_partial_and_only_releases_observed_inputs(
        tmp_path, capture_stub, observed_entry):
    module, _ = capture_stub
    def failed(ctx, name, callsite, code_selector, **options):
        contract = {'name': name, 'callsite': callsite, 'status': 'failed',
                    'phase': 'executing_original_call' if observed_entry else 'reaching_callsite'}
        if observed_entry:
            contract['entry_conditions'] = {'registers': {'general': {'eax': '0x1234'}}}
        ctx.state['native_capture_pending'] = contract
        raise RuntimeError('original call did not return')
    module.capture_native_call = failed
    controller, _, _, _ = make_controller(tmp_path, SOURCE)
    add(controller, 'capture', produces=['native-call:read'], operation={
        'verb': 'capture-native-call', 'params': {'name': 'read', 'callsite': 0x1000, 'code_selector': 8}})
    add(controller, 'entry-consumer', requires=['native-entry:read'])
    failed_reply = controller.handle({'verb': 'run-work', 'params': {'id': 'capture'}})
    assert not failed_reply['ok'] and 'did not return' in failed_reply['error']['message']
    partial, = (tmp_path / 'evidence').glob('native-contract-partial-*.json')
    assert json.loads(partial.read_text())['status'] == 'failed'
    status = request(controller, 'work-queue')
    assert status['fact_keys'] == (['native-entry:read'] if observed_entry else [])
    assert status['ready'] == (['entry-consumer'] if observed_entry else [])
    assert status['task_counts'] == {'failed': 1, 'pending': 1}
    controller.close()


@pytest.mark.parametrize('verb', ['run-work', 'close'])
def test_queue_cannot_recursively_run_or_close_the_runtime(tmp_path, verb):
    controller, _, _, _ = make_controller(tmp_path, SOURCE)
    add(controller, 'invalid', operation={'verb': verb})
    reply = controller.handle({'verb': 'run-work', 'params': {'id': 'invalid'}})
    assert not reply['ok']
    assert not controller.closed
    assert request(controller, 'work-queue')['task_counts'] == {'failed': 1}
    controller.close()


def test_list_exposes_work_queue_operations_and_capture_trigger(tmp_path, capture_stub):
    controller, _, _, _ = make_controller(tmp_path, SOURCE)
    listing = request(controller, 'list')
    contracts = listing['builtin_parameters']
    assert contracts['capture-native-call']['required'] == ['name', 'callsite', 'code_selector']
    assert 'trigger' in contracts['capture-native-call']['optional']
    assert contracts['work-queue']['operations']['add']['required'] == ['id']
    assert contracts['work-queue']['operations']['publish']['required'] == ['key', 'value', 'evidence']
    assert 'outputs' in contracts['work-queue']['operations']['complete']['optional']
    controller.close()


def test_compact_capture_exposes_buffer_delta_and_unlocks_its_consumer(tmp_path, capture_stub):
    module, _ = capture_stub
    def capture(ctx, name, callsite, code_selector, **options):
        return {'name': name, 'callsite': callsite, 'status': 'returned', 'phase': 'complete',
            'entry_conditions': {'registers': {'general': {'eax': '0x4000'}}},
            'return_registers': {'general': {'eax': '0x1'}}, 'continuation': [],
            'arguments': [{'register': 'EAX', 'value': 0x4000,
                'pointer_hypothesis': {'address': 0x4000, 'hex': '0d000000', 'bytes': 4}}],
            'post_arguments': [{'register': 'EAX', 'value': 0x4000,
                'pointer_hypothesis': {'address': 0x4000, 'hex': '63000000', 'bytes': 4}}]}
    module.capture_native_call = capture
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    add(controller, 'interpret-buffer', requires=['native-buffer-change:read'])
    result = request(controller, 'capture-native-call', name='read', callsite=0x12000, code_selector=8)
    comparison, = result['argument_changes']['comparisons']
    assert comparison['first_u32_le'] == {'before': 13, 'after': 99}
    assert result['returned_eax'] == '0x1'
    assert request(controller, 'work-queue')['ready'] == ['interpret-buffer']
    raw = json.loads(Path(result['path']).read_text())
    assert raw['post_arguments'][0]['pointer_hypothesis']['hex'] == '63000000'
    assert not session.calls
