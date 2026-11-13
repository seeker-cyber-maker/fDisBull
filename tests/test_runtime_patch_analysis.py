"""Temporal captures reach regional analysis without relabeling native evidence."""
import hashlib
import json
from types import SimpleNamespace

import pytest

pytest.importorskip('z3')
pytest.importorskip('unicorn')

from fdisbull.debug_semantics import PE_TRACE_SEMANTICS, normalize_trace
from fdisbull.project import Project
from fdisbull.runtime_code import qualify_capture
from fdisbull.wine_arch import register_names
from fixtures_formats import pe64


SITE = 0x140001010


def _store(project, identifier, kind, document, run='authored-cpu-replay'):
    raw = json.dumps(document, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
                       (identifier, run, identifier + '.json', kind, digest, raw, '{}'))
    return digest


def _capture(project, identifier, code):
    """Authored capture peer plus independent CPU states; never a Wine run."""
    import unicorn
    from unicorn import x86_const as reg
    cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    cpu.mem_map(SITE & ~4095, 4096)
    cpu.mem_write(SITE, code)
    cpu.reg_write(reg.UC_X86_REG_RAX, 0xfedcba9876543210)
    cpu.reg_write(reg.UC_X86_REG_EFLAGS, 0x202)
    events = []

    def before(guest, address, size, _):
        events.append({'address': hex(address), 'project_address': hex(address),
                       'bytes': bytes(guest.mem_read(address, size)).hex(),
                       'registers': {'rip': hex(address), 'rflags': hex(guest.reg_read(reg.UC_X86_REG_EFLAGS)),
                                     'general': {name: hex(guest.reg_read(getattr(reg, 'UC_X86_REG_' + name.upper())))
                                                 for name in register_names(64) - {'rip', 'rflags'}},
                                     'thread': 17, 'cpu_mode': 'long64'}})

    cpu.hook_add(unicorn.UC_HOOK_CODE, before)
    cpu.emu_start(SITE, SITE + len(code), count=8)
    normalize_trace('wine-qemu', events, version=1)
    trace = {'mapping': {'backend': 'wine-qemu', 'bits': 64,
                         'source_sha256': project.meta['source_sha256'],
                         'version_sha256': project.version(1)['sha256'],
                         'capture_provider': 'authored-unicorn-replay'},
             'version': 1, 'semantics': PE_TRACE_SEMANTICS, 'complete': True,
             'observation_contract': {'provider': 'authored-unicorn-replay'}, 'events': events}
    session = SimpleNamespace(project=project, version=project.version(1), run_id='authored-cpu-replay',
                              static_base=0x140000000, runtime_base=0x140000000, delta=0,
                              metadata={'backend': 'wine-qemu'}, registers=lambda: events[0]['registers'])
    observation = qualify_capture(session, {'project_address': hex(SITE), 'runtime_address': hex(SITE),
        'hex': code.hex(), 'sha256': hashlib.sha256(code).hexdigest(), 'view': 'ram',
        'active_layers': [], 'generation': 0})
    _store(project, identifier + '-capture', 'code-snapshot', observation)
    _store(project, identifier + '-trace', 'trace', trace)
    project.db.commit()
    child = project.debug_promote_code(identifier + '-capture', max_instructions=8)
    return child['version'], identifier + '-trace'


@pytest.fixture
def pair(tmp_path):
    source = tmp_path / 'authored.exe'
    source.write_bytes(pe64())
    with Project.create(tmp_path / 'analysis.fdb', source) as project:
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            ('authored-cpu-replay', 1, 'authored', 'authored', 'closed', '{}'))
        project.db.commit()
        a, at = _capture(project, 'one', bytes.fromhex('b80100000090'))
        b, bt = _capture(project, 'two', bytes.fromhex('b80200000090'))
        yield project, a, b, at, bt


def test_changed_runtime_versions_recover_difference_and_preserve_evidence(pair):
    project, a, b, at, bt = pair
    before = [tuple(r) for r in project.db.execute('SELECT id,sha256,data FROM debug_artifacts ORDER BY id')]
    result = project.debug_compare_runtime_code(a, b, at, bt, contract={})
    assert result['regional']['status'] == 'different'
    assert result['baseline']['version'] == a and result['layer']['version'] == b
    assert result['baseline']['source_version'] == result['layer']['source_version'] == 1
    assert result['baseline']['execution_proven'] is False
    assert result['semantic_equivalence'] is None
    assert [tuple(r) for r in project.db.execute('SELECT id,sha256,data FROM debug_artifacts ORDER BY id')] == before
    assert project.debug_compare_runtime_code(a, a, at, at, contract={})['regional']['status'] == 'equivalent_under_contract'


def test_byte_view_mismatch_is_not_a_behavior_proof(pair):
    project, a, b, at, bt = pair
    with pytest.raises(ValueError, match='match.*observed capture'):
        project.debug_compare_runtime_code(a, b, bt, at, contract={})


def test_inherited_exit_bytes_are_not_observed_region_evidence(pair):
    project, a, b, at, bt = pair
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', ('one-capture',)).fetchone()
    document = json.loads(bytes(row[0]))
    document['hex'] = document['hex'][:-2]
    document['sha256'] = hashlib.sha256(bytes.fromhex(document['hex'])).hexdigest()
    _store(project, 'short-capture', 'code-snapshot', document)
    project.db.commit()
    short = project.debug_promote_code('short-capture', max_instructions=8)['version']
    with pytest.raises(ValueError, match='fully observed'):
        project.debug_compare_runtime_code(short, b, at, bt, contract={})


def test_corrupt_capture_or_trace_does_not_reach_solver(pair):
    project, a, b, at, bt = pair
    project.db.execute('UPDATE debug_artifacts SET sha256=? WHERE id=?', ('0' * 64, at))
    project.db.commit()
    with pytest.raises(ValueError, match='trace hash mismatch'):
        project.debug_compare_runtime_code(a, b, at, bt, contract={})


def test_authored_edit_is_not_fully_observed_runtime_capture(pair):
    project, a, b, at, bt = pair
    edited = project.patch(SITE, 'b803000000', version=a)['version']
    with pytest.raises(ValueError, match='unmodified runtime capture'):
        project.debug_compare_runtime_code(edited, b, at, bt, contract={})


def test_runtime_site_must_use_the_capture_mapping(pair):
    project, a, b, at, bt = pair
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (at,)).fetchone()
    shifted = json.loads(bytes(row[0]))
    for event in shifted['events']:
        address = hex(int(event['address'], 16) + 0x100000)
        event['address'] = event['identity']['runtime_address'] = event['registers']['rip'] = address
    _store(project, 'different-loaded-site', 'trace', shifted)
    project.db.commit()
    with pytest.raises(ValueError, match='capture mapping'):
        project.debug_compare_runtime_code(a, a, 'different-loaded-site', at, contract={})


def test_public_offline_json_api_reopens_and_compares(pair):
    from fdisbull.cli import invoke
    project, a, b, at, bt = pair
    result = invoke('debug-compare-runtime-code', {'project': str(project.path),
        'baseline_version': a, 'layer_version': b, 'baseline_trace': at, 'layer_trace': bt,
        'contract': {}})
    assert result['regional']['status'] == 'different'


def test_trace_content_cannot_claim_another_run(pair):
    project, a, b, at, bt = pair
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (at,)).fetchone()
    wrong = json.loads(bytes(row[0]))
    wrong['run'] = 'some-other-run'
    _store(project, 'wrong-run-content', 'trace', wrong)
    project.db.commit()
    with pytest.raises(ValueError, match='owning source and run'):
        project.debug_compare_runtime_code(a, b, 'wrong-run-content', bt, contract={})
