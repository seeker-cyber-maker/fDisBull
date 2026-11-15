#!/usr/bin/env python3
"""Read-only storage admission for one local-hub/GitLab mirror growth phase.

The canonical storage helper checks the cache destination and internal reserve.
This command also checks the separate hub destination. Free-space figures are
never added: each destination must independently retain its requested reserve
after the conservative expected allocation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


FORMAT = 'fdisbull-mirror-storage-1'
TARGET = 40_000_000_000
FLOOR = 20_000_000_000
MAX_TIMEOUT = 5
MAX_REPLY_BYTES = 65_536


def _integer(value, name, *, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return value


def _path(value, name, *, directory=False, file=False):
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f'{name} must be an absolute path')
    resolved = path.resolve(strict=True)
    if directory and not resolved.is_dir():
        raise ValueError(f'{name} must be an existing directory')
    if file and not resolved.is_file():
        raise ValueError(f'{name} must be an existing file')
    return resolved


def _run(command, timeout):
    try:
        return subprocess.run(command, capture_output=True, text=True,
                              timeout=timeout, check=False,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    except subprocess.TimeoutExpired as exc:
        raise ValueError('admission subprocess timed out') from exc
    except OSError as exc:
        raise ValueError('admission subprocess could not start') from exc


def _bare_hub(hub, timeout):
    git = shutil.which('git')
    if git is None:
        raise ValueError('Git is unavailable for bare hub validation')
    result = _run([git, '--git-dir', str(hub), 'rev-parse', '--is-bare-repository'], timeout)
    if result.returncode != 0 or result.stdout.strip() != 'true':
        raise ValueError('hub must be an existing bare Git repository')


def _canonical_receipt(raw, cache, expected, reserve):
    if len(raw.encode('utf-8')) > MAX_REPLY_BYTES:
        raise ValueError('canonical storage receipt exceeds the response limit')
    try:
        receipt = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError('canonical storage receipt is not JSON') from exc
    if not isinstance(receipt, dict):
        raise ValueError('canonical storage receipt must be an object')
    required = ('admitted', 'path', 'expected_bytes', 'destination_target_bytes',
                'destination_pool_free_bytes', 'destination_minimum_bytes',
                'internal_free_bytes', 'internal_minimum_bytes', 'reasons')
    if any(key not in receipt for key in required):
        raise ValueError('canonical storage receipt is incomplete')
    if (type(receipt['admitted']) is not bool or receipt['path'] != str(cache)
            or type(receipt['expected_bytes']) is not int or receipt['expected_bytes'] != expected
            or type(receipt['destination_target_bytes']) is not int
            or receipt['destination_target_bytes'] != reserve):
        raise ValueError('canonical storage receipt does not match the request')
    for name in ('destination_pool_free_bytes', 'destination_minimum_bytes',
                 'internal_free_bytes', 'internal_minimum_bytes'):
        if type(receipt[name]) is not int or receipt[name] < 0:
            raise ValueError('canonical storage receipt contains invalid free-space data')
    reasons = receipt['reasons']
    if not isinstance(reasons, list) or any(type(reason) is not str or not reason for reason in reasons):
        raise ValueError('canonical storage receipt has invalid reasons')
    if receipt['admitted'] == bool(reasons):
        raise ValueError('canonical storage receipt admission and reasons disagree')
    if (receipt['destination_minimum_bytes'] < FLOOR
            or receipt['internal_minimum_bytes'] < FLOOR
            or receipt['destination_pool_free_bytes'] - expected < reserve
            or receipt['internal_free_bytes'] < receipt['internal_minimum_bytes']):
        if receipt['admitted']:
            raise ValueError('canonical storage receipt contradicts the required reserve')
    return receipt


def evaluate(admission_script, path, hub, expected_bytes, destination_reserve_bytes=TARGET,
             timeout_seconds=MAX_TIMEOUT):
    """Return a bounded, inspectable admission decision without writing files."""
    decision = {'format': FORMAT, 'admitted': False, 'expected_bytes': expected_bytes,
                'reserve_bytes': destination_reserve_bytes, 'cache_path': str(path),
                'hub_path': str(hub), 'reasons': []}
    try:
        expected = _integer(expected_bytes, 'expected_bytes', minimum=1)
        reserve = _integer(destination_reserve_bytes, 'destination_reserve_bytes', minimum=TARGET)
        timeout = _integer(timeout_seconds, 'timeout_seconds', minimum=1)
        if timeout > MAX_TIMEOUT:
            raise ValueError(f'timeout_seconds must be <= {MAX_TIMEOUT}')
        script = _path(admission_script, 'admission_script', file=True)
        cache = _path(path, 'path', directory=True)
        hub_path = _path(hub, 'hub', directory=True)
        decision['cache_path'], decision['hub_path'] = str(cache), str(hub_path)
        _bare_hub(hub_path, timeout)
    except (ValueError, OSError) as exc:
        decision['reasons'].append(str(exc))
        return decision

    command = [sys.executable, str(script), '--path', str(cache),
               '--expected-bytes', str(expected), '--destination-reserve-bytes', str(reserve)]
    try:
        result = _run(command, timeout)
        receipt = _canonical_receipt(result.stdout, cache, expected, reserve)
        decision['cache_receipt'] = {
            key: receipt[key] for key in ('admitted', 'path', 'expected_bytes',
                                          'destination_pool_free_bytes', 'destination_target_bytes',
                                          'destination_minimum_bytes', 'internal_free_bytes',
                                          'internal_minimum_bytes')}
        if result.returncode != 0:
            decision['reasons'].append('canonical storage helper returned nonzero')
        if not receipt['admitted']:
            decision['reasons'].extend(receipt['reasons'])
    except (ValueError, OSError) as exc:
        decision['reasons'].append(str(exc))

    try:
        stat = os.statvfs(hub_path)
        free = stat.f_bavail * stat.f_frsize
        if type(free) is not int or free < 0:
            raise ValueError('hub free-space observation is invalid')
        after = free - expected
        decision['hub_receipt'] = {'free_bytes': free, 'after_expected_bytes': after,
                                   'reserve_bytes': reserve, 'minimum_bytes': FLOOR}
        if after < reserve or after < FLOOR:
            decision['reasons'].append('hub expected allocation would violate its free-space reserve')
    except (ValueError, OSError) as exc:
        decision['reasons'].append(str(exc))

    decision['admitted'] = not decision['reasons']
    return decision


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admission-script', required=True)
    parser.add_argument('--path', required=True)
    parser.add_argument('--hub', required=True)
    parser.add_argument('--expected-bytes', required=True, type=int)
    parser.add_argument('--destination-reserve-bytes', type=int, default=TARGET)
    parser.add_argument('--timeout-seconds', type=int, default=MAX_TIMEOUT)
    args = parser.parse_args(argv)
    result = evaluate(args.admission_script, args.path, args.hub, args.expected_bytes,
                      args.destination_reserve_bytes, args.timeout_seconds)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0 if result['admitted'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
