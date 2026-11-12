"""Caller-owned DESQview machine profiles and stopped guest observations."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .qemm_runtime import _FATVolume, _dos_parts, _file, MAX_IMAGE, prepare_qemm_profile
from .memory_search_runtime import _capture, _locked, _read


PROFILE = 'desqview-386-v1'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare_profile(boot_image, *, program=r'\DV\DV.EXE', modules=None, qemm=False, startup=None):
    """Pin declared program/module members without modifying or booting a disk.

    Installed files and AUTOEXEC selection are caller choices. Finding a DV.EXE
    is not evidence that an installer ran or that the selected program boots.
    """
    if type(qemm) is not bool:
        raise ValueError('qemm must be boolean')
    if modules is None:
        modules = []
    if not isinstance(modules, list) or len(modules) > 64 or not all(isinstance(path,str) for path in modules):
        raise ValueError('DESQview modules must be at most 64 explicit DOS paths')
    path, data = _file(boot_image, MAX_IMAGE, 'DESQview DOS boot image')
    volume = _FATVolume(data)
    paths = [program, *modules] + ([] if startup is None else [startup])
    selected = [volume.boot_drive + '\\' + '\\'.join(_dos_parts(item, boot_drive=volume.boot_drive)) for item in paths]
    if len(selected) != len(set(selected)):
        raise ValueError('Duplicate DESQview profile member paths')
    members = []
    for index, name in enumerate(selected):
        contents = volume.read(name, maximum=4 * 1024 * 1024)
        if not contents:
            raise ValueError('Empty declared DESQview member: ' + name)
        if index == 0 and (len(contents) < 28 or contents[:2] != b'MZ'):
            raise ValueError('The selected DESQview program must be its MZ executable, not a COM launcher or package')
        members.append(dict(guest_path=name, size=len(contents), sha256=_sha(contents),
                            role='program' if index == 0 else 'startup' if startup is not None and index == len(selected)-1 else 'module'))
    manager = prepare_qemm_profile(path) if qemm else None
    result = dict(schema=1, profile=PROFILE, backend='qemu-machine',
                  boot_image=dict(path=str(path), size=len(data), sha256=_sha(data)),
                  volume=dict(format='FAT' + str(volume.bits), offset=volume.offset, partition=volume.partition, drive=volume.boot_drive),
                  selection=dict(program=selected[0], modules=selected[1:1+len(modules)],
                                 startup=selected[-1] if startup is not None else None, qemm=qemm),
                  members=members,
                  machine=dict(cpu='486', memory_mib=32, cpus=1, network='none',
                               disk='private-verified-copy-and-snapshot', boot_device=volume.boot_device, boot_drive=volume.boot_drive),
                  desqview=dict(configured='caller-selected program and modules', observed='unknown',
                                installation='unverified', kernel_version=None, product_version=None),
                  memory_manager=deepcopy(manager['memory_manager']) if manager else dict(configured='not_selected', observed='unknown'),
                  qemm_profile=manager,
                  limitations=['A member manifest does not prove a DOS boot, installation, startup or working multitasking.',
                               'A startup file is hash-identified, not interpreted as a verified launch recipe.',
                               'DVR bytes are pinned dependencies; this profile does not reconstruct their module ABI.',
                               'The helper observes its own current task. Other tasks need their own qualified identity.',
                               'Guest profile admission never edits the caller disk or installs a memory manager.'])
    identity = {key:result[key] for key in ('schema','profile','machine','selection','members')}
    identity['image_sha256'] = result['boot_image']['sha256']
    identity['qemm_profile_sha256'] = manager['profile_sha256'] if manager else None
    result['profile_sha256'] = _sha(json.dumps(identity,sort_keys=True,separators=(',',':')).encode())
    return result


def admit_profile(profile, boot_image):
    if isinstance(profile,str):
        if profile not in ('desqview', PROFILE):
            raise ValueError('Unknown DESQview guest profile')
        return prepare_profile(boot_image)
    if not isinstance(profile,dict) or profile.get('profile') != PROFILE or type(profile.get('schema')) is not int or profile['schema'] != 1:
        raise ValueError('Expected desqview-386-v1 profile')
    selection = profile.get('selection')
    if not isinstance(selection,dict) or set(selection) != {'program','modules','startup','qemm'}:
        raise ValueError('Malformed DESQview profile selection')
    current = prepare_profile(boot_image, **selection)
    for key in ('profile_sha256','machine','members','selection'):
        if profile.get(key) != current[key]:
            raise ValueError('DESQview profile input changed: ' + key)
    if any(profile.get('boot_image',{}).get(key) != current['boot_image'][key] for key in ('size','sha256')):
        raise ValueError('DESQview profile boot image changed')
    return current


def invoke(method, params):
    from .desqview import write_probe, parse_report, inspect_module, REPORT_SIZE
    p = dict(params)
    if method == 'desqview-profile':
        return prepare_profile(**p)
    if method == 'desqview-probe':
        return write_probe(**p)
    if method == 'desqview-module-inspect':
        return inspect_module(**p)
    if method == 'desqview-report':
        selected, data = _file(p.pop('path'), REPORT_SIZE, 'DESQview report')
        if p:
            raise ValueError('Unexpected DESQview report options')
        return dict(parse_report(data), source_path=str(selected))
    raise ValueError('Unknown DESQview method')


class DesqviewSessionMixin:
    @_locked
    def desqview_observe(self, address, *, space='linear', probe_base=None, expected_nonce=None):
        """Observe a report; optional exact helper-stop checks never inject code."""
        from .desqview import parse_report, probe_bytes, REPORT_SIZE
        from .memory_search_runtime import _integer
        from .debugger import stamp
        data, context, capture = _capture(self, address, REPORT_SIZE, space, 'desqview-report-observation')
        parsed = parse_report(data)
        if expected_nonce is not None and (not isinstance(expected_nonce,str) or parsed['nonce'] != expected_nonce.lower()):
            raise ValueError('DESQview report nonce does not match the selected helper')
        helper = dict(verified_at_ready_stop=False, executed_api_sequence='not_established_by_report')
        if probe_base is not None:
            if space != 'linear' or expected_nonce is None:
                raise ValueError('Helper-stop verification requires linear addresses and the emitted nonce')
            base = _integer(probe_base, 'DESQview COM segment base', 0, 0xffff0)
            if base % 16:
                raise ValueError('A DOS COM base must be paragraph aligned')
            program, asset = probe_bytes(mode='breakpoint', yields=parsed['cooperation']['requested_yields'], nonce=expected_nonce)
            if context['region']['start'] != base + asset['report_com_offset']:
                raise ValueError('DESQview report is outside the declared helper')
            current = self.registers()
            if hasattr(self,'vm'):
                pc = current.get('linear_pc')
                mode = current.get('cpu_mode')
                segment_base = current.get('address_state',{}).get('segments',{}).get('cs',{}).get('base')
            else:
                mode = current.get('cpu_mode')
                segment = int(current['segments']['cs'],0)
                segment_base = hex(segment * 16)
                pc = hex(segment * 16 + int(current['instruction_pointer'],0))
            if mode not in ('real','v86') or segment_base is None or int(segment_base,0) != base or pc is None or int(pc,0) != base + asset['ready_com_offset']:
                raise ValueError('The current stopped CPU is not at this DESQview helper ready point')
            prefix_length = asset['report_com_offset'] - 0x100
            actual = _read(self,base + 0x100,prefix_length,'linear')
            if actual != program[:prefix_length]:
                raise ValueError('Loaded DESQview helper code differs from the authored producer')
            if _read(self,context['region']['start'],REPORT_SIZE,'linear') != data:
                raise ValueError('DESQview report changed during helper verification')
            helper = dict(verified_at_ready_stop=True, program_sha256=_sha(program),
                          source_sha256=asset['source_sha256'], base=hex(base), ready_pc=pc,
                          nonce=expected_nonce.lower(), executed_api_sequence='not_a_whole-program_execution_proof',
                          task_scope='current helper task; not another DESQview window')
        observation = dict(captured_at=stamp(), run=self.run_id, context=context,
                           helper=helper, parsed=parsed, capture=capture,
                           freshness='current bytes at verified helper ready stop' if helper['verified_at_ready_stop'] else 'not_established',
                           scheduler_qualification='not_established_by_report')
        artifact = self._artifact('desqview-report.bin','desqview-report',data,observation)
        self._event('desqview-observe', dict(artifact=artifact['artifact'], **observation))
        return dict(artifact=artifact['artifact'], sha256=artifact['sha256'], **observation)
