"""Source-bound Z-machine v3 instruction processor.

This is the instruction-facts layer for Zork's virtual processor. It does not
execute a game, infer game intents, or turn guest offsets into native addresses.
The preserved executable-IR converter and game-intent UIL remain separate.

Encoding and control-flow rules follow the Z-machine Standards Document 1.1,
sections 1, 4, 6 and 15. Decoded destinations are candidates; a static edge does
not prove that the instruction runs or that a routine returns.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .processor import DecodedInstruction, Location, ProcessorInfo, Successor
from .zmachine import MAX_STORY_FILE, decode_v3, inspect_story_bytes


# These are decoder acceptance rules, not the executable converter's semantics.
# Keep them here rather than importing the converter and coupling the two layers.
_ARITY = {
    'je': (2, 4), 'jl': (2, 2), 'jg': (2, 2), 'dec_chk': (2, 2),
    'inc_chk': (2, 2), 'jin': (2, 2), 'test': (2, 2), 'or': (2, 2),
    'and': (2, 2), 'test_attr': (2, 2), 'set_attr': (2, 2),
    'clear_attr': (2, 2), 'store': (2, 2), 'insert_obj': (2, 2),
    'loadw': (2, 2), 'loadb': (2, 2), 'get_prop': (2, 2),
    'get_prop_addr': (2, 2), 'get_next_prop': (2, 2), 'add': (2, 2),
    'sub': (2, 2), 'mul': (2, 2), 'div': (2, 2), 'mod': (2, 2),
    'jz': (1, 1), 'get_sibling': (1, 1), 'get_child': (1, 1),
    'get_parent': (1, 1), 'get_prop_len': (1, 1), 'inc': (1, 1),
    'dec': (1, 1), 'print_addr': (1, 1), 'remove_obj': (1, 1),
    'print_obj': (1, 1), 'ret': (1, 1), 'jump': (1, 1),
    'print_paddr': (1, 1), 'load': (1, 1), 'not': (1, 1),
    'rtrue': (0, 0), 'rfalse': (0, 0), 'print': (0, 0),
    'print_ret': (0, 0), 'nop': (0, 0), 'save': (0, 0),
    'restore': (0, 0), 'restart': (0, 0), 'ret_popped': (0, 0),
    'pop': (0, 0), 'quit': (0, 0), 'new_line': (0, 0),
    'show_status': (0, 0), 'verify': (0, 0), 'call': (1, 4),
    'storew': (3, 3), 'storeb': (3, 3), 'put_prop': (3, 3),
    'read': (2, 2), 'print_char': (1, 1), 'print_num': (1, 1),
    'random': (1, 1), 'push': (1, 1), 'pull': (1, 1),
    'split_window': (1, 1), 'set_window': (1, 1),
    'output_stream': (1, 2), 'input_stream': (1, 1),
    'sound_effect': (1, 4),
}
_INDIRECT_VARIABLE = frozenset(('inc', 'dec', 'inc_chk', 'dec_chk', 'load', 'store', 'pull'))
_RETURNS = frozenset(('rtrue', 'rfalse', 'ret', 'ret_popped', 'print_ret'))


class ZMachineV3Processor:
    """Decode one checksum-qualified, immutable raw v3 story snapshot.

    ``program`` includes the original file's trailing padding and must be passed
    back to the generic dispatcher by identity. Only the declared story image
    can be decoded. Each source SHA has a separate byte-addressed location space.
    No current globals, locals, stack, saved game, or execution state is assumed.
    """

    __slots__ = ('_program', '_image', '_story_info', 'info')

    def __init__(self, story: bytes):
        metadata = inspect_story_bytes(story)
        self._program = bytes(story)
        self._image = self._program[:metadata['declared_bytes']]
        self._story_info = metadata
        self.info = ProcessorInfo(
            'fdisbull.zmachine.v3', '1',
            f"zmachine.v3.sha256:{metadata['sha256']}", 'byte',
            ('decode', 'static_successors'), None,
        )

    @classmethod
    def from_file(cls, path):
        """Read once, bounded, then qualify and decode that exact snapshot."""
        with Path(path).open('rb') as stream:
            story = stream.read(MAX_STORY_FILE + 1)
        return cls(story)

    @property
    def program(self) -> bytes:
        """Full original bytes, including padding; never mutable play-state RAM."""
        return self._program

    @property
    def story_info(self) -> dict[str, Any]:
        """Return independent metadata so caller edits cannot change decoding."""
        return dict(self._story_info)

    def _location(self, offset: int, evidence: str) -> tuple[Location | None, str]:
        # Header and padding are not executable candidates. Do not require high
        # memory: historical v3 stories can contain routines below that mark.
        if not 64 <= offset < len(self._image):
            return None, f'{evidence}; target offset {offset} is outside the declared instruction image'
        return Location(self.info.address_space, offset), evidence

    def _edge(self, kind: str, offset: int, evidence: str) -> Successor:
        target, evidence = self._location(offset, evidence)
        return Successor(kind, target, evidence)

    def _variable(self, number: int) -> dict[str, Any]:
        if number == 0:
            return {'number': 0, 'kind': 'stack', 'name': 'sp'}
        if number <= 15:
            return {'number': number, 'kind': 'local', 'name': f'local_{number}',
                    'index': number - 1, 'exists_in_current_frame': None}
        return {'number': number, 'kind': 'global', 'name': f'global_0x{number:02x}',
                'index': number - 16,
                'address': self._story_info['globals'] + 2 * (number - 16)}

    def _operand_details(self, instruction: dict[str, Any]) -> list[dict[str, Any]]:
        details = []
        for index, operand in enumerate(instruction['operands']):
            indirect = index == 0 and instruction['op'] in _INDIRECT_VARIABLE
            detail = {'index': index, 'role': 'variable_number' if indirect else 'value'}
            if operand['kind'] == 'variable':
                variable = self._variable(operand['value'])
                detail['read_variable'] = variable
                detail['stack_read'] = 'pop' if variable['kind'] == 'stack' else None
                text = 'pop(sp)' if variable['kind'] == 'stack' else variable['name']
                if indirect:
                    # The operand is read by value first; its runtime result
                    # then selects a variable. Initial globals are not used.
                    detail['referenced_variable'] = None
                    detail['reference_resolution'] = 'runtime_operand_value'
                    text = f'variable({text})'
            elif indirect:
                number = operand['value']
                if number > 255:
                    raise ValueError('Invalid indirect variable number')
                variable = self._variable(number)
                detail['referenced_variable'] = variable
                detail['stack_reference'] = 'in_place' if number == 0 else None
                text = f"variable({variable['name']})"
            else:
                text = f"0x{operand['value']:x}"
            detail['text'] = text
            details.append(detail)
        return details

    def _branch_edge(self, instruction: dict[str, Any], prefix: str = '') -> Successor:
        branch = instruction['branch']
        evidence = prefix + f"decoded branch when condition is {str(branch['when']).lower()}"
        if branch['return'] is not None:
            return Successor('return', None, evidence +
                             f"; returns {int(branch['return'])}, caller continuation is runtime state")
        return self._edge('branch', branch['target'], evidence + '; candidate instruction boundary')

    def _call(self, instruction: dict[str, Any]) -> tuple[dict[str, Any], Successor | None]:
        operand = instruction['operands'][0]
        call = {'packed_address': None, 'routine_header': None, 'entry': None,
                'local_count': None, 'initial_locals': None, 'status': 'unresolved_variable'}
        if operand['kind'] == 'variable':
            return call, Successor('call', None, 'routine packed address requires runtime operand value')
        packed = operand['value']
        call['packed_address'] = packed
        if packed == 0:
            call['status'] = 'null_routine'
            return call, None
        header = 2 * packed
        call['routine_header'] = header
        if not 64 <= header < len(self._image):
            call['status'] = 'invalid_routine_header'
            return call, Successor('call', None, f'routine header offset {header} is outside the declared instruction image')
        count = self._image[header]
        call['local_count'] = count
        if count > 15:
            call['status'] = 'invalid_routine_header'
            return call, Successor('call', None, f'routine header at {header:#x} has invalid local count {count}')
        entry = header + 1 + 2 * count
        if entry >= len(self._image):
            call['status'] = 'invalid_routine_header'
            return call, Successor('call', None, f'routine header at {header:#x} is truncated or has no instruction entry (offset {entry})')
        call['entry'] = entry
        call['initial_locals'] = [int.from_bytes(self._image[at:at + 2], 'big')
                                  for at in range(header + 1, entry, 2)]
        call['status'] = 'routine_candidate'
        return call, self._edge('call', entry,
                               f'packed address {packed:#x} * 2 gives routine header {header:#x}; '
                               f'{count} default locals precede candidate entry {entry:#x}')

    def decode(self, program: Any, location: Location) -> DecodedInstruction | None:
        """Decode a candidate start; reject malformed encodings explicitly.

        An offset at or after the declared image returns ``None`` (including
        padding). Header offsets, foreign program/space, invalid operand counts,
        unsupported opcodes and truncated instructions raise ``ValueError``.
        Invalid destinations retain the source evidence with an unresolved edge.
        """
        if program is not self._program:
            raise ValueError('Z-machine processor requires its immutable program snapshot')
        if not isinstance(location, Location) or location.space != self.info.address_space:
            raise ValueError('location is outside the processor address space')
        if location.offset < 64:
            raise ValueError('Z-machine header is outside the instruction image')
        if location.offset >= len(self._image):
            return None
        instruction = decode_v3(self._image, location.offset)
        name = instruction['op']
        low, high = _ARITY[name]
        if not low <= len(instruction['operands']) <= high:
            raise ValueError(f'Illegal operand count for v3 {name}')

        # Preserve every original decoder key. Fresh structures also prevent a
        # caller editing a returned fact from contaminating subsequent decodes.
        facts = dict(instruction)
        details = self._operand_details(instruction)
        facts.update(mnemonic=name, size=instruction['end'] - instruction['offset'],
                     flow='next', operand_details=details,
                     operand_evaluation='left_to_right')
        parts = [item['text'] for item in details]
        if 'store' in instruction:
            variable = self._variable(instruction['store'])
            facts['store_variable'] = dict(variable, stack_write='push' if variable['kind'] == 'stack' else None)
            parts.append('-> ' + variable['name'])
        if 'branch' in instruction:
            branch = instruction['branch']
            target = ('return ' + str(int(branch['return'])) if branch['return'] is not None
                      else f"{branch['target']:#x}")
            parts.append(('?true ' if branch['when'] else '?false ') + target)
        if 'text_offset' in instruction:
            # Keep the exact encoded span; text expansion and abbreviations are
            # separate data interpretation, not processor execution.
            parts.append(f"ztext[{instruction['text_offset']:#x}:{instruction['end']:#x}]")
        facts['op_str'] = ', '.join(parts)
        edges: list[Successor] = []
        end = instruction['end']

        if name == 'call':
            call, edge = self._call(instruction)
            facts['call'] = call
            facts['flow'] = 'indirect_call' if call['status'] == 'unresolved_variable' else 'call'
            if edge is not None:
                edges.append(edge)
            reason = ('null routine returns 0 immediately' if call['status'] == 'null_routine'
                      else 'call return assumed; return itself is not statically guaranteed')
            edges.append(self._edge('fallthrough', end, reason))
        elif name == 'jump':
            operand = instruction['operands'][0]
            if operand['kind'] == 'variable':
                facts['flow'] = 'indirect_jump'
                edges.append(Successor('branch', None, 'signed jump displacement requires runtime operand value'))
            else:
                facts['flow'] = 'jump'
                displacement = (operand['value'] ^ 0x8000) - 0x8000
                target = end + displacement - 2
                facts['jump'] = {'displacement': displacement, 'target': target}
                edges.append(self._edge('branch', target, 'decoded signed relative jump; candidate instruction boundary'))
        elif name in _RETURNS:
            facts['flow'] = 'return'
            value = 1 if name in ('rtrue', 'print_ret') else (0 if name == 'rfalse' else None)
            if name == 'ret' and instruction['operands'][0]['kind'] != 'variable':
                value = instruction['operands'][0]['value']
            facts['return_value'] = value
            edges.append(Successor('return', None, f'return value {value if value is not None else "requires runtime state"}; '
                                     'caller continuation is runtime state'))
        elif name == 'quit':
            facts['flow'] = 'halt'
        elif name == 'restart':
            facts['flow'] = 'restart'
            edges.append(self._edge('restart', self._story_info['initial_pc'],
                                    'restart restores initial story state and resets the call stack; original initial PC'))
        elif name == 'restore':
            facts['flow'] = 'restore'
            edges.append(Successor('restore', None, 'successful restore resumes an unknown saved continuation and state'))
            if instruction['branch']['when'] is False:
                edges.append(self._branch_edge(instruction, 'restore failure: '))
            else:
                edges.append(self._edge('fallthrough', end, 'restore failure; encoded condition is false'))
        elif 'branch' in instruction:
            facts['flow'] = 'conditional'
            edges.append(self._branch_edge(instruction))
            edges.append(self._edge('fallthrough', end, 'decoded branch not taken'))
        else:
            reason = 'execution resumes after input completes' if name == 'read' else 'decoded fallthrough'
            edges.append(self._edge('fallthrough', end, reason))
        return DecodedInstruction(location, facts, tuple(edges))
