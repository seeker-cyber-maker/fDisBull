"""Source-bound MADS conversation instruction decoder, not a complete MADS VM.

This processor handles the actual CNV conversation bytecode. Native scene code
still belongs to x86/RTLink. No arithmetic, host callback or gameplay equivalence
is inferred from successful decoding. See docs/MADS_PROCESSOR.md for references.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import struct

from .decoder_modules import DecoderModuleInfo, capture_input
from .mads_resources import (Cursor, HagArchive, MadsPack, bounded_int, require,
                             snapshot, MAX_ARCHIVE)
from .processor import DecodedInstruction, Location, ProcessorInfo, Successor

MODULE = 'fdisbull.mads.conversation'
PROFILE = 'mads-cnv-v1'
# Neutral spellings for command 1 and the conditional operations retain the
# encoded IDs. Upstream symbolic names do not establish original semantics.
COMMANDS = {0: 'end', 1: 'entry_flags_1', 2: 'hide', 3: 'unhide',
            4: 'message_1', 5: 'message_2', 6: 'error', 7: 'node',
            8: 'goto', 9: 'assign', 255: 'dialog_end'}


def _expression(reader):
    code = reader.u16()
    require(code in (*range(14), 255), f'unknown MADS expression operation {code}')
    operands = []
    for _ in range(0 if code == 255 else 1 if code == 0 else 2):
        flag, value = reader.u8(), reader.s16()
        operands.append(dict(kind='variable' if flag else 'immediate', value=value, encoded_flag=flag))
    return dict(operation=code, operands=operands, evaluated=False)


def _instruction(program, at, end):
    reader = Cursor(program, at, end)
    command = reader.u8()
    require(command in COMMANDS, f'unknown MADS conversation opcode {command} at {at}')
    count = 0 if command == 6 else 3 if command == 7 else 2 if command == 9 else 1
    conditions = [_expression(reader) for _ in range(count)]
    parameters = {}
    if command in (1, 2, 3):
        parameters['entry_ids'] = [reader.s16() for _ in range(reader.u8())]
    elif command in (4, 5):
        message_count, speech_count = reader.u8(), reader.u8()
        weights = [reader.u8() for _ in range(message_count)]
        messages = [reader.u16() for _ in range(message_count)]
        parameters['weighted_messages'] = [dict(weight=w, message_id=m) for w, m in zip(weights, messages)]
        parameters['speech_ids'] = [reader.u16() for _ in range(speech_count)]
    elif command in (8, 9):
        parameters['target_offset' if command == 8 else 'variable_index'] = reader.u16()
    size = reader.at-at
    reads = sorted({p['value'] for c in conditions for p in c['operands'] if p['kind'] == 'variable'})
    return dict(address=at, size=size, bytes=program[at:reader.at].hex(),
                mnemonic=COMMANDS[command], opcode=command, conditions=conditions,
                parameters=parameters, variable_reads=reads,
                variable_writes=[parameters['variable_index']] if command == 9 else [],
                qualification='encoded_instruction_facts_only')


@dataclass(frozen=True)
class Conversation:
    pack: MadsPack
    counts: tuple[int, ...]
    dialogs: tuple[tuple[int, int, int, int], ...]
    nodes: tuple[tuple[int, int, int, int, int], ...]

    @classmethod
    def read(cls, source):
        pack = MadsPack.read(source)
        require(len(pack.sections) == 7, 'CNV requires seven MADSPACK sections')
        header = pack.sections[0].data
        require(len(header) >= 126, 'CNV header truncated')
        counts = struct.unpack_from('<7H', header)
        nodes, dialogs, messages, lines, unknown, imports, speakers = counts
        require(speakers <= 5, 'CNV speaker count exceeds profile')
        text_size, commands_size = struct.unpack_from('<II', header, 118)
        require(commands_size <= 65536, 'CNV code exceeds 16-bit byte offsets')
        for i, size in enumerate((nodes*10, dialogs*8, messages*4, lines*2, text_size, commands_size), 1):
            require(len(pack.sections[i].data) == size, f'CNV section {i} size/count mismatch')
        dialog_rows = tuple(struct.iter_unpack('<hhHH', pack.sections[2].data))
        node_rows = tuple(struct.iter_unpack('<HHhhh', pack.sections[1].data))
        for text, speech, at, size in dialog_rows:
            require(at <= commands_size and size <= commands_size-at, 'CNV dialog outside command section')
            require(text == -1 or 0 <= text < lines, 'CNV dialog text index outside section')
        for start, count, _, _, _ in node_rows:
            require(start <= dialogs and count <= dialogs-start, 'CNV node dialog range outside table')
        for start, count in struct.iter_unpack('<HH', pack.sections[3].data):
            require(start <= lines and count <= lines-start, 'CNV message text range outside table')
        offsets = [item[0] for item in struct.iter_unpack('<H', pack.sections[4].data)]
        require(all(a <= b for a, b in zip(offsets, offsets[1:])), 'CNV text offsets not monotone')
        require(all(offset < text_size for offset in offsets), 'CNV text offset outside text section')
        return cls(pack, counts, dialog_rows, node_rows)

    @property
    def program(self):
        return self.pack.sections[6].data

    def metadata(self):
        return dict(format=PROFILE, source_sha256=sha256(self.pack.source).hexdigest(),
                    counts=dict(zip(('nodes', 'dialogs', 'messages', 'text_lines', 'unknown_word',
                                     'max_imports', 'speakers'), self.counts)),
                    dialogs=[dict(index=i, text_index=t, speech_index=v, offset=a, size=n)
                             for i, (t, v, a, n) in enumerate(self.dialogs)],
                    nodes=[dict(index=i, first_dialog=a, dialog_count=n, unknown_1=u,
                                active_raw=active, unknown_3=w)
                           for i, (a, n, u, active, w) in enumerate(self.nodes)],
                    command_sha256=sha256(self.program).hexdigest(), pack=self.pack.metadata(),
                    native_scene_code_decoded=False, runtime_execution=False)


class MADSConversationProcessor:
    """A byte-addressed, source-pinned decoder for ONE explicit dialog slice."""
    def __init__(self, conversation, function_index=0):
        require(isinstance(conversation, Conversation), 'expected parsed MADS conversation')
        bounded_int(function_index, 'dialog index', 0, len(conversation.dialogs)-1)
        _, _, start, length = conversation.dialogs[function_index]
        require(length > 0, 'selected dialog has no encoded script')
        self._program = conversation.program
        self._start, self._end = start, start+length
        self._rows = {}
        at = start
        # Decode only the selected declared range. Never scan unrelated resources
        # for possible opcodes or follow an operand as if it were code.
        while at < self._end:
            row = _instruction(self._program, at, self._end)
            self._rows[at] = row
            at += row['size']
        self.entry_address = start
        self.source_hash = sha256(conversation.pack.source).hexdigest()
        self.function_index = function_index
        self.info = ProcessorInfo(MODULE, '1',
            f'mads.cnv.sha256:{self.source_hash}:section:6:dialog:{function_index}',
            'byte', ('decode', 'static_successors'), None)

    def decode(self, program, location):
        require(program is self._program, 'MADS processor requires its captured command bytes')
        require(isinstance(location, Location) and location.space == self.info.address_space,
                'wrong MADS source address space')
        require(location.offset in self._rows, 'not an instruction boundary in the selected dialog')
        row = deepcopy(self._rows[location.offset])
        command = row['opcode']
        following = location.offset + row['size']
        edges = []
        if command == 8:
            target = row['parameters']['target_offset']
            target_location = Location(location.space, target) if target in self._rows else None
            edges.append(Successor('branch', target_location,
                         f'encoded conditional GOTO to section-6 byte {target}; predicate not evaluated'
                         + ('' if target_location else '; outside dialog or not an instruction boundary')))
        if command in (0, 6):
            row['flow'] = 'stop'
            edges.append(Successor('return', None, 'END/error terminates this modeled script; no host address inferred'))
        elif command == 255:
            row['flow'] = 'opaque'
            edges.append(Successor('engine_control', None, 'DIALOG_END execution semantics not qualified'))
        else:
            row['flow'] = 'conditional' if command in (7, 8) else 'next'
            if command == 7:
                edges.append(Successor('return', None, 'NODE can finish the current script; host continuation unbound'))
            if following in self._rows:
                edges.append(Successor('fallthrough', Location(location.space, following),
                                       'encoded next command; conditions and engine effects not evaluated'))
            elif following == self._end:
                edges.append(Successor('return', None, 'declared dialog script range exhausted'))
        row.update(dialog_index=self.function_index, dialog_relative_offset=location.offset-self._start,
                   address_domain='decompressed CNV section 6 bytes, not EXE/file/runtime addresses')
        return DecodedInstruction(location, row, tuple(edges))


class MADSConversationModule:
    info = DecoderModuleInfo(MODULE, '1', PROFILE, ('decode', 'static_successors'))

    def open(self, source, *, profile=PROFILE, function_index=0, member=None):
        require(profile == PROFILE, 'unsupported MADS conversation profile')
        archive_info = None
        if member is not None:
            archive = HagArchive.read(source)
            entry, raw = archive.select(member)
            archive_info = dict(sha256=sha256(archive.source).hexdigest(), member_index=entry.index,
                                member_name=entry.name, member_offset=entry.offset, member_size=entry.size)
        else:
            raw = snapshot(source)
        conversation = Conversation.read(raw)
        processor = MADSConversationProcessor(conversation, function_index)
        provenance = dict(kind=PROFILE, source_sha256=sha256(raw).hexdigest(),
                          program_sha256=sha256(conversation.program).hexdigest(),
                          function_index=function_index, entry_offset=processor.entry_address,
                          dialog_size=conversation.dialogs[function_index][3],
                          code_section=conversation.pack.sections[6].metadata(),
                          archive=archive_info, qualification='static_instruction_facts_only')
        return capture_input(self.info, processor, conversation.program,
                             Location(processor.info.address_space, processor.entry_address), provenance)


def main(argv=None):
    """Inspect private resources or analyze one dialog without a native project."""
    import argparse
    from .decoder_modules import analyze_input
    from .mads_resources import read_cnd
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('inspect', 'analyze'))
    parser.add_argument('path')
    parser.add_argument('--member', help='explicit HAG member name')
    parser.add_argument('--function-index', type=int, default=0)
    parser.add_argument('--max-instructions', type=int, default=40)
    parser.add_argument('--kind', choices=('hag', 'pack', 'cnv', 'cnd'), default='cnv')
    args = parser.parse_args(argv)
    try:
        if args.operation == 'analyze':
            result = analyze_input(MADSConversationModule().open(args.path, member=args.member,
                                   function_index=args.function_index), max_instructions=args.max_instructions)
        else:
            raw = snapshot(args.path, MAX_ARCHIVE if args.kind == 'hag' or args.member else 16*1024*1024)
            if args.member:
                _, raw = HagArchive.read(raw).select(args.member)
            result = (HagArchive.read(raw).metadata() if args.kind == 'hag' else
                      MadsPack.read(raw).metadata() if args.kind == 'pack' else
                      read_cnd(raw) if args.kind == 'cnd' else Conversation.read(raw).metadata())
        print(json.dumps(dict(ok=True, result=result), ensure_ascii=True, allow_nan=False))
        return 0
    except (ValueError, OSError) as error:
        print(json.dumps(dict(ok=False, error=str(error))))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
