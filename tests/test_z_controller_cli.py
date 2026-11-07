import io
import json

import pytest

from fdisbull.cli import main
from fdisbull.z_controller import ZController


def arguments(actions, *extra):
    return ['z-controller', 'private.fdb', '--executable', 'native-backend',
            '--game-dir', 'private-game', '--actions', str(actions), *extra]


def test_cli_retains_one_owner_and_passes_selected_launch_contract(tmp_path, monkeypatch, capsys):
    actions = tmp_path / 'actions.py'
    actions.write_text('''
print('trusted action diagnostic')
def look(ctx):
    ctx.state['visits'] = ctx.state.get('visits', 0) + 1
    return {'visits': ctx.state['visits']}
ACTIONS = {'look': {'handler': look, 'entry': 'initial scene', 'next_state': 'same scene'}}
''')
    events = []
    class Project:
        def __exit__(self, *args):
            events.append('project closed')
    class Session:
        closed = False
        def close(self):
            self.closed = True
            events.append('session closed')
    def open_controller(cls, project, executable, game_dir, action_path, **kwargs):
        events.append((project, executable, game_dir, action_path, kwargs))
        return cls(Project(), Session(), action_path, root=kwargs['root'])
    monkeypatch.setattr(ZController, 'open', classmethod(open_controller))
    monkeypatch.setattr('sys.stdin', io.StringIO(
        '{"verb":"look"}\nnot json\n{"verb":"look","id":"second"}\n{"verb":"close"}\n'))
    assert main(arguments(actions, '--root', str(tmp_path), '--version-id', '3', '--spatial-mode', 'physical')) == 0
    captured = capsys.readouterr()
    rows = [json.loads(line) for line in captured.out.splitlines()]
    assert rows[0]['event'] == 'ready'
    assert rows[1]['result'] == {'visits': 1}
    assert not rows[2]['ok']
    assert rows[3]['id'] == 'second' and rows[3]['result'] == {'visits': 2}
    assert rows[4]['result'] == {'closed': True}
    assert captured.err.count('trusted action diagnostic') == 2
    assert events == [
        ('private.fdb', 'native-backend', 'private-game', str(actions),
         {'root': str(tmp_path), 'debugger_options': {'spatial_mode': 'physical', 'version': 3},
          'project_factory': None}),
        'session closed', 'project closed']


def test_cli_reports_launch_failure_as_one_json_error(tmp_path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        print('backend launch diagnostic')
        raise ValueError('selected backend cannot launch this target')
    monkeypatch.setattr(ZController, 'open', fail)
    assert main(arguments(tmp_path / 'actions.py')) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result['ok'] is False
    assert 'selected backend' in result['error']
    assert captured.err == 'backend launch diagnostic\n'


def test_cli_ready_timing_includes_project_and_backend_initialization(tmp_path, monkeypatch, capsys):
    clock = [100]
    events = []

    class Session:
        def close(self):
            print('backend close diagnostic')
            events.append('session closed')

    class Project:
        def __init__(self, path):
            print('project initialization diagnostic')
            events.append(('project opened', path, clock[0]))
            clock[0] = 200

        def debugger(self, executable, game_dir, **kwargs):
            print('backend initialization diagnostic')
            events.append(('backend opened', executable, game_dir, clock[0]))
            clock[0] = 400
            return Session()

        def __exit__(self, *args):
            print('project close diagnostic')
            events.append('project closed')

    monkeypatch.setattr('fdisbull.project.Project', Project)
    monkeypatch.setattr('fdisbull.z_controller.time.monotonic_ns', lambda: clock[0])
    monkeypatch.setattr('sys.stdin', io.StringIO(''))
    assert main(arguments(tmp_path / 'actions.py')) == 0
    captured = capsys.readouterr()
    rows = [json.loads(line) for line in captured.out.splitlines()]
    assert len(rows) == 1 and rows[0]['event'] == 'ready'
    assert rows[0]['controller_started_monotonic_ns'] == 100
    assert rows[0]['ready_monotonic_ns'] == 400
    assert captured.err.splitlines() == [
        'project initialization diagnostic', 'backend initialization diagnostic',
        'backend close diagnostic', 'project close diagnostic']
    assert events == [
        ('project opened', 'private.fdb', 100),
        ('backend opened', 'native-backend', 'private-game', 200),
        'session closed', 'project closed']


def test_cli_requires_explicit_trusted_action_path_before_open(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('must not launch before required argument validation')
    monkeypatch.setattr(ZController, 'open', forbidden)
    with pytest.raises(SystemExit) as error:
        main(['z-controller', 'private.fdb', '--executable', 'backend', '--game-dir', 'game'])
    assert error.value.code == 2
    assert '--actions' in capsys.readouterr().err
