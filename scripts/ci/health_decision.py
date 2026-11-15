"""Credential-free CI health decisions. No recovery actions or model calls."""
from contextlib import closing
import errno
import hashlib
import json
import math
from pathlib import Path
import socket
import sqlite3
import ssl
import subprocess
import time
import urllib.error

N8N = ('n8n_service', 'n8n_mcp', 'n8n_monitor_workflow', 'n8n_assistant_key')
SITES = ('https://www.brewsterjennings.ca/', 'https://release.brewsterjennings.ca/')
REASONS = frozenset('''observation_unavailable state_unavailable local_status_failed NeedsLogin NeedsMachineAuth
backend_stopped backend_not_running no_local_tailnet_address interface_missing home_ssh_banner_unavailable
home_ssh_service_refused home_peer_offline_or_unknown online_home_peer_path_unreachable home_ssh_reachable
local_status_timeout local_status_unreadable n8n_ready n8n_not_ready mcp_authorized mcp_invalid_response
mcp_unauthorized n8n_http_error n8n_unreachable mcp_probe_failed mcp_token_missing operations_workflow_disabled
operations_monitor_missing operations_monitor_stale operations_monitor_success operations_monitor_failed
assistant_credential_missing credential_probe_failed assistant_key_unauthorized assistant_key_expired
assistant_key_budget_exhausted assistant_key_authorized assistant_provider_unavailable n8n_database_unreadable
http_ok http_not_ok probe_unavailable'''.split())
TRANSPORT = frozenset(('timeout', 'dns_failure', 'tls_failure', 'connection_refused', 'network_unreachable', 'transport_unavailable'))
JOURNAL = Path('/var/lib/operations-health/decisions.sqlite')
MAX_RECORD_BYTES = 16384
MAX_JOURNAL_BYTES = 16 * 1024 * 1024


def number(v):
    return type(v) in (int, float) and math.isfinite(v) and abs(v) <= 10**16


def transport_cause(error):
    # Never stringify exceptions: URLs, response bodies or credentials can occur there.
    if isinstance(error, urllib.error.URLError):
        error = error.reason
    if isinstance(error, (TimeoutError, socket.timeout)):
        return 'timeout'
    if isinstance(error, socket.gaierror):
        return 'dns_failure'
    if isinstance(error, ssl.SSLError):
        return 'tls_failure'
    if isinstance(error, ConnectionRefusedError):
        return 'connection_refused'
    if isinstance(error, OSError) and error.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
        return 'network_unreachable'
    return 'transport_unavailable'


def component(value, now, require_fresh):
    x = value if isinstance(value, dict) else {}
    state = x.get('state') if x.get('state') in ('healthy', 'unhealthy', 'unknown') else 'unknown'
    checked = x.get('checked_epoch') if number(x.get('checked_epoch')) else None
    age = now - checked if checked is not None else None
    reason = x.get('reason') if isinstance(x.get('reason'), str) and x['reason'] in REASONS else 'source_reason_unrecognized'
    failures = []
    if not isinstance(value, dict): failures.append('component_missing_or_invalid')
    if state != 'healthy': failures.append('state_not_healthy')
    if checked is None: failures.append('sample_time_missing_or_invalid')
    elif age < 0: failures.append('sample_time_in_future')
    elif age > 660: failures.append('sample_older_than_660s')
    if require_fresh and x.get('fresh') is not True: failures.append('source_freshness_not_true')
    fresh = x.get('fresh') if type(x.get('fresh')) is bool else None
    out = {'state': state, 'reason': reason, 'checked_epoch': checked, 'age_seconds': age,
           'fresh': fresh, 'requires_source_freshness': require_fresh, 'failures': failures}
    if type(x.get('http_status')) is int and 100 <= x['http_status'] <= 599: out['http_status'] = x['http_status']
    if isinstance(x.get('transport_cause'), str) and x['transport_cause'] in TRANSPORT: out['transport_cause'] = x['transport_cause']
    return out


def evaluate(value, now=None, free_bytes=None):
    now = time.time() if now is None else now
    if not number(now): raise ValueError('invalid decision time')
    value = value if isinstance(value, dict) else {}
    checks = value.get('health_checks') if isinstance(value.get('health_checks'), dict) else {}
    sites = value.get('websites') if isinstance(value.get('websites'), dict) else {}
    named = {'doctor': component(value.get('doctor_observation'), now, True),
             'n8n_readiness': component(value.get('n8n_readiness'), now, False)}
    named.update({k: component(checks.get(k), now, True) for k in N8N})
    named.update({k: component(sites.get(k), now, False) for k in SITES})
    observed = value.get('observed_epoch') if number(value.get('observed_epoch')) else None
    snapshot_age = now-observed if observed is not None else None
    failures = []
    if value.get('read_only') is not True: failures.append({'component':'snapshot','reason':'read_only_not_true'})
    if value.get('model_required') is not False: failures.append({'component':'snapshot','reason':'model_free_not_true'})
    if snapshot_age is None or not 0 <= snapshot_age <= 120:
        failures.append({'component':'snapshot','reason':'snapshot_time_missing_future_or_older_than_120s'})
    # Reject extra components as a schema mismatch rather than silently skipping a former gate.
    if set(checks) != set(N8N) or set(sites) != set(SITES):
        failures.append({'component':'snapshot','reason':'component_inventory_mismatch'})
    for name, item in named.items():
        failures.extend({'component': name, 'reason': reason} for reason in item['failures'])
    disk = value.get('disk') if isinstance(value.get('disk'), dict) else {}
    disk_free = disk.get('free_bytes') if type(disk.get('free_bytes')) is int and disk['free_bytes'] >= 0 else None
    disk_failures = []
    if disk.get('state') != 'known': disk_failures.append('disk_state_not_known')
    if disk_free is None: disk_failures.append('disk_free_missing_or_invalid')
    # Free space is telemetry. Allocation and actual I/O errors belong to the
    # operation using the disk; a fixed reserve must not stop healthy CI.
    failures.extend({'component':'disk','reason':r} for r in disk_failures)
    return {'schema_version':1, 'healthy':not failures, 'observed_epoch':now,
            'free_bytes':free_bytes if type(free_bytes) is int and free_bytes >= 0 else None,
            'snapshot_observed_epoch':observed, 'snapshot_age_seconds':snapshot_age,
            'read_only':value.get('read_only') is True, 'model_required':value.get('model_required') is not False,
            'components':named, 'disk':{'state':'known' if disk.get('state')=='known' else 'unknown',
                'free_bytes':disk_free, 'minimum_free_bytes':None, 'failures':disk_failures},
            'failures':failures}


def failed_capture(reason, now=None):
    return {'schema_version':1, 'healthy':False, 'observed_epoch':time.time() if now is None else now,
            'components':{}, 'failures':[{'component':'snapshot','reason':reason}],
            'read_only':True, 'model_required':False}


def persist(record, path=JOURNAL):
    """Append only, bounded 16 MiB SQLite journal. Never evict original evidence."""
    body=json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False)
    if len(body.encode()) > MAX_RECORD_BYTES: raise ValueError('diagnostic record too large')
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    import os
    fd=os.open(path,os.O_WRONLY|os.O_CREAT,0o600);os.close(fd)
    with closing(sqlite3.connect(str(path),timeout=5)) as db, db:
        db.execute('PRAGMA synchronous=FULL')
        page_size=db.execute('PRAGMA page_size').fetchone()[0]
        db.execute('PRAGMA max_page_count=%d' % (MAX_JOURNAL_BYTES//page_size))
        db.execute('CREATE TABLE IF NOT EXISTS decisions (seq INTEGER PRIMARY KEY, observed_epoch REAL NOT NULL, healthy INTEGER NOT NULL, sha256 TEXT NOT NULL, body TEXT NOT NULL)')
        digest=hashlib.sha256(body.encode()).hexdigest()
        cursor=db.execute('INSERT INTO decisions(observed_epoch,healthy,sha256,body) VALUES(?,?,?,?)',
                          (record['observed_epoch'],int(record['healthy']),digest,body))
        seq=cursor.lastrowid
    return {'journal':str(path),'sequence':seq,'sha256':digest,'durable':True}


def capture(*, journal=JOURNAL, runner=subprocess.run, clock=time.time):
    """Caller boundary: no stdout/stderr, exception message or raw snapshot in receipts."""
    try:
        run=runner(['/usr/bin/python3','/usr/local/libexec/operations-monitor.py','--snapshot'],
                   capture_output=True,text=True,timeout=45,check=False)
        if run.returncode: record=failed_capture('snapshot_process_failed',clock())
        elif not isinstance(run.stdout,str): record=failed_capture('snapshot_json_invalid',clock())
        elif len(run.stdout.encode()) > 262144: record=failed_capture('snapshot_output_too_large',clock())
        else:
            try: value=json.loads(run.stdout)
            except (ValueError,TypeError): record=failed_capture('snapshot_json_invalid',clock())
            else: record=evaluate(value,clock()) if isinstance(value,dict) else failed_capture('snapshot_schema_invalid',clock())
    except subprocess.TimeoutExpired: record=failed_capture('snapshot_timeout',clock())
    except OSError: record=failed_capture('snapshot_process_unavailable',clock())
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError): record=failed_capture('snapshot_schema_invalid',clock())
    try: record['receipt']=persist(record,journal)
    except (OSError,sqlite3.Error,ValueError):
        record['receipt']={'durable':False,'reason':'diagnostic_persistence_unavailable'}
        # Preserve health result; caller must fail closed if it cannot retain the decision.
    return record


if __name__ == '__main__':
    print(json.dumps(capture(),separators=(',',':'),allow_nan=False))
