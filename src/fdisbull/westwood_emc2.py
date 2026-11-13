"""Westwood EMC2 guest processor: file-relative read-only instruction facts.

A generic 19-opcode decoder with edition-specific script-entry convention.
Syscall handlers are deliberately *not* inferred: they differ across games.
No guest execution, native EXE association, UDL/UIL synthesis or behavior parity.
"""
from __future__ import annotations

from hashlib import sha256
import struct

from .processor import DecodedInstruction, Location, ProcessorInfo, Successor
from .westwood_media import parse_emc2

NAMES = ('jmp', 'set_ret_value', 'push_ret_or_pos', 'push', 'push',
         'push_reg', 'push_bp_neg', 'push_bp_add', 'pop_ret_or_pos',
         'pop_reg', 'pop_bp_neg', 'pop_bp_add', 'add_sp', 'sub_sp',
         'sys_call', 'if_not_jmp', 'negate', 'eval', 'set_ret_and_jmp')


class EMC2Processor:
    """An immutable script with source-byte offsets and explicit guest ABI."""

    def __init__(self, program: bytes, *, profile: str, function_index: int = 0):
        if profile not in ('kyrandia1-dos', 'lol1-dos'):
            raise ValueError('select an explicit Westwood game/entry profile')
        self.source = program
        parsed = parse_emc2(program)
        self.metadata = parsed
        self.profile = profile
        self.data_offset = parsed['chunks']['DATA']['offset']
        self.data_length = parsed['chunks']['DATA']['size']
        slots = parsed['entry_slots']
        if type(function_index) is not int or not 0 <= function_index < len(slots):
            raise ValueError('EMC2 function index outside ORDR')
        entry = slots[function_index]
        if entry == 0xffff:
            raise ValueError('EMC2 selected function absent')
        word_delta = 0 if profile == 'kyrandia1-dos' else 1
        if entry+word_delta >= self.data_length//2:
            raise ValueError('EMC2 entry convention exceeds DATA section')
        self.entry_address = self.data_offset+2*(entry+word_delta)
        self.function_index = function_index
        self.info = ProcessorInfo(
            'fdisbull.westwood.emc2', '1',
            f'westwood.emc2.sha256:{parsed["sha256"]}:{profile}',
            'byte', ('decode', 'static_successors'), None)

    def _branch(self, kind: str, target_word: int, evidence: str) -> Successor:
        target_byte=self.data_offset+2*target_word
        if 0 <= target_word < self.data_length//2:
            return Successor(kind, Location(self.info.address_space,target_byte),evidence)
        return Successor(kind,None,evidence+f'; target word {target_word} outside DATA section')

    def decode(self, program: bytes, location: Location):
        if program is not self.source or location.space != self.info.address_space:
            raise ValueError('EMC2 source/program binding changed')
        pos=location.offset
        if (pos<self.data_offset or pos>=self.data_offset+self.data_length
                or (pos-self.data_offset)%2):
            return None
        word=struct.unpack_from('>H',program,pos)[0]
        op=(word>>8)&31
        param=0; size=2; imm_kind='none'
        if word & 0x8000:
            op=0;param=word&0x7fff;imm_kind='jump_word'
        elif word & 0x4000:
            param=struct.unpack('b',program[pos+1:pos+2])[0]
            imm_kind='signed_byte'
        elif word & 0x2000:
            if pos+4>self.data_offset+self.data_length:
                raise ValueError('EMC2 truncated long operand')
            param=struct.unpack_from('>h',program,pos+2)[0]
            size=4;imm_kind='signed_word'
        if op>=len(NAMES):
            raise ValueError('EMC2 unknown core opcode')
        following=pos+size
        facts=dict(mnemonic=NAMES[op], opcode=op, parameter=param,
                   immediate_kind=imm_kind, flow='next', size=size,
                   bytes=program[pos:pos+size].hex(),
                   word_offset=(pos-self.data_offset)//2,
                   syscall_id=(param & 255 if op==14 else None),
                   syscall_behavior='unbound_game_specific' if op==14 else None)
        if op==0:
            facts['flow']='jump'
            edges=(self._branch('branch',param,'direct EMC2 word-offset jump'),)
        elif op==15:
            facts['flow']='conditional'
            target=param & 0x7fff
            edges=(self._branch('branch',target,'if-not-jump candidate; condition requires stack'),
                   self._branch('fallthrough',(following-self.data_offset)//2,'condition true continuation'))
        elif op==18 or (op==8 and param!=0):
            facts['flow']='return'
            edges=(Successor('return',None,'stack-dependent return/transfer; caller continuation unresolved'),)
        else:
            edges=(self._branch('fallthrough',(following-self.data_offset)//2,'sequential script word'),)
        return DecodedInstruction(location,facts,edges)
