import io
import json
import os
import base64
import struct
from pathlib import Path

import pytest

from fdisbull.z_controller import MAX_REQUEST_BYTES, ZController, serve, serve_controller


class FakeSession:
    run_id = 'owned-run'

    def __init__(self):
        self.calls = []
        self.closed = False
        self.close_count = 0

    def call(self, method, params=None):
        self.calls.append((method, params))
        return {'method': method, 'data_base64': 'AAECAw=='}

    def run(self, **params):
        self.calls.append(('run', params))
        return {'outcome': 'guest_time', 'guest_elapsed_ms': params['guest_ms'],
                'requested_guest_ms': params['guest_ms'], 'timed_out': False,
                'host_elapsed_ms': 2, 'session': {'large': 'omitted'}}

    def screenshot(self, name):
        self.calls.append(('screenshot', name))
        return {'artifact': 'frame-id', 'name': name, 'sha256': 'frame-digest',
                'metadata': {'width': 320, 'height': 200}}

    def close(self):
        self.close_count += 1
        self.closed = True


class FakeProject:
    def __init__(self):
        self.close_count = 0
        self.exports = []

    def __exit__(self, *args):
        self.close_count += 1

    def debug_export(self, artifact, path):
        self.exports.append((artifact, path))


def make_controller(tmp_path, source):
    path = tmp_path / 'actions.py'
    path.write_text(source)
    project, session = FakeProject(), FakeSession()
    return ZController(project, session, path), path, project, session


SOURCE = '''
def step(ctx, amount=1):
    ctx.state['count'] = ctx.state.get('count', 0) + amount
    return {'count': ctx.state['count']}
def route(ctx):
    return [ctx.invoke('step', amount=2), ctx.invoke('step', amount=3)]
ACTIONS = {
    'step': {'handler': step, 'description': 'Advance once', 'entry': 'ready', 'next_state': 'advanced'},
    'route': {'handler': route, 'entry': 'ready', 'next_state': 'advanced'},
}
'''


@pytest.fixture
def serializer_controller(tmp_path):
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    code = b'\xb8' + struct.pack('<I', 0x2000)
    code += b'\x8b\x15' + struct.pack('<I', 0x3000)
    code += b'\xbb' + struct.pack('<I', 12)
    code += b'\xe8' + struct.pack('<i', 0x5000 - (0x1000 + len(code) + 5)) + b'\xc3'

    def memory(method, params):
        session.calls.append((method, params))
        assert method == 'memory.read'
        assert params['address']['space'] == 'linear'
        address = int(params['address']['offset'], 16)
        data = {0x1000: code, 0x2000: b'actors.dat\0'}.get(address, b'')
        return {'data_base64': base64.b64encode(data).decode()}

    session.call = memory
    options = {
        'ranges': [[0x1000, 0x1000 + len(code)]], 'code_base': 0x1000,
        'serializers': [{'entry': 0x5000, 'operation': 'write',
                         'filename': 'eax', 'buffer': 'edx', 'length': 'ebx'}]}
    yield controller, options, session
    controller.close()


def test_serializer_json_defaults_to_summary_and_retains_raw_once(serializer_controller, tmp_path):
    controller, options, session = serializer_controller
    reply = controller.handle({'verb': 'serializer-candidates', 'params': options})
    assert reply['ok'], reply
    summary = reply['result']
    assert summary['format'] == 'fdisbull-serializer-candidate-summary-1'
    assert 'candidates' not in summary
    path = Path(summary['path'])
    assert path.parent == tmp_path / 'evidence'
    assert path.name.startswith('serializer-candidates-')
    raw = json.loads(path.read_text())
    assert raw == controller.ctx.state['serializer_candidates']
    candidate, = raw['candidates']
    assert candidate['filename']['text'] == 'actors.dat'
    assert candidate['buffer'] == {'kind': 'pointer_global', 'address': 0x3000, 'pointer_width': 4}
    assert candidate['length'] == 12
    family, = summary['families']
    assert family['writes'][0]['buffer']['slot_address'] == '0x3000'
    assert family['writes'][0]['buffer']['pointee_address'] is None
    assert family['observed_write_lengths'] == [12]
    summary_reads = list(session.calls)
    assert sum(int(params['address']['offset'], 16) == 0x1000 for _, params in summary_reads) == 1
    session.calls.clear()
    assert controller.ctx.serializer_candidates(**options) == raw
    assert session.calls == summary_reads  # Summarizing adds no native reads.
    assert not session.closed


def test_serializer_python_default_keeps_numeric_raw_result(serializer_controller, tmp_path):
    controller, options, session = serializer_controller
    raw = controller.ctx.serializer_candidates(**options)
    assert raw['format'] == 'fdisbull-serializer-candidates-1'
    assert raw['candidates'][0]['buffer']['address'] == 0x3000
    assert raw is controller.ctx.state['serializer_candidates']
    assert 'path' not in raw
    assert not (tmp_path / 'evidence').exists()
    assert session.calls


def test_serializer_json_raw_override_and_custom_output(serializer_controller, tmp_path):
    controller, options, session = serializer_controller
    output = tmp_path / 'phase' / 'load-candidates.json'
    reply = controller.handle({'verb': 'serializer-candidates', 'params': {
        **options, 'summary': False, 'output': str(output)}})
    assert reply['ok'], reply
    raw = reply['result']
    assert raw['format'] == 'fdisbull-serializer-candidates-1'
    assert raw['path'] == str(output)
    assert raw['candidates'][0]['buffer']['address'] == 0x3000
    assert json.loads(output.read_text()) == controller.ctx.state['serializer_candidates']
    assert sum(int(params['address']['offset'], 16) == 0x1000 for _, params in session.calls) == 1


def test_serializer_summary_validation_precedes_native_reads(serializer_controller):
    controller, options, session = serializer_controller
    reply = controller.handle({'verb': 'serializer-candidates', 'params': {**options, 'summary': 'false'}})
    assert not reply['ok']
    assert reply['error']['message'] == 'summary must be boolean'
    assert session.calls == []


def test_serializer_default_paths_preserve_earlier_extraction(serializer_controller):
    controller, options, session = serializer_controller
    first = controller.handle({'verb': 'serializer-candidates', 'params': options})['result']
    first_path = Path(first['path'])
    original = first_path.read_bytes()
    previous_read = session.call

    def changed_filename(method, params):
        if int(params['address']['offset'], 16) == 0x2000:
            return {'data_base64': base64.b64encode(b'changed.dat\0').decode()}
        return previous_read(method, params)

    session.call = changed_filename
    second = controller.handle({'verb': 'serializer-candidates', 'params': options})['result']
    assert first['path'] != second['path']
    assert first_path.read_bytes() == original
    assert json.loads(original)['candidates'][0]['filename']['text'] == 'actors.dat'
    assert json.loads(Path(second['path']).read_text())['candidates'][0]['filename']['text'] == 'changed.dat'


@pytest.fixture
def record_controller(tmp_path):
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    source = b''.join((i.to_bytes(4, 'little') + f'Actor {i}'.encode()).ljust(68, b'\0')
                      for i in range(250)) + b'footer'
    path = tmp_path / 'actors.dat'
    path.write_bytes(source)
    options = {'path': str(path), 'stride': 68, 'source_label': 'synthetic census', 'name_offset': 4}
    yield controller, options, source, session
    controller.close()


def test_record_json_keeps_full_census_with_bounded_preview(record_controller, tmp_path, monkeypatch):
    from fdisbull import record_candidates
    controller, options, source, session = record_controller
    original_read = record_candidates._read
    reads = []

    def read_once(*args):
        reads.append(args)
        return original_read(*args)

    monkeypatch.setattr(record_candidates, '_read', read_once)
    reply = controller.handle({'verb': 'record-rows', 'params': options})
    assert reply['ok'], reply
    summary = reply['result']
    assert summary['complete'] is True
    assert summary['record_count'] == summary['returned_rows'] == 250
    assert summary['next_row'] is None
    assert summary['named_rows_in_returned_range'] == 250
    assert summary['named_rows_truncated'] is True
    assert len(summary['named_rows']) <= 16
    assert len(summary['example_rows']) <= 4
    assert 'rows' not in summary
    assert len(json.dumps(summary)) < 5000
    path = Path(summary['path'])
    assert path.parent == tmp_path / 'evidence'
    assert path.name.startswith('record-rows-')
    raw = json.loads(path.read_text())
    assert raw == controller.ctx.state['record_rows']
    reconstructed = b''.join(bytes.fromhex(row['raw_hex']) for row in raw['rows'])
    assert reconstructed + bytes.fromhex(raw['trailing_hex']) == source
    assert len(reads) == 1
    assert session.calls == []


def test_record_json_partial_census_and_raw_override(record_controller, tmp_path):
    controller, options, _, _ = record_controller
    reply = controller.handle({'verb': 'record-rows', 'params': {**options, 'limit': 10}})
    summary = reply['result']
    assert summary['complete'] is False
    assert summary['returned_rows'] == 10 and summary['record_count'] == 250
    assert summary['next_row'] == 10
    raw = json.loads(Path(summary['path']).read_text())
    assert len(raw['rows']) == 10 and raw['complete'] is False
    reply = controller.handle({'verb': 'record-rows', 'params': {
        **options, 'summary': False, 'output': 'phase/records.json'}})
    assert reply['ok'], reply
    assert len(reply['result']['rows']) == 250
    assert reply['result']['path'] == str(tmp_path / 'phase' / 'records.json')
    assert reply['result']['complete'] is True


def test_record_python_default_preserves_raw_shape_without_writing(record_controller, tmp_path):
    controller, options, _, _ = record_controller
    raw = controller.ctx.record_rows(**options)
    assert len(raw['rows']) == 250
    assert raw is controller.ctx.state['record_rows']
    assert 'path' not in raw and 'format' not in raw
    assert not (tmp_path / 'evidence').exists()


def test_record_default_paths_preserve_earlier_source_census(record_controller):
    controller, options, source, _ = record_controller
    first = controller.handle({'verb': 'record-rows', 'params': options})['result']
    first_path = Path(first['path'])
    original = first_path.read_bytes()
    Path(options['path']).write_bytes(source.replace(b'Actor 0\0', b'NewOne!\0', 1))
    second = controller.handle({'verb': 'record-rows', 'params': options})['result']
    assert first['path'] != second['path']
    assert first_path.read_bytes() == original
    assert json.loads(original)['rows'][0]['name'] == 'Actor 0'
    assert json.loads(Path(second['path']).read_text())['rows'][0]['name'] == 'NewOne!'


def test_record_summary_bounds_long_names_and_bytes(tmp_path):
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    path = tmp_path / 'long-name.dat'
    path.write_bytes(b'A' * 4096)
    reply = controller.handle({'verb': 'record-rows', 'params': {
        'path': str(path), 'source_label': 'synthetic long name',
        'stride': 4096, 'name_offset': 0, 'name_length': 4096}})
    assert reply['ok'], reply
    summary = reply['result']
    assert summary['named_rows'][0]['name_truncated'] is True
    assert len(summary['named_rows'][0]['name']) <= 80
    assert summary['example_rows'][0]['raw_prefix_truncated'] is True
    assert len(summary['example_rows'][0]['raw_prefix_hex']) <= 64
    assert len(json.dumps(summary)) < 2000
    assert session.calls == []
    controller.close()


def test_named_actions_compose_and_reload_without_restarting(tmp_path):
    c, path, p, d = make_controller(tmp_path, SOURCE)
    listing = c.handle({'verb': 'list'})
    assert listing['ok']
    assert listing['result']['actions'][0]['entry'] == 'ready'
    assert listing['result']['actions'][0]['parameters']['optional'] == {'amount': 1}
    assert listing['result']['builtin_parameters']['record-frontier']['required'] == ['roots']
    frontier = listing['result']['builtin_parameters']['record-frontier']
    assert frontier['optional']['output'] is None
    assert frontier['generated_defaults']['output'] == 'evidence/record-frontier-{monotonic_ns}.json'
    assert listing['result']['builtin_parameters']['serializer-discovery']['required'] == ['ranges']
    candidates = listing['result']['builtin_parameters']['serializer-candidates']
    assert candidates['required'] == ['ranges', 'serializers']
    assert candidates['optional']['summary'] is True
    assert candidates['optional']['output'] is None
    assert candidates['generated_defaults']['output'] == 'evidence/serializer-candidates-{monotonic_ns}.json'
    rows = listing['result']['builtin_parameters']['record-rows']
    assert rows['optional']['summary'] is True
    assert rows['optional']['output'] is None
    assert rows['generated_defaults']['output'] == 'evidence/record-rows-{monotonic_ns}.json'
    assert rows['optional']['limit'] == 256
    assert c.handle({'verb': 'route', 'id': 'r'})['result'] == [{'count': 2}, {'count': 5}]
    original_stat = path.stat()
    path.write_text(SOURCE.replace("+ amount", "- amount"))
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert c.handle({'verb': 'step'})['result'] == {'count': 4}
    assert c.ctx.d is d and c.ctx.p is p
    assert d.close_count == p.close_count == 0
    c.close()


def test_bad_reload_does_not_run_stale_code_or_destroy_state(tmp_path):
    c, path, p, d = make_controller(tmp_path, SOURCE)
    assert c.handle({'verb': 'step'})['result']['count'] == 1
    path.write_text('this is not valid python !')
    error = c.handle({'verb': 'step'})
    assert not error['ok'] and error['error']['type'] == 'SyntaxError'
    assert c.ctx.state['count'] == 1 and not d.closed
    assert c.handle({'verb': 'call', 'params': {'method': 'memory.read'}})['ok']
    path.write_text(SOURCE + "\ndef fail(ctx):\n    ctx.state['partial'] = True\n    raise RuntimeError('action failed')\nACTIONS['fail'] = {'handler': fail}\n")
    assert not c.handle({'verb': 'fail'})['ok']
    assert c.ctx.state['partial'] is True
    assert c.handle({'verb': 'step'})['result']['count'] == 2
    c.close()
    assert d.close_count == p.close_count == 1


def test_helpers_require_guest_budget_and_keep_raw_bytes(tmp_path):
    c, path, p, d = make_controller(tmp_path, SOURCE)
    assert not c.handle({'verb': 'run', 'params': {'timeout_ms': 100}})['ok']
    assert d.calls == []
    assert c.handle({'verb': 'run', 'params': {'guest_ms': 50, 'timeout_ms': 500}})['result']['guest_elapsed_ms'] == 50
    assert 'session' not in c.handle({'verb': 'run', 'params': {'guest_ms': 5}})['result']
    assert c.handle({'verb': 'call', 'params': {'method': 'memory.read'}})['result']['data_base64'] == 'AAECAw=='
    frame = c.handle({'verb': 'frame', 'params': {'output': 'frame.png'}})['result']
    assert frame['artifact'] == 'frame-id'
    assert p.exports == [('frame-id', tmp_path / 'frame.png')]
    c.close()


def test_jsonl_recovers_after_bad_requests_and_closes_on_eof(tmp_path):
    c, path, p, d = make_controller(tmp_path, SOURCE + "\nprint('module diagnostic')\n")
    output, errors = io.StringIO(), io.StringIO()
    serve_controller(c, io.StringIO('bad json\n[]\n{"verb":"step","id":7}\n'), output, error_stream=errors)
    rows = [json.loads(s) for s in output.getvalue().splitlines()]
    assert rows[0]['event'] == 'ready'
    assert [r['ok'] for r in rows[1:]] == [False, False, True]
    assert rows[-1]['id'] == 7 and rows[-1]['result'] == {'count': 1}
    assert 'module diagnostic' in errors.getvalue()
    assert d.close_count == p.close_count == 1


def test_close_stops_stream_and_cleanup_still_closes_project_on_error(tmp_path):
    c, path, p, d = make_controller(tmp_path, SOURCE)
    out = io.StringIO()
    serve_controller(c, io.StringIO('{"verb":"close"}\n{"verb":"step"}\n'), out)
    assert len(out.getvalue().splitlines()) == 2
    c.close()
    assert d.close_count == p.close_count == 1
    c, path, p, d = make_controller(tmp_path, SOURCE)
    def fail_close():
        raise RuntimeError('cleanup failed')
    d.close = fail_close
    with pytest.raises(RuntimeError, match='cleanup failed'):
        c.close()
    assert p.close_count == 1


def test_composed_route_keeps_one_generation_until_next_request(tmp_path):
    source = SOURCE + '''
from pathlib import Path
def replace_and_route(ctx):
    p = Path(__file__)
    p.write_text(p.read_text().replace('+ amount', '- amount'))
    return ctx.invoke('route')
ACTIONS['replace-and-route'] = {'handler': replace_and_route}
'''
    c, path, p, d = make_controller(tmp_path, source)
    assert c.handle({'verb': 'replace-and-route'})['result'] == [{'count': 2}, {'count': 5}]
    assert c.handle({'verb': 'step'})['result'] == {'count': 4}
    c.close()


def test_module_system_exit_and_non_json_result_do_not_end_the_owner(tmp_path):
    c, path, p, d = make_controller(tmp_path, 'raise SystemExit(3)')
    assert c.handle({'verb': 'list'})['error']['type'] == 'SystemExit'
    assert not d.closed
    path.write_text("def bad(ctx): return b'raw'\nACTIONS = {'bad': {'handler': bad}}\n")
    assert c.handle({'verb': 'bad'})['error']['type'] == 'TypeError'
    path.write_text(SOURCE)
    assert c.handle({'verb': 'route'})['ok']
    c.close()


def test_bad_large_and_utf8_lines_are_drained_without_losing_next_request(tmp_path):
    c, path, p, d = make_controller(tmp_path, SOURCE)
    incoming = io.BytesIO(b'x' * (MAX_REQUEST_BYTES + 20) + b'\n\xff\n{"verb":"step"}\n')
    output = io.StringIO()
    serve_controller(c, incoming, output)
    rows = [json.loads(s) for s in output.getvalue().splitlines()]
    assert [r['ok'] for r in rows[1:]] == [False, False, True]
    assert rows[-1]['result'] == {'count': 1}
    assert d.close_count == p.close_count == 1


def test_transport_failure_closes_both_resources(tmp_path):
    c, path, p, d = make_controller(tmp_path, SOURCE)
    class BrokenOutput:
        def write(self, value):
            raise BrokenPipeError('consumer disconnected')
    with pytest.raises(BrokenPipeError):
        serve_controller(c, io.StringIO(''), BrokenOutput())
    assert d.close_count == p.close_count == 1


def test_open_constructs_only_one_session_and_closes_failed_launch(tmp_path):
    actions = tmp_path / 'actions.py'
    actions.write_text(SOURCE)
    project, session = FakeProject(), FakeSession()
    launches = []
    def launch(executable, game_dir, **kwargs):
        launches.append((executable, game_dir, kwargs))
        return session
    project.debugger = launch
    output = io.StringIO()
    serve('project.fdb', 'backend', 'game', actions, debugger_options={'version': 1},
          project_factory=lambda path: project,
          input_stream=io.StringIO('{"verb":"route"}\n{"verb":"step"}\n'),
          output_stream=output)
    assert launches == [('backend', 'game', {'version': 1})]
    assert session.close_count == project.close_count == 1
    failed = FakeProject()
    def fail_launch(*args, **kwargs):
        raise ValueError('bad backend')
    failed.debugger = fail_launch
    with pytest.raises(ValueError, match='bad backend'):
        ZController.open('project.fdb', 'backend', 'game', actions, project_factory=lambda path: failed)
    assert failed.close_count == 1


def test_frontier_summary_bounds_large_shared_groups_without_losing_unknowns(tmp_path, monkeypatch):
    import fdisbull.record_candidates as module
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    sources = [{'label': 'handoff', 'path': '/source', 'files': [],
                'files_truncated': True, 'errors': [{'reason': 'unreadable'}]}]
    changes = []
    for index in range(150):
        identity = {'label': 'handoff', 'path': f'/source/f{index}.dat', 'size': 50,
                    'sha256': 'a' * 64}
        changes.append({'relative_path': f'f{index}.dat', 'before': identity,
                        'after': identity if index < 140 else None,
                        'kind': 'same_bytes' if index < 140 else 'unobserved'})
    shared = [{'source_label': 'handoff', 'source_root': '/source', 'record_count': index + 10,
               'basis': 'equal arithmetic row counts; relationship unverified',
               'files': [{'path': f'/source/f{j}.dat', 'relative_path': f'f{j}.dat',
                          'stride': 12, 'name_supported': index == 79 and j == 49}
                         for j in range(50)]} for index in range(80)]
    tasks = [{'kind': 'inspect_partitions', 'source_label': 'handoff',
              'path': f'/source/f{i}.dat', 'size': 50, 'candidate': None,
              'requires_runtime': False, 'next': 'Inspect the selected rows'} for i in range(32)]
    raw = {'schema': 'fdisbull-record-frontier-1', 'sources': sources, 'changes': changes,
           'source_comparisons': [{'before_label': 'earlier', 'after_label': 'handoff', 'files': changes}],
           'shared_record_counts': shared, 'ready_tasks': tasks,
           'blocked_tasks': [{'kind': 'runtime', 'reason': 'Save control unresolved', 'blocks_offline_tasks': False}],
           'errors': [{'source_label': 'handoff', 'path': f'/source/f{i}', 'reason': 'unobserved'} for i in range(20)],
           'limits': {'ready_tasks_total': 100, 'ready_tasks_omitted': 68}, 'status': 'partial'}
    calls = []
    def analyze(**options):
        calls.append(options)
        return raw
    monkeypatch.setattr(module, 'record_frontier', analyze)
    reply = controller.handle({'verb': 'record-frontier', 'params': {
        'roots': [{'path': '/source', 'label': 'handoff'}]}})
    assert reply['ok'], reply
    summary = reply['result']
    assert summary['format'] == 'fdisbull-record-frontier-summary-1'
    assert summary['status'] == 'partial'
    assert summary['sources'][0]['files_truncated'] is True
    assert summary['change_counts'] == {'same_bytes': 140, 'unobserved': 10}
    assert all(row['kind'] == 'unobserved' for row in summary['changes'])
    assert all(row['after_size'] is None for row in summary['changes'])
    assert summary['source_comparisons'][0]['change_counts']['unobserved'] == 10
    assert len(summary['shared_record_counts']) == 4
    strongest = summary['shared_record_counts'][0]
    assert strongest['record_count'] == 89
    assert strongest['files'][0]['name_supported'] is True
    assert strongest['file_preview'] == {'total': 50, 'returned': 6, 'omitted': 44}
    assert summary['previews']['shared_record_counts']['omitted'] == 76
    assert summary['previews']['ready_tasks'] == {'total': 100, 'returned': 8, 'omitted': 92}
    assert summary['previews']['errors'] == {'total': 20, 'returned': 8, 'omitted': 12}
    assert summary['blocked_tasks'] == raw['blocked_tasks']
    assert 'sha256' not in json.dumps(summary)
    assert len(json.dumps(summary)) < 16000
    assert len(json.dumps(raw)) > 350000
    assert json.loads(Path(summary['path']).read_text()) == raw
    assert controller.ctx.state['record_frontier'] is raw
    assert len(calls) == 1 and session.calls == []
    controller.close()


def test_frontier_default_artifacts_preserve_previous_snapshots_and_read_once(tmp_path, monkeypatch):
    import fdisbull.record_candidates as module
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    source = tmp_path / 'files'
    source.mkdir()
    target = source / 'actors.dat'
    target.write_bytes(bytes(68 * 3))
    reads = []
    original_read = module._read
    def read(path, maximum):
        reads.append(path)
        return original_read(path, maximum)
    monkeypatch.setattr(module, '_read', read)
    roots = [{'path': str(source), 'label': 'selected slot'}]
    first = controller.handle({'verb': 'record-frontier', 'params': {'roots': roots}})['result']
    first_path = Path(first['path'])
    first_bytes = first_path.read_bytes()
    assert first_path.name.startswith('record-frontier-')
    target.write_bytes(b'A' + target.read_bytes()[1:])
    second = controller.handle({'verb': 'record-frontier', 'params': {
        'roots': roots, 'previous': first['path']}})['result']
    assert second['path'] != first['path']
    assert first_path.read_bytes() == first_bytes
    assert second['change_counts'] == {'changed': 1}
    assert second['changes'][0]['source_label'] == 'selected slot'
    assert second['changes'][0]['before_size'] == second['changes'][0]['after_size'] == 204
    assert len(reads) == 2  # One actual file read per invocation, not another for the summary.
    assert json.loads(Path(second['path']).read_text()) == controller.ctx.state['record_frontier']
    assert session.calls == []
    controller.close()


def test_frontier_raw_override_and_explicit_output(tmp_path):
    controller, _, _, session = make_controller(tmp_path, SOURCE)
    source = tmp_path / 'files'
    source.mkdir()
    (source / 'actors.dat').write_bytes(bytes(68 * 3))
    reply = controller.handle({'verb': 'record-frontier', 'params': {
        'roots': [{'path': str(source), 'label': 'selected slot'}],
        'summary': False, 'output': 'phase/frontier.json'}})
    assert reply['ok'], reply
    raw = reply['result']
    assert raw['schema'] == 'fdisbull-record-frontier-1'
    assert raw['sources'][0]['files'][0]['sha256']
    assert raw['path'] == str(tmp_path / 'phase/frontier.json')
    assert json.loads(Path(raw['path']).read_text()) == controller.ctx.state['record_frontier']
    assert session.calls == []
    controller.close()
