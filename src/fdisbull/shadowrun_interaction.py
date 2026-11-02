"""Exact-profile lift of the original Stoker sign resource selection."""
from __future__ import annotations
import hashlib
from pathlib import Path
from .game_il import author_program

ROM_SHA256='92a614491fc3ea12a6df32459cce08b48574b7b814e244c07eb860dc5c6edb7e'
BRANCH_SHA256='cd4dee0efd5f235cc7fa49bfd69fc8da37e6de0be3e2644c68325b1d33ed8fcf'
TRANSITION_SHA256='5f0ec34ae1a08c47904481f5388ce1fc7113dd523c85074242f00df75f06ef67'
REQUEST_GUARD_SHA256='a10a7f731be4ae696fd1c1474f85e1dbd1733d2da133ce78b8de7f480e44905a'
GATE_SHA256='70022fdfa3d4981bb5c53abf3c7df02eece2cb558bde43f97f473a23e10b665f'
EVENT_SHA256='17facf5e4d703729c8dac49f1f97802141d467a586eb75202de06bc5a01bef7c'
SELECTOR_SHA256='c3fe3559b339cd9a938833904d017d05cee91615ef5552702e793c8a483b4152'
SOURCE=Path(__file__).parent/'game_sources'/'shadowrun_interaction.c'


def lift_stoker_interaction(rom):
    if len(rom)!=2097152 or hashlib.sha256(rom).hexdigest()!=ROM_SHA256:
        raise ValueError('Shadowrun interaction requires the exact reviewed source ROM')
    if hashlib.sha256(rom[0x1f71e:0x1f770]).hexdigest()!=SELECTOR_SHA256:
        raise ValueError('Shadowrun selector source changed')
    if hashlib.sha256(rom[0xb858:0xb866]).hexdigest()!=EVENT_SHA256:
        raise ValueError('Shadowrun event projection source changed')
    if hashlib.sha256(rom[0xb7fa:0xb834]).hexdigest()!=GATE_SHA256:
        raise ValueError('Shadowrun collision gate source changed')
    for lo,hi,digest in ((0xba3a,0xba7c,BRANCH_SHA256),(0xba82,0xbaa2,TRANSITION_SHA256),(0xb7b8,0xb7fa,REQUEST_GUARD_SHA256)):
        if hashlib.sha256(rom[lo:hi]).hexdigest()!=digest:
            raise ValueError('Shadowrun request source changed')
    raw=SOURCE.read_bytes()
    evidence={'kind':'source-bound-reviewed-procedural-slice','source_sha256':ROM_SHA256,
      'source_range':[0x1f71e,0x1f770],'source_range_sha256':SELECTOR_SHA256,
      'event_source_range':[0xb858,0xb866],'event_source_sha256':EVENT_SHA256,
      'gate_source_range':[0xb7fa,0xb834],'gate_source_sha256':GATE_SHA256,
      'branch_source_range':[0xba3a,0xba7c],'branch_source_sha256':BRANCH_SHA256,
      'transition_source_range':[0xba82,0xbaa2],'transition_source_sha256':TRANSITION_SHA256,
      'request_guard_source_range':[0xb7b8,0xb7fa],'request_guard_source_sha256':REQUEST_GUARD_SHA256,
      'authoring_sha256':hashlib.sha256(raw).hexdigest(),
      'scope':'bounded source branches and Stoker request; dispatch side effects excluded; A-B-A UI is a target projection'}
    result=author_program(raw.decode(),evidence=evidence)
    if SOURCE.read_bytes()!=raw:raise ValueError('Shadowrun interaction source changed during capture')
    return result
