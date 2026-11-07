"""DESQview profile admission, service persistence and paused helper identity.

Fixtures are authored data, not a DESQview kernel or a native boot claim.
"""
from copy import deepcopy
import hashlib
import json
import struct

import pytest

from fdisbull.cli import respond
from fdisbull.desqview import probe_bytes
from fdisbull.desqview_runtime import DesqviewSessionMixin, admit_profile, prepare_profile
from fdisbull.project import Project
from test_memory_search_runtime import CaptureSession
from test_qemm_runtime import fat_image


def test_profile_pins_members_and_rechecks_disk_without_inventing_installation(tmp_path):
    image = tmp_path / 'dos.img'
    original = fat_image().replace(b'QEMM       ', b'DV         ').replace(b'QEMM386 SYS', b'DV      EXE')
    image.write_bytes(original)
    profile = prepare_profile(image, modules=[r'\CONFIG.SYS'])
    assert profile['selection']['program'] == r'A:\DV\DV.EXE'
    assert len(profile['members']) == 2
    assert profile['desqview']['observed'] == 'unknown'
    assert profile['desqview']['installation'] == 'unverified'
    assert profile['memory_manager']['configured'] == 'not_selected'
    assert profile['machine']['cpus'] == 1 and profile['machine']['cpu'] == '486'
    assert image.read_bytes() == original
    claims = deepcopy(profile)
    claims['desqview'].update(observed='installed', kernel_version='2.80')
    assert admit_profile(claims, image)['desqview']['observed'] == 'unknown'
    claims['machine']['cpus'] = 2
    with pytest.raises(ValueError, match='input changed'):
        admit_profile(claims, image)
    image.write_bytes(original[:-1] + b'x')
    with pytest.raises(ValueError, match='changed'):
        admit_profile(profile, image)


def test_qemm_combination_uses_existing_actual_config_and_driver_admission(tmp_path):
    image = tmp_path / 'dos.img'
    image.write_bytes(fat_image())
    # The authored MZ is a profile fixture, not an authenticated vendor product.
    result = prepare_profile(image, program=r'\QEMM\QEMM386.SYS', qemm=True, startup=r'\CONFIG.SYS')
    assert result['memory_manager']['configured'] == 'qemm'
    assert result['qemm_profile']['memory_manager']['observed'] == 'unknown'
    assert result['members'][-1]['role'] == 'startup'
    assert admit_profile(result, image)['profile_sha256'] == result['profile_sha256']


@pytest.mark.parametrize('options', [
    dict(program=r'\CONFIG.SYS'), dict(program=r'\..\DV.EXE'),
    dict(program=r'C:\QEMM\QEMM386.SYS'),
    dict(program=r'\QEMM\QEMM386.SYS', modules=[r'\QEMM\QEMM386.SYS']),
    dict(program=r'\QEMM\QEMM386.SYS', modules=['missing.dvr']),
    dict(program=r'\QEMM\QEMM386.SYS', modules=['x'] * 65),
    dict(program=r'\QEMM\QEMM386.SYS', qemm='yes'),
])
def test_invalid_profile_selection_refuses(tmp_path, options):
    image = tmp_path / 'dos.img'
    image.write_bytes(fat_image())
    with pytest.raises(ValueError):
        prepare_profile(image, **options)


def test_raw_module_formats_keep_distinct_entry_contracts(tmp_path):
    from fdisbull.desqview import inspect_module
    module = tmp_path / 'fixture.dvr'
    data = bytearray(128)
    data[:8] = b'\xe9\x0d\x00\x90DVdx'
    data[16] = 0xcb
    module.write_bytes(data)
    result = inspect_module(module)
    assert result['recognized'] and result['generation'] == 'DVdx'
    assert result['entry'] == dict(offset=0, initial_jump=16)
    assert result['initialization']['context_pointer'] == 'far pointer at SS:[SP+4] on stage-one entry'
    assert not result['executed'] and not result['launchable_as_dos_program']
    data = bytearray(128)
    struct.pack_into('<H',data,0,16)
    struct.pack_into('<H',data,16,0x220)
    data[18:28] = b'DMA Memory'
    struct.pack_into('<H',data,28,96)
    data[30] = 0xcb
    module.write_bytes(data)
    assert not inspect_module(module)['recognized']
    older = inspect_module(module, expected_type='DMA Memory', expected_version=0x225)
    assert older['descriptor']['offset'] == 16 and older['entry']['offset'] == 30
    assert older['descriptor']['export_table_offset'] == 96
    assert older['descriptor']['version_compatible']
    assert inspect_module(module, expected_type='DMA Memory', expected_version=0x230)['descriptor']['version_compatible'] is False
    with pytest.raises(ValueError, match='type differs'):
        inspect_module(module, expected_type='Wrong Type')
    struct.pack_into('<H',data,28,128)
    module.write_bytes(data)
    with pytest.raises(ValueError, match='table is outside'):
        inspect_module(module, expected_type='DMA Memory')


def test_service_facts_survive_restart_and_child_versions(tmp_path):
    target = tmp_path / 'aware.com'
    target.write_bytes(bytes.fromhex('b8012bb94544ba5153cd21b80010cd15b81b10cd15b81c10cd15b8004ccd21'))
    database = tmp_path / 'aware.fdb'
    with Project.create(database, target, image='com') as project:
        project.analyze(max_instructions=64)
        rows = project.disassembly('1000:0100', lines=20)['instructions']
        services = [row['interrupt_service'] for row in rows if row.get('interrupt_service')]
        assert [service['name'] for service in services[:4]] == [
            'installation_check', 'pause', 'begin_critical', 'end_critical']
        assert all(not service['runtime_observed'] for service in services)
        child = project.patch('1000:0107', '50')['version']
        project.analyze(version=child, max_instructions=64)
        assert project.disassembly('1000:0109', lines=1, version=child)['instructions'][0]['interrupt_service']['name'] == 'set_date'
    with Project(database) as reopened:
        service = reopened.disassembly('1000:0109', lines=1, version=1)['instructions'][0]['interrupt_service']
        assert service['name'] == 'installation_check' and not service['handler_verified']
    result = respond(dict(method='dos-services', params=dict(vector=0x21, registers=dict(ax=0x2b01, cx=0x4445, dx=0x5351))))
    assert result['ok'] and result['result']['family'] == 'desqview'


class Observer(DesqviewSessionMixin, CaptureSession):
    def registers(self):
        return dict(cpu_mode=self.context['cpu_mode'], segments=dict(cs=hex(self.base >> 4)),
                    instruction_pointer=hex(self.pc))


@pytest.fixture
def observer(tmp_path):
    program, asset = probe_bytes(mode='breakpoint', yields=3, nonce='ab' * 16)
    binary = tmp_path / 'fdvapi.com'
    binary.write_bytes(program)
    with Project.create(tmp_path / 'probe.fdb', binary, image='com') as project:
        session = Observer(project)
        session.base, session.pc = 0x4000, asset['ready_com_offset']
        session.ram[session.base + 0x100:session.base + 0x100 + len(program)] = program
        address = session.base + asset['report_com_offset']
        # Explicitly authored absence report. No simulated kernel is presented
        # as proof of native DESQview execution.
        struct.pack_into('<H', session.ram, address + 10, 1)
        struct.pack_into('<H', session.ram, address + 34, 0x10)
        yield project, session, address, asset


def test_live_observer_qualifies_exact_helper_ready_stop_and_retains_report(observer):
    project, session, address, asset = observer
    result = session.desqview_observe(address, probe_base=hex(session.base), expected_nonce='ab' * 16)
    assert result['helper']['verified_at_ready_stop']
    assert result['parsed']['desqview']['present'] is False
    assert result['scheduler_qualification'] == 'not_established_by_report'
    row = project.db.execute('SELECT * FROM debug_artifacts WHERE id=?', (result['artifact'],)).fetchone()
    assert row['kind'] == 'desqview-report' and len(row['data']) == 64
    assert hashlib.sha256(row['data']).hexdigest() == result['sha256']
    assert json.loads(row['metadata'])['helper']['nonce'] == 'ab' * 16
    weak = session.desqview_observe(address)
    assert weak['freshness'] == 'not_established'
    assert not weak['helper']['verified_at_ready_stop']


@pytest.mark.parametrize('fault', ['nonce', 'pc', 'base', 'code', 'mode', 'running', 'report', 'physical'])
def test_helper_identity_failures_never_become_fresh_reports(observer, fault):
    _, session, address, asset = observer
    options = dict(probe_base=session.base, expected_nonce='ab' * 16)
    if fault == 'nonce':
        options['expected_nonce'] = 'cd' * 16
    elif fault == 'pc':
        session.pc += 1
    elif fault == 'base':
        options['probe_base'] += 16
    elif fault == 'code':
        session.ram[session.base + 0x100] ^= 1
    elif fault == 'mode':
        session.context.update(cpu_mode='protected', cr0='0x1')
    elif fault == 'running':
        session.stopped = False
    elif fault == 'report':
        address += 1
    else:
        options['space'] = 'physical'
    with pytest.raises(ValueError):
        session.desqview_observe(address, **options)
    assert not session.writes


def test_public_live_workspace_and_script_dispatch(observer):
    from fdisbull.debugger import DebugWorkspace
    from fdisbull.debug_script import validate_script
    project, session, address, _ = observer
    workspace = DebugWorkspace()
    workspace.sessions[session.run_id] = session
    reply = workspace.invoke('debug-desqview-observe', project.path, dict(run=session.run_id, address=address))
    assert reply['parsed']['status'] == 'absent'
    snapshot = workspace.invoke('debug-memory-snapshot', project.path, dict(run=session.run_id, address=address, length=64, task_id='helper'))
    assert snapshot['snapshot']['length'] == 64
    script = dict(format='fdisbull-script-1', backend='qemu-machine', steps=[
        dict(op='memory-snapshot', address='0x30000', length=64, task_id='task-lifetime'),
        dict(op='desqview-observe', address='0x30200'),
    ])
    assert len(validate_script(script)) == 2
    with pytest.raises(ValueError):
        validate_script({**script, 'backend':'scummvm-agi'})
