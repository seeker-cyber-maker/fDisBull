#!/usr/bin/env python3
"""Replay qualified normal schedules with read-only audio-clock telemetry.

Raw service/tick rates retain the strict warmed wall-clock target. Scheduler
credit accounting is additional evidence and never balances away audio latency.
Original schedules, game observations and final video must replay identically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from check_miniplanets_native import _private_output
from check_miniplanets_nes_game import run_host, save
from verify_miniplanets_level import NES_SHA

SOURCE_TIMER_HZ = 118.89963993409864
CLOCK_SYMBOLS = {
    'interrupt': '_audio_interrupt_count', 'tick': '_audio_tick_count',
    'due': '_audio_due_slots', 'served': '_audio_served_slots',
    'physical': '_audio_physical_entries', 'catchup': '_audio_catchup_slots',
    'late_calls': '_audio_late_calls', 'max_owed': '_audio_max_owed',
    'late_requests': '_audio_late_requests'}

ATOMIC_LOW_PROTOCOL = {
    'format': 'miniplanets-audio-tempo-protocol-2',
    'observation': 'Atomic low bytes, modulo256 deltas; retain all original16-bit words as diagnostics.',
    'minimum_measured_host_intervals': 3000, 'warmup_host_frames': 100,
    'service_increments_per_host_interval_max': 16,
    'outstanding_slots_max_exclusive': 128,
    'queue_lateness_increments_per_host_interval_max': 240,
    'queue_bound_reason': 'At most16 serviced slots per observation interval, each has at most15 queued-request iterations.',
    'source_tick_endpoint_allowance': 2, 'service_endpoint_allowance': 1,
    'scheduled_slot_endpoint_allowance': 1,
    'rate_target': 'Two scheduled services per hostframe; sourceTimerHz118.89963993409864.',
    'raw_word_policy': 'Inconsistent high words stay torn/unknown; only bounded atomic-byte deltas support the v2 rate claim.',
    'latency_policy': 'Show unadjusted rates, endpoint and maximum debt; credit accounting never erases a slow clock.',
    'feedback_extension': 'Ordinary input-only first-level route, then1500 neutral hostframes after Stage1-2 publication.',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def compressed_inputs(masks, mapping):
    result = []
    start = 0
    for end in range(1, len(masks)+1):
        if end == len(masks) or masks[end] != masks[start]:
            if masks[start]:
                result.append({'start': start, 'end': end,
                    'buttons': [name for name, bit in mapping.items() if masks[start] & (1 << bit)]})
            start = end
    return result


def clock_statistics(counters, frames, fps):
    """Classify a warmed raw window without repairing torn multi-byte reads."""
    first, last = counters[0], counters[-1]
    elapsed = frames / fps
    deltas = {name: (last[name]-first[name]) & 65535 for name in first}
    discontinuities = []
    peaks = dict(services=0, source_ticks=0, physical_entries=0)
    has_scheduler = 'due' in first
    debts = []
    if has_scheduler:
        debts = [(row['due']-row['served']) & 65535 for row in counters]
    for index, (a, b) in enumerate(zip(counters, counters[1:]), 1):
        step = {name: (b[name]-a[name]) & 65535 for name in a}
        peaks['services'] = max(peaks['services'], step['interrupt'])
        peaks['source_ticks'] = max(peaks['source_ticks'], step['tick'])
        reasons = []
        if has_scheduler:
            previous_debt = (a['due']-a['served']) & 65535
            current_debt = (b['due']-b['served']) & 65535
            peaks['physical_entries'] = max(peaks['physical_entries'], step['physical'])
            if step['due'] > 4:
                reasons.append('large/torn scheduled-slot delta')
            if previous_debt >= 32768 or current_debt >= 32768:
                reasons.append('served frontier ahead of due or torn counter')
            if step['served'] > step['due']+previous_debt:
                reasons.append('served slots exceed newly due slots plus previous debt')
            # An entry already in flight at the first observation may finish
            # four slots without increasing the entry counter in this interval.
            if step['served'] > 4*(step['physical']+1):
                reasons.append('served slots exceed four per possible IRQ owner')
            # audio_tick increments its entry counter before returning; the
            # scheduler commits served only after that call has completed.
            if abs(step['interrupt']-step['served']) > 1:
                reasons.append('service-entry/completed-slot delta inconsistent')
            if step['physical'] >= 128:
                reasons.append('large/torn physical-entry delta')
        elif step['interrupt'] > 12:
            reasons.append('large/torn service delta without scheduler telemetry')
        if step['tick'] > step['interrupt']+1:
            reasons.append('source ticks exceed possible entered services')
        if reasons:
            discontinuities.append({'offset': index, 'before': a, 'after': b, 'reasons': reasons})
    expected_calls = frames*2
    expected_ticks = elapsed*SOURCE_TIMER_HZ
    strict_rate = (abs(deltas['interrupt']-expected_calls) <= 1 and
                   abs(deltas['tick']-expected_ticks) <= 1.1)
    scheduled_rate = not has_scheduler or abs(deltas['due']-expected_calls) <= 1
    classification = ('inconclusive-counter-discontinuity' if discontinuities else
                      'passed' if strict_rate and scheduled_rate else 'failed-tempo')
    return {'elapsed_emulated_seconds': elapsed,
        'counter_before': first, 'counter_after': last, 'counter_deltas': deltas,
        'expected_service_calls': expected_calls, 'expected_source_ticks': expected_ticks,
        'measured_service_hz': deltas['interrupt']/elapsed,
        'measured_source_tick_hz': deltas['tick']/elapsed,
        'counter_discontinuities': discontinuities, 'classification': classification,
        'observed_per_hostframe_peaks': peaks,
        'scheduler_debt': {'before': debts[0], 'after': debts[-1], 'maximum_observed': max(debts),
            'minimum_observed': min(debts), 'max_owed_diagnostic': last.get('max_owed'),
            'late_calls_delta': deltas.get('late_calls'), 'late_requests_delta': deltas.get('late_requests')}
            if has_scheduler else None,
        'strict_wallclock_target': True,
        'scope': 'Warmed raw native service/tick rate; debt accounting is reported, never used to erase latency.'}


def atomic_clock_statistics(counters, frames, fps):
    """Qualify relative counts from atomic bytes under the frozen v2 bounds."""
    if frames < ATOMIC_LOW_PROTOCOL['minimum_measured_host_intervals'] or len(counters) != frames+1:
        raise ValueError('protocolv2 requires at least3000 measured host intervals')
    if not {'interrupt','tick','due','served','physical'} <= counters[0].keys():
        raise ValueError('protocolv2 requires scheduler telemetry')
    names = [name for name in counters[0] if name != 'max_owed']
    totals = {name: 0 for name in names}
    observations = []
    word_unknowns = []
    invalid = []
    first = counters[0]
    initial_debt = ((first['due'] & 255)-(first['served'] & 255)) & 255
    debts = [initial_debt]
    peaks = {name: 0 for name in names}
    max_owed_low = first.get('max_owed', 0) & 255
    for index, row in enumerate(counters):
        if index:
            previous = counters[index-1]
            increments = {}
            for name in names:
                delta = ((row[name] & 255)-(previous[name] & 255)) & 255
                increments[name] = delta
                bound = 240 if name == 'late_requests' else 16
                if delta > bound:
                    invalid.append({'offset': index, 'counter': name, 'delta': delta, 'bound': bound})
                totals[name] += delta
                peaks[name] = max(peaks[name], delta)
            debts.append(initial_debt+totals['due']-totals['served'])
            if increments['served'] > 4*(increments['physical']+1):
                invalid.append({'offset':index,'reason':'more than four slots per possible IRQ owner'})
            if increments['tick'] > increments['interrupt']+1:
                invalid.append({'offset':index,'reason':'source ticks exceed entered services'})
        entered_not_committed=((row['interrupt'] & 255)-(row['served'] & 255)) & 255
        if entered_not_committed>1:
            invalid.append({'offset':index,'entered_not_committed':entered_not_committed})
        if not 0 <= debts[-1] < 128:
            invalid.append({'offset': index, 'debt': debts[-1], 'required_range': [0,127]})
        max_owed_low = max(max_owed_low, row.get('max_owed', 0) & 255)
        if (row.get('max_owed', 0) & 255) >= 128:
            invalid.append({'offset': index, 'max_owed_low': row['max_owed'] & 255})
        for name in names:
            expected_word = (first[name]+totals[name]) & 65535
            if row[name] != expected_word:
                word_unknowns.append({'offset': index, 'counter': name, 'raw16': row[name],
                    'word_from_initial_anchor_and_atomic_delta': expected_word,
                    'classification': 'torn-or-unknown-high-word'})
        observations.append({'offset': index, 'low_bytes': {name: row[name] & 255 for name in row},
                             'relative_counts': dict(totals), 'outstanding_slots': debts[-1]})
    elapsed = frames/fps
    expected_services = frames*2
    expected_ticks = elapsed*SOURCE_TIMER_HZ
    rate_ok = (abs(totals['interrupt']-expected_services) <= 1 and
               abs(totals['due']-expected_services) <= 1 and
               abs(totals['tick']-expected_ticks) <= 2)
    result = {
        'classification': 'inconclusive-atomic-bound' if invalid else 'passed' if rate_ok else 'failed-tempo',
        'measurement_method': 'protocolv2 bounded atomic-low-byte observation; raw high words are not repaired',
        'elapsed_emulated_seconds': elapsed,
        'counter_before': first, 'counter_after': counters[-1],
        'counter_deltas': totals,
        'raw16_endpoint_deltas': {name: (counters[-1][name]-first[name]) & 65535 for name in first},
        'expected_service_calls': expected_services, 'expected_source_ticks': expected_ticks,
        'measured_service_hz': totals['interrupt']/elapsed,
        'measured_source_tick_hz': totals['tick']/elapsed,
        'unadjusted_service_count_error': totals['interrupt']-expected_services,
        'unadjusted_source_tick_count_error': totals['tick']-expected_ticks,
        'unadjusted_source_rate_error_hz': totals['tick']/elapsed-SOURCE_TIMER_HZ,
        'atomic_bound_violations': invalid, 'observed_per_hostframe_peaks': peaks,
        'raw_word_observation_status': 'torn-or-unknown-high-words-present' if word_unknowns else 'consistent-with-atomic-deltas',
        'raw_word_inconsistencies': word_unknowns,
        'scheduler_debt': {'before': initial_debt, 'after': debts[-1], 'maximum_observed': max(debts),
            'minimum_observed': min(debts), 'max_owed_low_diagnostic': max_owed_low,
            'late_calls_delta': totals.get('late_calls'), 'late_requests_delta': totals.get('late_requests')},
        'strict_wallclock_target': True,
        'scope': 'Bounded atomic-byte counter deltas qualify the rate. Raw16-bit tears remain unknown diagnostics; no pending debt is added to measured rates.',
    }
    return result, observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cartridge', 'core', 'sessions-root', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--protocol', choices=('raw-v1','atomic-low-v2'), default='raw-v1')
    parser.add_argument('--measured-host-intervals', type=int)
    args = parser.parse_args()
    intervals = args.measured_host_intervals if args.measured_host_intervals is not None else (3000 if args.protocol=='atomic-low-v2' else 549)
    if intervals < (3000 if args.protocol=='atomic-low-v2' else 1):parser.error('measurement window below protocol minimum')
    cartridge, core = Path(args.cartridge).resolve(), Path(args.core).resolve()
    original, out = Path(args.sessions_root).resolve(), _private_output(args.output)
    out.mkdir()
    manifest = json.loads(cartridge.with_name('manifest.json').read_text())
    if sha(cartridge.read_bytes()) != manifest['rom_sha256'] or sha(core.read_bytes()) != NES_SHA:
        parser.error('cartridge or core identity mismatch')
    labels = cartridge.parent/'build/labels.txt'
    symbols = {name: int(value, 16) for value, name in re.findall(
        r'^al\s+([0-9A-Fa-f]+)\s+\.(_[A-Za-z0-9_]+)$', labels.read_text(), re.M)}
    addresses = {name: symbols[symbol] for name, symbol in CLOCK_SYMBOLS.items() if symbol in symbols}
    if not {'interrupt', 'tick'} <= addresses.keys():
        raise ValueError('audio service/tick counters missing')
    optional = set(CLOCK_SYMBOLS)-{'interrupt', 'tick'}
    if addresses.keys() & optional and not optional <= addresses.keys():
        raise ValueError('incomplete scheduler telemetry symbols')
    counter_watches = []
    for name, address in addresses.items():
        if 0x6000 <= address < 0x7fff:
            memory_id, offset = 0, address-0x6000
        elif 0 <= address < 0x7ff:
            memory_id, offset = 2, address
        else:
            raise ValueError('counter outside supported native RAM mapping: '+name)
        counter_watches.append({'name': 'clock_'+name, 'memory_id': memory_id, 'offset': offset, 'length': 2})
    frozen = {str(p): sha(p.read_bytes()) for p in (cartridge, core, labels)}
    report = {'format': 'miniplanets-normal-native-audio-tempo-2', 'status': 'running',
        'cartridge_sha256': manifest['rom_sha256'], 'core_sha256': NES_SHA,
        'labels_sha256': sha(labels.read_bytes()), 'counter_cpu_addresses': addresses,
        'source_timer_hz': SOURCE_TIMER_HZ, 'verifier_sha256': sha(Path(__file__).read_bytes()), 'sessions': []}
    if args.protocol=='atomic-low-v2':
        report['protocol']=ATOMIC_LOW_PROTOCOL
        report['protocol_sha256']=sha(json.dumps(ATOMIC_LOW_PROTOCOL,sort_keys=True,separators=(',',':')).encode())
        save(out/'protocol-before-run.json',ATOMIC_LOW_PROTOCOL)
    try:
        names = [p.name for p in sorted(original.glob('performance-stage-*')) if p.is_dir()]
        names.append('feedback-route')
        for name in names:
            folder = original/name
            before = json.loads((folder/'receipt.json').read_text())
            if before['rom_sha256'] != manifest['rom_sha256'] or before['core_sha256'] != NES_SHA:
                raise ValueError('original schedule is bound to another executable/core')
            old_trace = json.loads((folder/'ram_trace.json').read_text())
            masks = [r['input_mask'] for r in old_trace['frames']]
            receipt, trace, wall = run_host(core, cartridge, out/name, len(masks),
                [*old_trace['watches'], *counter_watches], patches=before['patches'],
                inputs=compressed_inputs(masks, before['input_map']))
            if receipt['frame_rgb_sha256'] != before['frame_rgb_sha256']:
                raise AssertionError('controller schedule replay changed the final video state')
            if len(old_trace['frames']) != len(trace['frames']):
                raise AssertionError('controller schedule replay changed the frame count')
            for old, new in zip(old_trace['frames'], trace['frames']):
                if old['input_mask'] != new['input_mask'] or old['frame'] != new['frame']:
                    raise AssertionError('controller callback replay differs')
                if any(new['raw'][k] != value for k, value in old['raw'].items()):
                    raise AssertionError(f'CPU state replay differs in {name}, frame {old["frame"]}')
            rows = trace['frames']
            start, end = 100, 100+intervals
            if end>=len(rows):raise ValueError('fresh session is too short for the declared measurement window')
            counters = [{key: int.from_bytes(bytes.fromhex(row['raw']['clock_'+key]), 'little')
                         for key in addresses} for row in rows[start:end+1]]
            if args.protocol=='atomic-low-v2':
                stats,observations=atomic_clock_statistics(counters,end-start,receipt['fps'])
                save(out/(name+'-atomic-low-observations.json'),observations)
                stats['atomic_observations_sha256']=sha((out/(name+'-atomic-low-observations.json')).read_bytes())
            else:stats=clock_statistics(counters,end-start,receipt['fps'])
            entry = {'name': name, 'host_start': start, 'host_end': end,
                'elapsed_wall_seconds': wall, 'state_and_controller_replay_identical': True,
                'trace_sha256': receipt['ram_trace_sha256'],
                **stats}
            report['sessions'].append(entry)
            print(name, entry['counter_deltas']['interrupt'], entry['counter_deltas']['tick'],
                round(entry['measured_source_tick_hz'], 6), 'Hz', entry['classification'], flush=True)
        report['inputs_unchanged'] = all(sha(Path(path).read_bytes()) == digest for path, digest in frozen.items())
        report['status'] = ('input-changed' if not report['inputs_unchanged'] else
            'passed' if all(s['classification'] == 'passed' for s in report['sessions']) else 'failed')
    except Exception as exc:
        report['status'] = 'failed'
        report['failure'] = str(exc)
        raise
    finally:
        save(out/'summary.json', report)
    print(json.dumps(report, indent=2))
    if report['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
