#!/usr/bin/env python3
"""One-shot adoption of the pinned OVH health decision; no monitoring loop."""
import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
import subprocess

HELPER = Path('/usr/local/libexec/health_decision.py')
HELPER_SHA256 = '34a5b8a626fc796df252e77946e50bd9a96dec678084649a80791618416d03d8'
TIMEOUT_SECONDS = 55
MAX_RECORD_BYTES = 65536


def _valid(record):
    # Structural validation is not a second evaluation of the health policy.
    if type(record) is not dict:
        return False
    required = {'schema_version', 'healthy', 'observed_epoch', 'read_only',
                'model_required', 'components', 'failures', 'receipt'}
    optional = {'free_bytes', 'snapshot_observed_epoch', 'snapshot_age_seconds', 'disk'}
    if not required <= record.keys() or record.keys() - required - optional:
        return False
    if (type(record['schema_version']) is not int or record['schema_version'] != 1
            or type(record['healthy']) is not bool or type(record['read_only']) is not bool
            or type(record['model_required']) is not bool):
        return False
    def number(value):
        return value is None or type(value) in (int, float) and math.isfinite(value)
    if not all(number(record.get(k)) for k in ('observed_epoch', 'free_bytes', 'snapshot_observed_epoch', 'snapshot_age_seconds')):
        return False
    def token(value):
        return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_]{1,128}', value) is not None
    def failures(value):
        return (type(value) is list and all(type(item) is dict and set(item) == {'component', 'reason'}
                and isinstance(item['component'], str) and item['component'] in components | {'snapshot', 'disk'}
                and token(item['reason']) for item in value))
    components = {'doctor', 'n8n_readiness', 'n8n_service', 'n8n_mcp',
                  'n8n_monitor_workflow', 'n8n_assistant_key',
                  'https://www.brewsterjennings.ca/', 'https://release.brewsterjennings.ca/'}
    items = record['components']
    if type(items) is not dict or not set(items) <= components or not failures(record['failures']):
        return False
    # Acquisition failures have an empty inventory and cannot be healthy.
    if items:
        if set(items) != components or not optional <= record.keys():
            return False
    elif record['healthy'] or 'disk' in record:
        return False
    for item in items.values():
        if (type(item) is not dict or not {'state', 'reason', 'checked_epoch', 'age_seconds',
                'fresh', 'requires_source_freshness', 'failures'} <= item.keys()
                or item.keys() - {'state', 'reason', 'checked_epoch', 'age_seconds', 'fresh',
                                  'requires_source_freshness', 'failures', 'http_status', 'transport_cause'}
                or item['state'] not in ('healthy', 'unhealthy', 'unknown') or not token(item['reason'])
                or not number(item['checked_epoch']) or not number(item['age_seconds'])
                or 'http_status' in item and (type(item['http_status']) is not int or not 100 <= item['http_status'] <= 599)
                or type(item['requires_source_freshness']) is not bool
                or item['fresh'] is not None and type(item['fresh']) is not bool
                or type(item['failures']) is not list or not all(token(x) for x in item['failures'])
                or 'transport_cause' in item and not token(item['transport_cause'])):
            return False
    if 'disk' in record:
        disk = record['disk']
        if (type(disk) is not dict or set(disk) != {'state', 'free_bytes', 'minimum_free_bytes', 'failures'}
                or disk['state'] not in ('known', 'unknown') or not number(disk['free_bytes'])
                or not number(disk['minimum_free_bytes']) or type(disk['failures']) is not list
                or not all(token(x) for x in disk['failures'])):
            return False
    receipt = record['receipt']
    if type(receipt) is not dict or type(receipt.get('durable')) is not bool:
        return False
    if receipt['durable']:
        return (set(receipt) == {'journal', 'sequence', 'sha256', 'durable'}
                and receipt['journal'] == '/var/lib/operations-health/decisions.sqlite'
                and type(receipt['sequence']) is int and receipt['sequence'] > 0
                and isinstance(receipt['sha256'], str)
                and re.fullmatch(r'[0-9a-f]{64}', receipt['sha256']) is not None)
    return set(receipt) == {'durable', 'reason'} and receipt['reason'] == 'diagnostic_persistence_unavailable'


def _persist(path, payload):
    """Create a bounded, exclusive receipt and sync both file and directory."""
    data = (json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError('receipt too large')
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def capture_health(receipt_path, *, helper=HELPER, expected_sha256=HELPER_SHA256,
                   runner=subprocess.run):
    """Capture one decision, durably record it, then return a fail-closed gate.

    The default helper and digest are the adopted production contract. Injectable
    parameters support isolated boundary tests; callers must use production defaults.
    The parent receipt directory must exist; an existing receipt is never replaced.
    """
    record = None
    reason = None
    try:
        digest = hashlib.sha256(Path(helper).read_bytes()).hexdigest()
        if digest != expected_sha256:
            reason = 'helper_hash_mismatch'
        else:
            result = runner(['/usr/bin/python3', str(helper)], capture_output=True,
                            timeout=TIMEOUT_SECONDS, check=False)
            if result.returncode != 0:
                reason = 'helper_process_failed'
            elif not isinstance(result.stdout, bytes) or len(result.stdout) > MAX_RECORD_BYTES:
                reason = 'helper_output_invalid'
            else:
                try:
                    candidate = json.loads(result.stdout, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    if not _valid(candidate):
                        reason = 'helper_schema_invalid'
                    else:
                        record = candidate
                except (ValueError, UnicodeDecodeError, RecursionError):
                    reason = 'helper_json_invalid'
    except subprocess.TimeoutExpired:
        reason = 'helper_timeout'
    except OSError:
        reason = 'helper_unavailable'
    except (TypeError, AttributeError, ValueError):
        reason = 'helper_protocol_invalid'
    payload = {'format': 'fdisbull-offline-health-gate-1', 'helper_sha256': expected_sha256,
               'record': record, 'failure': reason}
    try:
        _persist(receipt_path, payload)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        return {'continue': False, 'reason': 'caller_receipt_unavailable'}
    if reason is not None:
        return {'continue': False, 'reason': reason}
    if record['receipt']['durable'] is not True:
        return {'continue': False, 'reason': 'helper_receipt_not_durable'}
    if record['healthy'] is not True:
        return {'continue': False, 'reason': 'unhealthy'}
    return {'continue': True, 'reason': 'healthy_and_durable'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True, help='new receipt path in an existing per-run directory')
    args = parser.parse_args()
    result = capture_health(args.receipt)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['continue'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
