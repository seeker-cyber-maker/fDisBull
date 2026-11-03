"""Strict CHIP-8 family classification; independent table and branch oracles.

A recognized opcode is NOT evidence that an arbitrary ROM word is reachable code.
SCHIP/XO extensions are classified but not executed by the minimal VM.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Instruction:
    word: int
    family: str
    tier: str
    size: int = 2

    @property
    def x(self): return (self.word >> 8) & 0xF
    @property
    def y(self): return (self.word >> 4) & 0xF
    @property
    def kk(self): return self.word & 0xFF
    @property
    def nnn(self): return self.word & 0xFFF
    @property
    def n(self): return self.word & 0xF

# mask, value, family. Specific patterns override less specific classes.
CLASSIC = [
    (0xFFFF, 0x00E0, 'CLS'), (0xFFFF, 0x00EE, 'RET'),
    (0xF000, 0x0000, 'SYS'),
    (0xF000, 0x1000, 'JP'), (0xF000, 0x2000, 'CALL'),
    (0xF000, 0x3000, 'SE_VX_KK'), (0xF000, 0x4000, 'SNE_VX_KK'),
    (0xF00F, 0x5000, 'SE_VX_VY'),
    (0xF000, 0x6000, 'LD_VX_KK'), (0xF000, 0x7000, 'ADD_VX_KK'),
    (0xF00F, 0x8000, 'LD_VX_VY'), (0xF00F, 0x8001, 'OR'),
    (0xF00F, 0x8002, 'AND'), (0xF00F, 0x8003, 'XOR'),
    (0xF00F, 0x8004, 'ADD_VX_VY'), (0xF00F, 0x8005, 'SUB'),
    (0xF00F, 0x8006, 'SHR'), (0xF00F, 0x8007, 'SUBN'),
    (0xF00F, 0x800E, 'SHL'),
    (0xF00F, 0x9000, 'SNE_VX_VY'),
    (0xF000, 0xA000, 'LD_I'), (0xF000, 0xB000, 'JP_V0'),
    (0xF000, 0xC000, 'RND'), (0xF000, 0xD000, 'DRW'),
    (0xF0FF, 0xE09E, 'SKP'), (0xF0FF, 0xE0A1, 'SKNP'),
    (0xF0FF, 0xF007, 'LD_VX_DT'), (0xF0FF, 0xF00A, 'WAIT_KEY'),
    (0xF0FF, 0xF015, 'LD_DT_VX'), (0xF0FF, 0xF018, 'LD_ST_VX'),
    (0xF0FF, 0xF01E, 'ADD_I_VX'), (0xF0FF, 0xF029, 'FONT'),
    (0xF0FF, 0xF033, 'BCD'), (0xF0FF, 0xF055, 'SAVE'),
    (0xF0FF, 0xF065, 'LOAD'),
]
SCHIP = [
    (0xFFF0, 0x00C0, 'SCR_DOWN'),
    (0xFFFF, 0x00FB, 'SCR_RIGHT'), (0xFFFF, 0x00FC, 'SCR_LEFT'),
    (0xFFFF, 0x00FD, 'EXIT'), (0xFFFF, 0x00FE, 'LOW_RES'),
    (0xFFFF, 0x00FF, 'HIGH_RES'),
    (0xF0FF, 0xF030, 'BIG_FONT'),
    (0xF0FF, 0xF075, 'SAVE_FLAGS'), (0xF0FF, 0xF085, 'LOAD_FLAGS'),
]
XO = [
    (0xFFFF, 0xF000, 'LONG_I'), # 4-byte word followed by a 16-bit address
    (0xFFF0, 0x00D0, 'SCR_UP'),
    (0xF00F, 0x5002, 'RANGE_SAVE'), (0xF00F, 0x5003, 'RANGE_LOAD'),
    (0xF0FF, 0xF001, 'PLANE'), (0xF0FF, 0xF002, 'AUDIO'),
    (0xF0FF, 0xF03A, 'AUDIO_PITCH'),
]
PROFILES = ('chip8', 'schip', 'xo')

def patterns(profile):
    if profile not in PROFILES: raise ValueError('unknown CHIP-8 dialect')
    entries = [(m, v, name, 'classic' if name != 'SYS' else 'legacy') for m, v, name in CLASSIC]
    if profile in ('schip', 'xo'):
        entries += [(m, v, name, 'schip') for m, v, name in SCHIP]
    if profile == 'xo':
        entries += [(m, v, name, 'xo') for m, v, name in XO]
    return sorted(entries, key=lambda x: (-x[0].bit_count(), x[2]))

def decode_table(word, profile='chip8'):
    if not (0 <= word <= 0xffff): raise ValueError('one unsigned word required')
    for mask, value, family, tier in patterns(profile):
        if (word & mask) == value:
            return Instruction(word, family, tier, 4 if family == 'LONG_I' else 2)
    return Instruction(word, 'INVALID', 'invalid')

def decode_branches(word, profile='chip8'):
    """Separate case-structure oracle, deliberately not using table/masks."""
    if profile not in PROFILES or not (0 <= word < 65536): raise ValueError('bad request')
    a = word >> 12; x = (word >> 8) & 15; y = (word >> 4) & 15
    low = word & 15; kk = word & 255
    fam = 'INVALID'; tier = 'invalid'
    if a == 0:
        fam = 'CLS' if word == 0xe0 else 'RET' if word == 0xee else 'SYS'
    elif a == 1: fam = 'JP'
    elif a == 2: fam = 'CALL'
    elif a == 3: fam = 'SE_VX_KK'
    elif a == 4: fam = 'SNE_VX_KK'
    elif a == 5:
        if low == 0: fam = 'SE_VX_VY'
    elif a == 6: fam = 'LD_VX_KK'
    elif a == 7: fam = 'ADD_VX_KK'
    elif a == 8:
        fam = {0:'LD_VX_VY',1:'OR',2:'AND',3:'XOR',4:'ADD_VX_VY',5:'SUB',6:'SHR',7:'SUBN',14:'SHL'}.get(low,'INVALID')
    elif a == 9:
        if low == 0: fam = 'SNE_VX_VY'
    elif a == 10: fam = 'LD_I'
    elif a == 11: fam = 'JP_V0'
    elif a == 12: fam = 'RND'
    elif a == 13: fam = 'DRW'
    elif a == 14:
        fam = {0x9e:'SKP',0xa1:'SKNP'}.get(kk,'INVALID')
    elif a == 15:
        fam = {7:'LD_VX_DT',10:'WAIT_KEY',21:'LD_DT_VX',24:'LD_ST_VX',30:'ADD_I_VX',
               41:'FONT',51:'BCD',85:'SAVE',101:'LOAD'}.get(kk,'INVALID')
    if fam != 'INVALID': tier = 'legacy' if fam == 'SYS' else 'classic'
    if profile in ('schip','xo'):
        if a == 0 and y == 0xc and x == 0: fam, tier = 'SCR_DOWN','schip'
        elif word in {0xfb,0xfc,0xfd,0xfe,0xff}:
            fam, tier = {0xfb:'SCR_RIGHT',0xfc:'SCR_LEFT',0xfd:'EXIT',0xfe:'LOW_RES',0xff:'HIGH_RES'}[word],'schip'
        elif a == 15 and kk in (0x30,0x75,0x85):
            fam, tier = {0x30:'BIG_FONT',0x75:'SAVE_FLAGS',0x85:'LOAD_FLAGS'}[kk],'schip'
    if profile == 'xo':
        if word == 0xf000: fam, tier = 'LONG_I','xo'
        elif a == 0 and x == 0 and y == 0xd: fam, tier = 'SCR_UP','xo'
        elif a == 5 and low in (2,3): fam, tier = {2:'RANGE_SAVE',3:'RANGE_LOAD'}[low],'xo'
        elif a == 15 and kk in (1,2,0x3a):
            fam, tier = {1:'PLANE',2:'AUDIO',0x3a:'AUDIO_PITCH'}[kk],'xo'
    return Instruction(word,fam,tier,4 if fam == 'LONG_I' else 2)

def validate_rules():
    # No two same-tier patterns may shadow one another except the intentional SYS envelope.
    for profile in PROFILES:
        p = patterns(profile)
        for i,(m1,v1,n1,t1) in enumerate(p):
            for m2,v2,n2,t2 in p[i+1:]:
                if ((v1 ^ v2) & (m1 & m2)) == 0 and not (n1 == 'SYS' or n2 == 'SYS'):
                    raise AssertionError(f'overlapping {profile} patterns: {n1} and {n2}')