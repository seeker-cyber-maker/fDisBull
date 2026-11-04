"""DinoPark pixel-only scene reads retain exact predicates without PNG artifacts."""
import hashlib
import json
import os
from types import SimpleNamespace

from PIL import Image
import pytest

from fdisbull import dinopark_scenes as scenes
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.screenshot_codecs import RGBAFrame
from fdisbull.project import Project


def original_pattern(name='office'):
    return json.loads(scenes.PATTERNS.read_text())['scenes'][name]


def office_image():
    # Authored anchors only, not original screenshot bytes.
    image = Image.new('RGB', (320, 200), (1, 2, 3))
    for sample in original_pattern()['samples']:
        image.putpixel((sample['x'], sample['y']), tuple(sample['rgb']))
    return image


class PixelDebug:
    def __init__(self, image=None, encodings=('png', 'png-indexed')):
        image = office_image() if image is None else image
        pixels = image.convert('RGBA').tobytes()
        self.frame = RGBAFrame(image.width, image.height, pixels, hashlib.sha256(pixels).hexdigest(),
            {'width':image.width,'height':image.height,'frame_id':43,'mode_id':5,'captured_ticks':120,
             'format':'rgba','pixel_format':'RGBA8','transport':{'encoding':'png-indexed','sha256':'encoded-digest'}})
        self.rpc = SimpleNamespace(capabilities={'video':{'screenshot_encodings':list(encodings)}})
        self.calls = []
        self.assertions = []

    def frame_rgba(self, *, encoding):
        self.calls.append(encoding)
        return self.frame

    def scene_assert(self, scene, **options):
        self.assertions.append((scene, options))
        return {'status':'matched'}


@pytest.mark.parametrize('encodings,expected', [
    (('png','png-indexed'), 'png-indexed'), (('png',), 'png'), ((), 'png'),
])
def test_observation_uses_direct_pixels_and_keeps_identity_without_persistence(monkeypatch, encodings, expected):
    native = PixelDebug(encodings=encodings)

    def forbidden(*args, **kwargs):
        raise AssertionError('Pixel observation must not use a PNG artifact or image encoder')

    monkeypatch.setattr(scenes, 'take_frame', forbidden)
    monkeypatch.setattr(Image, 'open', forbidden)
    monkeypatch.setattr(Image.Image, 'save', forbidden)
    descriptor, image = scenes.observe_frame(object(), native, 'check-office')
    assert native.calls == [expected]
    assert image.mode == 'RGB' and image.tobytes() == office_image().tobytes()
    assert scenes.matches(image, original_pattern())
    assert descriptor['capture'] == 'direct' and descriptor['persistent'] is False
    assert 'artifact' not in descriptor and descriptor['sha256'] == native.frame.sha256
    assert descriptor['metadata']['frame_id'] == 43 and descriptor['metadata']['mode_id'] == 5
    assert descriptor['metadata']['transport']['sha256'] == 'encoded-digest'
    json.dumps(descriptor)  # No pixel bytes or live objects leak into receipts.


def test_adapter_without_direct_api_uses_explicit_read_only_legacy_capture(monkeypatch):
    calls = []
    expected = ({'artifact':'legacy'}, office_image())

    def capture(project, debug, name, *, hooks):
        calls.append((name, hooks))
        return expected

    monkeypatch.setattr(scenes, 'take_frame', capture)
    assert scenes.observe_frame(object(), object(), 'old-adapter') == expected
    assert calls == [('old-adapter', False)]


def test_direct_readback_failure_is_not_retried_through_another_capture(monkeypatch):
    native = PixelDebug()
    native.frame_rgba = lambda **kw: (_ for _ in ()).throw(DebuggerError('pixel identity unknown'))
    fallback = []
    monkeypatch.setattr(scenes, 'take_frame', lambda *a, **k:fallback.append(True))
    with pytest.raises(DebuggerError, match='identity unknown'):
        scenes.observe_frame(object(), native, 'failed-read')
    assert fallback == []


def test_other_video_dimensions_stay_unqualified():
    native = PixelDebug(Image.new('RGB', (640, 200)))
    with pytest.raises(RuntimeError, match='video dimensions'):
        scenes.observe_frame(object(), native, 'wrong-mode')


@pytest.mark.parametrize('case', ['matched', 'wrong', 'ambiguous'])
def test_real_view_check_uses_fast_pixels_without_weakening_uniqueness(monkeypatch, case):
    debug = PixelDebug()
    events = []
    text = scenes.TextScene(debug, 'office', 'bank', project=object(),
                            patterns={'office':original_pattern(),'bank':original_pattern('bank')}, event=events.append)
    money = {'cash':5000,'working_cash':5000,'loan':0}
    monkeypatch.setattr(scenes, 'balances', lambda d:money)
    monkeypatch.setattr(scenes, 'run_guest', lambda *a:pytest.fail('Zero-wait view check advanced the guest'))
    if case == 'ambiguous':
        text.patterns['copy'] = text.patterns['office']
    views = ['bank'] if case == 'wrong' else ['office','copy'] if case == 'ambiguous' else ['office']
    if case == 'matched':
        assert text.observe_one_of(views, money, 'office-check', wait_slices=0) == 'office'
    else:
        with pytest.raises(RuntimeError, match='uniquely recognized'):
            text.observe_one_of(views, money, 'office-check', wait_slices=0)
    assert debug.calls == ['png-indexed']
    assert events[-1]['frame']['persistent'] is False


def test_status_read_uses_fast_frame_but_retains_native_scene_and_state_checks(monkeypatch):
    debug = PixelDebug()
    patterns = {n:original_pattern(n) for n in ('office','quarter_popup','parking_hint')}
    events = []
    text = scenes.TextScene(debug, 'office', 'bank', project=object(), patterns=patterns, event=events.append)
    text.park_opened = True
    snapshot = {'observed':'native-state'}
    monkeypatch.setattr(scenes, 'park_snapshot', lambda d:snapshot)
    text.format_status = lambda value:'qualified status'
    assert text.observe_park_status('status') == (snapshot, 'qualified status')
    assert debug.calls == ['png-indexed']
    assert debug.assertions == [('office', {'object':'office.bank'})]
    assert events[-1]['frame']['persistent'] is False


def test_real_native_observer_equals_durable_png_and_leaves_artifacts_unchanged(tmp_path, monkeypatch):
    backend = os.environ.get('FDISBULL_DOSBOX')
    if not backend:
        pytest.skip('Set FDISBULL_DOSBOX for actual native DinoPark observer acceptance')
    target = tmp_path / 'CHECK.COM'
    # Authored mode-13 fixture with two distinct pixels; no game bytes.
    target.write_bytes(bytes.fromhex('b81300cd10b800a08ec031ffb80102fcabebfe'))
    with Project.create(tmp_path/'check.fdb', target, image='com') as project:
        with project.debugger(backend, tmp_path) as debug:
            debug.run(guest_ms=80, timeout_ms=5000, fast_forward=True)
            legacy, image = scenes.take_frame(project, debug, 'legacy-view', hooks=False)
            before = debug.registers()
            changes = project.db.total_changes
            counts = [project.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                      for table in ('debug_events','debug_artifacts')]

            def no_png_save(*args, **kwargs):
                raise AssertionError('Scene observation attempted a PNG artifact')

            with monkeypatch.context() as guard:
                guard.setattr(Image.Image, 'save', no_png_save)
                descriptor, current = scenes.observe_frame(project, debug, 'current-view')
            assert current.mode == 'RGB' and current.tobytes() == image.tobytes()
            assert descriptor['capture'] == 'direct' and not descriptor['persistent']
            assert descriptor['metadata']['transport']['encoding'] == 'png-indexed'
            assert all(descriptor['metadata'][key] == legacy['metadata'][key]
                       for key in ('frame_id','mode_id','captured_ticks'))
            assert debug.registers() == before
            assert project.db.total_changes == changes
            assert [project.db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                    for table in ('debug_events','debug_artifacts')] == counts
            with pytest.raises(KeyError, match='artifact'):
                scenes.definition(descriptor,'check',{}, {},'check',[0,0],{})
