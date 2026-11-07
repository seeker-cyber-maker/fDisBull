import json

from test_z_controller import make_controller, SOURCE


def test_capture_survives_new_owner_and_composes_current_handler(tmp_path):
    c, path, _, _ = make_controller(tmp_path, SOURCE)
    reply = c.handle({'verb': 'capture-action', 'params': {
        'name': 'two-steps', 'steps': [{'verb': 'step', 'params': {'amount': 2}},
                                    {'verb': 'run', 'params': {'guest_ms': 20}}],
        'entry': 'menu', 'next_state': 'chosen', 'execute': True,
        'observation': {'before': 'menu seen', 'after': 'choice seen'}}})
    assert reply['ok'], reply
    assert reply['result']['execution']['steps'][0] == {'count': 2}
    assert not reply['result']['execution']['transition_verified']
    assert 'before' in reply['result'] and 'after' in reply['result']
    c.close()
    c2, _, _, d = make_controller(tmp_path, SOURCE.replace('+ amount', '- amount'))
    result = c2.handle({'verb': 'two-steps'})
    assert result['ok'] and result['result']['steps'][0] == {'count': -2}
    assert [name for name, _ in d.calls] == ['run']  # no repeat screenshots
    c2.close()


def test_entry_observation_and_failure_preserve_recipe_without_auto_retry(tmp_path):
    c, _, _, _ = make_controller(tmp_path, SOURCE)
    params = {'name': 'guarded', 'steps': [{'verb': 'step'}], 'requires': {'scene': 'menu'}}
    assert c.handle({'verb': 'capture-action', 'params': params})['ok']
    assert not c.handle({'verb': 'guarded'})['ok']
    assert c.ctx.state == {}
    assert c.handle({'verb': 'observe-state', 'params': {'state': {'scene': 'menu'}, 'observation': 'frame-1'}})['ok']
    assert c.handle({'verb': 'guarded'})['result']['steps'] == [{'count': 1}]
    assert c.ctx.state['scene'] == 'menu'  # never infer transition from input receipt
    assert not c.handle({'verb': 'capture-action', 'params': params})['ok']
    assert c.handle({'verb': 'capture-action', 'params': {**params, 'replace': True}})['ok']
    c.close()


def test_bad_recipes_fail_before_effects_and_python_can_promote(tmp_path):
    c, path, _, d = make_controller(tmp_path, SOURCE)
    for step in ({'verb': 'close'}, {'verb': 'missing'}, {'verb': 'new'}):
        assert not c.handle({'verb': 'capture-action', 'params': {'name': 'new', 'steps': [step]}})['ok']
    assert not d.calls and not c.recipes_path.exists()
    assert c.handle({'verb': 'capture-action', 'params': {'name': 'new', 'steps': [{'verb': 'step'}]}})['ok']
    path.write_text(SOURCE + "\nACTIONS['new'] = {'handler': lambda ctx: 'native replacement'}\n")
    assert c.handle({'verb': 'new'})['result'] == 'native replacement'
    assert json.loads(c.recipes_path.read_text())['actions']['new']['steps']
    c.close()


def test_failed_capture_exposes_completed_steps_and_before_frame(tmp_path):
    source = SOURCE + "\ndef fail(ctx): raise RuntimeError('blocked')\nACTIONS['fail'] = {'handler': fail}\n"
    c, _, _, _ = make_controller(tmp_path, source)
    reply = c.handle({'verb': 'capture-action', 'params': {'name': 'partial',
                     'steps': [{'verb': 'step'}, {'verb': 'fail'}], 'execute': True}})
    assert not reply['ok']
    assert reply['capture_progress']['before']['artifact'] == 'frame-id'
    assert reply['capture_progress']['path'] == str(c.recipes_path)
    assert reply['recipe_progress'][0]['completed_steps'] == [{'count': 1}]
    assert reply['recipe_progress'][0]['active_step'] == 1
    assert c.ctx.state['count'] == 1
    assert c.handle({'verb': 'step'})['result'] == {'count': 2}
    c.close()


def test_non_json_step_keeps_failure_response_serializable(tmp_path):
    source = SOURCE + "\nACTIONS['bytes'] = {'handler': lambda ctx: b'raw'}\n"
    c, _, _, _ = make_controller(tmp_path, source)
    assert c.handle({'verb': 'capture-action', 'params': {'name': 'bad-result',
                     'steps': [{'verb': 'step'}, {'verb': 'bytes'}]}})['ok']
    reply = c.handle({'verb': 'bad-result'})
    assert not reply['ok']
    json.dumps(reply, allow_nan=False)
    assert c.handle({'verb': 'step'})['result'] == {'count': 2}
    c.close()
