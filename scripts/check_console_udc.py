#!/usr/bin/env python3
"""Run a bounded Libretro session in a disposable process; ROMs stay external."""
import argparse
from array import array
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import wave

from PIL import Image


def sha(data):
    return hashlib.sha256(data).hexdigest()


def integer(value, low, high=None):
    return type(value) is int and value >= low and (high is None or value <= high)


def validate_watches(watches):
    if not isinstance(watches, list) or len(watches) > 64:
        raise ValueError('watch must be a list of up to 64 raw RAM slices')
    for watch in watches:
        if (not isinstance(watch, dict) or not isinstance(watch.get('name'), str)
                or not watch['name'] or not integer(watch.get('offset'), 0)
                or not integer(watch.get('length'), 1, 1024)
                or type(watch.get('memory_id', 2)) is not int
                or watch.get('memory_id', 2) not in (0, 2)):
            raise ValueError('watch requires name, nonnegative offset, length1..1024 and memory_id0 or2')
    if len({w['name'] for w in watches}) != len(watches):
        raise ValueError('watch names must be unique')
    return watches


def validate_patches(patches, frames):
    if not isinstance(patches, list) or len(patches) > 4096:
        raise ValueError('patches must be a finite list of up to4096 memory writes')
    result = []
    total = 0
    for patch in patches:
        if (not isinstance(patch, dict)
                or set(patch) != {'frame', 'memory_id', 'offset', 'data_hex'}
                or not integer(patch.get('frame'), 0, frames - 1)
                or type(patch.get('memory_id')) is not int
                or patch['memory_id'] not in (0, 2)
                or not integer(patch.get('offset'), 0)
                or not isinstance(patch.get('data_hex'), str)):
            raise ValueError('patch requires frame within run, memory_id0 or2, offset and data_hex')
        try:
            data = bytes.fromhex(patch['data_hex'])
        except ValueError as exc:
            raise ValueError('patch data_hex must contain whole hexadecimal bytes') from exc
        if not 1 <= len(data) <= 16384:
            raise ValueError('each patch must contain1..16384 bytes')
        total += len(data)
        if total > 1024 * 1024:
            raise ValueError('combined memory patches exceed1MiB')
        result.append({**patch, 'data_hex': data.hex()})
    return result


def frame_numbers(value, frames):
    if value is None:
        return []
    parts = value.split(',')
    if not parts or any(not part.strip().isdigit() for part in parts):
        raise ValueError('frame-images requires comma-separated zero-based frame numbers')
    numbers = [int(part.strip()) for part in parts]
    if len(numbers) != len(set(numbers)) or any(not 0 <= n < frames for n in numbers):
        raise ValueError('frame-images must be unique frames within the run')
    return sorted(numbers)


def validate_feedback_policy(policy):
    allowed={'format','kind','rom_sha256','publication','max_logic_steps','post_goal_host_frames'}
    optional={'post_transition_host_frames'}
    if (not isinstance(policy,dict) or not allowed<=set(policy)<=allowed|optional
            or policy['format']!='fdisbull-publication-controller-1'
            or policy['kind']!='miniplanets-stage1-1'
            or not isinstance(policy['rom_sha256'],str)
            or len(policy['rom_sha256'])!=64
            or any(c not in '0123456789abcdef' for c in policy['rom_sha256'])
            or not integer(policy['max_logic_steps'],1,5000)
            or not integer(policy['post_goal_host_frames'],0,1000)
            or ('post_transition_host_frames' in policy
                and not integer(policy['post_transition_host_frames'],0,5000))):
        raise ValueError('invalid finite publication controller policy')
    p=policy['publication']
    if (not isinstance(p,dict) or p.get('memory_id')!=2 or type(p.get('memory_id')) is not int
            or p.get('slots')!=4 or type(p.get('slots')) is not int
            or p.get('stride')!=48 or type(p.get('stride')) is not int
            or not integer(p.get('base'),0,2048-4*48)):
        raise ValueError('feedback requires the bounded four-slot system-RAM publication')
    if (not integer(p.get('sequence'),0,0) or not integer(p.get('version'),1,1)
            or not integer(p.get('epoch'),2,2)):
        raise ValueError('unsupported publication validity layout')
    required={'mode','stage','anim','input_buttons','player_x','player_y','player_jump',
              'player_win','player_die','keys_left','ingame_status'}
    fields=p.get('fields')
    if not isinstance(fields,dict) or not required<=set(fields) or len(fields)>64:
        raise ValueError('feedback publication lacks required fields')
    for name,field in fields.items():
        if (not isinstance(name,str) or not name.isidentifier() or not isinstance(field,list)
                or len(field)!=2 or not integer(field[0],4,47)
                or type(field[1]) is not int or field[1] not in (1,2,4)
                or field[0]+field[1]>48):
            raise ValueError('feedback publication field is outside its record')
    return policy


def validate_feedback_session(policy, *, system, rom_sha256, inputs, patches, buttons):
    validate_feedback_policy(policy)
    if system!='nes' or patches or inputs:
        raise ValueError('feedback mode requires NES, no RAM patches and no competing static inputs')
    if policy['rom_sha256']!=rom_sha256:
        raise ValueError('feedback policy is bound to a different cartridge')
    if not {'RIGHT','LEFT','UP','DOWN','A','START'}<=set(buttons):
        raise ValueError('feedback controller input map lacks required ordinary buttons')


class PublicationController:
    """Finite, read-only feedback for a declared first-level controller route.

    Tile-interior waypoints leave room for the observed controller latency.
    Only ordinary buttons are submitted; this class has no memory-write API.
    """
    def __init__(self,policy):
        self.policy=validate_feedback_policy(policy);self.expected_epoch=1
        self.mask=0;self.phase='title';self.segment=0;self.settling=False
        self.steps=0;self.observations=[];self.completed=False;self.stop_frame=None
        self.reason=None;self.goal_epoch=None;self.goal_host_frame=None
        self.stage_transition=None

    def _fail(self,reason,host_frame):
        self.reason=reason;self.mask=0;self.stop_frame=host_frame

    def _route(self,s,host_frame):
        x,y,j=s['player_x'],s['player_y'],s['player_jump']
        if self.settling:
            self.mask=0
            if s['input_buttons']==0:
                self.settling=False;self.segment+=1
            else:return
        actions=[(4,160<=y<=172,True),(1,56<=x<64,True),
                 (17,j>0,False),(1,168<=x<176,True),
                 (4,96<=y<=104,True),(2,96<=x<=104,True),
                 (18,j>0,False),(2,x<=4 and s['keys_left']==0,True),
                 (1,56<=x<64,True),(17,j>0,False),
                 (1,168<=x<176,True),(8,False,False)]
        if self.segment==7 and x<=4 and s['keys_left']!=0:
            self._fail('key was not collected at the guarded waypoint',host_frame);return
        if self.segment>=len(actions):
            self._fail('finite route exhausted without goal',host_frame);return
        mask,finished,settle=actions[self.segment]
        if finished:
            if settle:self.settling=True;self.mask=0
            else:
                self.segment+=1;self.mask=actions[self.segment][0]
        else:self.mask=mask

    def observe(self,raw,host_frame):
        p=self.policy['publication']
        for _ in range(4):
            if self.stop_frame is not None and not self.completed:
                break
            slot=self.expected_epoch%4;packet=raw[slot*48:(slot+1)*48]
            if len(packet)!=48:raise ValueError('truncated feedback publication memory')
            if packet[0]&1 or packet[1]!=1:break
            number=int.from_bytes(packet[2:4],'little')
            if number!=self.expected_epoch:
                if self.steps and number>self.expected_epoch and (number-self.expected_epoch)%4==0:
                    self._fail('publication ring overrun',host_frame)
                break
            s={name:int.from_bytes(packet[at:at+width],'little') for name,(at,width) in p['fields'].items()}
            self.steps+=1;self.expected_epoch+=1
            if self.completed:
                if self.stage_transition is None and s['mode']==1 and s['stage']==1:
                    self.stage_transition={'epoch':number,'host_frame':host_frame,'observed':s}
                    self.stop_frame=(host_frame+self.policy['post_transition_host_frames']
                        if 'post_transition_host_frames' in self.policy else min(self.stop_frame,host_frame+8))
            elif self.steps>self.policy['max_logic_steps']:
                self._fail('logical-step budget exhausted',host_frame)
            elif s['mode']==1 and s['stage']==0 and s['player_win'] and s['keys_left']==0:
                self.completed=True;self.mask=0;self.reason='goal observed in completed projection'
                self.goal_epoch=number;self.goal_host_frame=host_frame
                self.stop_frame=host_frame+self.policy['post_goal_host_frames']
            elif s['mode']==1 and s['player_die']:
                self._fail('player death observed',host_frame)
            elif s['mode']==0:
                self.phase='title';self.mask=64 if s['anim']>=85 else 0
            elif s['mode']==8:
                if not self.phase.startswith('intro'):
                    self.phase='intro_release';self.mask=0
                elif self.phase=='intro_release':
                    if s['input_buttons']==0:self.phase='intro_start';self.mask=64
                    else:self.mask=0
                else:self.mask=64
            elif s['mode']==1:
                if s['stage']!=0:self._fail('unexpected stage before first-level goal',host_frame)
                elif s['ingame_status']&1:self._fail('unexpected pause during route',host_frame)
                else:
                    if self.phase not in ('landing','route'):
                        self.phase='landing';self.mask=0
                    if self.phase=='landing':
                        self.mask=0
                        if s['player_jump']==0:self.phase='route';self.mask=4
                    else:self._route(s,host_frame)
            else:self._fail('unexpected game mode before route completion',host_frame)
            self.observations.append({'host_frame':host_frame,'epoch':number,'phase':self.phase,
                'segment':self.segment,'settling':self.settling,'next_buttons':self.mask,'observed':s})
            if self.steps>=self.policy['max_logic_steps'] and not self.completed and self.stop_frame is None:
                self._fail('logical-step budget exhausted',host_frame)

    def result(self):
        return {'completed':self.completed,'reason':self.reason or 'host-frame budget exhausted',
                'logical_steps_observed':self.steps,'goal_epoch':self.goal_epoch,
                'goal_host_frame':self.goal_host_frame,'final_phase':self.phase,'final_segment':self.segment,
                'next_stage_transition':self.stage_transition,
                **({'post_transition_host_frames':self.policy['post_transition_host_frames']}
                   if 'post_transition_host_frames' in self.policy else {}),
                'assistance':'Read-only completed-state feedback; ordinary controller buttons only; no RAM writes.'}


def frame_image(record):
    raw, width, height, pitch, fmt = record
    rgb = bytearray(width * height * 3)
    bpp = 4 if fmt == 1 else 2
    for y in range(height):
        for x in range(width):
            p = y * pitch + x * bpp
            value = int.from_bytes(raw[p:p+bpp], sys.byteorder)
            if fmt == 1:
                r, g, b = (value >> 16) & 255, (value >> 8) & 255, value & 255
            elif fmt == 2:
                r, g, b = ((value >> 11) & 31) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31
            else:
                r, g, b = ((value >> 10) & 31) * 255 // 31, ((value >> 5) & 31) * 255 // 31, (value & 31) * 255 // 31
            j = (y * width + x) * 3
            rgb[j:j+3] = bytes((r, g, b))
    return Image.frombytes('RGB', (width, height), bytes(rgb)), bytes(rgb)


def write_audio_capture(out, pcm, sample_rate, callback_counts):
    if not math.isfinite(sample_rate) or not 1 <= round(sample_rate) <= 768000:
        raise ValueError('core supplied an invalid audio sample rate')
    if len(pcm) % 4:
        raise ValueError('captured audio is not complete stereo PCM16')
    values = array('h')
    values.frombytes(pcm)
    if sys.byteorder != 'little':
        values.byteswap()
    peak = max((abs(v) for v in values), default=0)
    rms = math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0
    path = out / 'audio.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(round(sample_rate))
        output.writeframes(pcm)
    return {'path': path.name, 'channels': 2, 'bits_per_sample': 16,
            'byte_order': 'little-endian signed PCM', 'sample_rate': round(sample_rate),
            'stereo_frames': len(pcm) // 4, 'sample_count': len(values),
            'nonzero_samples': sum(v != 0 for v in values), 'peak': peak,
            'peak_normalized': peak / 32768.0, 'rms': rms,
            'rms_normalized': rms / 32768.0, 'pcm_sha256': sha(pcm),
            'wav_sha256': sha(path.read_bytes()), **callback_counts}


class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


class InputDescriptor(C.Structure):
    _fields_ = [('port', C.c_uint), ('device', C.c_uint), ('index', C.c_uint), ('id', C.c_uint), ('description', C.c_char_p)]


class SystemInfo(C.Structure):
    _fields_ = [('library_name', C.c_char_p), ('library_version', C.c_char_p), ('valid_extensions', C.c_char_p), ('need_fullpath', C.c_bool), ('block_extract', C.c_bool)]


class Geometry(C.Structure):
    _fields_ = [('base_width', C.c_uint), ('base_height', C.c_uint), ('max_width', C.c_uint), ('max_height', C.c_uint), ('aspect_ratio', C.c_float)]


class Timing(C.Structure):
    _fields_ = [('fps', C.c_double), ('sample_rate', C.c_double)]


class AVInfo(C.Structure):
    _fields_ = [('geometry', Geometry), ('timing', Timing)]


class SnesTraceEvent(C.Structure):
    _fields_ = [(name,C.c_uint32) for name in
                ('kind','pc','address','value','a','x','y','s','d','p','db','opcode')]

class SnesControllerSample(C.Structure):
    _fields_ = [(name,C.c_uint32) for name in ('kind','serial','held','previous','edge','actor')]

class SnesHardwareSample(C.Structure):
    _fields_ = [(name,C.c_uint32) for name in (
        'ordinal','serial','boundary','caller','task','return_pc','parent_return',
        'seed_before','nmi_low','nmi_high','beam_h','beam_v','latch','result','seed_after','seen')]

class SnesHardwareModal(C.Structure):
    _fields_ = [(name,C.c_uint32) for name in ('boundary','serial','kind','pc')]

def controller_journal_summary(samples, dropped):
    grouped={}
    for sample in samples:
        if sample['kind'] in ('modal','conversation'):
            continue  # Multiple selector polls in one main-loop pass are expected.
        grouped.setdefault((sample['kind'],sample['serial']),[]).append(
            (sample['held'],sample['previous'],sample['edge'],sample['actor']))
    keys=lambda items:[{'kind':kind,'serial':serial} for kind,serial in items]
    serials={sample['serial'] for sample in samples}
    disagreements=[serial for serial in sorted(serials)
                   if ('main',serial) in grouped and ('player',serial) in grouped
                   and {v[0] for v in grouped['main',serial]}!={v[0] for v in grouped['player',serial]}]
    return {'format':'snes-main-loop-controller-journal-1',
            'phase':'main before 80:9D9D with 80:963A JSR return 963C; player before 80:DE91; modal or typed conversation after its 9D9D calls; serial is latest 80:962E checkpoint',
            'dropped':dropped,'samples':samples,
            'duplicate_serials':keys([key for key,items in grouped.items() if len(items)>1]),
            'conflicting_serials':keys([key for key,items in grouped.items() if len(set(items))>1]),
            'consumer_disagreements':disagreements}


def snes_range(value):
    if value is None:
        return (0,0)
    parts=value.split(':')
    if len(parts)!=2:
        raise ValueError('SNES trace range requires start:exclusive-end')
    lo,hi=(int(part,0) for part in parts)
    if not 0<=lo<hi<=0x1000000:
        raise ValueError('SNES trace range outside 24-bit bus')
    return lo,hi


def checkpoint_plan(pc, selected, frames, limit=4):
    if pc is None and selected is None:return []
    if (type(pc) is not int or not 0<pc<=0xffffff or selected is None
            or type(limit) is not int or not 1<=limit<=8):
        raise ValueError('SNES checkpoint requires a 24-bit PC, selected frames and limit1..8')
    result=frame_numbers(selected,frames)
    if len(result)>6000:raise ValueError('at most 6000 checkpoint video frames')
    if len(result)>128 and limit!=1:raise ValueError('more than 128 checkpoint frames requires limit 1')
    return result


def controller_buttons(system):
    buttons={'UP':4,'DOWN':5,'LEFT':6,'RIGHT':7,'START':3,'B':0}
    if system=='nes': buttons.update({'A':8,'SELECT':2})
    elif system=='snes': buttons.update({'A':8,'X':9,'Y':1,'L':10,'R':11,'SELECT':2})
    elif system=='genesis': buttons.update({'A':1,'C':8})
    else: raise ValueError('unsupported controller system')
    return buttons


def worker(args):
    core_path = Path(args.core).resolve()
    rom_path = Path(args.rom).resolve()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if rom_path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('ROM exceeds 64 MiB')
    rom = rom_path.read_bytes()
    core_hash = sha(core_path.read_bytes())
    inputs = json.loads(Path(args.inputs).read_text()) if args.inputs else []
    if not isinstance(inputs, list):
        raise ValueError('inputs must be a list of {start,end,buttons} objects')
    buttons = controller_buttons(args.system)
    if args.input_map:
        buttons = {k.upper(): v for k, v in json.loads(Path(args.input_map).read_text()).items()}
    if any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < 16 for v in buttons.values()):
        raise ValueError('input-map IDs must be integers from 0 through 15')
    watches = validate_watches(json.loads(Path(args.watch).read_text()) if args.watch else [])
    patch_bytes = Path(args.patches).read_bytes() if args.patches else None
    patches = validate_patches(json.loads(patch_bytes) if patch_bytes is not None else [], args.frames)
    feedback_bytes=Path(args.feedback_policy).read_bytes() if args.feedback_policy else None
    feedback=PublicationController(json.loads(feedback_bytes)) if feedback_bytes is not None else None
    if feedback is not None:
        validate_feedback_session(feedback.policy,system=args.system,rom_sha256=sha(rom),
                                  inputs=inputs,patches=patches,buttons=buttons)
    selected_frames = set(frame_numbers(args.frame_images, args.frames))
    ram_frames = set(frame_numbers(args.frame_ram, args.frames))
    if len(ram_frames) > 64:
        raise ValueError('at most 64 full RAM snapshots')
    by_frame = {}
    for patch in patches:
        by_frame.setdefault(patch['frame'], []).append(patch)
    masks = [0] * args.frames
    for entry in inputs:
        start, end = entry['start'], entry['end']
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= args.frames):
            raise ValueError('input range must be within frames and end exclusive')
        mask = 0
        for button in entry['buttons']:
            mask |= 1 << buttons[button.upper()]
        for i in range(start, end):
            masks[i] |= mask
    lib = C.CDLL(str(core_path))
    ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
    VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
    AUDIO = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
    BATCH = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
    POLL = C.CFUNCTYPE(None)
    STATE = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
    descriptors = []
    pixel = [0]
    frame = [None]
    current = [0]
    pcm = bytearray()
    audio_errors = []
    audio_counts = {'single_callback_frames': 0, 'batch_callback_frames': 0}
    audio_limit = 256 * 1024 * 1024
    system_dir = C.create_string_buffer(os.fsencode(str(out)))
    @ENV
    def environment(cmd, data):
        if cmd == 11:  # RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS
            entries = C.cast(data, C.POINTER(InputDescriptor))
            for i in range(256):
                entry = entries[i]
                if not entry.description:
                    return True
                descriptors.append({'port': entry.port, 'device': entry.device, 'index': entry.index, 'id': entry.id, 'description': entry.description.decode(errors='replace')})
            return False
        if cmd == 10:  # RETRO_ENVIRONMENT_SET_PIXEL_FORMAT
            pixel[0] = C.cast(data, C.POINTER(C.c_int))[0]
            return pixel[0] in (0, 1, 2)
        if cmd in (9, 31):  # system and save directory
            C.cast(data, C.POINTER(C.c_char_p))[0] = C.cast(system_dir, C.c_char_p)
            return True
        if cmd == 3:  # can dupe
            C.cast(data, C.POINTER(C.c_bool))[0] = True
            return True
        return False
    @VIDEO
    def video(data, width, height, pitch):
        if data:
            frame[0] = (C.string_at(data, pitch * height), width, height, pitch, pixel[0])
    @AUDIO
    def audio(left, right):
        if args.capture_audio:
            if len(pcm) + 4 > audio_limit:
                if not audio_errors:
                    audio_errors.append('audio capture exceeds 256 MiB')
                return
            pcm.extend(struct.pack('<hh', left, right))
            audio_counts['single_callback_frames'] += 1
    @BATCH
    def batch(data, frames):
        if args.capture_audio:
            if frames > 1048576 or len(pcm) + frames * 4 > audio_limit or (frames and not data):
                if not audio_errors:
                    audio_errors.append('invalid or oversized audio batch')
                return 0
            raw = C.string_at(data, frames * 4) if frames else b''
            if sys.byteorder != 'little':
                values = array('h')
                values.frombytes(raw)
                values.byteswap()
                raw = values.tobytes()
            pcm.extend(raw)
            audio_counts['batch_callback_frames'] += frames
        return frames
    @POLL
    def poll():
        pass
    @STATE
    def state(port, device, index, button):
        if port or device != 1 or index:
            return 0
        if button == 256:
            return C.c_int16(masks[current[0]]).value
        return int(button < 16 and bool(masks[current[0]] & (1 << button)))
    callbacks = [(lib.retro_set_environment, environment), (lib.retro_set_video_refresh, video), (lib.retro_set_audio_sample, audio), (lib.retro_set_audio_sample_batch, batch), (lib.retro_set_input_poll, poll), (lib.retro_set_input_state, state)]
    for setter, callback in callbacks:
        setter.argtypes = [type(callback)]
        setter(callback)
    lib.retro_init()
    info = SystemInfo()
    lib.retro_get_system_info(C.byref(info))
    rom_buffer = C.create_string_buffer(rom)
    game = GameInfo(os.fsencode(str(rom_path)), None if info.need_fullpath else C.cast(rom_buffer, C.c_void_p), len(rom), None)
    lib.retro_load_game.argtypes = [C.POINTER(GameInfo)]
    lib.retro_load_game.restype = C.c_bool
    if not lib.retro_load_game(C.byref(game)):
        raise RuntimeError('core rejected ROM')
    av = AVInfo()
    lib.retro_get_system_av_info(C.byref(av))
    lib.retro_get_memory_data.argtypes = [C.c_uint]
    lib.retro_get_memory_data.restype = C.c_void_p
    lib.retro_get_memory_size.argtypes = [C.c_uint]
    lib.retro_get_memory_size.restype = C.c_size_t
    def memory_slice(memory_id, offset, length):
        size = lib.retro_get_memory_size(memory_id)
        ptr = lib.retro_get_memory_data(memory_id)
        if not ptr or offset + length > size:
            raise ValueError(f'memory slice is outside available memory_id {memory_id}')
        return ptr + offset
    trace = []
    patch_trace = []
    images = []
    ram_images = []
    snes_trace=[]
    checkpoint_frames=checkpoint_plan(args.snes_checkpoint_pc,args.snes_checkpoint_frames,args.frames,args.snes_checkpoint_limit)
    checkpoints=[]
    controller_samples=[]
    controller_dropped=0
    hardware_samples=[]
    hardware_modals=[]
    hardware_dropped=0
    hardware_modal_dropped=0
    if checkpoint_frames:
        if args.system!='snes':raise ValueError('SNES checkpoint requires SNES')
        lib.fdisbull_snes_checkpoint_config.argtypes=[C.c_uint32,C.c_uint32]
        lib.fdisbull_snes_checkpoint_clear.argtypes=[]
        lib.fdisbull_snes_checkpoint_count.restype=C.c_uint32
        lib.fdisbull_snes_checkpoint_dropped.restype=C.c_uint32
        lib.fdisbull_snes_checkpoint_ram.argtypes=[C.c_uint32]
        lib.fdisbull_snes_checkpoint_ram.restype=C.c_void_p
        lib.fdisbull_snes_checkpoint_registers.argtypes=[C.c_uint32]
        lib.fdisbull_snes_checkpoint_registers.restype=C.POINTER(SnesTraceEvent)
        lib.fdisbull_snes_checkpoint_serial.argtypes=[C.c_uint32]
        lib.fdisbull_snes_checkpoint_serial.restype=C.c_uint32
        lib.fdisbull_snes_checkpoint_config(args.snes_checkpoint_pc,args.snes_checkpoint_limit)
    if args.snes_controller_journal:
        lib.fdisbull_snes_controller_config.argtypes=[C.c_uint32]
        lib.fdisbull_snes_controller_clear.argtypes=[]
        lib.fdisbull_snes_controller_count.restype=C.c_uint32
        lib.fdisbull_snes_controller_dropped.restype=C.c_uint32
        lib.fdisbull_snes_controller_samples.restype=C.POINTER(SnesControllerSample)
        lib.fdisbull_snes_controller_config(1)
    if args.snes_hardware_journal:
        lib.fdisbull_snes_hardware_config.argtypes=[C.c_uint32,C.c_uint32]
        lib.fdisbull_snes_hardware_clear.argtypes=[]
        for name in ('count','dropped','busy','modal_count','modal_dropped'):
            getattr(lib,'fdisbull_snes_hardware_'+name).restype=C.c_uint32
        lib.fdisbull_snes_hardware_samples.restype=C.POINTER(SnesHardwareSample)
        lib.fdisbull_snes_hardware_modals.restype=C.POINTER(SnesHardwareModal)
        lib.fdisbull_snes_hardware_modal_ram.argtypes=[C.c_uint32]
        lib.fdisbull_snes_hardware_modal_ram.restype=C.c_void_p
        lib.fdisbull_snes_hardware_config(1,int(args.snes_modal_ram))
    if args.snes_trace_frames:
        if args.system!='snes': raise ValueError('SNES trace requires SNES')
        start,end=(int(x) for x in args.snes_trace_frames.split(':'))
        if not 0<=start<end<=args.frames or end-start>120: raise ValueError('SNES trace limited to 120 frames')
        pc_lo,pc_hi=snes_range(args.snes_trace_pc)
        wr_lo,wr_hi=snes_range(args.snes_trace_write)
        if pc_hi==wr_hi==0: raise ValueError('SNES trace requires a PC or write filter')
        configure=lib.fdisbull_snes_trace_config
        configure.argtypes=[C.c_uint32]*5
        lib.fdisbull_snes_trace_count.restype=C.c_uint32
        lib.fdisbull_snes_trace_dropped.restype=C.c_uint32
        lib.fdisbull_snes_trace_events.restype=C.POINTER(SnesTraceEvent)
    frames_ran=0
    for i in range(args.frames):
        current[0] = i
        if feedback is not None:
            ordinary={'RIGHT':1,'LEFT':2,'UP':4,'DOWN':8,'A':16,'B':32,'START':64,'SELECT':128}
            masks[i]=sum(1<<buttons[name] for name,bit in ordinary.items()
                         if feedback.mask&bit and name in buttons)
        for patch in by_frame.get(i, []):
            data = bytes.fromhex(patch['data_hex'])
            address = memory_slice(patch['memory_id'], patch['offset'], len(data))
            before = C.string_at(address, len(data))
            C.memmove(address, data, len(data))
            actual = C.string_at(address, len(data))
            if actual != data:
                raise RuntimeError('memory patch readback differs from requested bytes')
            patch_trace.append({**patch, 'before_hex': before.hex(), 'after_hex': actual.hex(),
                                'data_sha256': sha(data)})
        if args.snes_trace_frames and start<=i<end:
            configure(pc_lo,pc_hi,wr_lo,wr_hi,65536)
        if checkpoint_frames:lib.fdisbull_snes_checkpoint_clear()
        if args.snes_controller_journal:lib.fdisbull_snes_controller_clear()
        if args.snes_hardware_journal:lib.fdisbull_snes_hardware_clear()
        lib.retro_run()
        if i in checkpoint_frames:
            count=lib.fdisbull_snes_checkpoint_count();dropped=lib.fdisbull_snes_checkpoint_dropped()
            if count>args.snes_checkpoint_limit:raise ValueError('checkpoint count exceeds configured limit')
            captures=[]
            for j in range(count):
                pointer=lib.fdisbull_snes_checkpoint_ram(j)
                registers=lib.fdisbull_snes_checkpoint_registers(j)
                if not pointer or not registers:raise ValueError('checkpoint data missing')
                raw=C.string_at(pointer,131072);serial=lib.fdisbull_snes_checkpoint_serial(j)
                name=None
                if not args.snes_checkpoint_digests:
                    name=f'checkpoint-{i:06d}-{j:02d}.bin';(out/name).write_bytes(raw)
                captures.append({'file':name,'size':len(raw),'sha256':sha(raw),'serial':serial,
                                 'registers':{k:getattr(registers.contents,k) for k,_ in SnesTraceEvent._fields_}})
            checkpoints.append({'video_frame':i,'dropped':dropped,'captures':captures})
        if args.snes_controller_journal:
            count=lib.fdisbull_snes_controller_count()
            controller_dropped+=lib.fdisbull_snes_controller_dropped()
            if count>32:raise ValueError('controller sample count exceeds bound')
            samples=lib.fdisbull_snes_controller_samples()
            for j in range(count):
                sample=samples[j]
                if sample.kind not in (1,2,3,4,5,6):raise ValueError('unknown controller consumer')
                controller_samples.append({'video_frame':i,'kind':{1:'main',2:'player',3:'modal',4:'conversation',5:'conversation',6:'conversation'}[sample.kind],
                                           'serial':sample.serial,'held':sample.held,'previous':sample.previous,
                                           'edge':sample.edge,'actor':sample.actor if sample.kind==2 else None,
                                           **({'pc':sample.actor} if sample.kind>=3 else {}),
                                           **({'context':{4:'primary',5:'keyword',6:'exit'}[sample.kind]} if sample.kind>=4 else {}),
                                           **({'source_return':{4:0x91ac,5:0x922f}[sample.kind]} if sample.kind in (4,5) else {})})
        if args.snes_hardware_journal:
            count=lib.fdisbull_snes_hardware_count()
            hardware_dropped+=lib.fdisbull_snes_hardware_dropped()
            if count>1024:raise ValueError('hardware sample count exceeds bound')
            samples=lib.fdisbull_snes_hardware_samples()
            for j in range(count):
                sample=samples[j]
                row={name:getattr(sample,name) for name in (
                    'ordinal','serial','boundary','caller','nmi_low','nmi_high','beam_h','beam_v')}
                row.update({'video_frame':i,'context':sample.task if sample.caller==3 else 0xffff,
                            'verification':{name:getattr(sample,name) for name in (
                                'task','return_pc','parent_return','seed_before','latch','result','seed_after','seen')}})
                hardware_samples.append(row)
            count=lib.fdisbull_snes_hardware_modal_count()
            hardware_modal_dropped+=lib.fdisbull_snes_hardware_modal_dropped()
            if count>32:raise ValueError('modal sample count exceeds bound')
            modals=lib.fdisbull_snes_hardware_modals()
            for j in range(count):
                row={name:getattr(modals[j],name) for name in ('boundary','serial','kind','pc')}
                pointer=lib.fdisbull_snes_hardware_modal_ram(j)
                if not pointer:raise ValueError('modal RAM missing')
                raw=C.string_at(pointer,131072)
                name=f'modal-{row["boundary"]:06d}.bin';(out/name).write_bytes(raw)
                row.update({'video_frame':i,'file':name,'size':len(raw),'sha256':sha(raw)})
                hardware_modals.append(row)
        if args.snes_trace_frames and start<=i<end:
            count=lib.fdisbull_snes_trace_count();dropped=lib.fdisbull_snes_trace_dropped()
            events=lib.fdisbull_snes_trace_events()
            snes_trace.append({'frame':i,'dropped':dropped,'events':[
                {name:getattr(events[j],name) for name,_ in SnesTraceEvent._fields_} for j in range(count)]})
            configure(0,0,0,0,0)
        frames_ran=i+1
        if i in ram_frames:
            n=lib.retro_get_memory_size(2)
            if not 0 < n <= 2*1024*1024:
                raise ValueError('system RAM snapshot exceeds bounded size')
            data=C.string_at(memory_slice(2,0,n),n)
            name=f'ram-{i:06d}.bin'
            (out/name).write_bytes(data)
            ram_images.append({'frame':i,'file':name,'size':n,'sha256':sha(data)})
        if audio_errors:
            raise RuntimeError(audio_errors[0])
        if watches:
            trace.append({'frame': i, 'input_mask': masks[i], 'raw': {
                w['name']: C.string_at(memory_slice(w.get('memory_id', 2), w['offset'], w['length']), w['length']).hex()
                for w in watches}})
        if i in selected_frames:
            if frame[0] is None:
                raise RuntimeError(f'core produced no video for requested frame {i}')
            picture, pixels = frame_image(frame[0])
            image_path = out / f'frame-{i:06d}.png'
            picture.save(image_path)
            images.append({'frame': i, 'path': image_path.name, 'width': picture.width,
                           'height': picture.height, 'rgb_sha256': sha(pixels),
                           'png_sha256': sha(image_path.read_bytes())})
        if feedback is not None:
            p=feedback.policy['publication']
            raw=C.string_at(memory_slice(2,p['base'],4*48),4*48)
            feedback.observe(raw,i)
            if feedback.stop_frame is not None and i>=feedback.stop_frame:
                break
    trace_bytes = (json.dumps({'phase': 'after retro_run; frame is zero-based', 'watches': watches, 'frames': trace}, separators=(',', ':')) + '\n').encode()
    if watches:
        (out / 'ram_trace.json').write_bytes(trace_bytes)
    snes_trace_hash=None
    if args.snes_trace_frames:
        trace_data=(json.dumps({'scope':'CPU opcode and successful direct bus stores; no DMA/MMIO completeness claim',
            'last_opcode_pc_for_writes':True,'frames':snes_trace},separators=(',',':'))+'\n').encode()
        (out/'snes_trace.json').write_bytes(trace_data)
        snes_trace_hash=sha(trace_data)
    controller_hash=None
    if args.snes_controller_journal:
        journal=controller_journal_summary(controller_samples,controller_dropped)
        journal_data=(json.dumps(journal,separators=(',',':'))+'\n').encode()
        (out/'controller_journal.json').write_bytes(journal_data)
        controller_hash=sha(journal_data)
    hardware_hash=None
    if args.snes_hardware_journal:
        journal={'format':'snes-shadowrun-hardware-journal-1',
                 'scope':'all C530 calls from boot; raw reads only are replay inputs; verification fields and modal RAM never gameplay inputs',
                 'read_order':[{'pc':0x80c536,'address':0x2137,'field':'latch'},
                               {'pc':0x80c53c,'address':0x7e1c92,'field':'nmi_low'},
                               {'pc':0x80c542,'address':0x213c,'field':'beam_h'},
                               {'pc':0x80c549,'address':0x7e1c93,'field':'nmi_high'},
                               {'pc':0x80c54f,'address':0x213d,'field':'beam_v'}],
                 'boundary_phase':'increments at every accepted main or modal/controller conversation sample; player samples excluded',
                 'dropped':hardware_dropped,'incomplete_at_end':lib.fdisbull_snes_hardware_busy(),
                 'modal_dropped':hardware_modal_dropped,'samples':hardware_samples,'modals':hardware_modals,
                 'rom_sha256':sha(rom),'core_sha256':core_hash,'controller_journal_sha256':controller_hash}
        raw=(json.dumps(journal,separators=(',',':'))+'\n').encode()
        (out/'hardware_journal.json').write_bytes(raw);hardware_hash=sha(raw)
    if frame[0] is None:
        raise RuntimeError('core produced no video frame')
    raw, width, height, pitch, fmt = frame[0]
    picture, rgb = frame_image(frame[0])
    picture.save(out / 'frame.png')
    lib.retro_get_memory_data.argtypes = [C.c_uint]
    lib.retro_get_memory_data.restype = C.c_void_p
    lib.retro_get_memory_size.argtypes = [C.c_uint]
    lib.retro_get_memory_size.restype = C.c_size_t
    size = lib.retro_get_memory_size(2)
    ptr = lib.retro_get_memory_data(2)
    memory = C.string_at(ptr, size) if ptr and size else b''
    (out / 'system_ram.bin').write_bytes(memory)
    save_size = lib.retro_get_memory_size(0)
    save_ptr = lib.retro_get_memory_data(0)
    save_memory = C.string_at(save_ptr, save_size) if save_ptr and save_size else b''
    if save_memory:
        (out / 'save_ram.bin').write_bytes(save_memory)
    captured_audio = write_audio_capture(out, pcm, av.timing.sample_rate, audio_counts) if args.capture_audio else None
    lib.retro_serialize_size.restype = C.c_size_t
    n = lib.retro_serialize_size()
    lib.retro_serialize.argtypes = [C.c_void_p, C.c_size_t]
    lib.retro_serialize.restype = C.c_bool
    serialized = C.create_string_buffer(n) if n else None
    snapshot = serialized.raw if n and lib.retro_serialize(serialized, n) else b''
    if snapshot:
        (out / 'state.bin').write_bytes(snapshot)
    if sha(core_path.read_bytes()) != core_hash or sha(rom_path.read_bytes()) != sha(rom):
        raise RuntimeError('core or ROM changed during session')
    if args.patches and Path(args.patches).read_bytes() != patch_bytes:
        raise RuntimeError('memory patch input changed during session')
    if args.feedback_policy and Path(args.feedback_policy).read_bytes()!=feedback_bytes:
        raise RuntimeError('feedback policy changed during session')
    receipt = {'input_map': buttons, 'input_descriptors': descriptors, 'watches': watches, 'ram_trace_sha256': sha(trace_bytes) if watches else None, 'system': args.system, 'core_path': str(core_path), 'core_sha256': core_hash, 'core_name': info.library_name.decode(), 'core_version': info.library_version.decode(), 'rom_sha256': sha(rom), 'frames': frames_ran if feedback else args.frames, 'inputs': inputs, 'pixel_format': ['0RGB1555', 'XRGB8888', 'RGB565'][fmt], 'width': width, 'height': height, 'fps': av.timing.fps, 'sample_rate': av.timing.sample_rate, 'frame_rgb_sha256': sha(rgb), 'frame_png_sha256': sha((out / 'frame.png').read_bytes()), 'system_ram_size': size, 'system_ram_sha256': sha(memory), 'system_ram_byte_order': 'raw core bytes; address mapping not validated', 'state_size': len(snapshot), 'state_sha256': sha(snapshot) if snapshot else None, 'core_options': 'defaults; no frontend overrides'}
    receipt.update({'save_ram_size': len(save_memory), 'save_ram_sha256': sha(save_memory) if save_memory else None,
                    'frame_ram':ram_images,
                    'snes_trace_sha256':snes_trace_hash,
                    'snes_controller_journal_sha256':controller_hash,
                    'snes_hardware_journal_sha256':hardware_hash,
                    'snes_checkpoints':{'pc':args.snes_checkpoint_pc,'phase':'before selected opcode at instruction entry; video frame identifies containing retro_run','frames':checkpoints} if checkpoint_frames else None,
                    'snes_checkpoint_digests_only':bool(args.snes_checkpoint_digests),
                    'snes_trace_filters':{'frames':args.snes_trace_frames,'pc':args.snes_trace_pc,'write':args.snes_trace_write} if snes_trace_hash else None,
                    'save_ram_byte_order': 'raw core bytes; address mapping not validated',
                    'audio_capture': captured_audio, 'frame_images': images,
                    'frame_images_phase': 'after retro_run; frame is zero-based',
                    'memory_injection_mode': 'assisted state injection' if patches else 'no memory patches',
                    'patches': patches, 'patches_input_sha256': sha(patch_bytes) if patch_bytes is not None else None,
                    'patches_phase': 'before retro_run; frame is zero-based; list order retained within a frame',
                    'patch_trace': patch_trace,
                    'patch_trace_sha256': sha((json.dumps(patch_trace, separators=(',', ':')) + '\n').encode()) if patches else None})
    if feedback is not None:
        observation_bytes=(json.dumps(feedback.observations,separators=(',',':'))+'\n').encode()
        (out/'feedback_observations.json').write_bytes(observation_bytes)
        receipt['feedback_controller']={'policy':feedback.policy,'policy_sha256':sha(feedback_bytes),
            'result':feedback.result(),'frames_requested':args.frames,
            'observations_sha256':sha(observation_bytes),'observations':len(feedback.observations),
            'callback_masks':masks[:frames_ran],
            'callback_masks_sha256':sha((json.dumps(masks[:frames_ran],separators=(',',':'))+'\n').encode()),
            'requested_images_not_reached':sorted(selected_frames-{x['frame'] for x in images})}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    lib.retro_unload_game()
    lib.retro_deinit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', required=True)
    parser.add_argument('--rom', required=True)
    parser.add_argument('--system', required=True, choices=['nes', 'genesis', 'snes'])
    parser.add_argument('--frames', required=True, type=int)
    parser.add_argument('--inputs', help='Path to a JSON file of start/end exclusive frame ranges and Libretro button names')
    parser.add_argument('--input-map', help='JSON mapping semantic button names to Libretro IDs')
    parser.add_argument('--feedback-policy',help='Finite read-only publication controller policy; incompatible with static inputs or RAM patches')
    parser.add_argument('--watch', help='JSON raw RAM slices: name, offset, length, optional memory_id (0 save RAM or default2 system RAM)')
    parser.add_argument('--patches', help='JSON finite memory writes: frame, memory_id (0 or2), offset, data_hex; applied before the named frame')
    parser.add_argument('--capture-audio', action='store_true', help='Capture actual stereo PCM16 callbacks to audio.wav with audio statistics')
    parser.add_argument('--frame-images', help='Comma-separated zero-based frames to save after retro_run')
    parser.add_argument('--frame-ram', help='At most 64 zero-based frames for private complete system RAM snapshots')
    parser.add_argument('--snes-trace-frames', help='Bounded frame start:exclusive-end (at most 120)')
    parser.add_argument('--snes-trace-pc', help='24-bit opcode address start:exclusive-end')
    parser.add_argument('--snes-trace-write', help='24-bit direct bus write address start:exclusive-end')
    parser.add_argument('--snes-checkpoint-pc',type=lambda x:int(x,0),help='Instruction-entry PC for private WRAM checkpoints; requires matching instrumented core')
    parser.add_argument('--snes-checkpoint-frames',help='At most 6000 checkpoint video frames; more than 128 requires limit 1; each capture uses 128 KiB')
    parser.add_argument('--snes-checkpoint-limit',type=int,default=4,help='At most1..8 checkpoints per video frame; dropped count retained')
    parser.add_argument('--snes-checkpoint-digests',action='store_true',help='Keep checkpoint hashes and metadata without writing private WRAM snapshots')
    parser.add_argument('--snes-controller-journal',action='store_true',help='Observe main-loop held/previous controller words with a compatible core')
    parser.add_argument('--snes-hardware-journal',action='store_true',help='Observe every Shadowrun C530 hardware read with a compatible core; raw journal stays private')
    parser.add_argument('--snes-modal-ram',action='store_true',help='Keep private RAM at every observed modal/conversation input boundary; requires hardware journal')
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.frames <= 10000 or not 0 < args.timeout <= 600:
        parser.error('frames must be 1..10000 and timeout 0..600 seconds')
    try:
        frame_numbers(args.frame_images, args.frames)
        checkpoint_plan(args.snes_checkpoint_pc,args.snes_checkpoint_frames,args.frames,args.snes_checkpoint_limit)
        if args.snes_checkpoint_digests and (args.system!='snes' or args.snes_checkpoint_pc is None or not args.snes_checkpoint_frames):
            raise ValueError('checkpoint digests require SNES checkpoints')
        if args.snes_controller_journal and (args.system!='snes' or args.snes_checkpoint_pc!=0x80962e or not args.snes_checkpoint_frames):
            raise ValueError('controller journal requires SNES 80:962E checkpoints')
        if args.snes_hardware_journal and not args.snes_controller_journal:
            raise ValueError('hardware journal requires SNES controller journal')
        if args.snes_modal_ram and not args.snes_hardware_journal:
            raise ValueError('modal RAM requires hardware journal')
        if len(frame_numbers(args.frame_ram, args.frames)) > 64:
            raise ValueError('at most 64 full RAM snapshots')
    except ValueError as exc:
        parser.error(str(exc))
    output = Path(args.output).resolve()
    if output.exists():
        parser.error('output already exists; choose a fresh directory')
    if any((ancestor / '.git').exists() for ancestor in (output, *output.parents)):
        parser.error('output must be outside a Git checkout')
    if args.worker:
        worker(args)
    else:
        command = [sys.executable, __file__, *sys.argv[1:], '--worker']
        try:
            proc = subprocess.run(command, timeout=args.timeout, capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            raise SystemExit('emulator worker timed out')
        if proc.returncode:
            raise SystemExit(f'emulator worker failed ({proc.returncode}): {proc.stderr[-4000:]}')
        print(Path(args.output).resolve() / 'receipt.json')


if __name__ == '__main__':
    main()
