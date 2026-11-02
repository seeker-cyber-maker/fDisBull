"""Owned coordinate watch with ordinary keyboard input for KQ1 stairs.

This is a bounded runtime observation, not a simulated movement or a memory
edit. A watched write can be tentative; only the settled final state qualifies.
"""
from copy import deepcopy

from examples.agi.spatial_trial import read, require


class MotionProbe:
    MAX_WRITES = 1024
    KEYS = {'left': ('x', -1), 'right': ('x', 1), 'up': ('y', -1), 'down': ('y', 1)}

    def __init__(self, owner, *, axis, target, key, profile='stairs'):
        require(key in self.KEYS and axis == self.KEYS[key][0] and type(target) is int and
                0 <= target <= (154 if axis == 'x' else 167) and
                type(profile) is str and profile in ('stairs','fresh-room1'), 'Invalid motion target or profile')
        self.owner, self.axis, self.target, self.key = owner, axis, target, key
        self.profile = profile
        self.sign = self.KEYS[key][1]
        self.active, self.failed, self.stopping = False, False, False
        self.record, self.start_state, self.table = None, None, None
        self.input, self.stop_input = None, None
        self.last_coordinate = None

    def _fail(self, error, phase):
        self.failed = True
        self.owner.execution_blocked = True
        failure = {'phase': phase, 'type': type(error).__name__, 'message': str(error)}
        if self.record is not None:
            self.record.setdefault('failure', failure)
            self.record['status'], self.record['complete'] = 'incomplete', False
        self.owner.report.setdefault('precise_motion_failure', failure)

    def _state(self):
        o = self.owner
        data = read(o.d, o.ds+9, 0x132)
        flags = data[0x100:0x120]
        flag = lambda n: bool(flags[n//8] & (0x80 >> (n % 8)))
        table = int.from_bytes(read(o.d, o.ds+0x963, 2), 'little')
        if self.record is not None:
            self.record['last_actor_table'] = table
        require(0 < table and table+43 <= 65536 and (self.table is None or table == self.table),
                'Motion actor table changed')
        actor = read(o.d, o.ds+table, 43)
        base = o.inventory['base']
        require(type(base) is int and 0 < base and base+66 <= 65536 and
                int.from_bytes(read(o.d, o.ds+0x969, 2), 'little') == base,
                'Motion inventory table changed')
        state = {'room': data[0], 'score': data[3], 'control_direction': data[6], 'swimming': data[94],
                 'player_control': int.from_bytes(data[0x130:0x132], 'little'),
                 'x': int.from_bytes(actor[3:5], 'little', signed=True),
                 'y': int.from_bytes(actor[5:7], 'little', signed=True),
                 'view': actor[7], 'width': int.from_bytes(actor[26:28], 'little'),
                 'step_size': actor[30], 'direction': actor[33],
                 'drawn': bool(actor[37]&1), 'water': flag(0), 'trigger': flag(3),
                 'initializing': flag(5), 'dead': flag(63), 'shield_flag': flag(102),
                 'shield_location': read(o.d, o.ds+base+65, 1)[0],
                 'window': int.from_bytes(read(o.d, o.ds+0xd15, 2), 'little')}
        if self.record is not None:
            self.record['last_observation'] = deepcopy(state)
        profile_ok = (state['room'] in (66,67,68,69) and state['score'] == 19 and
                      state['shield_flag'] and state['shield_location'] == 255) if self.profile == 'stairs' else (
                      state['room'] == 1 and state['score'] == 0 and not state['shield_flag'] and
                      state['shield_location'] == 0)
        require(profile_ok and 0 <= state['x'] <= 154 and 0 <= state['y'] <= 167 and state['swimming'] == 0 and
                state['player_control'] == 1 and not any(state[k] for k in ('water','trigger','dead','initializing','window')) and
                state['drawn'] and state['view'] == 0 and state['width'] == 6 and state['step_size'] == 1,
                'Motion room, control or safety changed')
        if self.start_state is not None:
            other = 'y' if self.axis == 'x' else 'x'
            require(state['room'] == self.start_state['room'] and state[other] == self.start_state[other],
                    'Motion room or other coordinate changed')
            delta = self.sign*(state[self.axis]-self.last_coordinate)
            require(delta >= 0 and self.sign*(self.target-state[self.axis]) >= 0,
                    'Motion coordinate reversed or overshot')
        return table, state

    def _queue(self, field):
        o = self.owner
        item = {'kind': 'keyboard', 'key': 'press:'+self.key, 'delivered': None, 'complete': False}
        o.inputs.append(item); o.journal.append({'kind': 'input', 'record': item})
        self.record[field] = item
        receipt = o.d.keyboard_press(self.key, hold_ms=1, gap_ms=1)
        item['delivery'] = receipt
        item['delivered'] = receipt.get('accepted') if type(receipt.get('accepted')) is bool else None
        require(item['delivered'] is True, 'Motion keyboard delivery unknown')
        return item

    def start(self):
        o = self.owner
        require(not self.active and not self.failed and not getattr(o, 'execution_blocked', False) and
                o.watch is None and not o.trace_active and
                not getattr(getattr(o, 'quest_probe', None), 'active', False) and
                (getattr(o, 'motion_probe', None) is self or
                 not getattr(getattr(o, 'motion_probe', None), 'active', False)) and o._idle(),
                'Motion owner or keyboard not idle')
        table, state = self._state()
        require(state['direction'] == 0 and state['control_direction'] == 0 and
                self.sign*(self.target-state[self.axis]) > 0, 'Motion start or target differs')
        self.table, self.start_state = table, deepcopy(state)
        self.last_coordinate = state[self.axis]
        self.record = {'format': 'fdisbull-agi-precise-motion-1', 'status': 'incomplete',
                       'complete': False, 'profile': self.profile, 'axis': self.axis, 'target': self.target, 'key': self.key,
                       'initial': deepcopy(state), 'last_observation': deepcopy(state),
                       'last_actor_table': table, 'writes': [], 'watch': None}
        o.report.setdefault('precise_motion', []).append(self.record)
        self.active = True
        try:
            o.watch_kind = 'quest-motion'
            o.arm('w', o.ds+table+(3 if self.axis == 'x' else 5))
            self.record['watch'] = o.watch
            self.input = self._queue('initial_input')
        except BaseException as error:
            self._fail(error, 'setup')
            raise
        return self.record

    def handle_stop(self, out):
        try:
            require(self.active and not self.failed and not self.stopping, 'Motion watch inactive or failed')
            o = self.owner
            reason = (out.get('session') or {}).get('stop_reason', {})
            require(out.get('outcome') == 'breakpoint' and o.watch is not None and
                    reason.get('breakpoint_id') == o.watch and o.watch_kind == 'quest-motion',
                    'Foreign motion stop preserved')
            access = reason.get('data_access', {}); cause = access.get('instruction', {})
            regs = o.d.registers()
            require(access.get('access') == 'w' and cause.get('space') == 'segmented' and
                    int(cause.get('segment', '-1'), 16) == o.cs and
                    0 <= int(cause.get('offset', '-1'), 16) <= 65535 and
                    int(regs['segments']['cs'], 16) == o.cs and int(regs['segments']['ds'], 16)*16 == o.ds,
                    'Motion writer or segments differ')
            _, state = self._state()
            require(len(self.record['writes']) < self.MAX_WRITES, 'Motion write budget exhausted')
            self.record['writes'].append({'coordinate': state[self.axis], 'state': state,
                                          'cause_offset': int(cause['offset'],16)})
            self.last_coordinate = state[self.axis]
            if state[self.axis] != self.target:
                return
            require(o._idle(), 'Initial motion key not settled at target')
            self.input['complete'] = True
            o.remove_watch()
            self.stopping = True
            self.stop_input = self._queue('stop_input')
        except BaseException as error:
            if self.active: self._fail(error, 'stop')
            raise

    def poll(self):
        try:
            require(self.active and not self.failed, 'Motion probe inactive or failed')
            o = self.owner
            _, state = self._state()
            self.last_coordinate = state[self.axis]
            if not self.stopping:
                require(state[self.axis] != self.target, 'Motion target escaped owned watch')
                return False
            require(state[self.axis] == self.target, 'Motion target did not remain exact')
            if not o._idle() or state['direction'] != 0 or state['control_direction'] != 0:
                return False
            self.stop_input['complete'] = True
            self.record.update(status='verified', complete=True, final=state)
            self.active = False
            return True
        except BaseException as error:
            if self.active: self._fail(error, 'poll')
            raise
