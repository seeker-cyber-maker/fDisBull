"""Authored adapter and public-routing checks, not original-game qualification.

The imported fixture explicitly replaces the edition profile with an authored,
unqualified all-return resource. It tests package plumbing and rule realization;
it does not establish correspondence to original game code or native behavior.
"""
from copy import deepcopy
import gzip
import json

import pytest

from fdisbull.cli import main, respond
from fdisbull.court_adapter import CourtAdapterError, CourtRuntime, evaluate_bow
from test_kq1_bow_mapping import authored_game, authored_package, authored_profile


def source_state():
    value = {'variables': [0] * 256, 'flags': [False] * 256,
             'ego': {'x': 70, 'y': 110}, 'words': [239, 208],
             'player_control': True, 'host': {'authored_marker': ['preserved']}}
    value['variables'][0], value['variables'][3] = 53, 1
    value['flags'][2] = True
    return value


def waiting_state():
    value = source_state()
    value['ego']['x'] = 63
    value['variables'][3] = 4
    value['flags'][22] = value['flags'][24] = True
    value['flags'][98] = value['flags'][168] = True
    value['player_control'] = False
    return value


def write_document(path, value):
    raw = json.dumps(value).encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == '.gz' else raw)
    return path


@pytest.fixture
def runtime(authored_package):
    return CourtRuntime(authored_package)


def ack(runtime, result, state=None):
    return runtime.step(result['state'] if state is None else state,
                        {'kind': 'ack', 'continuation': result['continuation']})


def test_only_declared_clock_changes_survive_both_modal_acknowledgements(runtime):
    before = waiting_state()
    original = deepcopy(before)
    refusal = runtime.step(before)
    assert refusal['status'] == 'awaiting_ack'
    assert refusal['effects'][-1] == {'operation': 'print', 'operands': [55]}
    ticked = deepcopy(refusal['state'])
    ticked['variables'][11:15] = [59, 59, 23, 254]
    completion = ack(runtime, refusal, ticked)
    assert completion['status'] == 'awaiting_ack'
    assert completion['effects'][-1] == {'operation': 'print', 'operands': [4]}
    assert completion['state']['variables'][11:15] == [59, 59, 23, 254]
    assert completion['state']['ego'] == {'x': 70, 'y': 110}
    assert completion['state']['variables'][3] == 4
    assert completion['state']['flags'][22] is False
    assert completion['state']['flags'][98] is False
    ticked_again = deepcopy(completion['state'])
    ticked_again['variables'][11:15] = [0, 0, 0, 255]
    finished = ack(runtime, completion, ticked_again)
    assert finished['status'] == 'slice_complete'
    assert finished['state'] == ticked_again
    assert finished['effects'] == [] and finished['continuation'] is None
    assert before == original
    assert refusal['state']['variables'][11:15] == [0, 0, 0, 0]


@pytest.mark.parametrize('change', [
    lambda s: s['variables'].__setitem__(3, 99),
    lambda s: s['variables'].__setitem__(60, 99),
    lambda s: s['variables'].__setitem__(61, 99),
    lambda s: s['variables'].__setitem__(31, 99),
    lambda s: s['variables'].__setitem__(100, 99),
    lambda s: s['ego'].__setitem__('x', 64),
    lambda s: s['flags'].__setitem__(168, False),
    lambda s: s['flags'].__setitem__(4, False),
    lambda s: s['words'].pop(),
    lambda s: s.__setitem__('player_control', True),
    lambda s: s['host']['authored_marker'].append('changed'),
])
def test_modal_ack_refuses_every_other_source_state_change(runtime, change):
    pending = runtime.step(waiting_state())
    changed = deepcopy(pending['state'])
    changed['variables'][11] = 1  # Clock movement cannot authorize other writes.
    change(changed)
    original = deepcopy(changed)
    with pytest.raises(CourtAdapterError, match='Stale source state'):
        ack(runtime, pending, changed)
    assert changed == original


def test_modal_token_remains_bound_to_the_validated_package(runtime):
    pending = runtime.step(waiting_state())
    pending['continuation']['package_sha256'] = '0' * 64
    with pytest.raises(CourtAdapterError, match='package'):
        ack(runtime, pending)


@pytest.mark.parametrize('change', [
    lambda s: s['variables'].pop(),
    lambda s: s['variables'].__setitem__(3, True),
    lambda s: s['variables'].__setitem__(3, 256),
    lambda s: s['variables'].__setitem__(3, -1),
    lambda s: s['flags'].pop(),
    lambda s: s['flags'].__setitem__(24, 1),
    lambda s: s['ego'].__setitem__('x', False),
    lambda s: s['ego'].__setitem__('z', 1),
    lambda s: s['words'].append(True),
    lambda s: s['words'].append(65536),
    lambda s: s.__setitem__('player_control', 1),
    lambda s: s.__setitem__('host', []),
    lambda s: s.__setitem__('extra', 1),
    lambda s: s.pop('ego'),
])
def test_raw_state_validation_rejects_widened_or_missing_types(runtime, change):
    before = source_state()
    change(before)
    original = deepcopy(before)
    with pytest.raises(CourtAdapterError):
        runtime.step(before)
    assert before == original


@pytest.mark.parametrize('space,number,value,reason', [
    ('variables', 0, 54, 'outside_initial_audience'),
    ('variables', 74, 3, 'outside_initial_audience'),
    ('flags', 5, True, 'outside_initial_audience'),
    ('flags', 27, True, 'outside_initial_audience'),
    ('flags', 194, True, 'outside_initial_audience'),
    ('flags', 195, True, 'outside_initial_audience'),
    ('variables', 30, 1, 'ending_prefix_not_idle'),
    ('variables', 70, 1, 'ending_prefix_not_idle'),
    ('variables', 71, 1, 'ending_prefix_not_idle'),
    ('flags', 15, True, 'nonblocking_or_timed_output'),
    ('variables', 21, 1, 'nonblocking_or_timed_output'),
    ('flags', 22, True, 'unqualified_animation_completion'),
])
def test_unqualified_context_is_returned_unchanged_without_semantic_effects(
        runtime, space, number, value, reason):
    before = source_state()
    before[space][number] = value
    original = deepcopy(before)
    result = runtime.step(before)
    assert result['status'] == 'unrecovered'
    assert result['reason'] == reason
    assert result['state'] == original
    assert result['effects'] == [] and result['executed_intents'] == []
    assert result['continuation'] is None
    result['state']['host']['authored_marker'].append('caller result mutation')
    assert before == original


@pytest.mark.parametrize('change,reason', [
    (lambda s: s.__setitem__('words', [13, 208]), 'other_parser_command_retained_as_ir'),
    (lambda s: s.__setitem__('words', []), 'other_parser_command_retained_as_ir'),
    (lambda s: s['ego'].__setitem__('x', 160), 'actor_outside_qualified_screen'),
    (lambda s: s['ego'].__setitem__('y', 168), 'actor_outside_qualified_screen'),
])
def test_other_commands_and_outside_screen_positions_stay_unrecovered(runtime, change, reason):
    before = source_state()
    change(before)
    result = runtime.step(before)
    assert result['status'] == 'unrecovered' and result['reason'] == reason
    assert result['state'] == before and result['effects'] == []


def test_public_api_reads_gzipped_package_state_and_ack_event(authored_package, tmp_path):
    package = write_document(tmp_path / 'authored.package.json.gz', authored_package)
    before = waiting_state()
    state_file = write_document(tmp_path / 'authored.state.json.gz', before)
    first = evaluate_bow(package, state_file=state_file)
    assert first['status'] == 'awaiting_ack'
    assert first['native_execution'] is False
    assert first['execution_scope'] == 'intent_rules_and_bound_engine_requests'
    assert first['host_dependencies'] == [
        'animation_scheduler', 'rendering', 'modal_input_and_clock']
    clocked = deepcopy(first['state'])
    clocked['variables'][11] = 1
    write_document(state_file, clocked)
    event_file = write_document(tmp_path / 'authored.event.json.gz',
                                {'kind': 'ack', 'continuation': first['continuation']})
    second = evaluate_bow(package, state_file=state_file, event_file=event_file)
    assert second['status'] == 'awaiting_ack'
    assert second['outcome'] == 'bow_completed'
    assert second['state']['variables'][11] == 1
    assert second['effects'][-1] == {'operation': 'print', 'operands': [4]}
    assert gzip.decompress(state_file.read_bytes()) == json.dumps(clocked).encode()
    assert json.loads(gzip.decompress(package.read_bytes())) == authored_package


@pytest.mark.parametrize('options', [
    {}, {'state': source_state(), 'state_file': 'unused.json'},
    {'state': source_state(), 'event': {'kind': 'cycle'}, 'event_file': 'unused.json'},
])
def test_public_api_rejects_ambiguous_input_sources_before_reading(options):
    with pytest.raises(CourtAdapterError, match='Supply'):
        evaluate_bow('does-not-exist.json', **options)


def test_public_event_budget_applies_to_decompressed_bytes(authored_package, tmp_path):
    package = write_document(tmp_path / 'authored.package.json', authored_package)
    oversized = tmp_path / 'authored.event.json.gz'
    oversized.write_bytes(gzip.compress(b' ' * (64 * 1024) + b'{"kind":"cycle"}', mtime=0))
    assert oversized.stat().st_size < 1024
    with pytest.raises(CourtAdapterError, match='byte budget'):
        evaluate_bow(package, state=source_state(), event_file=oversized)


@pytest.mark.parametrize('contents', [
    gzip.compress(b'{}', mtime=0)[:-4],
    bytes.fromhex('1f8b0800000000000203') + b'\xff' * 10,
], ids=['truncated_footer', 'invalid_deflate'])
def test_public_cli_returns_a_structured_error_for_damaged_gzip(tmp_path, capsys, contents):
    damaged = tmp_path / 'authored.damaged.json.gz'
    damaged.write_bytes(contents)
    state_file = write_document(tmp_path / 'authored.state.json', source_state())
    assert main(['kq1-bow-evaluate', str(damaged), '--state-file', str(state_file)]) == 1
    response = json.loads(capsys.readouterr().out)
    assert response['ok'] is False
    assert response['error']['type'] == 'CourtAdapterError'


def test_projectless_respond_exports_and_evaluates_authored_package(authored_profile, tmp_path):
    game, _ = authored_profile
    project = tmp_path / 'must-not-open.fdb'
    package = tmp_path / 'authored.export.json.gz'
    exported = respond({'method': 'kq1-bow-intents', 'params': {
        'game_dir': str(game), 'output': str(package),
    }}, default_project=str(project))
    assert exported['ok'], exported
    assert exported['result']['bindings']['edition_qualification'] == 'unqualified_authored_mapping_fixture'
    assert exported['result']['bindings']['native_execution_verified'] is False
    response = respond({'method': 'kq1-bow-evaluate', 'params': {
        'package': str(package), 'state': source_state(),
    }}, default_project=str(project))
    assert response['ok'], response
    result = response['result']
    assert result['outcome'] == 'bow_started'
    assert result['state']['variables'][3] == 4
    assert result['state']['ego'] == {'x': 63, 'y': 110}
    assert result['native_execution'] is False
    assert not project.exists()


def test_real_cli_exports_evaluates_and_resumes_with_an_event_file(
        authored_profile, tmp_path, capsys):
    game, _ = authored_profile
    package, uil, udl = [tmp_path / name for name in
                         ('authored.package.json.gz', 'authored.uil.json', 'authored.udl.json.gz')]
    assert main(['kq1-bow-intents', str(game), '--output', str(package),
                 '--uil', str(uil), '--udl', str(udl)]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported['ok'], exported
    document = json.loads(gzip.decompress(package.read_bytes()))
    assert json.loads(uil.read_text()) == document['uil']
    assert json.loads(gzip.decompress(udl.read_bytes())) == document['udl']
    state_file = write_document(tmp_path / 'authored.state.json', waiting_state())
    assert main(['kq1-bow-evaluate', str(package), '--state-file', str(state_file)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first['ok'] and first['result']['status'] == 'awaiting_ack'
    pending = first['result']
    pending['state']['variables'][11] = 1
    write_document(state_file, pending['state'])
    event_file = write_document(tmp_path / 'authored.ack.json.gz',
                                {'kind': 'ack', 'continuation': pending['continuation']})
    assert main(['kq1-bow-evaluate', str(package), '--state-file', str(state_file),
                 '--event-file', str(event_file)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert second['ok'], second
    assert second['result']['outcome'] == 'bow_completed'
    assert second['result']['native_execution'] is False
    assert second['result']['state']['variables'][11] == 1
    assert second['result']['effects'][-1] == {'operation': 'print', 'operands': [4]}
    assert not list(tmp_path.glob('*.fdb'))


def test_real_cli_rejects_unqualified_fixture_without_exporting(authored_game, tmp_path, capsys):
    destination = tmp_path / 'not-created.json'
    assert main(['kq1-bow-intents', str(authored_game), '--output', str(destination)]) == 1
    response = json.loads(capsys.readouterr().out)
    assert response['ok'] is False
    assert 'Exact qualified KQ1 resource set' in response['error']['message']
    assert not destination.exists()


def test_public_cli_reports_invalid_raw_state_without_creating_a_project(
        authored_package, tmp_path):
    package = write_document(tmp_path / 'authored.package.json', authored_package)
    invalid = source_state()
    invalid['variables'][3] = True
    project = tmp_path / 'must-not-open.fdb'
    response = respond({'method': 'kq1-bow-evaluate', 'params': {
        'package': str(package), 'state': invalid,
    }}, default_project=str(project))
    assert response['ok'] is False
    assert response['error']['type'] == 'CourtAdapterError'
    assert not project.exists()
