"""Bounded two-game mapper-225 packer for compatible authored NROM images.

The selected program must not write $8000-$ffff and must not need cartridge
RAM: unlike NROM, mapper 225 interprets those writes as bank selection. The
caller is responsible for attesting authorship and this behavioral constraint.
"""
from __future__ import annotations
import hashlib
import json
import os
import stat
from pathlib import Path
import shutil
import tempfile

from .console_udc import _private_directory


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _read_bounded(path, limit, *, exact=None):
    """Read one stable regular file without allocating beyond limit + 1."""
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > limit or
                (exact is not None and before.st_size != exact)):
            raise ValueError('Input is not a regular file of an accepted size')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(fd)
        def identity(st):
            return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        current = path.stat(follow_symlinks=False)
        if (len(raw) > limit or len(raw) != before.st_size or
                identity(before) != identity(after) or identity(after) != identity(current)):
            raise ValueError('Input changed during reading')
        return raw, identity(after)
    finally:
        os.close(fd)


class _Code:
    def __init__(self):
        self.data = bytearray(); self.labels = {}; self.fixups = []
    def emit(self, *data): self.data.extend(data)
    def label(self, name): self.labels[name] = 0x8000 + len(self.data)
    def absolute(self, op, name):
        self.emit(op, 0, 0); self.fixups.append((len(self.data)-2, name, False))
    def branch(self, op, name):
        self.emit(op, 0); self.fixups.append((len(self.data)-1, name, True))
    def finish(self):
        for pos, name, branch in self.fixups:
            target = self.labels[name]
            if branch:
                d = target - (0x8000+pos+1)
                if not -128 <= d <= 127: raise ValueError('menu branch out of range')
                self.data[pos] = d & 255
            else:
                self.data[pos:pos+2] = target.to_bytes(2, 'little')
        return bytes(self.data)


def _menu(mirroring):
    # A/B selection uses the ordinary serial controller.  Switching banks
    # happens from internal RAM so the next opcode is not fetched from the
    # newly selected game at the menu's former PC.
    a = _Code(); a.label('reset')
    # Reset may leave the previously selected CHR bank latched. Restore menu
    # PRG and CHR explicitly before touching PPU output.
    a.emit(0x78,0xd8,0xa9,0,0x8d,0x00,0x80,0xa2,0xff,0x9a,0xe8,0x8e,0x00,0x20,0x8e,0x01,0x20)
    a.label('vblank'); a.emit(0x2c,0x02,0x20); a.branch(0x10,'vblank')
    a.emit(0xa9,0x3f,0x8d,0x06,0x20,0xa9,0x00,0x8d,0x06,0x20,
           0xa9,0x0f,0x8d,0x07,0x20,0xa9,0x30,0x8d,0x07,0x20)
    a.emit(0xa9,0x21,0x8d,0x06,0x20,0xa9,0x46,0x8d,0x06,0x20)
    a.emit(0xa2,0x00); a.label('textloop'); a.absolute(0xbd,'text');a.emit(0x8d,0x07,0x20,0xe8,0xe0,0x1b);a.branch(0xd0,'textloop')
    a.emit(0xa9,0,0x8d,0x05,0x20,0x8d,0x05,0x20,0xa9,0x1e,0x8d,0x01,0x20)
    a.label('poll'); a.emit(0xa9,1,0x8d,0x16,0x40,0xa9,0,0x8d,0x16,0x40,
                            0xad,0x16,0x40,0x29,1);a.branch(0xd0,'select1')
    a.emit(0xad,0x16,0x40,0x29,1);a.branch(0xd0,'select2');a.absolute(0x4c,'poll')
    for idx in (1,2):
        a.label('select'+str(idx))
        # Require both selection buttons to be released before entering a game.
        # This prevents the menu action becoming the game's first A/B input.
        a.label('release'+str(idx));a.emit(0xa9,1,0x8d,0x16,0x40,0xa9,0,0x8d,0x16,0x40,
              0xad,0x16,0x40,0x29,1);a.branch(0xd0,'release'+str(idx))
        a.emit(0xad,0x16,0x40,0x29,1);a.branch(0xd0,'release'+str(idx))
        a.emit(0x78,0xa9,0,0x8d,0,0x20,0x8d,1,0x20,0xa2,0)
        a.label('copy'+str(idx));a.absolute(0xbd,'trampoline'+str(idx));a.emit(0x9d,0x00,0x02,0xe8,0xe0,8);a.branch(0xd0,'copy'+str(idx));a.emit(0x4c,0,2)
    a.label('text'); a.data.extend(b'A GAME 1   B GAME 2        ')
    # A13 chooses horizontal mirroring in this mapper.
    for idx in (1,2):
        address = 0x8000 | (0x2000 if mirroring == 'horizontal' else 0) | (idx << 7) | idx
        a.label('trampoline'+str(idx)); a.emit(0xa9,0,0x8d,address&255,address>>8,0x6c,0xfc,0xff)
    raw=a.finish()
    if len(raw)>0x7ffa: raise ValueError('menu exceeds one bank')
    return raw + bytes(0x7ffa-len(raw)) + b'\x00\x80'*3


def _menu_chr():
    # ASCII indexed 8x8 bitmap tiles; a compact original bitmap alphabet.
    glyphs={'A':['01110','10001','10001','11111','10001','10001','10001'],
            'B':['11110','10001','10001','11110','10001','10001','11110'],
            'G':['01111','10000','10000','10111','10001','10001','01111'],
            'M':['10001','11011','10101','10101','10001','10001','10001'],
            'E':['11111','10000','10000','11110','10000','10000','11111'],
            '1':['00100','01100','00100','00100','00100','00100','01110'],
            '2':['01110','10001','00001','00010','00100','01000','11111']}
    raw=bytearray(8192)
    for char, rows in glyphs.items():
        for y,row in enumerate(rows): raw[ord(char)*16+y]=int(row,2)<<2
    return bytes(raw)


def _nrom(raw):
    if len(raw)!=16+32768+8192 or raw[:4]!=b'NES\x1a' or raw[4:6]!=b'\x02\x01':
        raise ValueError('Expected iNES 32 KiB PRG + 8 KiB CHR-ROM NROM')
    h=raw[:16]
    if h[6]&0xfe or h[7] or any(h[8:]):
        raise ValueError('Only mapper 0 without trainer, battery, four-screen, NES2 or other extensions is supported')
    return {'mirroring':'vertical' if h[6]&1 else 'horizontal', 'prg':raw[16:32784], 'chr':raw[32784:]}


def build_multicart(inputs, *, output, authored_compatible=False):
    """Build exactly two caller-attested compatible authored ROMs privately."""
    if authored_compatible is not True: raise ValueError('Caller must attest authored compatible inputs')
    if not isinstance(inputs,(tuple,list)) or len(inputs)!=2: raise ValueError('Exactly two input games are required')
    paths=[Path(p).expanduser().resolve() for p in inputs]
    if len(set(paths)) != 2: raise ValueError('Input paths must differ')
    captures=[_read_bounded(p,40976,exact=40976) for p in paths]
    originals=[raw for raw, _ in captures]; games=[_nrom(b) for b in originals]
    if games[0]['mirroring']!=games[1]['mirroring']: raise ValueError('Input mirroring must match')
    mirr=games[0]['mirroring']; destination=_private_directory(output)
    header=b'NES\x1a'+bytes([8,4,0x10,0xe0])+bytes(8)
    image=header+_menu(mirr)+b''.join(x['prg'] for x in games)+bytes(32768)+_menu_chr()+b''.join(x['chr'] for x in games)+bytes(8192)
    manifest={'format':'fdisbull-nes-multicart-1','mapper':225,'selection':'A: game 1; B: game 2; reset behavior is hardware-dependent',
              'inputs':[{'sha256':_sha(b),'size':len(b)} for b in originals], 'mirroring':mirr,
              'rom_sha256':_sha(image),'rom_size':len(image),'games':2,'caller_attested_authored_and_mapper_compatible':True,
              'limitations':['No PRG-ROM writes or cartridge RAM use by games','NROM 32 KiB PRG and 8 KiB CHR-ROM only','Individual game compatibility requires runtime qualification']}
    temp=Path(tempfile.mkdtemp(prefix='.nes-multicart-',dir=destination.parent))
    try:
        (temp/'program.nes').write_bytes(image)
        (temp/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if any(_read_bounded(p,40976,exact=40976)!=capture for p,capture in zip(paths,captures)): raise ValueError('Input changed during compilation')
        if destination.exists(): raise ValueError('Output appeared during compilation')
        temp.rename(destination)
    except BaseException:
        shutil.rmtree(temp,ignore_errors=True);raise
    return manifest


def multicart_profiles():
    return {'format':'fdisbull-nes-multicart-profiles-1', 'profiles':[{'id':'mapper225-authored-nrom-two-game-1',
      'target_mapper':225,'game_count':2,'input_mapper':0,'prg_bytes':32768,'chr_bytes':8192,
      'purpose':'packaging already generated authored games, not game lifting',
      'caller_attestation':'authored, no PRG-ROM writes, no cartridge RAM',
      'reset':'FCEUmm core reset returned to menu in bounded test; physical hardware unverified'}]}


def inspect_multicart_path(path):
    """Inspect a bounded iNES cartridge header; no title or count inference."""
    source=Path(path).expanduser().resolve()
    raw, identity = _read_bounded(source,8*1024*1024)
    if len(raw)<16 or raw[:4]!=b'NES\x1a': raise ValueError('Expected iNES header')
    h=raw[:16]
    if h[7]&12==8: raise ValueError('NES 2.0 inspection is not implemented')
    trainer=512 if h[6]&4 else 0
    expected=16+trainer+16384*h[4]+8192*h[5]
    if expected!=len(raw): raise ValueError('iNES image length does not match header')
    if _read_bounded(source,8*1024*1024)!=(raw,identity): raise ValueError('Input changed during inspection')
    return {'format':'fdisbull-nes-cartridge-inspection-1','sha256':_sha(raw),'size':len(raw),
            'mapper':(h[7]&0xf0)|(h[6]>>4),'prg_rom_bytes':h[4]*16384,
            'chr_rom_bytes':h[5]*8192,'chr_ram':h[5]==0,'trainer':bool(trainer),
            'mirroring':'four-screen' if h[6]&8 else 'vertical' if h[6]&1 else 'horizontal',
            'unique_game_count':'unknown','menu_entries':'not analyzed',
            'scope':'header/container facts; not gameplay, title or uniqueness validation'}
