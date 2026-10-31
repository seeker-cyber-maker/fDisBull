"""Integration uses the owner's original resource only when explicitly present."""
from copy import deepcopy
import json
import hashlib
import os
from types import SimpleNamespace
from pathlib import Path
import sys

import pytest
from examples.agi.build_z_scene import build
from fdisbull.agi import load_logic
from fdisbull.il_scenes import ILSceneBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import Player

SOURCE = Path(os.environ.get('FDISBULL_KQ1_SOURCE', '/nonexistent'))
RECEIPT = Path(__file__).resolve().parents[1] / 'docs/evidence/agi-host-2026-10-31/receipt.json'

@pytest.fixture
def inputs():
    if not (SOURCE / 'LOGDIR').exists():
        pytest.skip('owner-supplied KQ1 resource unavailable')
    trial = Path(os.environ.get('FDISBULL_AGI_ERASE_TRIAL', '/nonexistent'))
    if not trial.is_file():
        pytest.skip('owner-supplied native erase trial unavailable')
    return load_logic(SOURCE / 'LOGDIR', SOURCE, 103, profile='2.917'), json.loads(RECEIPT.read_text()), trial.read_bytes()


def test_player_observes_independent_source_backed_probes(inputs):
    scene, evidence = build(*inputs)
    backend = ILSceneBackend(scene)
    player = Player(backend)
    assert 'diagnostic probes' in player.execute('look')
    assert 'goat' in player.execute('use water').lower()
    departure = player.execute('use departure')
    assert 'goat' in departure.lower() and 'object 13 was erased' in departure
    assert backend.observe()['coverage']['partial'] is True
    assert evidence['binding']['departure']['source_offsets'] == [413, 427]
    assert backend.state == {'$object13_drawn': False}
    assert player.execute('use departure') == 'Rejected: Action refused.'
    assert backend.save('after')['status'] == 'saved'
    assert backend.load('after')['status'] == 'restored'
    assert player.execute('use departure') == 'Rejected: Action refused.'


def test_unqualified_or_mismatched_receipt_is_rejected(inputs):
    resource, original, trial = inputs
    with pytest.raises(ValueError, match='trial hash mismatch'):
        build(resource, original, trial + b' ')
    for change in ('source', 'incomplete', 'difference', 'missing_op'):
        receipt = deepcopy(original)
        case = next(c for c in receipt['cases'] if c['case'] == 'erase')
        if change == 'source': receipt['source_logic_sha256'] = '0' * 64
        if change == 'incomplete': case['complete'] = False
        if change == 'difference': case['differences'] = ['difference']
        if change == 'missing_op': case['host_operations'] = []
        with pytest.raises(ValueError): build(resource, receipt, trial)


def test_portable_authored_scene_contract(monkeypatch):
    # Synthetic source is a test fixture, not a source or native qualification.
    import examples.agi.build_z_scene as module
    code = bytearray(452)
    code[413:415] = bytes([101, 2]); code[427:429] = bytes([36, 13]); code[450:452] = bytes([101, 1])
    resource = SimpleNamespace(logic=103, profile='2.917', resource_sha256=module.SOURCE,
                               code=bytes(code), provenance=lambda: {'resource_sha256': module.SOURCE})
    monkeypatch.setattr(module, 'logic_messages', lambda _: {module.SOURCE: {'1': 'water text', '2': 'departure text'}})
    receipt = json.loads(RECEIPT.read_text())
    before = bytearray(43); before[0x25] = 1
    after = bytearray(before); after[0x25] = 0
    trial = json.dumps({'status': 'verified', 'complete': True, 'native_execution': True,
                        'differences': [], 'identity': {'resource_sha256': module.SOURCE},
                        'attempts': [{'offset': 427, 'status': 'completed',
                                      'raw_before': {'object_13_hex': before.hex()},
                                      'raw_after': {'object_13_hex': after.hex()}}]}).encode()
    next(c for c in receipt['cases'] if c['case'] == 'erase')['private_trial_sha256'] = hashlib.sha256(trial).hexdigest()
    scene, _ = build(resource, receipt, trial)
    invalid = json.loads(trial); invalid['attempts'][0]['raw_after']['object_13_hex'] = before.hex()
    invalid_trial = json.dumps(invalid).encode()
    bad_receipt = deepcopy(receipt)
    next(c for c in bad_receipt['cases'] if c['case'] == 'erase')['private_trial_sha256'] = hashlib.sha256(invalid_trial).hexdigest()
    with pytest.raises(ValueError, match='drawn flag transition'):
        build(resource, bad_receipt, invalid_trial)
    player = Player(ILSceneBackend(scene))
    assert 'water text' in player.execute('use water')
    assert 'departure text' in player.execute('use departure')
    damaged = bytearray(code); damaged[427] = 0
    resource.code = bytes(damaged)
    with pytest.raises(ValueError, match='instruction mismatch'):
        build(resource, receipt, trial)
