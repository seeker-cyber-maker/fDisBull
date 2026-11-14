"""Storage admission contracts without invoking the user's live helper."""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import mirror_storage_admit as admit


@pytest.fixture
def paths(tmp_path):
    cache_parent = tmp_path / 'cache-parent'
    cache_parent.mkdir()
    hub = tmp_path / 'hub.git'
    subprocess.run(['git', 'init', '--bare', str(hub)], capture_output=True, check=True)
    script = tmp_path / 'storage_admit.py'
    script.write_text('# fake helper for tests\n')
    return script, cache_parent, hub


def receipt(cache, expected, reserve, *, free=None, admitted=True, reasons=None):
    return {'admitted': admitted, 'path': str(cache), 'expected_bytes': expected,
            'destination_target_bytes': reserve,
            'destination_pool_free_bytes': reserve + expected if free is None else free,
            'destination_minimum_bytes': admit.FLOOR,
            'internal_free_bytes': reserve, 'internal_minimum_bytes': admit.FLOOR,
            'reasons': [] if reasons is None else reasons}


def fake_boundaries(monkeypatch, cache_receipt, hub_free, *, helper_exit=0, helper_text=None,
                    helper_timeout=False):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs['timeout'] <= admit.MAX_TIMEOUT
        if 'rev-parse' in command:
            return subprocess.CompletedProcess(command, 0, 'true\n', '')
        assert command[0] == sys.executable and '--expected-bytes' in command
        if helper_timeout:
            raise subprocess.TimeoutExpired(command, kwargs['timeout'])
        return subprocess.CompletedProcess(command, helper_exit,
                                           json.dumps(cache_receipt) if helper_text is None else helper_text,
                                           '')

    monkeypatch.setattr(admit.subprocess, 'run', run)
    monkeypatch.setattr(admit.os, 'statvfs',
                        lambda path: SimpleNamespace(f_bavail=hub_free, f_frsize=1))
    return calls


def test_each_pool_must_independently_keep_the_reserve(monkeypatch, paths):
    script, cache, hub = paths
    expected, reserve = 3_000_000_000, admit.TARGET
    calls = fake_boundaries(monkeypatch, receipt(cache, expected, reserve, free=60_000_000_000),
                            hub_free=reserve + expected - 1)
    result = admit.evaluate(script, cache, hub, expected, reserve)
    assert result['admitted'] is False
    assert result['cache_receipt']['destination_pool_free_bytes'] == 60_000_000_000
    assert result['hub_receipt']['after_expected_bytes'] == reserve - 1
    assert result['reasons'] == ['hub expected allocation would violate its free-space reserve']
    assert len(calls) == 2


def test_exact_reserve_boundary_is_admitted(monkeypatch, paths):
    script, cache, hub = paths
    expected, reserve = 9, admit.TARGET
    fake_boundaries(monkeypatch, receipt(cache, expected, reserve), reserve + expected)
    result = admit.evaluate(script, cache, hub, expected, reserve)
    assert result['admitted'] is True
    assert result['reasons'] == []
    assert result['cache_receipt']['destination_pool_free_bytes'] == reserve + expected
    assert result['hub_receipt']['after_expected_bytes'] == reserve


@pytest.mark.parametrize('failure', ['malformed', 'nonzero', 'timeout', 'mismatched'])
def test_helper_failure_never_admits(monkeypatch, paths, failure):
    script, cache, hub = paths
    expected, reserve = 1, admit.TARGET
    helper_text = '{' if failure == 'malformed' else None
    helper_exit = 2 if failure == 'nonzero' else 0
    report = receipt(cache, expected + 1 if failure == 'mismatched' else expected, reserve)
    fake_boundaries(monkeypatch, report, reserve + expected + 1,
                    helper_exit=helper_exit, helper_text=helper_text,
                    helper_timeout=failure == 'timeout')
    result = admit.evaluate(script, cache, hub, expected, reserve)
    assert result['admitted'] is False
    assert result['reasons']
    assert result['hub_receipt']['after_expected_bytes'] >= reserve


def test_below_target_reserve_and_nonbare_hub_are_rejected(paths):
    script, cache, hub = paths
    assert admit.evaluate(script, cache, hub, 1, admit.TARGET - 1)['admitted'] is False
    assert admit.evaluate(script, cache, cache, 1)['admitted'] is False


def test_real_subprocess_boundary_with_safe_fake_helper(monkeypatch, paths):
    script, cache, hub = paths
    script.write_text(
        'import argparse, json, os\n'
        'p=argparse.ArgumentParser()\n'
        'p.add_argument("--path", required=True)\n'
        'p.add_argument("--expected-bytes", type=int, required=True)\n'
        'p.add_argument("--destination-reserve-bytes", type=int, required=True)\n'
        'a=p.parse_args()\n'
        'print(json.dumps(dict(admitted=True,path=os.path.realpath(a.path),'
        'expected_bytes=a.expected_bytes,destination_target_bytes=a.destination_reserve_bytes,'
        'destination_pool_free_bytes=a.destination_reserve_bytes+a.expected_bytes,'
        'destination_minimum_bytes=20000000000,internal_free_bytes=40000000000,'
        'internal_minimum_bytes=20000000000,reasons=[])))\n'
    )
    monkeypatch.setattr(admit.os, 'statvfs',
                        lambda path: SimpleNamespace(f_bavail=admit.TARGET + 7, f_frsize=1))
    result = admit.evaluate(script, cache, hub, 7)
    assert result['admitted'] is True
    assert result['cache_receipt']['path'] == str(cache.resolve())
    assert result['hub_receipt']['after_expected_bytes'] == admit.TARGET
