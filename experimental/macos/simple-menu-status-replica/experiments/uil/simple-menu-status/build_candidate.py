"""Build an authored app-control candidate in fDisBull's existing v1 IL.

This does not lift ARM64 machine code. It encodes the declared, bounded slice
from replica source and screenshot observations, retaining those distinctions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(name, value):
    # CLI input is capped at 64 KiB before parsing; use canonical compact UIL.
    options = {'sort_keys': True, 'separators': (',', ':')} if name.endswith('.uil.json') else {'indent': 2}
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, **options) + '\n')


def source_evidence(relative, marker=None):
    path = ROOT / relative
    raw = path.read_bytes()
    lines = raw.decode().splitlines()
    selected, start, end = raw, 1, len(lines)
    if marker:
        start = next(i + 1 for i, line in enumerate(lines) if marker in line)
        depth = 0
        for end in range(start, len(lines) + 1):
            depth += lines[end - 1].count('{') - lines[end - 1].count('}')
            if depth == 0:
                break
        selected = ('\n'.join(lines[start - 1:end]) + '\n').encode()
    return {'kind': 'replica_source', 'file': relative, 'sha256': digest(raw),
            'lines': [start, end], 'selection_sha256': digest(selected),
            'claim': 'replica source projection; original correspondence unproved'}


def ref(name): return {'var': '$' + name}
def eq(name, value): return {'op': 'eq', 'left': ref(name), 'right': value}
def neg(condition): return {'op': 'not', 'condition': condition}
def both(*conditions): return {'op': 'and', 'conditions': list(conditions)}
def member(name, values): return neg(both(*(neg(eq(name, value)) for value in values)))
def setv(ident, name, value): return {'id': ident, 'op': 'set', 'var': '$' + name, 'value': value}
def increment(ident, name): return {'id': ident, 'op': 'add', 'var': '$' + name, 'value': 1}
def emit(ident, resource): return {'id': ident, 'op': 'text', 'resource': resource}
def require(ident, condition): return {'id': ident, 'op': 'require', 'condition': condition}
def branch(ident, condition, yes, no=()):
    return {'id': ident, 'op': 'if', 'condition': condition, 'then': list(yes), 'else': list(no)}
def toggle(ident, name):
    return branch(ident, eq(name, True), [setv(ident + '.off', name, False)],
                  [setv(ident + '.on', name, True)])


def build():
    evidence = {
        'replica.layout': source_evidence('Sources/StatusReplica/main.swift', 'func applyPreset('),
        'replica.memory': source_evidence('Sources/StatusCore/MemoryMood.swift'),
        'replica.sleep': source_evidence('Sources/StatusReplica/main.swift', 'func toggleCaffeine('),
        'replica.sleep_ui': source_evidence('Sources/StatusReplica/main.swift', 'private var caffeineDetails:'),
        'replica.sleep_footer': source_evidence('Sources/StatusReplica/main.swift', 'Text("Prevent Sleep").font('),
        'replica.preferences': source_evidence('Sources/StatusCore/ReplicaPreferences.swift'),
        'observed.controls': {'kind': 'observation_ledger', 'file': 'PARITY.md',
            'sha256': digest((ROOT / 'PARITY.md').read_bytes()),
            'observation_index': 'observations.json',
            'observation_index_sha256': digest((HERE / 'observations.json').read_bytes()),
            'claim': 'screen-visible labels and surfaces; not a native execution trace'},
        'authored.host_protocol': {'kind': 'authored_candidate',
            'claim': 'request/ack protocol authored for this experiment; not recovered from original'},
    }
    initial = {'action': ('u8', 0), 'arg': ('u8', 0), 'menu_open': ('bool', False),
               'layout': ('u8', 4), 'show_gpu': ('bool', True),
               'show_storage': ('bool', True), 'show_battery': ('bool', True),
               'show_network': ('bool', True), 'show_processes': ('bool', False),
               'show_details': ('bool', False), 'memory_mood': ('u8', 0),
               'icon': ('u8', 0), 'sleep_active': ('bool', False),
               'sleep_pending': ('u8', 0), 'sleep_display': ('bool', False),
               'sleep_error': ('bool', False), 'additional_open': ('bool', False),
               'detail_page': ('u8', 0), 'settings_open': ('bool', False),
               'preferences_dirty': ('bool', False), 'ack_id': ('u64', 0),
               'sleep_request_id': ('u64', 0), 'preferences_revision': ('u64', 0)}
    layouts = ['Simple', 'Developer', 'Battery', 'Local AI', 'Custom']
    for i in range(5): initial['checked_' + str(i)] = ('bool', i == 4)
    variables = {'$' + k: {'type': t, 'initial': v} for k, (t, v) in initial.items()}
    texts = {'memory.unknown': '❔', 'memory.normal': '😊', 'memory.warning': '😐',
             'memory.critical': '😰', 'sleep.off': 'Off', 'sleep.active': 'Until stopped',
             'effect.sleep.start.request': 'Host request: acquire idle-sleep assertion',
             'effect.sleep.stop.request': 'Host request: release idle-sleep assertion',
             'effect.preferences.write.request': 'Host request: write replica preferences',
             'view.menu.changed': 'Dashboard visibility changed',
             'view.detail.changed': 'Attached detail selection changed',
             'view.icon.native': 'Selected icon needs the native renderer',
             'host.operation.failed': 'Host operation failed',
             'host.preferences.ack': 'Modeled preference-write acknowledgment received'}
    for i, name in enumerate(layouts): texts['layout.' + str(i)] = name
    resources = {k: {'kind': 'text', 'text': v} for k, v in texts.items()}
    actions = {}
    body = [require('input.action.valid', member('action', range(15))),
            require('state.layout.valid', member('layout', range(5))),
            require('state.memory.valid', member('memory_mood', range(4))),
            require('state.icon.valid', member('icon', range(7))),
            require('state.sleep.pending.valid', member('sleep_pending', range(3))),
            require('state.sleep.start.consistent', neg(both(eq('sleep_pending', 1), eq('sleep_active', True)))),
            require('state.sleep.stop.consistent', neg(both(eq('sleep_pending', 2), eq('sleep_active', False)))),
            require('state.detail.valid', member('detail_page', range(6)))]

    def dirty(ident):
        return [require(ident + '.not_exhausted', neg(eq('preferences_revision', 2**64 - 1))),
                increment(ident + '.revision', 'preferences_revision'),
                setv(ident + '.dirty', 'preferences_dirty', True)]

    def action(code, name, blocks, evidence_ids):
        actions[str(code)] = name
        node = branch('action.' + name, eq('action', code), blocks)
        node['evidence'] = evidence_ids
        body.append(node)

    actions['0'] = 'render_current_projection'
    action(1, 'toggle_dashboard', [toggle('menu.toggle', 'menu_open'),
           emit('menu.changed', 'view.menu.changed')], ['observed.controls'])
    presets = [require('layout.request.valid', member('arg', range(5)))]
    for i, name in enumerate(layouts):
        values = {'layout': i, 'show_gpu': name != 'Battery',
                  'show_storage': name != 'Simple', 'show_battery': name in ('Battery', 'Custom'),
                  'show_network': name not in ('Simple', 'Local AI'),
                  'show_processes': name == 'Developer', 'show_details': name == 'Developer',
                  'preferences_dirty': True}
        presets.append(branch('layout.' + str(i), eq('arg', i),
                       [setv('layout.' + str(i) + '.' + key, key, value) for key, value in values.items()] +
                       dirty('layout.' + str(i) + '.prefs') + [emit('layout.' + str(i) + '.name', 'layout.' + str(i)),
                        emit('layout.' + str(i) + '.persist', 'effect.preferences.write.request')]))
    action(2, 'select_layout', presets, ['replica.layout'])
    flags = ['show_gpu', 'show_storage', 'show_battery', 'show_network', 'show_processes', 'show_details']
    toggles = [require('section.request.valid', member('arg', range(6)))]
    for i, flag in enumerate(flags): toggles.append(branch('section.' + flag, eq('arg', i), [toggle(flag + '.toggle', flag)]))
    toggles += [setv('section.custom', 'layout', 4)] + dirty('section.prefs') + [
                emit('section.persist', 'effect.preferences.write.request')]
    action(3, 'toggle_section', toggles, ['observed.controls', 'replica.preferences'])
    action(4, 'memory_pressure_event', [require('memory.input.valid', member('arg', range(4))),
           setv('memory.update', 'memory_mood', ref('arg'))], ['replica.memory'])
    idle = both(eq('sleep_pending', 0), eq('sleep_active', False))
    action(5, 'request_sleep_start', [require('sleep.start.allowed', idle),
           require('sleep.start.id.available', neg(eq('sleep_request_id', 2**64 - 1))),
           increment('sleep.start.id', 'sleep_request_id'),
           setv('sleep.start.pending', 'sleep_pending', 1), setv('sleep.start.clear_error', 'sleep_error', False),
           emit('sleep.start.request', 'effect.sleep.start.request')], ['replica.sleep', 'authored.host_protocol'])
    action(6, 'complete_sleep_start', [require('sleep.start.ack.expected', eq('sleep_pending', 1)),
           require('sleep.start.ack.id', eq('ack_id', ref('sleep_request_id'))),
           require('sleep.start.ack.valid', member('arg', range(2))),
           setv('sleep.start.ack.clear', 'sleep_pending', 0),
           branch('sleep.start.result', eq('arg', 1), [setv('sleep.start.success', 'sleep_active', True)],
                  [setv('sleep.start.failure', 'sleep_error', True), emit('sleep.start.error', 'host.operation.failed')])],
           ['authored.host_protocol'])
    action(7, 'request_sleep_stop', [require('sleep.stop.allowed', both(eq('sleep_pending', 0), eq('sleep_active', True))),
           require('sleep.stop.id.available', neg(eq('sleep_request_id', 2**64 - 1))),
           increment('sleep.stop.id', 'sleep_request_id'),
           setv('sleep.stop.pending', 'sleep_pending', 2), setv('sleep.stop.clear_error', 'sleep_error', False),
           emit('sleep.stop.request', 'effect.sleep.stop.request')], ['replica.sleep', 'authored.host_protocol'])
    action(8, 'complete_sleep_stop', [require('sleep.stop.ack.expected', eq('sleep_pending', 2)),
           require('sleep.stop.ack.id', eq('ack_id', ref('sleep_request_id'))),
           require('sleep.stop.ack.valid', member('arg', range(2))), setv('sleep.stop.ack.clear', 'sleep_pending', 0),
           branch('sleep.stop.result', eq('arg', 1), [setv('sleep.stop.success', 'sleep_active', False)],
                  [setv('sleep.stop.failure', 'sleep_error', True), emit('sleep.stop.error', 'host.operation.failed')])],
           ['authored.host_protocol'])
    action(9, 'toggle_additional_options', [toggle('additional.toggle', 'additional_open')], ['observed.controls', 'replica.sleep_ui'])
    action(10, 'select_sleep_mode', [require('sleep.mode.editable', idle),
           require('sleep.mode.valid', member('arg', range(2))),
           branch('sleep.mode.value', eq('arg', 1), [setv('sleep.mode.display', 'sleep_display', True)],
                  [setv('sleep.mode.system', 'sleep_display', False)]),
           ] + dirty('sleep.mode.prefs') + [emit('sleep.mode.persist', 'effect.preferences.write.request')],
           ['observed.controls', 'replica.preferences', 'replica.sleep_ui'])
    action(11, 'select_detail', [require('detail.request.valid', member('arg', range(6))),
           branch('detail.sleep.reopen', both(eq('arg', 5), neg(eq('detail_page', 5))),
                  [setv('detail.sleep.collapse.additional', 'additional_open', False)]),
           setv('detail.update', 'detail_page', ref('arg')), emit('detail.changed', 'view.detail.changed')], ['observed.controls', 'replica.sleep_footer'])
    action(12, 'select_icon', [require('icon.request.valid', member('arg', range(7))),
           setv('icon.update', 'icon', ref('arg'))] + dirty('icon.prefs') + [
           emit('icon.persist', 'effect.preferences.write.request')], ['replica.preferences'])
    action(13, 'toggle_settings', [toggle('settings.toggle', 'settings_open')], ['observed.controls'])
    action(14, 'complete_preference_write', [require('preferences.ack.expected', eq('preferences_dirty', True)),
           require('preferences.ack.id', eq('ack_id', ref('preferences_revision'))),
           require('preferences.ack.valid', member('arg', range(2))),
           branch('preferences.result', eq('arg', 1), [setv('preferences.clean', 'preferences_dirty', False)],
                  [emit('preferences.failed', 'host.operation.failed')]),
           emit('preferences.ack', 'host.preferences.ack')], ['authored.host_protocol'])
    for i in range(5):
        body.append(branch('checkmark.' + str(i), eq('layout', i),
                    [setv('checkmark.' + str(i) + '.on', 'checked_' + str(i), True)],
                    [setv('checkmark.' + str(i) + '.off', 'checked_' + str(i), False)]))
    emoji = []
    for i, name in enumerate(['unknown', 'normal', 'warning', 'critical']):
        emoji.append(branch('memory.render.' + name, eq('memory_mood', i), [emit('memory.emoji.' + name, 'memory.' + name)]))
    body.append(branch('icon.render', eq('icon', 0), emoji, [emit('icon.render.native', 'view.icon.native')]))
    body.append(branch('sleep.render', eq('sleep_active', True), [emit('sleep.render.active', 'sleep.active')],
                       [emit('sleep.render.off', 'sleep.off')]))
    document = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': variables,
                'resources': resources, 'evidence': evidence, 'body': body}
    write('candidate.uil.json', document)
    write('contract.json', {
        'kind': 'sidecar-contract-not-uil-syntax', 'status': 'authored_candidate',
        'claim': 'bounded replica-source/observation-assisted control model; no ARM64 semantic lift',
        'program': 'candidate.uil.json', 'actions': actions,
        'original_identity': {'file': 'original-identity.json',
                              'sha256': digest((HERE / 'original-identity.json').read_bytes()),
                              'behavior_binding': 'unresolved'},
        'enums': {'layout': dict(enumerate(layouts)), 'section': dict(enumerate(flags)),
                  'memory_mood': dict(enumerate(['unknown', 'normal', 'warning', 'critical'])),
                  'icon': dict(enumerate(['Memory emoji', 'CPU Emoji', 'CPU & Memory', 'CPU & Battery',
                                         'Animated Pulse', 'Animated Dots', 'Car Animation'])),
                  'detail_page': dict(enumerate(['none', 'CPU', 'GPU', 'Memory', 'Storage', 'Sleep'])),
                  'sleep_pending': {'0': 'none', '1': 'start request', '2': 'stop request'},
                  'completion_arg': {'0': 'failure', '1': 'success'}},
        'host_boundary': {
            'effect.sleep.start.request': 'declarative text token only; no IOPM assertion acquired',
            'effect.sleep.stop.request': 'declarative text token only; no IOPM assertion released',
            'effect.preferences.write.request': 'declarative text token only; no UserDefaults write',
            'completion_actions': 'supplied by test driver; not an observed native completion',
            'completion_identity': 'ack_id must match the current sleep_request_id or preferences_revision; counters refuse exhaustion rather than wrapping',
            'sleep_scope': 'untimed idle-sleep state only; process tracking and timer expiry unresolved'},
        'unresolved': ['original SwiftUI event dispatch and function-to-control mapping',
            'exact original preset semantics and preferences encoding', 'native sleep/persistence effect binding',
            'metrics sampling, units, graph history, startup memory estimate and pressure acquisition',
            'fonts, geometry, SF Symbols, colors and image rendering',
            'alerts, network/VPN, volume scans, sharing, localization, process tracking and login registration'],
        'source_inventory': evidence,
    })


if __name__ == '__main__':
    build()
