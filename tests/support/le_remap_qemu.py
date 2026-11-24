"""Collect and reopen a QEMU LE tracking trace across a guest-controlled remap."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys

from fdisbull.cli import public_addresses
from fdisbull.project import Project
from support.le_translation_native import integer, register


def summarize(event):
    regs = event['registers']
    cpu_cs = integer(regs['registers']['cs'])
    q = event['qualification']
    mapping = event['mapping_identity']
    pc = integer(regs['linear_pc'])
    result = dict(
        cs=cpu_cs,
        ip=integer(regs['instruction_pointer']),
        pc=pc,
        esi=register(regs, 'si'),
        qualified=q['qualified'],
    )
    if not q['qualified']:
        assert q['source_location'] is None and mapping is None
        return result
    descriptor = mapping['descriptor']
    assert cpu_cs == mapping['selector'] == descriptor['selector']
    assert descriptor['descriptor']['base'] + result['ip'] == pc == mapping['linear_address']
    data = bytes.fromhex(q['execution_bytes'])
    backing = [w['physical'] + i for w in mapping['instruction_backing'] for i in range(w['length'])]
    assert len(data) == len(backing) == q['instruction_size']
    extended = {}
    if mapping['instruction_backing'] and 'page_size' in mapping['instruction_backing'][0]:
        row = mapping['instruction_backing'][0]
        extended = {key: row[key] for key in ('page_size', 'paging_mode', 'entries', 'page_attributes')}
    return dict(
        **result, **extended,
        hex=data.hex(),
        backing=backing,
        obj=q['source_location']['object_index'],
        offset=q['source_location']['object_offset'],
        cs_base=descriptor['descriptor']['base'],
        cs_limit=descriptor['descriptor']['limit'],
        descriptor=descriptor['descriptor']['raw'],
        source_instruction_sha256=q['source_instruction_sha256'],
    )


def pae_cpu_context(registers):
    state = registers['address_state']
    control = state['control']
    return dict(mode=registers['cpu_mode'], paging=state['paging'],
                cr0=integer(control['CR0']), cr3=integer(control['CR3']), cr4=integer(control['CR4']),
                cs=integer(registers['registers']['cs']), ip=integer(registers['instruction_pointer']))


def high_alias_reads(debug, cfg):
    reader = debug.vm.debugger()
    observed = []
    for address in (cfg['first_target'], cfg['second_target']):
        high = reader.memory(address, 2, space='physical')
        low = reader.memory(address & 0xffffffff, 2, space='physical')
        assert address >= 2**32 and high.hex() == '46cb' and low.hex() == cfg['low_alias_marker']
        observed.append(dict(address=address, high=high.hex(), low=low.hex()))
    return observed


def run(stage, phase):
    cfg = json.loads((stage / 'config.json').read_text())
    source = Path(cfg['source'])
    db = stage / 'qemu.fdb'
    rt = os.environ
    options = dict(
        backend='qemu-dos',
        dos_boot_image=str(stage / 'boot.img'),
        dos_mcopy=rt['FDISBULL_QEMU_DOS_MCOPY'],
        dos_startup_batch='FDAUTO.BAT',
        qemu_transport='pipe',
        qemu_firmware=rt['FDISBULL_QEMU_DOS_FIRMWARE'],
        qemu_checkpoint_tool=rt['FDISBULL_QEMU_IMG'],
    )
    if cfg.get('high_physical'):
        from fdisbull.qemu_dos import prepare_dos_profile
        options['guest_profile'] = prepare_dos_profile(stage / 'boot.img', cpu='max', memory_mib=64,
                                                      max_ram_below_4g_mib=32)
    checkpoints_at = cfg['checkpoint_index']
    owners, ids = [], []
    pae_context = {}
    aliases = []
    check_pae = cfg.get('paging_mode', '').startswith('pae-')
    with Project.create(db, source, image='mz') if phase == 'before' else Project(db) as project:
        with project.debugger(
            rt['FDISBULL_QEMU_DOS'], source.parent, _on_spawn=owners.append, **options
        ) as debug:
            if check_pae:
                entry = pae_cpu_context(debug.registers())
                assert entry['mode'] == 'real' and not entry['paging'] and not (entry['cr4'] & 0x20)
                pae_context['entry'] = entry
            if phase == 'before':
                bp = debug.breakpoint(cfg['start_pc'])['breakpoint_id']
                stop = debug.run(timeout_ms=10000)
                assert (
                    stop['outcome'] == 'breakpoint'
                    and bp in stop['session']['stop_reason']['breakpoint_ids']
                )
                debug.delete_breakpoint(bp)
            else:
                before = json.loads((stage / 'qemu-before.json').read_text())
                state = before['checkpoint']
                restore = debug.load_machine_state(state, timeout_ms=60000)
                assert restore['machine_state_restored'] and not restore['protected_source_rebound']
                if check_pae:
                    restored = pae_cpu_context(debug.registers())
                    assert restored == before['pae_cpu_context']['checkpoint']
                    pae_context['restored'] = restored
                assert not debug.dos_source_binding()['live']
            if cfg.get('high_physical') and phase == 'after':
                assert debug.vm.machine_configuration['max_ram_below_4g_mib'] == 32
                aliases = high_alias_reads(debug, cfg)
            binding = debug.dos_source_bind(tracking='paged', expected_source_sha256=cfg['sha256'])
            assert binding['live'] and binding['tracking'] == 'paged'
            if phase == 'before':
                first = debug.trace(
                    'before-remap-checkpoint.json',
                    count=checkpoints_at,
                    source_view='embedded-le',
                    bits=32,
                    timeout_ms=60000,
                )
                ids.append(first['artifact'])
                regs = debug.registers()
                if check_pae:
                    checkpoint = pae_cpu_context(regs)
                    assert checkpoint['mode'] == 'protected' and checkpoint['paging'] and checkpoint['cr4'] & 0x20
                    pae_context['checkpoint'] = checkpoint
                assert integer(regs['instruction_pointer']) == cfg['target_ip']
                assert integer(regs['registers']['cs']) == cfg['start_cs']
                mapping = debug.dos_source_binding()['mapping_identity']
                assert mapping['instruction_backing'][0]['physical'] == cfg['second_target']
                if cfg.get('high_physical'):
                    assert debug.vm.machine_configuration['max_ram_below_4g_mib'] == 32
                    aliases = high_alias_reads(debug, cfg)
                state = debug.save_machine_state()['artifact']
            else:
                assert (
                    binding['binding_id'] != before['binding_id']
                    and binding['capture_epoch'] != before['epoch']
                )
            tail = debug.trace(
                'from-remap-checkpoint.json',
                count=cfg['boundaries'] - checkpoints_at,
                source_view='embedded-le',
                bits=32,
                timeout_ms=60000,
            )
            ids.append(tail['artifact'])
            if phase == 'before':
                debug.load_machine_state(state, timeout_ms=60000)
                assert not debug.dos_source_binding()['live']
                fresh = debug.dos_source_bind(tracking='paged', expected_source_sha256=cfg['sha256'])
                assert fresh['binding_id'] != binding['binding_id']
                assert (
                    fresh['mapping_identity']['instruction_backing'][0]['physical']
                    == cfg['second_target']
                )
                assert debug.step()['outcome'] == 'step'
                stepped = debug.dos_source_binding()
                assert stepped['execution_coverage'] == 'stepped-boundaries'
                assert (
                    stepped['mapping_identity']['instruction_backing'][0]['physical']
                    == cfg['second_target'] + 1
                )
                bp = debug.breakpoint(cfg['start_pc'])['breakpoint_id']
                endpoint = debug.run(timeout_ms=10000)
                assert bp in endpoint['session']['stop_reason']['breakpoint_ids']
                debug.delete_breakpoint(bp)
                stopped = debug.dos_source_binding()
                assert stopped['execution_coverage'] == 'stopped-endpoints'
                assert stopped['last_observation']['source_location']['object_offset'] == cfg['start_ip']
    assert owners and all(p.poll() == 0 for p in owners)
    events = []
    with Project(db) as project:
        for identifier in ids:
            verified = project.debug_analyze_le_tracking_trace(identifier)
            assert verified['outcome'] == 'count' and verified['binding_id'] == binding['binding_id']
            events.extend(summarize(e) for e in verified['events'])
        assert len(project.versions()) == 1
    if phase == 'after':
        env = {**os.environ, 'FDISBULL_OUTPUT_ARTIFACT_DIR': str(stage / 'cli-output')}
        cli = [sys.executable, '-m', 'fdisbull']
        reply = json.loads(
            subprocess.check_output(
                [*cli, 'debug-analyze-le-tracking-trace', str(db), ids[-1]], env=env, text=True
            )
        )
        assert reply['ok']
        if reply['result'].get('format') == 'fdisbull-output-ref-1':
            path = stage / 'cli-trace.json'
            exported = json.loads(
                subprocess.check_output(
                    [*cli, 'output-export', reply['result']['artifact']['id'], str(path)],
                    env=env,
                    text=True,
                )
            )
            assert exported['ok']
            reply = json.loads(path.read_bytes())
        assert reply['ok'] and reply['result'] == public_addresses(verified)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == cfg['sha256']
    result = dict(
        checkpoint=state,
        events=events,
        artifacts=ids,
        epoch=binding['capture_epoch'],
        binding_id=binding['binding_id'],
    )
    if cfg.get('high_physical'):
        result['high_alias_reads'] = aliases
    if check_pae:
        result['pae_cpu_context'] = pae_context
    (stage / ('qemu-' + phase + '.json')).write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    run(Path(sys.argv[1]), sys.argv[2])
