"""Bounded, read-only reconciliation for one held GitHub dispatch intent.

The CLI accepts one exact operator request. It never retries, dispatches,
clears a provider stop, or changes the held action receipt.
"""
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import time
import uuid


HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('held_reconcile_transport', HERE / 'production_transport.py')
transport = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transport)

ACTION_KEY = 'induced-missing-policy-23fa9831-20261114-01'
REQUEST_SHA256 = 'ac8a51ab8263044d78cf1c5726fdbb19851c2824197534b2c90fee244dea219d'
PRESTATE_PATH = Path('/Volumes/CACHE/fdisbull-ci-builds/production-control-23fa9831-20261114/auth-hold/reconciliation-prestate.json')
PRESTATE_SHA256 = 'cd4326afdb1ce6dd848c6bba5b7e429c1168d2d82d834abb2089d0762ea4cf28'
GENESIS_READBACK_SHA256 = '7caaab32c161ff130ded5cebb5a901cc0e28a8b060aee214295516132a8d5e7f'
GENESIS_CONTROL_SHA = '23fa9831d9e55deb1204b693c70e4325176ab75e'
SOURCE_ACTIVATION_SHA256 = 'a712abb4f5802762107ff7eefed1be84e008ff2bad803eaa9fef1c85fcceef53'
V0341_UNCHANGED_SHA256 = '011f1b8cb281edda208026aee9cdb238b800b2d7'
DEPLOYED_BRIDGE_SHA256 = 'eb9b3bedbe9d0cfff61ddddbb46b48f907ad767cabd6df38947dd7108f88d335'
ACTION_RECEIPT_SHA256 = 'a420ce30cd10cecadd3440490a725d735dc5af427da1b5506c05dfe61adc8acf'
BATCH_RECEIPT_SHA256 = '74ee2d1dec6b7306d84c5be114cdc762b79d1e80389393835154e8a873ffb8b6'
ANCHOR_SHA256 = '44cc951ef345b1d1d55bb9c0a867ceff396f2c3473a8f9542fd3431c59e3fae6'
STATUS_SHA256 = 'bcc3d331db3f2d4cd604022edcdc212d8af701d4b6c9b5f85378f3133bdcb0d5'
INSTALLATION_SHA256 = '20c066321ae7533563d6599d6ef1d01270947619f4a60b65037d60a49ece2d1d'
HOST_INTENT_SHA256 = '9e6012270315af6d2ae383a80e179ec1050ad7a53627976e222342458c5a3da0'
SERVICE_ERROR_SHA256 = '690593255a3bef79888eebcb8caf765fe7bc113c09fae9eafb07b8389219d20f'
NATIVE_INVOCATION_ID = 'd1f5ecfe5d1d43b3b7a19cf41ec46585'
NATIVE_INVOCATION_PID = 545610
NATIVE_EXIT_CODE = 1
NATIVE_STARTED_EPOCH = 1794633631.518904
NATIVE_FINISHED_EPOCH = 1794633634.979659
PROVIDER_STOP_EPOCH = 1794633634.556402
PROVIDER_STOP_REASON = 'provider_authentication_required'
REPOSITORY = 'seeker-cyber-maker/fDisBull'
WORKFLOW_ID = 417757453
EXPECTED_LOGIN = 'seeker-cyber-maker'
MAX_GETS = 12
PAGE_SIZE = 100
MAX_PAGES = 10
MAX_RESPONSE_BYTES = 1024 * 1024
READ_RECORD_PREFIX = '__held_canonical_read__:'


class ReconciliationUnknown(RuntimeError):
    """The evidence is incomplete or unsafe; no certificate may be issued."""


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _canonical_sha(value):
    return _sha(_json_bytes(value))


def _is_sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def _read_regular(path, limit, *, owner=None, private=False):
    path = Path(path)
    if path.is_symlink():
        raise ReconciliationUnknown('evidence_symlink')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > limit:
            raise ReconciliationUnknown('evidence_file_invalid')
        if owner is not None and st.st_uid != owner:
            raise ReconciliationUnknown('evidence_owner_invalid')
        if private and st.st_mode & 0o077:
            raise ReconciliationUnknown('evidence_permissions_invalid')
        chunks, remaining = [], limit + 1
        while remaining:
            block = os.read(fd, min(65536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        data = b''.join(chunks)
        if len(data) > limit:
            raise ReconciliationUnknown('evidence_size_limit')
        return data
    finally:
        os.close(fd)


def _decode_prestate(prestate):
    expected_paths = {
        '/Users/tiga/.local/state/fdisbull-ci-production/bridge-anchor.json': ANCHOR_SHA256,
        '/Volumes/CODEX/Codex_Projects/fDisBull/.git/fdisbull-ci-status/007f50c6f89b577ea6fa646ef39d49c8646c539bd91477d81c0918dbc7cbaf30/state.json': STATUS_SHA256,
        '/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge-state/510f55688843de9ae209f8a1435cc76fcd51deb183fcb97a1246cba3333041c4.json': ACTION_RECEIPT_SHA256,
        '/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge-state/791b3a351d81c67c6b1b8e10ea8b212a116978aa5c98a5e3210963c424f25ed6.json': BATCH_RECEIPT_SHA256,
        '/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge-state/installation.json': INSTALLATION_SHA256,
        '/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge/production_transport.py': DEPLOYED_BRIDGE_SHA256,
    }
    if (type(prestate) is not dict or set(prestate) != {'schema', 'captured_epoch', 'action_key', 'request_sha256',
            'anchor_sequence', 'only_action_and_batch', 'files'}
            or prestate.get('schema') != 'fdisbull-held-dispatch-prestate-1'
            or prestate.get('action_key') != ACTION_KEY or prestate.get('request_sha256') != REQUEST_SHA256
            or prestate.get('anchor_sequence') != 3 or prestate.get('only_action_and_batch') is not True
            or type(prestate.get('captured_epoch')) not in (float, int) or not math.isfinite(prestate['captured_epoch'])):
        raise ReconciliationUnknown('prestate_identity_mismatch')
    files = prestate['files']
    if type(files) is not list or len(files) != len(expected_paths):
        raise ReconciliationUnknown('prestate_file_set_mismatch')
    decoded = {}
    for row in files:
        if type(row) is not dict or set(row) != {'path', 'sha256', 'size', 'bytes_base64'}:
            raise ReconciliationUnknown('prestate_record_schema')
        path = row['path']
        if path not in expected_paths or path in decoded or row['sha256'] != expected_paths[path]:
            raise ReconciliationUnknown('prestate_record_identity')
        try:
            data = base64.b64decode(row['bytes_base64'], validate=True)
        except (ValueError, TypeError):
            raise ReconciliationUnknown('prestate_bytes_invalid') from None
        if len(data) != row['size'] or _sha(data) != row['sha256']:
            raise ReconciliationUnknown('prestate_bytes_hash_mismatch')
        decoded[path] = data
    if set(decoded) != set(expected_paths):
        raise ReconciliationUnknown('prestate_file_set_mismatch')
    base = '/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge-state/'
    anchor = json.loads(decoded['/Users/tiga/.local/state/fdisbull-ci-production/bridge-anchor.json'])
    status = json.loads(decoded['/Volumes/CODEX/Codex_Projects/fDisBull/.git/fdisbull-ci-status/007f50c6f89b577ea6fa646ef39d49c8646c539bd91477d81c0918dbc7cbaf30/state.json'])
    action = json.loads(decoded[base + '510f55688843de9ae209f8a1435cc76fcd51deb183fcb97a1246cba3333041c4.json'])
    batch = json.loads(decoded[base + '791b3a351d81c67c6b1b8e10ea8b212a116978aa5c98a5e3210963c424f25ed6.json'])
    install = json.loads(decoded[base + 'installation.json'])
    if (type(anchor) is not dict or anchor.get('sequence') != 3 or len(anchor.get('actions', {})) != 2
            or set(anchor['actions'].values()) != {ACTION_RECEIPT_SHA256, BATCH_RECEIPT_SHA256}
            or action != {'action_key': ACTION_KEY, 'request_sha256': REQUEST_SHA256, 'status': 'unknown'}
            or batch.get('kind') != 'provider-batch' or batch.get('provider') != 'github'
            or batch.get('owner') != transport.OWNER or batch.get('remaining') != 99
            or status.get('host') != 'github.com' or status.get('repo') != REPOSITORY.lower()
            or status.get('owner') != transport.OWNER
            or not isinstance(status.get('provider_stop'), dict)
            or status['provider_stop'].get('reason') != PROVIDER_STOP_REASON
            or status.get('next_allowed_at') != batch.get('expires')
            or install != {'installation_id': transport.INSTALLATION_ID, 'volume_uuid': transport.VOLUME_UUID}):
        raise ReconciliationUnknown('prestate_contents_mismatch')
    return {'document_sha256': PRESTATE_SHA256, 'action_key': ACTION_KEY, 'request_sha256': REQUEST_SHA256,
            'anchor_sha256': ANCHOR_SHA256, 'anchor_sequence': 3,
            'action_sha256': ACTION_RECEIPT_SHA256, 'batch_sha256': BATCH_RECEIPT_SHA256,
            'provider_state_sha256': STATUS_SHA256, 'installation_sha256': INSTALLATION_SHA256,
            'deployed_bridge_sha256': DEPLOYED_BRIDGE_SHA256, 'batch_remaining': 99,
            'provider_stop_reason': PROVIDER_STOP_REASON}


def load_prestate():
    data = _read_regular(PRESTATE_PATH, 128 * 1024, owner=os.getuid(), private=True)
    if _sha(data) != PRESTATE_SHA256:
        raise ReconciliationUnknown('prestate_file_digest_mismatch')
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError):
        raise ReconciliationUnknown('prestate_json_invalid') from None
    return _decode_prestate(value)


def _path_page(path):
    prefix = f'/repos/{REPOSITORY}/actions/workflows/{WORKFLOW_ID}/runs?per_page=100&page='
    if path == '/user':
        return None
    if not isinstance(path, str) or not path.startswith(prefix):
        raise ReconciliationUnknown('canonical_path_not_allowed')
    page = path[len(prefix):]
    if not re.fullmatch(r'[1-9][0-9]?', page) or not 1 <= int(page) <= MAX_PAGES:
        raise ReconciliationUnknown('canonical_page_not_allowed')
    return int(page)


def _result_body(response):
    if (type(response) is not dict or set(response) - {'http_status', 'data', 'request_id'}
            or type(response.get('http_status')) is not int or not 100 <= response['http_status'] <= 599):
        raise ReconciliationUnknown('provider_response_schema')
    try:
        data = response.get('data')
        raw = _json_bytes(data)
    except (TypeError, ValueError):
        raise ReconciliationUnknown('provider_response_not_json') from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ReconciliationUnknown('provider_response_too_large')
    return data, _sha(raw)


def _nonce_match(value, nonce):
    if isinstance(value, str):
        return nonce in value
    if isinstance(value, dict):
        return any(_nonce_match(k, nonce) or _nonce_match(v, nonce) for k, v in value.items())
    if isinstance(value, list):
        return any(_nonce_match(v, nonce) for v in value)
    return False


def collect_canonical_runs(fetch_get, *, action_key=ACTION_KEY, request_sha256=REQUEST_SHA256,
                           prestate_sha256=PRESTATE_SHA256, collector_source_sha256=None):
    """Collect a bounded exhaustive read through a caller that debits each GET first."""
    if (not callable(fetch_get) or action_key != ACTION_KEY or request_sha256 != REQUEST_SHA256
            or prestate_sha256 != PRESTATE_SHA256 or not _is_sha(collector_source_sha256)):
        raise ReconciliationUnknown('canonical_request_identity_mismatch')
    nonce = _sha(action_key.encode('utf-8'))
    request_receipts = []

    def get(path):
        if len(request_receipts) >= MAX_GETS:
            raise ReconciliationUnknown('canonical_get_budget_exhausted')
        _path_page(path)
        try:
            response = fetch_get(path)
        except Exception as exc:
            raise ReconciliationUnknown('canonical_provider_read_unknown:' + type(exc).__name__) from None
        data, response_sha = _result_body(response)
        request_receipts.append({'path': path, 'http_status': response['http_status'],
                                 'response_sha256': response_sha})
        if response['http_status'] != 200:
            raise ReconciliationUnknown('canonical_provider_non_200')
        return data, response_sha

    user, _ = get('/user')
    if (type(user) is not dict or user.get('login') != EXPECTED_LOGIN
            or isinstance(user.get('id'), bool) or not isinstance(user.get('id'), int) or user['id'] <= 0):
        raise ReconciliationUnknown('canonical_account_mismatch')

    first_ids = None
    all_ids, matches, pages = [], [], []
    total_count = None
    expected_pages = None
    for page in range(1, MAX_PAGES + 1):
        path = f'/repos/{REPOSITORY}/actions/workflows/{WORKFLOW_ID}/runs?per_page={PAGE_SIZE}&page={page}'
        data, response_sha = get(path)
        if type(data) is not dict or type(data.get('workflow_runs')) is not list:
            raise ReconciliationUnknown('canonical_runs_shape')
        total = data.get('total_count')
        rows = data['workflow_runs']
        if type(total) is not int or total < 0 or total > PAGE_SIZE * MAX_PAGES or len(rows) > PAGE_SIZE:
            raise ReconciliationUnknown('canonical_total_count_invalid')
        if total_count is None:
            total_count = total
            expected_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        elif total != total_count:
            raise ReconciliationUnknown('canonical_total_count_changed')
        expected_rows = min(PAGE_SIZE, max(0, total_count - (page - 1) * PAGE_SIZE))
        if len(rows) != expected_rows:
            raise ReconciliationUnknown('canonical_page_not_exhaustive')
        page_ids, page_matches = [], []
        for row in rows:
            if (type(row) is not dict or isinstance(row.get('id'), bool)
                    or not isinstance(row.get('id'), (str, int)) or not str(row['id']).isdecimal()
                    or int(row['id']) <= 0 or str(row.get('workflow_id')) != str(WORKFLOW_ID)):
                raise ReconciliationUnknown('canonical_run_identity_invalid')
            run_id = str(int(row['id']))
            attempt = row.get('run_attempt')
            if attempt is not None and (isinstance(attempt, bool) or not isinstance(attempt, int) or attempt <= 0):
                raise ReconciliationUnknown('canonical_run_attempt_invalid')
            if run_id in all_ids:
                raise ReconciliationUnknown('canonical_run_id_duplicate')
            page_ids.append(run_id); all_ids.append(run_id)
            if _nonce_match(row, nonce):
                page_matches.append(run_id); matches.append(run_id)
        pages.append({'page': page, 'total_count': total, 'run_ids': page_ids,
                      'matching_run_ids': page_matches, 'response_sha256': response_sha})
        if page == 1:
            first_ids = page_ids
        if page == expected_pages:
            break
    else:
        raise ReconciliationUnknown('canonical_pages_incomplete')

    if len(all_ids) != total_count:
        raise ReconciliationUnknown('canonical_run_total_mismatch')
    repeat_path = f'/repos/{REPOSITORY}/actions/workflows/{WORKFLOW_ID}/runs?per_page={PAGE_SIZE}&page=1'
    repeat_data, repeat_sha = get(repeat_path)
    if (type(repeat_data) is not dict or type(repeat_data.get('workflow_runs')) is not list
            or repeat_data.get('total_count') != total_count):
        raise ReconciliationUnknown('canonical_snapshot_changed')
    repeat_rows = repeat_data['workflow_runs']
    repeat_ids = []
    for row in repeat_rows:
        if type(row) is not dict or str(row.get('workflow_id')) != str(WORKFLOW_ID):
            raise ReconciliationUnknown('canonical_repeat_schema')
        item = row.get('id')
        if isinstance(item, bool) or not isinstance(item, (int, str)) or not str(item).isdecimal() or int(item) <= 0:
            raise ReconciliationUnknown('canonical_repeat_identity')
        repeat_ids.append(str(int(item)))
    first_page = pages[0]
    # IDs plus whole response digest bind the captured first-page snapshot.
    if len(repeat_rows) != len(first_ids) or repeat_ids != first_ids or repeat_sha != first_page['response_sha256']:
        raise ReconciliationUnknown('canonical_snapshot_changed')
    if len(request_receipts) > MAX_GETS or len(set(all_ids)) != len(all_ids):
        raise ReconciliationUnknown('canonical_uniqueness_or_budget_failure')
    result = {'schema': 'fdisbull-held-canonical-read-1', 'action_key': action_key,
              'request_sha256': request_sha256, 'nonce_sha256': nonce,
              'repository': REPOSITORY, 'workflow_id': WORKFLOW_ID, 'actor_login': EXPECTED_LOGIN,
              'total_count': total_count, 'page_count': expected_pages, 'run_ids': all_ids,
              'matching_run_ids': matches, 'pages': pages, 'requests': request_receipts,
              'stability_check': {'total_count': total_count, 'run_ids': repeat_ids,
                                  'response_sha256': repeat_sha},
              'complete': True, 'stable': True, 'collector_source_sha256': collector_source_sha256}
    result['canonical_result_sha256'] = _canonical_sha({k: v for k, v in result.items() if k != 'canonical_result_sha256'})
    return result


class DurableCanonicalReader:
    """Bounded GET adapter over the fixed provider bridge and its shared locks."""

    def __init__(self, bridge, prestate, *, clock=time.time, max_gets=MAX_GETS):
        if type(max_gets) is not int or max_gets != MAX_GETS or not callable(clock):
            raise ValueError('fixed read budget required')
        self.bridge, self.clock, self.prestate = bridge, clock, prestate
        self.max_gets = max_gets
        self.scan_id = uuid.uuid4().hex
        self.key = READ_RECORD_PREFIX + _sha(ACTION_KEY.encode('utf-8'))
        self.record_path = bridge._file(self.key)
        self._read_count = 0
        self._pre = None

    def _now(self):
        now = self.bridge.status_api._clock_value(self.clock)
        return now

    def _paths(self):
        host, repo, root, scope = self.bridge._scope_state('github')
        if host.lower() != 'github.com' or repo.lower() != REPOSITORY.lower():
            raise ReconciliationUnknown('shared_scope_mismatch')
        return host, repo, root, scope

    def _read_small(self, path):
        return _read_regular(path, transport.MAX_INPUT, owner=os.getuid(), private=True)

    def _snapshot_locked(self, host, repo, scope):
        state_path = scope / 'state.json'
        state_bytes = self._read_small(state_path)
        state = self.bridge.status_api._load_state(state_path, host.lower(), repo.lower())
        anchor_bytes = self._read_small(self.bridge.anchor)
        anchor = json.loads(anchor_bytes)
        action_path = self.bridge._file(ACTION_KEY)
        batch_path = self.bridge._file(transport.BATCH_PREFIX + 'github')
        action_bytes = self._read_small(action_path)
        batch_bytes = self._read_small(batch_path)
        marker_bytes = self._read_small(self.bridge.state / 'installation.json')
        action = json.loads(action_bytes); batch = json.loads(batch_bytes)
        return {'anchor_sha256': _sha(anchor_bytes), 'sequence': anchor.get('sequence'),
                'action_sha256': _sha(action_bytes), 'action_status': action.get('status'),
                'action_request_sha256': action.get('request_sha256'),
                'batch_sha256': _sha(batch_bytes), 'batch_remaining': batch.get('remaining'),
                'provider_state_sha256': _sha(state_bytes),
                'provider_stop_reason': (state.get('provider_stop') or {}).get('reason'),
                'provider_owner': state.get('owner'), 'next_allowed_at': state.get('next_allowed_at'),
                'installation_sha256': _sha(marker_bytes),
                'action_count': len(anchor.get('actions', {})), 'actions': anchor.get('actions', {})}

    def _require_prestate(self, snap, now):
        if (snap['anchor_sha256'] != ANCHOR_SHA256 or snap['sequence'] != 3
                or snap['action_sha256'] != ACTION_RECEIPT_SHA256 or snap['action_status'] != 'unknown'
                or snap['action_request_sha256'] != REQUEST_SHA256
                or snap['batch_sha256'] != BATCH_RECEIPT_SHA256 or snap['batch_remaining'] != 99
                or snap['provider_state_sha256'] != STATUS_SHA256
                or snap['provider_stop_reason'] != PROVIDER_STOP_REASON or snap['provider_owner'] != transport.OWNER
                or snap['installation_sha256'] != INSTALLATION_SHA256 or snap['action_count'] != 2
                or now < snap['next_allowed_at']):
            raise ReconciliationUnknown('live_prestate_not_exact_or_cooldown')

    def reserve(self):
        with self.bridge._bridge_lock():
            host, repo, _, scope = self._paths()
            with self.bridge.status_api._locked(scope) as acquired:
                if not acquired:
                    raise ReconciliationUnknown('shared_status_busy')
                now = self._now()
                snap = self._snapshot_locked(host, repo, scope)
                self._require_prestate(snap, now)
                if self.record_path.exists() or self.record_path.is_symlink():
                    raise ReconciliationUnknown('diagnostic_budget_already_used')
                self._pre = snap
                record = {'schema': 'fdisbull-held-canonical-read-budget-1',
                          'action_key_sha256': _sha(ACTION_KEY.encode()), 'request_sha256': REQUEST_SHA256,
                          'prestate_sha256': PRESTATE_SHA256, 'owner': transport.OWNER,
                          'provider': 'github', 'status': 'reserved', 'scan_id': self.scan_id,
                          'reserved_at': now, 'expires_at': now + 300, 'max_gets': MAX_GETS,
                          'used': 0, 'remaining': MAX_GETS, 'calls': []}
                self.bridge._save_mirrored(self.record_path, record)

    def __call__(self, path):
        page = _path_page(path)
        if self._read_count == 0 and path != '/user':
            raise ReconciliationUnknown('account_read_must_be_first')
        if self._read_count > 0 and path == '/user':
            raise ReconciliationUnknown('account_read_duplicate')
        if self._pre is None:
            self.reserve()
        with self.bridge._bridge_lock():
            host, repo, _, scope = self._paths()
            with self.bridge.status_api._locked(scope) as acquired:
                if not acquired:
                    raise ReconciliationUnknown('shared_status_busy')
                now = self._now()
                snap = self._snapshot_locked(host, repo, scope)
                if (snap['provider_owner'] != transport.OWNER or snap['provider_stop_reason'] != PROVIDER_STOP_REASON
                        or now < snap['next_allowed_at'] or snap['action_sha256'] != ACTION_RECEIPT_SHA256
                        or snap['batch_sha256'] != BATCH_RECEIPT_SHA256 or snap['provider_state_sha256'] != STATUS_SHA256):
                    raise ReconciliationUnknown('shared_gate_changed')
                data = self._read_small(self.record_path)
                record = json.loads(data)
                if (record.get('schema') != 'fdisbull-held-canonical-read-budget-1'
                        or record.get('scan_id') != self.scan_id or record.get('status') not in ('reserved', 'reading')
                        or record.get('owner') != transport.OWNER or record.get('provider') != 'github'
                        or record.get('prestate_sha256') != PRESTATE_SHA256 or record.get('used') != self._read_count
                        or record.get('remaining') != MAX_GETS - self._read_count
                        or type(record.get('expires_at')) not in (int, float) or now >= record['expires_at']
                        or self._read_count >= MAX_GETS):
                    raise ReconciliationUnknown('diagnostic_budget_invalid')
                calls = list(record['calls'])
                calls.append({'path': path, 'page': page, 'status': 'inflight', 'started_at': now})
                debit = {**record, 'status': 'reading', 'used': self._read_count + 1,
                         'remaining': MAX_GETS - self._read_count - 1, 'calls': calls}
                # This mirror write is durable before _call_provider can launch
                # either the named gh auth lookup or its fixed GET process.
                self.bridge._save_mirrored(self.record_path, debit)
                response = self.bridge._call_provider('github', 'GET', path, None, False)
                body, response_sha = _result_body(response)
                calls[-1] = {'path': path, 'page': page, 'status': 'complete', 'started_at': now,
                             'completed_at': self._now(), 'http_status': response['http_status'],
                             'response_sha256': response_sha}
                debit = {**debit, 'calls': calls}
                self.bridge._save_mirrored(self.record_path, debit)
                self._read_count += 1
                return response

    def finish(self):
        if self._read_count < 3:
            raise ReconciliationUnknown('canonical_read_set_incomplete')
        with self.bridge._bridge_lock():
            host, repo, _, scope = self._paths()
            with self.bridge.status_api._locked(scope) as acquired:
                if not acquired:
                    raise ReconciliationUnknown('shared_status_busy')
                now = self._now()
                current = self._snapshot_locked(host, repo, scope)
                if (current['action_sha256'] != ACTION_RECEIPT_SHA256 or current['batch_sha256'] != BATCH_RECEIPT_SHA256
                        or current['provider_state_sha256'] != STATUS_SHA256
                        or current['provider_stop_reason'] != PROVIDER_STOP_REASON
                        or current['provider_owner'] != transport.OWNER):
                    raise ReconciliationUnknown('held_state_changed')
                record = json.loads(self._read_small(self.record_path))
                if (record.get('scan_id') != self.scan_id or record.get('used') != self._read_count
                        or any(call.get('status') != 'complete' for call in record.get('calls', []))):
                    raise ReconciliationUnknown('canonical_read_incomplete')
                record.update(status='complete', finished_at=now)
                self.bridge._save_mirrored(self.record_path, record)
                final = self._snapshot_locked(host, repo, scope)
                expected_sequence = self._pre['sequence'] + 2 * self._read_count + 2
                if (final['sequence'] != expected_sequence or final['action_sha256'] != ACTION_RECEIPT_SHA256
                        or final['batch_sha256'] != BATCH_RECEIPT_SHA256
                        or final['provider_state_sha256'] != STATUS_SHA256
                        or final['provider_stop_reason'] != PROVIDER_STOP_REASON):
                    raise ReconciliationUnknown('poststate_mirror_mismatch')
                return {'mirror_pre': self._pre, 'mirror_post': final,
                        'read_budget_sha256': _sha(self._read_small(self.record_path)),
                        'read_count': self._read_count,
                        'read_budget_calls': record['calls']}


def collect_with_bridge(bridge, prestate):
    """Run the only enabled operational read, using the installed fixed bridge."""
    if (Path(bridge.state) != Path(transport.STATE_DIR) or Path(bridge.anchor) != Path(transport.ANCHOR_FILE)
            or bridge.status_dir is not None):
        raise ReconciliationUnknown('fixed_bridge_required')
    collector_sha = _sha(Path(__file__).read_bytes())
    reader = DurableCanonicalReader(bridge, prestate)
    reader.reserve()
    canonical = collect_canonical_runs(reader, collector_source_sha256=collector_sha)
    closure = reader.finish()
    canonical.update(closure)
    canonical['canonical_result_sha256'] = _canonical_sha({k: v for k, v in canonical.items()
                                                             if k != 'canonical_result_sha256'})
    return canonical


def canonical_read(document, *, bridge=None):
    if (type(document) is not dict or set(document) != {'operation', 'action_key', 'request_sha256', 'prestate_sha256'}
            or document.get('operation') != 'canonical_read' or document.get('action_key') != ACTION_KEY
            or document.get('request_sha256') != REQUEST_SHA256 or document.get('prestate_sha256') != PRESTATE_SHA256):
        raise ReconciliationUnknown('fixed_canonical_read_request_required')
    prestate = load_prestate()
    if prestate['document_sha256'] != document['prestate_sha256']:
        raise ReconciliationUnknown('requested_prestate_mismatch')
    bridge = bridge or transport.ProviderBridge(transport.STATE_DIR)
    return collect_with_bridge(bridge, prestate)


def _validate_canonical(canonical, expected_collector_sha256):
    required = {'schema', 'action_key', 'request_sha256', 'nonce_sha256', 'repository', 'workflow_id',
                'actor_login', 'total_count', 'page_count', 'run_ids', 'matching_run_ids', 'pages',
                'requests', 'stability_check', 'complete', 'stable', 'collector_source_sha256',
                'mirror_pre', 'mirror_post', 'read_budget_sha256', 'read_count', 'read_budget_calls',
                'canonical_result_sha256'}
    if (type(canonical) is not dict or set(canonical) != required
            or canonical.get('schema') != 'fdisbull-held-canonical-read-1'
            or canonical.get('action_key') != ACTION_KEY or canonical.get('request_sha256') != REQUEST_SHA256
            or canonical.get('nonce_sha256') != _sha(ACTION_KEY.encode())
            or canonical.get('repository') != REPOSITORY or canonical.get('workflow_id') != WORKFLOW_ID
            or canonical.get('actor_login') != EXPECTED_LOGIN or canonical.get('complete') is not True
            or canonical.get('stable') is not True or canonical.get('collector_source_sha256') != expected_collector_sha256
            or not _is_sha(expected_collector_sha256)):
        raise ReconciliationUnknown('canonical_evidence_identity_mismatch')
    total = canonical.get('total_count'); pages = canonical.get('pages'); page_count = canonical.get('page_count')
    if (type(total) is not int or not 0 <= total <= PAGE_SIZE * MAX_PAGES
            or type(pages) is not list or type(page_count) is not int
            or page_count != max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) or len(pages) != page_count):
        raise ReconciliationUnknown('canonical_pages_invalid')
    seen = []
    for i, page in enumerate(pages, 1):
        expected_len = min(PAGE_SIZE, max(0, total - (i - 1) * PAGE_SIZE))
        if (type(page) is not dict or set(page) != {'page', 'total_count', 'run_ids', 'matching_run_ids', 'response_sha256'}
                or page.get('page') != i or page.get('total_count') != total or type(page.get('run_ids')) is not list
                or len(page['run_ids']) != expected_len or type(page.get('matching_run_ids')) is not list
                or not _is_sha(page.get('response_sha256'))):
            raise ReconciliationUnknown('canonical_page_shape_invalid')
        if any(not isinstance(r, str) or not r.isdecimal() or int(r) <= 0 for r in page['run_ids']):
            raise ReconciliationUnknown('canonical_run_identity_invalid')
        if any(r not in page['run_ids'] for r in page['matching_run_ids']):
            raise ReconciliationUnknown('canonical_match_binding_invalid')
        seen.extend(page['run_ids'])
    if (seen != canonical['run_ids'] or len(seen) != total or len(set(seen)) != len(seen)
            or canonical['matching_run_ids'] != [r for p in pages for r in p['matching_run_ids']]
            or canonical['matching_run_ids']):
        raise ReconciliationUnknown('canonical_run_set_or_nonce_match')
    expected_calls = page_count + 2
    requests = canonical.get('requests')
    if (type(requests) is not list or len(requests) != expected_calls or len(requests) > MAX_GETS
            or requests[0].get('path') != '/user'
            or any(type(x) is not dict or set(x) != {'path', 'http_status', 'response_sha256'}
                   or x.get('http_status') != 200 or not _is_sha(x.get('response_sha256')) for x in requests)):
        raise ReconciliationUnknown('canonical_request_receipts_invalid')
    budget_calls = canonical.get('read_budget_calls')
    if type(budget_calls) is not list or len(budget_calls) != expected_calls:
        raise ReconciliationUnknown('canonical_budget_call_shape_invalid')
    for request, call in zip(requests, budget_calls):
        if (type(call) is not dict or set(call) != {'path', 'page', 'status', 'started_at', 'completed_at',
                                                   'http_status', 'response_sha256'}
                or call.get('path') != request['path'] or call.get('status') != 'complete'
                or call.get('http_status') != request['http_status']
                or call.get('response_sha256') != request['response_sha256']
                or type(call.get('started_at')) not in (int, float)
                or type(call.get('completed_at')) not in (int, float)
                or call['completed_at'] < call['started_at']
                or call.get('page') != _path_page(call['path'])):
            raise ReconciliationUnknown('canonical_budget_call_binding_invalid')
    for i, page in enumerate(pages):
        expected_path = f'/repos/{REPOSITORY}/actions/workflows/{WORKFLOW_ID}/runs?per_page={PAGE_SIZE}&page={i+1}'
        if requests[i + 1].get('path') != expected_path or requests[i + 1].get('response_sha256') != page['response_sha256']:
            raise ReconciliationUnknown('canonical_page_request_binding_invalid')
    stability = canonical.get('stability_check')
    if (type(stability) is not dict or set(stability) != {'total_count', 'run_ids', 'response_sha256'}
            or stability.get('total_count') != total or stability.get('run_ids') != pages[0]['run_ids']
            or stability.get('response_sha256') != pages[0]['response_sha256']
            or requests[-1].get('path') != f'/repos/{REPOSITORY}/actions/workflows/{WORKFLOW_ID}/runs?per_page={PAGE_SIZE}&page=1'
            or requests[-1].get('response_sha256') != stability['response_sha256']):
        raise ReconciliationUnknown('canonical_stability_binding_invalid')
    if (type(canonical.get('read_count')) is not int or canonical['read_count'] != expected_calls
            or not _is_sha(canonical.get('read_budget_sha256'))
            or not _is_sha(canonical.get('canonical_result_sha256'))):
        raise ReconciliationUnknown('canonical_read_budget_missing')
    expected_result_sha = _canonical_sha({k: v for k, v in canonical.items() if k != 'canonical_result_sha256'})
    if expected_result_sha != canonical['canonical_result_sha256']:
        raise ReconciliationUnknown('canonical_result_digest_mismatch')


def verify_no_send_certificate(facts, canonical, *, expected_collector_sha256):
    """Pure fail-closed verifier; it never reads files or invokes a provider."""
    required = {'schema', 'prestate_sha256', 'prestate_receipt', 'genesis', 'native_invocation'}
    if type(facts) is not dict or set(facts) != required or facts.get('schema') != 'fdisbull-held-no-send-facts-1':
        raise ReconciliationUnknown('local_facts_schema_invalid')
    if facts.get('prestate_sha256') != PRESTATE_SHA256:
        raise ReconciliationUnknown('prestate_fact_digest_mismatch')
    pre = _decode_prestate(facts['prestate_receipt'])
    _validate_canonical(canonical, expected_collector_sha256)
    genesis = facts['genesis']
    genesis_required = {'readback_sha256', 'control_sha', 'all25modules_verified',
                        'provider_history_sequence', 'provider_actions_before_live_check',
                        'source_activation_sha256', 'v0341_unchanged_sha256'}
    if (type(genesis) is not dict or set(genesis) != genesis_required
            or genesis != {'readback_sha256': GENESIS_READBACK_SHA256, 'control_sha': GENESIS_CONTROL_SHA,
                           'all25modules_verified': True, 'provider_history_sequence': 0,
                           'provider_actions_before_live_check': 0,
                           'source_activation_sha256': SOURCE_ACTIVATION_SHA256,
                           'v0341_unchanged_sha256': V0341_UNCHANGED_SHA256}):
        raise ReconciliationUnknown('genesis_readback_mismatch')
    native = facts['native_invocation']
    native_required = {'invocation_id', 'pid', 'started_epoch', 'finished_epoch', 'exit_code',
                       'action_key', 'request_sha256', 'host_intent_sha256', 'host_intent_epoch',
                       'service_error_sha256', 'service_error_epoch', 'deployed_bridge_sha256'}
    if (type(native) is not dict or set(native) != native_required
            or native.get('invocation_id') != NATIVE_INVOCATION_ID or native.get('pid') != NATIVE_INVOCATION_PID
            or native.get('exit_code') != NATIVE_EXIT_CODE or native.get('action_key') != ACTION_KEY
            or native.get('request_sha256') != REQUEST_SHA256 or native.get('host_intent_sha256') != HOST_INTENT_SHA256
            or native.get('service_error_sha256') != SERVICE_ERROR_SHA256
            or native.get('deployed_bridge_sha256') != DEPLOYED_BRIDGE_SHA256
            or native.get('started_epoch') != NATIVE_STARTED_EPOCH
            or native.get('finished_epoch') != NATIVE_FINISHED_EPOCH
            or native.get('host_intent_epoch') != 1794633633.228689
            or native.get('service_error_epoch') != 1794633634.9547014
            or not native['started_epoch'] <= native['host_intent_epoch'] <= PROVIDER_STOP_EPOCH
            or not PROVIDER_STOP_EPOCH <= native['service_error_epoch'] <= native['finished_epoch']):
        raise ReconciliationUnknown('native_invocation_not_source_bound')
    pre_mirror = canonical['mirror_pre']; post = canonical['mirror_post']
    mirror_fields = {'anchor_sha256', 'sequence', 'action_sha256', 'action_status', 'action_request_sha256',
                     'batch_sha256', 'batch_remaining', 'provider_state_sha256', 'provider_stop_reason',
                     'provider_owner', 'next_allowed_at', 'installation_sha256', 'action_count', 'actions'}
    if type(pre_mirror) is not dict or type(post) is not dict or set(pre_mirror) != mirror_fields or set(post) != mirror_fields:
        raise ReconciliationUnknown('mirror_snapshot_schema_invalid')
    for mirror in (pre_mirror, post):
        if (not _is_sha(mirror.get('anchor_sha256')) or not _is_sha(mirror.get('action_sha256'))
                or not _is_sha(mirror.get('batch_sha256')) or not _is_sha(mirror.get('provider_state_sha256'))
                or not _is_sha(mirror.get('installation_sha256'))
                or type(mirror.get('sequence')) is not int or type(mirror.get('action_count')) is not int
                or type(mirror.get('actions')) is not dict or type(mirror.get('next_allowed_at')) not in (int, float)):
            raise ReconciliationUnknown('mirror_snapshot_values_invalid')
    if (pre_mirror.get('anchor_sha256') != ANCHOR_SHA256 or pre_mirror.get('sequence') != 3
            or pre_mirror.get('action_sha256') != pre['action_sha256']
            or pre_mirror.get('action_status') != 'unknown'
            or pre_mirror.get('action_request_sha256') != REQUEST_SHA256
            or pre_mirror.get('batch_sha256') != BATCH_RECEIPT_SHA256 or pre_mirror.get('batch_remaining') != 99
            or pre_mirror.get('provider_state_sha256') != STATUS_SHA256
            or pre_mirror.get('provider_stop_reason') != PROVIDER_STOP_REASON
            or pre_mirror.get('provider_owner') != transport.OWNER
            or pre_mirror.get('installation_sha256') != INSTALLATION_SHA256 or pre_mirror.get('action_count') != 2
            or pre_mirror.get('next_allowed_at') < PROVIDER_STOP_EPOCH):
        raise ReconciliationUnknown('mirror_prestate_mismatch')
    count = canonical['read_count']
    if (post.get('sequence') != 3 + 2 * count + 2 or post.get('action_sha256') != ACTION_RECEIPT_SHA256
            or post.get('action_status') != 'unknown' or post.get('action_request_sha256') != REQUEST_SHA256
            or post.get('batch_sha256') != BATCH_RECEIPT_SHA256 or post.get('batch_remaining') != 99
            or post.get('provider_state_sha256') != STATUS_SHA256
            or post.get('provider_stop_reason') != PROVIDER_STOP_REASON or post.get('provider_owner') != transport.OWNER
            or post.get('installation_sha256') != INSTALLATION_SHA256 or post.get('action_count') != 3
            or post.get('next_allowed_at') != pre_mirror.get('next_allowed_at')):
        raise ReconciliationUnknown('mirror_poststate_mismatch')
    read_key = READ_RECORD_PREFIX + _sha(ACTION_KEY.encode())
    read_filename = bridge_record_filename(read_key)
    budget_hash = canonical['read_budget_sha256']
    action_filename = bridge_record_filename(ACTION_KEY)
    batch_filename = bridge_record_filename(transport.BATCH_PREFIX + 'github')
    if (not _is_sha(budget_hash) or type(pre_mirror.get('actions')) is not dict
            or pre_mirror['actions'] != {action_filename: ACTION_RECEIPT_SHA256,
                                         batch_filename: BATCH_RECEIPT_SHA256}
            or type(post.get('actions')) is not dict
            or post['actions'] != {action_filename: ACTION_RECEIPT_SHA256,
                                   batch_filename: BATCH_RECEIPT_SHA256,
                                   read_filename: budget_hash}):
        raise ReconciliationUnknown('budget_record_not_mirrored')
    cert = {'schema': 'fdisbull-held-no-send-certificate-1',
            'verified': True, 'no_api_process_started_source_bound': True,
            'no_api_process_started_basis': 'inference_from_pinned_pre_http_failure_source_and_closed_native_window',
            'action_key': ACTION_KEY, 'request_sha256': REQUEST_SHA256,
            'prestate_sha256': PRESTATE_SHA256, 'genesis_readback_sha256': GENESIS_READBACK_SHA256,
            'deployed_bridge_sha256': DEPLOYED_BRIDGE_SHA256,
            'native_invocation_id': NATIVE_INVOCATION_ID, 'native_invocation_pid': NATIVE_INVOCATION_PID,
            'canonical_result_sha256': _canonical_sha(canonical),
            'canonical_total_count': canonical['total_count'], 'canonical_page_count': canonical['page_count'],
            'canonical_matching_run_ids': [], 'canonical_stable': True,
            'read_count': count, 'read_budget_sha256': budget_hash,
            'original_action_sha256_before_after': [ACTION_RECEIPT_SHA256, post['action_sha256']],
            'original_batch_sha256_before_after': [BATCH_RECEIPT_SHA256, post['batch_sha256']],
            'provider_state_sha256_before_after': [STATUS_SHA256, post['provider_state_sha256']],
            'provider_stop_reason': PROVIDER_STOP_REASON,
            'mirror_post': post,
            'collector_source_sha256': expected_collector_sha256,
            }
    cert['certificate_sha256'] = _canonical_sha(cert)
    return cert


def bridge_record_filename(key):
    return _sha(key.encode('utf-8')) + '.json'


def main(argv=None):
    if argv not in (None, []):
        print('{"status":"unknown","reason":"unsupported_cli"}')
        return 2
    try:
        raw = sys.stdin.buffer.read(16385)
        if len(raw) > 16384:
            raise ReconciliationUnknown('request_too_large')
        document = json.loads(raw)
        result = canonical_read(document)
        print(json.dumps({'status': 'complete', 'canonical': result}, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception as exc:
        reason = exc.args[0] if isinstance(exc, ReconciliationUnknown) and exc.args else type(exc).__name__
        if not isinstance(reason, str) or not re.fullmatch(r'[a-z0-9_:.-]{1,100}', reason):
            reason = 'unknown'
        print(json.dumps({'status': 'unknown', 'reason': reason}, sort_keys=True, separators=(',', ':')))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
