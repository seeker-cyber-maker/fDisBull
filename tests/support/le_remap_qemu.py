"""Collect and reopen a QEMU LE tracking trace across a guest-controlled remap."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys

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
    return dict(
        **result,
        hex=data.hex(),
        backing=backing,
        obj=q['source_location']['object_index'],
        offset=q['source_location']['object_offset'],
        cs_base=descriptor['descriptor']['base'],
        cs_limit=descriptor['descriptor']['limit'],
        descriptor=descriptor['descriptor']['raw'],
        source_instruction_sha256=q['source_instruction_sha256'],
    )


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
    checkpoints_at = cfg['checkpoint_index']
    owners, ids = [], []
    with Project.create(db, source, image='mz') if phase == 'before' else Project(db) as project:
        with project.debugger(
            rt['FDISBULL_QEMU_DOS'], source.parent, _on_spawn=owners.append, **options
        ) as debug:
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
                assert not debug.dos_source_binding()['live']
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
                assert integer(regs['instruction_pointer']) == cfg['target_ip']
                assert integer(regs['registers']['cs']) == cfg['start_cs']
                mapping = debug.dos_source_binding()['mapping_identity']
                assert mapping['instruction_backing'][0]['physical'] == cfg['second_target']
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
        assert reply['ok'] and reply['result'] == verified
    assert hashlib.sha256(source.read_bytes()).hexdigest() == cfg['sha256']
    result = dict(
        checkpoint=state,
        events=events,
        artifacts=ids,
        epoch=binding['capture_epoch'],
        binding_id=binding['binding_id'],
    )
    (stage / ('qemu-' + phase + '.json')).write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    run(Path(sys.argv[1]), sys.argv[2])
