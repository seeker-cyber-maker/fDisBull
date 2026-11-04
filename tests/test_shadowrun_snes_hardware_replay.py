"""Private-observation validation rejects broken provenance and input order."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'hardware_replay_checker', ROOT / 'scripts/shadowrun_snes_hardware_replay.py')
CHECKER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CHECKER)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def recording(tmp_path):
    # Authored zero-table ROM makes the independent expected transform simple:
    # low=1, high=2, next=2 XOR 4=6; no original game bytes are retained here.
    rom = bytes(0x465d)
    title = bytearray(131072)
    title[0x1d04] = 5
    controller = {'samples': [
        {'kind': 'main', 'serial': 1, 'video_frame': 1000},
        {'kind': 'conversation', 'context': 'primary', 'pc': 0x80a67d,
         'serial': 1, 'video_frame': 1001},
        {'kind': 'main', 'serial': 2, 'video_frame': 1002},
    ]}
    controller_bytes = json.dumps(controller).encode()
    modal = bytes(131072)
    (tmp_path / 'modal-000002.bin').write_bytes(modal)
    data = {
        'format': CHECKER.FORMAT, 'rom_sha256': digest(rom),
        'core_sha256': 'authored-observer',
        'controller_journal_sha256': digest(controller_bytes),
        'read_order': copy.deepcopy(CHECKER.READ_ORDER),
        'dropped': 0, 'modal_dropped': 0, 'incomplete_at_end': 0,
        'samples': [{
            'ordinal': 1, 'serial': 1, 'boundary': 1, 'video_frame': 1000,
            'caller': 1, 'context': 0xffff, 'nmi_low': 1, 'nmi_high': 2,
            'beam_h': 3, 'beam_v': 4,
            'verification': {'task': 34, 'return_pc': 0xff11,
                             'parent_return': 0x9666,
                             'seed_before': 5, 'seed_after': 6,
                             'result': 0x0201, 'seen': 31, 'latch': 255},
        }],
        'modals': [{'boundary': 2, 'serial': 1, 'video_frame': 1001,
                    'kind': 4, 'pc': 0x80a67d, 'file': 'modal-000002.bin',
                    'size': len(modal), 'sha256': digest(modal)}],
    }

    def load(edit=None):
        candidate = copy.deepcopy(data)
        if edit:
            edit(candidate)
        raw = json.dumps(candidate).encode()
        (tmp_path / 'hardware_journal.json').write_bytes(raw)
        receipt = {'core_sha256': 'authored-observer',
                   'snes_hardware_journal_sha256': digest(raw)}
        return CHECKER.HardwareReplay(tmp_path, receipt, controller_bytes, rom, title)

    return SimpleNamespace(load=load, root=tmp_path, data=data)


def test_recording_validates_raw_draw_without_supplying_seed_or_result(recording):
    replay = recording.load()
    assert replay.validated == 1
    assert replay.modal_source(2) == bytes(131072)
    assert replay.summary()['consumed_draws'] == 0
    state = {}
    machine = SimpleNamespace(set_state=lambda values: state.update(values))
    setter = lambda ctx, name, index, value: 0
    native = SimpleNamespace(ctx=None, lib=SimpleNamespace(fdisbull_state_set=setter))
    assert replay.prepare(0, machine, native) == []
    records = replay.prepare(1, machine, native)
    assert len(records) == 1
    assert state['hardware_input_count'] == 1
    assert state['hardware_nmi_lows'][0] == 1
    assert state['hardware_nmi_highs'][0] == 2
    assert not any('seed' in key or 'result' in key for key in state)
    reader = SimpleNamespace(get=lambda key: {'hardware_input_index': 1,
                                             'hardware_ordinal': 1}[key],
                             byte=lambda at: 6)
    replay.complete(reader, records)
    assert replay.summary()['consumed_draws'] == 1


@pytest.mark.parametrize('field', ['dropped', 'modal_dropped', 'incomplete_at_end'])
def test_incomplete_observation_is_rejected(recording, field):
    with pytest.raises(ValueError, match='completeness'):
        recording.load(lambda data: data.__setitem__(field, 1))


@pytest.mark.parametrize('field,value', [
    ('ordinal', 2), ('serial', 2), ('boundary', 4), ('video_frame', 999),
    ('caller', True), ('nmi_low', 256), ('context', 34),
])
def test_bad_raw_input_identity_or_order_is_rejected(recording, field, value):
    with pytest.raises(ValueError):
        recording.load(lambda data: data['samples'][0].__setitem__(field, value))


@pytest.mark.parametrize('field,value', [
    ('seen', 15), ('result', 0x0200), ('seed_before', 4), ('seed_after', 7),
])
def test_result_metadata_checks_independent_transform_and_title_seed(recording, field, value):
    with pytest.raises(ValueError):
        recording.load(lambda data: data['samples'][0]['verification'].__setitem__(field, value))


def test_source_read_order_is_binding(recording):
    with pytest.raises(ValueError, match='read phase'):
        recording.load(lambda data: data['read_order'].reverse())


def test_row_cannot_be_assigned_before_a_later_controller_poll(recording):
    with pytest.raises(ValueError, match='interval'):
        recording.load(lambda data: data['samples'][0].__setitem__('video_frame', 1002))


def test_typed_caller_must_agree_with_source_return(recording):
    with pytest.raises(ValueError, match='caller'):
        recording.load(lambda data: data['samples'][0]['verification'].__setitem__('return_pc', 0xf4d2))


def test_vm_context_must_agree_with_observed_task(recording):
    def edit(data):
        row = data['samples'][0]
        row.update({'caller': 3, 'context': 36})
        row['verification']['return_pc'] = 0xf4d2
    with pytest.raises(ValueError, match='context|caller'):
        recording.load(edit)


def test_missing_modal_snapshot_is_rejected_before_replay(recording):
    with pytest.raises(ValueError, match='modal'):
        recording.load(lambda data: data['modals'].clear())


def test_modal_path_and_snapshot_bytes_are_bound(recording):
    with pytest.raises(ValueError, match='modal'):
        recording.load(lambda data: data['modals'][0].__setitem__('file', '../other.bin'))
    replay = recording.load()
    (recording.root / 'modal-000002.bin').write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        replay.modal_source(2)


def test_previously_compared_modal_snapshot_is_rechecked_at_closeout(recording):
    replay=recording.load()
    replay.modal_source(2)
    assert replay.changed_modal_files()==[]
    path=recording.root/'modal-000002.bin'
    path.write_bytes(b'changed after its comparison')
    assert replay.changed_modal_files()==[str(path)]


def test_skipping_a_public_input_boundary_is_rejected(recording):
    replay = recording.load()
    with pytest.raises(ValueError, match='consecutive'):
        replay.prepare(1, None, None)


@pytest.mark.parametrize('index,ordinal,seed', [(0, 1, 6), (1, 0, 6), (1, 1, 5)])
def test_unused_rows_wrong_ordinal_or_seed_break_comparison(recording, index, ordinal, seed):
    replay = recording.load()
    reader = SimpleNamespace(get=lambda key: {'hardware_input_index': index,
                                             'hardware_ordinal': ordinal}[key],
                             byte=lambda at: seed)
    with pytest.raises(ValueError):
        replay.complete(reader, replay.by_boundary[1])
