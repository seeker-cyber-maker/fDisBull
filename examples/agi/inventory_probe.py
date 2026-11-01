"""Source-bound, stop-driven probes for two original KQ1 inventory writes.

The owner controls guest execution and teardown. These probes observe only
bounded writes and original handler returns; they do not authenticate captures.
"""
from copy import deepcopy
from hashlib import sha256
import json

from examples.agi.spatial_trial import read, require
from examples.agi.verify_mushroom import GET_HANDLER
from examples.agi.verify_troll import OBJECT_SHA256, SCORE_WRITER
from fdisbull.agi_layout import logic_layout


class PickupProbe:
    """Observe key or chest pickup without issuing input or resuming execution."""

    CASES = {
        (40, 5, 0x2d6, 0x2db, 3, ('item', 'return', 'score')),
        (58, 2, 0x25d, 0x25a, 8, ('score', 'item', 'return')),
    }

    def __init__(self, owner, *, name, logic, item, item_offset, score_offset,
                 score_delta, before_score, order):
        require(isinstance(name, str) and name in ('key', 'chest'), 'Invalid pickup name')
        order = tuple(order) if isinstance(order, (list, tuple)) else ()
        require((logic, item, item_offset, score_offset, score_delta, order) in self.CASES and
                (name, logic) in (('key', 40), ('chest', 58)) and
                type(before_score) is int and 0 <= before_score <= 255-score_delta,
                'Unsupported pickup specification')
        self.owner, self.name = owner, name
        self.logic, self.item, self.item_offset = logic, item, item_offset
        self.score_offset, self.score_delta, self.before_score = score_offset, score_delta, before_score
        self.order, self.index = order, 0
        self.active, self.failed, self.item_frame, self.proof = False, False, None, None
        self.location = None

    def persist(self):
        path = self.owner.root / f'{self.name}-pickup.private.json'
        path.write_text(json.dumps(self.proof, indent=2) + '\n')
        return path

    def _fail(self, error, phase):
        """Latch the owner before best-effort evidence writes; retain the first error."""
        self.failed = True
        self.owner.execution_blocked = True
        failure = {'phase': phase, 'type': type(error).__name__, 'message': str(error)}
        failure = self.owner.report.setdefault('quest_pickup_failure', failure)
        if self.proof is not None:
            self.proof['status'], self.proof['complete'] = 'incomplete', False
            self.proof.setdefault('failure', failure)
            try:
                self.persist()
            except BaseException as save_error:
                failure.setdefault('persistence_error', {'type': type(save_error).__name__,
                                                          'message': str(save_error)})

    def _binding(self):
        o = self.owner
        raw = (o.source / 'OBJECT').read_bytes()
        require(sha256(raw).hexdigest() == OBJECT_SHA256, 'Pickup OBJECT identity differs')
        decoded = bytes(x ^ b'Avis Durgan'[i % 11] for i, x in enumerate(raw))
        base, end = o.inventory['base'], o.inventory['end']
        require(type(base) is int and type(end) is int and 0 < base < end <= 65536 and
                end-base == 81 and len(decoded) >= 3+81 and int.from_bytes(decoded[:2], 'little') == 81,
                'Pickup inventory bounds differ')
        require(int.from_bytes(read(o.d, o.ds+0x969, 2), 'little') == base and
                int.from_bytes(read(o.d, o.ds+0x96b, 2), 'little') == end,
                'Live inventory table differs')
        rec = self.item*3
        name = int.from_bytes(decoded[3+rec:3+rec+2], 'little')
        stop = decoded.find(b'\0', 3+name)
        require(0 < name and 3+name < stop < len(decoded) and stop-(3+name) <= 64 and
                base+name+(stop-(3+name))+1 <= 65536, 'Pickup name bounds differ')
        name_bytes = decoded[3+name:stop+1]
        require(read(o.d, o.ds+base+rec, 2) == name.to_bytes(2, 'little') and
                read(o.d, o.ds+base+name, len(name_bytes)) == name_bytes,
                'Live named inventory record differs')
        self.location = o.ds+base+rec+2
        return {'source_sha256': OBJECT_SHA256, 'base': base, 'end': end, 'stride': 3,
                'item': self.item, 'record_offset': rec, 'name_offset': name,
                'location_offset': rec+2, 'location_linear': self.location,
                'carried_value': 255, 'name_sha256': sha256(name_bytes).hexdigest()}

    def _source(self, regs):
        o = self.owner
        require(int(regs['segments']['cs'], 16) == o.cs and
                int(regs['segments']['ds'], 16)*16 == o.ds, 'Pickup segment changed')
        rec = int.from_bytes(read(o.d, o.ds+0x979, 2), 'little')
        desc = read(o.d, o.ds+rec, 10)
        code = int.from_bytes(desc[4:6], 'little')
        resource = o.resources[self.logic]
        require(sha256(resource.payload).hexdigest() == resource.resource_sha256 and
                resource.payload[2:2+len(resource.code)] == resource.code and
                desc[2] == self.logic and code+len(resource.code) <= 65536 and
                read(o.d, o.ds+code, len(resource.code)) == resource.code,
                'Pickup loaded source differs')
        starts = set(logic_layout(resource.payload)['instructions'])
        require(self.item_offset+2 in starts and self.score_offset+2 in starts and
                resource.code[self.item_offset:self.item_offset+2] == bytes((92, self.item)) and
                resource.code[self.score_offset:self.score_offset+3] == bytes((5, 3, self.score_delta)),
                'Pickup source operations differ')
        return code

    def start(self):
        o = self.owner
        require(not self.active and not self.failed and not getattr(o, 'execution_blocked', False) and
                o.watch is None and not o.trace_active,
                'Pickup probe already active or owner busy')
        require(read(o.d, o.cs*16+0x7471, len(GET_HANDLER)) == GET_HANDLER and
                read(o.d, o.cs*16+0x72d4, len(SCORE_WRITER)) == SCORE_WRITER and
                read(o.d, o.ds+0x78d, 2) == bytes.fromhex('7174'), 'Pickup handlers differ')
        binding = self._binding()
        require(read(o.d, o.ds+12, 1) == bytes((self.before_score,)) and
                read(o.d, self.location, 1) == b'\0', 'Pickup initial state differs')
        self.proof = {'format': 'fdisbull-agi-quest-pickup-1', 'name': self.name,
                      'status': 'incomplete', 'complete': False, 'native_execution': False,
                      'source_logic': self.logic, 'source_logic_sha256': o.resources[self.logic].resource_sha256,
                      'item': self.item, 'item_source_offset': self.item_offset,
                      'score_source_offset': self.score_offset, 'score_delta': self.score_delta,
                      'order': list(self.order), 'before': {'score': self.before_score, 'item_location': 0},
                      'known_effects': {'score': self.before_score, 'item_location': 0},
                      'inventory_binding': binding}
        self.active = True
        try:
            self.persist()
            self._arm(self.order[0])
        except BaseException as error:
            self._fail(error, 'setup')
            raise
        return self.proof

    def persist_partial_trace(self):
        """Persist retained trace evidence after the owner has stopped collection."""
        receipt = self.owner.trace_receipt
        require(self.proof is not None and isinstance(receipt, dict) and
                receipt.get('name') == self.name, 'No owned pickup trace to persist')
        path = self.owner.root / f'partial-{self.name}-trace.private.json'
        path.write_text(json.dumps(receipt, indent=2) + '\n')
        self.proof['partial_trace'] = {'path': path.name, 'sha256': sha256(path.read_bytes()).hexdigest(),
                                       'event_count': len(receipt['events']), 'complete': receipt['complete']}
        self.persist()
        return self.proof['partial_trace']

    def _arm(self, stage):
        o = self.owner
        o.watch_kind = f'quest-{self.name}-{stage}'
        if stage == 'return': o.arm('execution', 0x2fa, 'segmented')
        else: o.arm('w', o.ds+12 if stage == 'score' else self.location)

    def _begin_trace(self):
        o = self.owner
        o.trace_receipt = {'format': 'fdisbull-agi-quest-trace-1', 'name': self.name,
                           'maximum_count': 128, 'complete': False, 'events': [], 'runs': [],
                           'scope': 'Fetch observations; original writes and handler return are separate stops.'}
        o.trace_start_index = len(o.journal)
        o.trace_active = True  # A lost response leaves trace ownership uncertain.
        o.d.call('trace.start', {'detail': 'normal', 'instruction_count': 128})

    def _finish_trace(self):
        o = self.owner
        page = o.d.call('trace.read', {'cursor': None, 'limit': 256})
        events, known = page.get('events'), o.trace_receipt['events']
        o.trace_receipt['runs'] = [x['result'] for x in o.journal[o.trace_start_index:]
                                   if isinstance(x.get('result'), dict)]
        require(isinstance(events, list) and len(events) >= len(known) and
                events[:len(known)] == known, 'Pickup trace contradicts retained prefix')
        o.trace_receipt['events'] = events
        require(not page.get('next_cursor') and 0 < len(events) < 128 and
                all(isinstance(x, dict) for x in events) and bool(o.trace_receipt['runs']),
                'Pickup trace exhausted or incomplete')
        o.stop_trace()
        o.trace_receipt['complete'] = True
        path = o.root / f'{self.name}-trace.private.json'
        path.write_text(json.dumps(o.trace_receipt, indent=2) + '\n')
        return {'path': path.name, 'sha256': sha256(path.read_bytes()).hexdigest(),
                'event_count': len(events), 'maximum_count': 128}

    def handle_stop(self, out):
        try:
            require(self.active and not self.failed and self.index < len(self.order), 'Pickup probe inactive or failed')
            self._handle_stop(out)
        except BaseException as error:
            if self.active:
                self._fail(error, 'stop')
            raise

    def _handle_stop(self, out):
        o = self.owner
        reason = (out.get('session') or {}).get('stop_reason', {})
        require(out.get('outcome') == 'breakpoint' and o.watch is not None and
                reason.get('breakpoint_id') == o.watch, 'Foreign stop preserved')
        stage = self.order[self.index]
        require(o.watch_kind == f'quest-{self.name}-{stage}', 'Pickup stage changed')
        regs = o.d.registers()
        code = self._source(regs)
        require(self._binding() == self.proof['inventory_binding'], 'Inventory binding changed')
        ip = int(regs['instruction_pointer'], 16)
        cursor = self.item_offset+2
        score = read(o.d, o.ds+12, 1)[0]
        item = read(o.d, self.location, 1)[0]
        effects = self.proof['known_effects']
        if stage == 'return':
            ss, bp, prior_code = self.item_frame
            require(not reason.get('data_access') and ip == 0x2fa and code == prior_code and
                    int(regs['segments']['ss'], 16) == ss and
                    int(regs['general']['esp'], 16)&65535 == bp+8 and
                    int(regs['general']['eax'], 16)&65535 == code+cursor and
                    read(o.d, ss*16+bp+8, 2) == (code+cursor).to_bytes(2, 'little') and
                    score == effects['score'] and item == effects['item_location'], 'Pickup handler return differs')
            self.proof['handler_return'] = {'offset': 0x2fa, 'observed': True,
                                            'source_cursor_offset': cursor, 'stack_verified': True}
        else:
            access = reason.get('data_access', {}); cause = access.get('instruction', {})
            offset, resume = (0x72da, 0x72de) if stage == 'score' else (0x7482, 0x7486)
            require(access.get('access') == 'w' and cause.get('space') == 'segmented' and
                    int(cause.get('segment', '-1'), 16) == o.cs and
                    int(cause.get('offset', '-1'), 16) == offset and ip == resume, 'Pickup writer differs')
            if stage == 'score':
                bx = int(regs['general']['ebx'], 16)&65535
                al = int(regs['general']['eax'], 16)&255
                require(bx == 3 and al == self.score_delta and
                        int(regs['general']['esi'], 16)&65535 == code+self.score_offset+3 and
                        score == self.before_score+self.score_delta and item == effects['item_location'],
                        'Pickup score operands or state differ')
                self.proof['score_writer'] = {'cause_offset': offset, 'resume_offset': resume, 'bx': bx, 'al': al}
                effects['score'] = score
            else:
                di = int(regs['general']['edi'], 16)&65535
                bp = int(regs['general']['ebp'], 16)&65535
                sp = int(regs['general']['esp'], 16)&65535
                ss = int(regs['segments']['ss'], 16)
                require(di == o.inventory['base']+self.item*3 and sp == bp <= 65525 and
                        read(o.d, ss*16+bp+6, 4) == (0x2fa).to_bytes(2, 'little')+(code+cursor).to_bytes(2, 'little') and
                        score == effects['score'] and item == 255, 'Pickup item writer or frame differs')
                self.item_frame = (ss, bp, code)
                self.proof['item_writer'] = {'cause_offset': offset, 'resume_offset': resume, 'di_offset': di}
                effects['item_location'] = item
        self.proof['native_execution'] = True
        self.persist()  # Commit each known effect before changing watches or tracing.
        o.remove_watch()
        self.index += 1
        if self.index < len(self.order):
            self._arm(self.order[self.index])
            if self.index == 1: self._begin_trace()
            return
        trace = self._finish_trace()
        self.proof.update(status='verified', complete=True, after=deepcopy(effects), trace=trace)
        self.persist()
        self.active = False
