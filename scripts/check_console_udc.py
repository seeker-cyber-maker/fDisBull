#!/usr/bin/env python3
"""Run a bounded Libretro session in a disposable process; ROMs stay external."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image


def sha(data):
    return hashlib.sha256(data).hexdigest()


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
    buttons = {'UP': 4, 'DOWN': 5, 'LEFT': 6, 'RIGHT': 7, 'START': 3, 'B': 0}
    buttons.update({'A': 8, 'SELECT': 2} if args.system == 'nes' else {'A': 1, 'C': 8})
    if args.input_map:
        buttons = {k.upper(): v for k, v in json.loads(Path(args.input_map).read_text()).items()}
    if any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v < 16 for v in buttons.values()):
        raise ValueError('input-map IDs must be integers from 0 through 15')
    watches = json.loads(Path(args.watch).read_text()) if args.watch else []
    if not isinstance(watches, list) or len(watches) > 64:
        raise ValueError('watch must be a list of up to 64 raw RAM slices')
    for watch in watches:
        if not isinstance(watch.get('name'), str) or not isinstance(watch.get('offset'), int) or not isinstance(watch.get('length'), int) or watch['offset'] < 0 or not 1 <= watch['length'] <= 1024:
            raise ValueError('watch entries require name, nonnegative offset and length 1..1024')
    if len({w['name'] for w in watches}) != len(watches):
        raise ValueError('watch names must be unique')
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
        pass
    @BATCH
    def batch(data, frames):
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
    trace = []
    for i in range(args.frames):
        current[0] = i
        lib.retro_run()
        if watches:
            size_now = lib.retro_get_memory_size(2)
            ptr_now = lib.retro_get_memory_data(2)
            if not ptr_now or any(w['offset'] + w['length'] > size_now for w in watches):
                raise ValueError('watch slice is outside available system RAM')
            trace.append({'frame': i, 'input_mask': masks[i], 'raw': {w['name']: C.string_at(ptr_now + w['offset'], w['length']).hex() for w in watches}})
    trace_bytes = (json.dumps({'phase': 'after retro_run; frame is zero-based', 'watches': watches, 'frames': trace}, separators=(',', ':')) + '\n').encode()
    if watches:
        (out / 'ram_trace.json').write_bytes(trace_bytes)
    if frame[0] is None:
        raise RuntimeError('core produced no video frame')
    raw, width, height, pitch, fmt = frame[0]
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
    Image.frombytes('RGB', (width, height), bytes(rgb)).save(out / 'frame.png')
    lib.retro_get_memory_data.argtypes = [C.c_uint]
    lib.retro_get_memory_data.restype = C.c_void_p
    lib.retro_get_memory_size.argtypes = [C.c_uint]
    lib.retro_get_memory_size.restype = C.c_size_t
    size = lib.retro_get_memory_size(2)
    ptr = lib.retro_get_memory_data(2)
    memory = C.string_at(ptr, size) if ptr and size else b''
    (out / 'system_ram.bin').write_bytes(memory)
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
    receipt = {'input_map': buttons, 'input_descriptors': descriptors, 'watches': watches, 'ram_trace_sha256': sha(trace_bytes) if watches else None, 'system': args.system, 'core_path': str(core_path), 'core_sha256': core_hash, 'core_name': info.library_name.decode(), 'core_version': info.library_version.decode(), 'rom_sha256': sha(rom), 'frames': args.frames, 'inputs': inputs, 'pixel_format': ['0RGB1555', 'XRGB8888', 'RGB565'][fmt], 'width': width, 'height': height, 'fps': av.timing.fps, 'sample_rate': av.timing.sample_rate, 'frame_rgb_sha256': sha(rgb), 'frame_png_sha256': sha((out / 'frame.png').read_bytes()), 'system_ram_size': size, 'system_ram_sha256': sha(memory), 'system_ram_byte_order': 'raw core bytes; address mapping not validated', 'state_size': len(snapshot), 'state_sha256': sha(snapshot) if snapshot else None, 'core_options': 'defaults; no frontend overrides'}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    lib.retro_unload_game()
    lib.retro_deinit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', required=True)
    parser.add_argument('--rom', required=True)
    parser.add_argument('--system', required=True, choices=['nes', 'genesis'])
    parser.add_argument('--frames', required=True, type=int)
    parser.add_argument('--inputs', help='JSON list of start/end exclusive frame ranges and Libretro button names')
    parser.add_argument('--input-map', help='JSON mapping semantic button names to Libretro IDs')
    parser.add_argument('--watch', help='JSON list of raw RAM slices: name, offset, length')
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.frames <= 10000 or not 0 < args.timeout <= 600:
        parser.error('frames must be 1..10000 and timeout 0..600 seconds')
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
