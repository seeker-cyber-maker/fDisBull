"""Stopped LE capture and offline replay use real binding receipts."""
from copy import deepcopy
import hashlib
import json

import pytest

from test_qemu_dos_le_checkpoint import source
from test_qemu_dos_source_admission import owned
from fdisbull.qemu_runtime_capture import _le_extent, qualify_qemu_le_capture, validate_qemu_le_capture


def test_le_capture_replays_binding_and_rejects_changed_gdt(source):
    s = source.session
    s.metadata['runtime_inputs'] = {'qemu_image': {'sha256': 'a' * 64}}
    recipe = s._le_source['recipe']
    placement = next(p for p in recipe['placements'] if p['object_index'] ==
                     recipe['initial_admission']['observation']['identity_evidence']['code_object'])
    address = placement['runtime_base']
    raw = next(data[:8] for start, data in source.peer.memory_regions if start == address)
    observed = dict(space='linear', view='ram', active_layers=[], runtime_address=hex(address),
                    length=len(raw), hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest(),
                    backing=[dict(physical_address=hex(address), length=len(raw))], generation=0)
    capture = qualify_qemu_le_capture(s, observed)
    assert capture is not None
    assert capture['project_address'] is None
    result = validate_qemu_le_capture(source.project, capture, s.metadata, run=s.run_id, version=s.version['id'])
    assert result['raw'] == raw and result['source_location']['object_offset'] == 0
    assert result['selector_offset'] == address - result['cpu']['cs_base']
    with source.project.transaction(True):
        source.project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?', (json.dumps(s.metadata), s.run_id))
        artifact = s._artifact('le-code.json', 'qemu-code-snapshot', json.dumps(capture).encode(), {})
    analysis = source.project.debug_analyze_le_code(artifact['artifact'])
    assert analysis['source_location']['object_offset'] == 0
    assert analysis['runtime_bytes'] == raw[:analysis['size']].hex()
    forged = deepcopy(capture)
    forged['le_capture']['selector_offset'] += 1
    with source.project.transaction(True):
        forged_artifact = s._artifact('forged.json', 'qemu-code-snapshot', json.dumps(forged).encode(), {})
    with pytest.raises(ValueError, match='source extent'):
        source.project.debug_analyze_le_code(forged_artifact['artifact'])
    with pytest.raises(ValueError, match='debug-analyze-le-code'):
        source.project.debug_promote_code(artifact['artifact'])
    wrong_producer = deepcopy(capture)
    wrong_producer['le_capture']['producer']['le.py'] = '0' * 64
    with pytest.raises(ValueError, match='producer identity differs'):
        validate_qemu_le_capture(source.project, wrong_producer, s.metadata, run=s.run_id, version=s.version['id'])
    damaged = deepcopy(capture)
    damaged['le_capture']['gdt_hex'] = '00' * (len(damaged['le_capture']['gdt_hex']) // 2)
    with pytest.raises(ValueError):
        validate_qemu_le_capture(source.project, damaged, s.metadata, run=s.run_id, version=s.version['id'])
    damaged = deepcopy(capture)
    damaged['project_address'] = hex(result['source_location']['preferred_address'])
    with pytest.raises(ValueError, match='source extent'):
        validate_qemu_le_capture(source.project, damaged, s.metadata, run=s.run_id, version=s.version['id'])


def test_extent_requires_current_selector_and_admitted_object(source):
    s = source.session
    recipe = s._le_source['recipe']; image = s._le_source['image']
    cpu = deepcopy(recipe['initial_admission']['observed_cpu'])
    start = next(p['runtime_base'] for p in recipe['placements'] if p['object_index'] ==
                 recipe['initial_admission']['observation']['identity_evidence']['code_object'])
    backing = [dict(physical_address=hex(start), length=8)]
    cpu['cs_limit'] = start - cpu['cs_base'] + 6
    with pytest.raises(ValueError, match='selector'):
        _le_extent(image, recipe, cpu, start, 8, backing)
    cpu['cs_limit'] += 1
    location, offset = _le_extent(image, recipe, cpu, start, 8, backing)
    assert location['object_offset'] == 0 and offset == start - cpu['cs_base']


def test_nonzero_cs_base_capture_replays(owned):
    from test_qemu_dos_le_match import descriptor
    s = owned.session; peer = owned.peer
    peer.cpu.update(cs_base=0x50000, ip=0x40, cs_limit=0xbf, cs_attributes=0x409a00)
    peer.table = bytes(8) + descriptor(0x50000, 0xbf, 32, 0x9a) + bytes(8)
    s.metadata['runtime_inputs'] = {'qemu_image': {'sha256': 'a' * 64}}
    s.dos_source_bind()
    start, content = peer.memory_regions[0]
    raw = content[:8]
    observed = dict(space='linear', view='ram', active_layers=[], runtime_address=hex(start),
                    length=len(raw), hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest(),
                    backing=[dict(physical_address=hex(start), length=len(raw))], generation=0)
    capture = qualify_qemu_le_capture(s, observed)
    assert capture is not None
    proof = validate_qemu_le_capture(owned.project, capture, s.metadata, run=s.run_id, version=s.version['id'])
    assert proof['cpu']['cs_base'] == 0x50000 and proof['selector_offset'] == 0
    outside = dict(observed, runtime_address=hex(start + 0xbe), length=4,
                   hex=content[0xbe:0xc2].hex(), sha256=hashlib.sha256(content[0xbe:0xc2]).hexdigest(),
                   backing=[dict(physical_address=hex(start + 0xbe), length=4)])
    assert qualify_qemu_le_capture(s, outside) is None
    forged = deepcopy(capture)
    forged.update(outside)
    forged['le_capture']['selector_offset'] = 0xbe
    with pytest.raises(ValueError, match='selector'):
        validate_qemu_le_capture(owned.project, forged, s.metadata, run=s.run_id, version=s.version['id'])


def test_le_capture_allows_modified_target_outside_anchor(source):
    s = source.session
    s.metadata['runtime_inputs'] = {'qemu_image': {'sha256': 'a' * 64}}
    start, original = source.peer.memory_regions[0]
    changed = bytearray(original)
    changed[180] ^= 1
    source.peer.memory_regions[0] = (start, bytes(changed))
    raw = bytes(changed[180:182]); address = start + 180
    observed = dict(space='linear', view='ram', active_layers=[], runtime_address=hex(address),
                    length=len(raw), hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest(),
                    backing=[dict(physical_address=hex(address), length=len(raw))], generation=0)
    capture = qualify_qemu_le_capture(s, observed)
    assert capture is not None
    result = validate_qemu_le_capture(source.project, capture, s.metadata, run=s.run_id, version=s.version['id'])
    assert result['raw'] == raw and result['source_location']['object_offset'] == 180
