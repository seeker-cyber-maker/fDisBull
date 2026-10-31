"""ARM64 Mach-O backings bind native instructions to retained file versions."""
from copy import deepcopy
from hashlib import sha256

import pytest

from fdisbull.code_backings import digest, materialize_code_backing, validate_source
from fdisbull.project import Project
from fixtures_formats import macho_arm64
from test_macho_slices import _fat, _x86_64


ENTRY = 0x100000100
CONDITIONAL = bytes.fromhex('40000054c0035fd6c0035fd6')  # b.eq +8; ret; ret


def _thin(code=CONDITIONAL):
    data = bytearray(macho_arm64())
    data[0x100:0x100 + len(code)] = code
    return bytes(data)


def _create(tmp_path, source_bytes, *, fat=False):
    source = tmp_path / 'source.macho'
    source.write_bytes(source_bytes)
    project = Project.create(tmp_path / 'capture.fdb', source,
                             **({'slice_arch': 'arm64'} if fat else {}))
    project.analyze()
    return project, source


@pytest.mark.parametrize('fat,offset', [(False, 0), (True, 8192)])
def test_arm64_capture_has_exact_four_byte_spans_and_original_container_offsets(tmp_path, fat, offset):
    source_bytes = _fat([(0x01000007, 3, _x86_64()),
                         (0x0100000C, 0, _thin())]) if fat else _thin()
    project, _ = _create(tmp_path, source_bytes, fat=fat)
    with project:
        before = project.db.total_changes
        captured = project.code_backings([ENTRY])
        assert project.db.total_changes == before
        assert captured['complete'] and not captured['unresolved']
        assert captured['source']['file_sha256'] == sha256(source_bytes).hexdigest()
        assert captured['source']['slice'] == dict(index=1 if fat else 0, offset=offset,
                                                  size=4096, selector='arm64',
                                                  sha256=sha256(_thin()).hexdigest())
        assert captured['coverage']['physical_bytes'] == 12
        assert captured['coverage']['encoding_bytes'] == 12
        assert [block['bytes'] for block in captured['blocks']] == [
            '40000054', 'c0035fd6', 'c0035fd6']
        assert [block['provenance']['file_offset'] for block in captured['blocks']] == [
            offset + 0x100, offset + 0x104, offset + 0x108]
        assert [block['provenance']['slice_relative_offset'] for block in captured['blocks']] == [
            0x100, 0x104, 0x108]
        assert all(block['provenance']['byte_roles'] == ['instruction_encoding'] * 4
                   and materialize_code_backing(block) == source_bytes[block['provenance']['file_offset']:
                                                                     block['provenance']['file_offset'] + 4]
                   for block in captured['blocks'])
        assert sorted((edge['kind'], edge['target']) for edge in captured['blocks'][0]['exits']) == [
            ('branch', 'arm64:64:little@0x100000108'),
            ('fallthrough', 'arm64:64:little@0x100000104')]
        assert validate_source(project, captured)['status'] == 'source_valid'


def test_arm64_old_capsule_survives_restart_but_patch_creates_new_backing(tmp_path):
    source_bytes = _fat([(0x01000007, 3, _x86_64()),
                         (0x0100000C, 0, _thin())])
    project, source = _create(tmp_path, source_bytes, fat=True)
    with project:
        original = project.code_backings([ENTRY])
        child = project.patch(ENTRY + 4, '1f2003d5')['version']  # RET -> NOP
        project.analyze()
        changed = project.code_backings([ENTRY])
        assert changed['source']['version'] == child
        assert changed['blocks'][1]['bytes'] == '1f2003d5'
        assert changed['blocks'][1]['backing_revision'] != original['blocks'][1]['backing_revision']
        assert changed['source']['slice']['sha256'] != original['source']['slice']['sha256']
        assert changed['source']['file_sha256'] != original['source']['file_sha256']
        assert changed['blocks'][1]['provenance']['file_offset'] == 8192 + 0x104
        with pytest.raises(ValueError, match='stale'):
            validate_source(project, original)
        assert validate_source(project, original, version=1)['status'] == 'source_valid'
        assert validate_source(project, changed)['status'] == 'source_valid'
    source.unlink()
    with Project(tmp_path / 'capture.fdb') as reopened:
        assert reopened.code_backings([ENTRY], version=1) == original
        assert reopened.code_backings([ENTRY]) == changed
        assert validate_source(reopened, original, version=1)['status'] == 'source_valid'
        assert validate_source(reopened, changed)['status'] == 'source_valid'


def test_arm64_source_rejects_relabelled_file_offset(tmp_path):
    project, _ = _create(tmp_path, _thin())
    with project:
        captured = project.code_backings([ENTRY])
        forged = deepcopy(captured)
        forged['blocks'][0]['provenance']['file_offset'] += 4
        block = forged['blocks'][0]
        block['backing_revision'] = digest({key: value for key, value in block.items()
                                            if key != 'backing_revision'})
        forged['sha256'] = digest({key: value for key, value in forged.items()
                                   if key != 'sha256'})
        with pytest.raises(ValueError, match='file offset'):
            validate_source(project, forged)


@pytest.mark.parametrize('encoding,flow,problem', [
    ('00001fd6', 'indirect_jump', 'unresolved'),  # BR X0
    ('01081fd7', 'indirect_jump', 'unresolved'),  # BRAA X0, X1
    ('43083fd7', 'indirect_call', 'calls'),       # BLRAA X2, X3
])
def test_arm64_indirect_and_authenticated_transfers_remain_unknown(tmp_path, encoding, flow, problem):
    project_bytes = _thin(bytes.fromhex(encoding + 'c0035fd6'))
    indirect_project, _ = _create(tmp_path, project_bytes)
    with indirect_project:
        captured = indirect_project.code_backings([ENTRY])
        assert not captured['complete'] and captured['unresolved']
        assert captured['blocks'][0]['flow'] == flow
        if flow == 'indirect_jump':
            assert captured['blocks'][0]['exits'] == []
        else:
            assert [edge['kind'] for edge in captured['blocks'][0]['exits']] == ['fallthrough']
        assert any(item['kind'] == problem for item in captured['unresolved'])
        assert validate_source(indirect_project, captured)['graph_complete'] is False
