import json
import subprocess
import sys
from pathlib import Path
import pytest
from fdisbull.zork import NamedZorkHarness, ZorkError, ZorkSession

def valid_story():
    data = bytearray(1024); data[0] = 3
    def word(at, value): data[at:at+2] = value.to_bytes(2, 'big')
    for at, value in ((4, 900), (6, 900), (8, 810), (10, 544), (12, 64), (14, 800), (24, 606), (26, 512)):
        word(at, value)
    data[810:814] = bytes([0, 4, 0, 0])
    word(28, sum(data[64:]) & 65535)
    return bytes(data)

@pytest.fixture
def session(tmp_path, monkeypatch):
    story = tmp_path / 'story.dat'; story.write_bytes(valid_story())
    original = subprocess.Popen
    def launch(args, **kwargs):
        args[2] = str(Path(__file__).with_name('zork_worker_fixture.py'))
        return original(args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', launch)
    with ZorkSession(story, python=sys.executable, timeout_ms=500) as s:
        yield s

def test_passive_observe_and_checkpoint(session, tmp_path):
    assert session.observe()['observation'] == 'initial'
    assert session.command('look')['observation'] == 'look'
    path = tmp_path / 'checkpoint'; session.save_checkpoint(path)
    session.command('north'); session.restore_checkpoint(path)
    assert session.observe()['observation'] == 'look'
    wrapper = json.loads(path.read_text()); wrapper['payload']['observation'] = 'tampered'; path.write_text(json.dumps(wrapper))
    with pytest.raises(ZorkError): session.restore_checkpoint(path)
    assert session.observe()['observation'] == 'look'

def test_timeout_poison_reset(session):
    with pytest.raises(ZorkError, match='deadline'): session.command('hang')
    with pytest.raises(ZorkError, match='reset'): session.command('look')
    session.reset()
    assert session.command('look')['observation'] == 'look'

def test_story_drift_fails_closed(session):
    Path(session.story).write_bytes(b'changed')
    with pytest.raises(ZorkError, match='changed'): session.command('look')
    with pytest.raises(ZorkError, match='reset'): session.command('look')

def test_finite_actions_and_fresh_scene_token(session):
    harness = NamedZorkHarness(session, {'a': {'match': 'initial', 'actions': {'inspect': {'command': 'look', 'expect': 'look'}}}, 'b': {'match': 'initial', 'actions': {'go': {'command': 'north', 'expect': 'north'}}}})
    token = harness.observe('a')['token']
    with pytest.raises(ZorkError): harness.act('b', 'go', token)
    assert harness.act('a', 'inspect', token)['response']['observation'] == 'look'
    with pytest.raises(ZorkError): harness.act('a', 'inspect', token)

def _rehash(path, modify):
    import hashlib
    wrapper = json.loads(path.read_text())
    modify(wrapper['payload'])
    raw = json.dumps(wrapper['payload'], sort_keys=True, separators=(',', ':')).encode()
    wrapper['sha256'] = hashlib.sha256(raw).hexdigest()
    path.write_text(json.dumps(wrapper))

@pytest.mark.parametrize('change', [
    lambda p: p['identity'].__setitem__('native_sha256', 'e' * 64),
    lambda p: p['state'].__setitem__(2, 999999),
    lambda p: p['state'].__setitem__(3, 999999),
    lambda p: p['transcript'][0].__setitem__('seq', 5),
    lambda p: p.__setitem__('observation', 'different'),
    lambda p: p.__setitem__('extra', True),
])
def test_invalid_checkpoint_refused_before_mutation(session, tmp_path, change):
    path = tmp_path / 'state'; session.save_checkpoint(path)
    _rehash(path, change)
    with pytest.raises(ZorkError, match='invalid checkpoint'): session.restore_checkpoint(path)
    assert session.command('look')['observation'] == 'look'

@pytest.mark.parametrize('command', ['malformed', 'oversize', 'bad'])
def test_bad_reply_poisons_observation(session, command):
    with pytest.raises(ZorkError): session.command(command)
    with pytest.raises(ZorkError): session.observe()
    session.reset()
    assert session.observe()['observation'] == 'initial'

def test_observation_and_identity_are_copies(session):
    view = session.observe(); view['identity']['story_sha256'] = 'changed'; view['transcript'][0]['text'] = 'changed'
    session.identity['story_sha256'] = 'changed'
    assert session.observe()['observation'] == 'initial'
    assert session.observe()['transcript'][0]['text'] == 'initial'
    assert session.command('look')['observation'] == 'look'
    session.close()
    with pytest.raises(ZorkError): session.observe()

def test_scene_qualification_and_latch(session):
    harness = NamedZorkHarness(session, {'opening': {'match': 'initial', 'actions': {'inspect': {'command': 'look', 'expect': 'not in response'}}}, 'next': {'match': 'look', 'actions': {'north': {'command': 'north', 'expect': 'north'}}}})
    with pytest.raises(ZorkError, match='does not match'): harness.observe('next')
    token = harness.observe('opening')['token']
    result = harness.act('opening', 'inspect', token)
    assert result['outcome'] == 'unexpected' and result['raw_command'] == 'look'
    with pytest.raises(ZorkError, match='reacquire'): harness.observe('next')
    assert harness.reacquire('next')['scene'] == 'next'

def test_invalid_numbers(tmp_path):
    story = tmp_path / 'story'; story.write_bytes(valid_story())
    for kwargs in ({'seed': 0}, {'seed': True}, {'timeout_ms': True}):
        with pytest.raises(ValueError): ZorkSession(story, python=sys.executable, **kwargs)

@pytest.mark.parametrize('text', ['a\x00b', 'café', 'a\tb', 'a\nb'])
def test_qualified_commands_require_printable_ascii(session, text):
    with pytest.raises(ValueError, match='ASCII'): session.command(text)
    assert session.observe()['observation'] == 'initial'


def test_checkpoint_protects_story_python_worker_and_hardlinks(session, tmp_path):
    import os
    link = tmp_path / 'story-hardlink'; os.link(session.story, link)
    for path in (session.story, session.python, Path(__file__).with_name('zork_worker_fixture.py'), link):
        with pytest.raises(ZorkError, match='protected'): session.save_checkpoint(path)
    assert session.command('look')['observation'] == 'look'


def test_reset_never_launches_changed_story(session, monkeypatch):
    Path(session.story).write_bytes(valid_story() + b'trailing')
    def forbidden(*args, **kwargs): raise AssertionError('worker launched for changed story')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    with pytest.raises(ZorkError, match='changed'): session.reset()
    with pytest.raises(ZorkError): session.observe()


def test_worker_directory_isolated_and_removed_on_close(session):
    directory = Path(session._worker_dir.name)
    story_before = Path(session.story).read_bytes()
    assert Path(session.command('cwd')['observation']).resolve() == directory.resolve()
    assert (directory / 'relative-save').read_text() == 'fixture'
    with pytest.raises(ZorkError, match='protected'):
        session.save_checkpoint(directory / 'checkpoint')
    session.close()
    assert not directory.exists()
    assert Path(session.story).read_bytes() == story_before


def test_worker_directory_removed_on_timeout(session):
    directory = Path(session._worker_dir.name)
    with pytest.raises(ZorkError, match='deadline'): session.command('hang')
    assert not directory.exists()


def test_worker_directory_removed_on_launch_failure(tmp_path, monkeypatch):
    import tempfile
    story = tmp_path / 'story'; story.write_bytes(valid_story())
    created = []
    original = tempfile.TemporaryDirectory
    def capture(*args, **kwargs):
        instance = original(*args, **kwargs); created.append(Path(instance.name)); return instance
    monkeypatch.setattr(tempfile, 'TemporaryDirectory', capture)
    def fail(*args, **kwargs): raise OSError('cannot launch')
    monkeypatch.setattr(subprocess, 'Popen', fail)
    with pytest.raises(OSError, match='cannot launch'): ZorkSession(story, python=sys.executable)
    assert len(created) == 1 and not created[0].exists()
