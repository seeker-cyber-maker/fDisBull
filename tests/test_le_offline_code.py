"""Offline LE decoding uses proved placements but never rewrites the carrier."""
import hashlib
import json

import pytest

from fdisbull.project import Project
from test_qemu_dos_le_identity import setup


def test_offline_le_normalizes_only_verified_complete_fixups(tmp_path, monkeypatch):
    image, cpu, _, _, _, _, recipe = setup()
    source = tmp_path / 'carrier.exe'
    source.write_bytes(image.source_bytes)
    with Project.create(tmp_path / 'carrier.fdb', source) as project:
        location = dict(source_view='embedded-le', application_source_sha256=recipe['application_source_sha256'],
                        object_id='le:1', object_index=1, object_offset=0, preferred_address=0x10000)
        proof = dict(image=image, recipe=recipe, source_location=location,
                     raw=bytes.fromhex('b800000700'), cpu=cpu, selector_offset=0x50000, source_receipt_sequence=1)
        monkeypatch.setattr('fdisbull.qemu_runtime_capture.validate_qemu_le_capture', lambda *a, **k: proof)
        monkeypatch.setattr('fdisbull.event_search._capture_sequence', lambda *a: 2)
        data = json.dumps(dict(runtime_address='0x50000')).encode()
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)', ('run', 1, 'now', None, 'closed', '{}'))
            project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
                               ('capture', 'run', 'capture', 'qemu-code-snapshot', hashlib.sha256(data).hexdigest(), data, '{}'))
        before = project.version(1)['sha256']
        result = project.debug_analyze_le_code('capture')
        assert result['runtime_bytes'] == 'b800000700'
        assert result['canonical_bytes'] == 'b800000200'
        assert result['fixups'][0]['target_object'] == 2
        assert result['fixups'][0]['record_file_offset'] == image.metadata['le']['fixups'][0]['record_file_offset']
        assert not result['execution_proven'] and len(project.versions()) == 1
        assert project.version(1)['sha256'] == before
        proof['source_receipt_sequence'] = 2
        with pytest.raises(ValueError, match='predates'):
            project.debug_analyze_le_code('capture')
        proof['source_receipt_sequence'] = 1
        proof['raw'] = bytes.fromhex('b801000700')
        with pytest.raises(ValueError, match='Modified LE runtime fixup'):
            project.debug_analyze_le_code('capture')
        proof['raw'] = bytes.fromhex('b80000')
        with pytest.raises(ValueError, match='complete decodable instruction'):
            project.debug_analyze_le_code('capture')
        proof['raw'] = bytes.fromhex('b000')
        with pytest.raises(ValueError, match='cuts through'):
            project.debug_analyze_le_code('capture')
        location.update(object_offset=64, preferred_address=0x10040)
        proof.update(raw=bytes.fromhex('eb00'), selector_offset=0x10040,
                     cpu=dict(cpu, cs_base=0x40000, ip=0x10080))
        result = project.debug_analyze_le_code('capture')
        assert result['instruction_selector_offset'] == '0x10040'
        assert result['stopped_pc']['linear'] == '0x50080'
        assert '10042' in result['runtime_instruction']
