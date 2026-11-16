"""Guest-visible calendar continuation across two stopped native captures.

Uses the SB16 native selectors, retaining that graph while observing CMOS
through genuine guest port I/O. No launch-argument/config assertion substitutes
for behavior: the old host-clock prefix can run this same regression and fail.
Only root runs native guests. The one host wait is deliberate and bounded.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from support.qemu_rtc_fixture import rtc_calendar
from test_qemu_clock_budget_native import park
from test_qemu_dos_process_native import assert_completion, com_address, read_bytes
from test_qemu_sb16_native import _launch, _runtime


def _calendar(raw):
    assert len(raw) == 8
    sec, minute, hour, day, month, year, century, mode = raw
    binary, clock24 = bool(mode & 4), bool(mode & 2)

    def number(value):
        if binary:
            return value
        assert value & 15 <= 9 and value >> 4 <= 9, 'Invalid guest BCD calendar'
        return (value >> 4) * 10 + (value & 15)

    pm = bool(hour & 128)
    hour = number(hour & 127)
    if not clock24:
        assert 1 <= hour <= 12
        hour = hour % 12 + (12 if pm else 0)
    stamp = datetime(number(century) * 100 + number(year), number(month), number(day),
                     hour, number(minute), number(sec), tzinfo=timezone.utc)
    return list(stamp.timetuple()[:6])


def _seconds(calendar):
    return int(datetime(*calendar, tzinfo=timezone.utc).timestamp())


def _symbols(debug, offsets):
    info = debug.dos_process_info()
    assert info['state'] == 'active'
    return {name: com_address(info, offset) for name, offset in offsets.items()
            if name != 'report_size'}


def _state(debug, symbols, offsets):
    clock = debug.clock_observe()
    raw = read_bytes(debug, symbols['report'], offsets['report_size'])
    assert raw[:4] == b'RTC1'
    return dict(cpu=debug.registers(), report_hex=raw.hex(),
        virtual_ns=clock['virtual_ns'], icount=clock['counter']['value'],
        baseline=_calendar(raw[4:12]), later=_calendar(raw[12:20]) if raw[12:20] != bytes(8) else None,
        stage=int.from_bytes(raw[20:22], 'little'))


def _future(debug, offsets):
    symbols = _symbols(debug, offsets)
    park(debug, symbols['sampled'])
    state = _state(debug, symbols, offsets)
    assert state['stage'] == 2
    return state


def test_native_rtc_calendar_preserves_stopped_time_and_both_checkpoint_continuations(tmp_path):
    runtime = _runtime()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'rtc-boot.img',
        runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    code, offsets = rtc_calendar(tmp_path, runtime['NASM'])
    source = tmp_path / 'RTC.COM'
    source.write_bytes(code)
    report = dict(format='fdisbull-authored-rtc-checkpoint-native-1', success=False,
                  host_wait_seconds=2.2, captures={}, futures={}, immediate_restores={})
    try:
        with Project.create(tmp_path / 'rtc.fdb', source, image='com') as project:
            with _launch(project, runtime, tmp_path, disk) as debug:
                symbols = _symbols(debug, offsets)
                park(debug, symbols['ready'])
                original = _state(debug, symbols, offsets)
                assert original['stage'] == 1 and original['later'] is None
                report['captured'] = original
                first = debug.save_state('rtc-first.state')
                report['captures']['first'] = first
                # Host time must not advance the guest RTC while virtual time
                # and its instruction counter remain stopped.
                start = time.monotonic()
                time.sleep(2.2)
                report['actual_host_wait_seconds'] = time.monotonic() - start
                assert report['actual_host_wait_seconds'] >= 2.1
                paused = _state(debug, symbols, offsets)
                assert paused == original
                second = debug.save_state('rtc-second.state')
                report['captures']['second'] = second
                assert _state(debug, symbols, offsets) == original
                report['futures']['original'] = _future(debug, offsets)
                for label, saved in (('first', first), ('second', second)):
                    old = debug.vm.process
                    epoch = debug.dos_process_info()['capture_epoch']
                    restored = debug.load_state(saved['artifact'])
                    assert restored['source_binding_restored'] is True
                    assert old.poll() is not None and debug.vm.process is not old
                    assert debug.vm.process.poll() is None
                    assert debug.dos_process_info()['capture_epoch'] != epoch
                    symbols = _symbols(debug, offsets)
                    initial = _state(debug, symbols, offsets)
                    report['immediate_restores'][label] = dict(receipt=restored, state=initial)
                    assert initial == original
                    report['futures'][label] = _future(debug, offsets)
                # Compare the actual calendar and arithmetic, including rollover
                # across a minute/day/year. A subsecond execution interval may
                # cross one calendar-second boundary; a host wait must not add2.
                expected = report['futures']['original']
                for label, future in report['futures'].items():
                    elapsed = future['virtual_ns'] - original['virtual_ns']
                    assert 0 < elapsed < 1_000_000_000, (label, elapsed)
                    calendar_delta = _seconds(future['later']) - _seconds(original['baseline'])
                    assert calendar_delta in (0, 1), (label, calendar_delta, future)
                    assert future['baseline'] == original['baseline']
                    assert future['later'] == expected['later'], label
                    assert future['report_hex'] == expected['report_hex'], label
                    assert future['virtual_ns'] == expected['virtual_ns'], label
                    assert future['icount'] == expected['icount'], label
                lease = debug.keyboard_key_down('q')['lease']
                debug.keyboard_key_up(lease)
                assert_completion(debug, debug.run(timeout_ms=5000), exit_code=42)
                owner = debug.vm.process
            assert owner.poll() is not None
        report['success'] = True
    finally:
        assert source.read_bytes() == code
        assert digest(boot) == boot_hash
        assert digest(disk['image']) == disk['prepared_sha256']
        (tmp_path / 'native-rtc-checkpoint.json').write_text(
            json.dumps(report, indent=2, sort_keys=True) + '\n')
