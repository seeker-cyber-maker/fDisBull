#!/usr/bin/env python3
"""Publish an already-pushed authored branch and reviewed text reports as a draft MR.

No commit, push, merge, credential creation, CI polling or description overwrite.
Default is an offline preview. See docs/AGENT_HANDOFF.md for the manifest contract.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlencode
import fcntl

PROJECT = 88349936
HOST = 'gitlab.com'
PROJECT_PATH = 'brewster-jennings-group/fdisbull'
WEB = f'https://{HOST}/{PROJECT_PATH}'
MAX_REPORT = 128 * 1024


class HandoffError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.handoff-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def text(value, name, limit=12000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise HandoffError(f'invalid {name}')
    if any(ord(c) < 32 and c not in '\n\t\r' for c in value):
        raise HandoffError(f'control bytes in {name}')
    return value


def reviewed_text(data):
    if not 0 < len(data) <= MAX_REPORT:
        raise HandoffError('report must contain 1..131072 bytes')
    try:
        value = data.decode('utf-8')
    except UnicodeError as exc:
        raise HandoffError('report must be UTF-8 text') from exc
    text(value, 'report', MAX_REPORT)
    # Defense in depth only: the submitting agent must inspect the entire report.
    if re.search(r'(?i)(-----BEGIN .*PRIVATE KEY|glpat-[\w-]+|sk-proj-[\w-]+|'
                 r'(?:password|access_token|refresh_token|private.token)\s*[=:]\s*\S+|'
                 r'data:[^\s]+;base64,|[A-Za-z0-9+/=_-]{256,})', value):
        raise HandoffError('possible secret or embedded payload; sanitize report')
    return value


def load_manifest(path):
    path = Path(path).resolve()
    if path.stat().st_size > 256 * 1024:
        raise HandoffError('manifest too large')
    m = json.loads(path.read_text())
    if m.get('schema') != 1 or m.get('project_id') != PROJECT:
        raise HandoffError('manifest schema/project mismatch')
    for key in ('origin', 'source_branch', 'target_branch', 'title', 'summary'):
        text(m.get(key), key)
    for key in ('source_branch', 'target_branch'):
        branch = m[key]
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,180}', branch) or '..' in branch:
            raise HandoffError('invalid branch')
    if m['source_branch'] == m['target_branch']:
        raise HandoffError('source and target branches must differ')
    for key in ('head', 'base'):
        if not re.fullmatch('[0-9a-f]{40}', m.get(key, '')):
            raise HandoffError(f'{key} must be an exact SHA-1 commit')
    for key in ('tests', 'limitations'):
        if not isinstance(m.get(key), list) or len(m[key]) > 30:
            raise HandoffError(f'{key} must be a list')
        for item in m[key]:
            text(item, key, 2000)
    attachments = m.get('attachments', [])
    if not isinstance(attachments, list) or len(attachments) > 8:
        raise HandoffError('at most eight reviewed text reports')
    reports = []
    for item in attachments:
        p = path.parent / item['path']
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_REPORT:
            raise HandoffError('report must be a small regular file')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.(md|txt|json|csv)', p.name):
            raise HandoffError('unsupported report filename/type')
        if item.get('reviewed') is not True:
            raise HandoffError('report requires full content review before publication')
        data = p.read_bytes()
        reviewed_text(data)
        if digest(data) != item.get('sha256'):
            raise HandoffError('report hash mismatch; review changed content')
        reports.append((p.name, data, digest(data)))
    if len({h for _, _, h in reports}) != len(reports):
        raise HandoffError('duplicate report content')
    m['key'] = digest((str(PROJECT) + '\n' + m['origin'] + '\n' + m['source_branch']).encode())
    return m, reports


class Glab:
    def request(self, method, endpoint, payload=None, data=None, filename=None, raw=False):
        cmd = ['glab', 'api', '--hostname', HOST, '--method', method, endpoint]
        stdin = None
        with tempfile.TemporaryDirectory(prefix='fdisbull-handoff-') as directory:
            if data is not None:
                p = Path(directory) / filename
                p.write_bytes(data)
                cmd += ['--form', f'file=@{p}']
            elif payload is not None:
                cmd += ['--input', '-']
                stdin = json.dumps(payload).encode()
            try:
                result = subprocess.run(cmd, input=stdin, capture_output=True, timeout=45)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise HandoffError('GitLab request unavailable/uncertain; inspect receipt before retry') from exc
        if result.returncode:
            # Never relay CLI stderr: it may include credentials/private response data.
            raise HandoffError('GitLab request failed; check existing glab authentication and permissions')
        return result.stdout if raw else json.loads(result.stdout)


def listing(api, endpoint):
    values = []
    for page in range(1, 101):
        sep = '&' if '?' in endpoint else '?'
        part = api.request('GET', f'{endpoint}{sep}per_page=100&page={page}')
        if not isinstance(part, list):
            raise HandoffError('invalid GitLab list response')
        values.extend(part)
        if len(part) < 100:
            return values
    raise HandoffError('pagination budget exceeded; no publication')


def branch_head(api, branch):
    return api.request('GET', f'projects/{PROJECT}/repository/branches/{quote(branch, safe="")}')['commit']['id']


def marker(m):
    return f'<!-- fdisbull-handoff:{m["key"]} -->'


def description(m):
    return (f'{marker(m)}\n\n{m["summary"]}\n\n'
            f'Origin: `{m["origin"]}`\nSource: `{m["source_branch"]}`\n'
            f'Head: `{m["head"]}`\nBase: `{m["base"]}`\nTarget: `{m["target_branch"]}`\n\n'
            'Tests (reported by submitting agent):\n' + '\n'.join(f'- {v}' for v in m['tests']) +
            '\n\nLimitations:\n' + '\n'.join(f'- {v}' for v in m['limitations']) + '\n')


def validate_mr(mr, m):
    if (mr.get('source_project_id') != PROJECT or mr.get('target_project_id') != PROJECT or
        mr.get('source_branch') != m['source_branch'] or mr.get('target_branch') != m['target_branch'] or
        mr.get('sha') != m['head'] or marker(m) not in (mr.get('description') or '') or
        mr.get('state') != 'opened' or mr.get('draft') is not True):
        raise HandoffError('MR identity/head/target/draft mismatch; no overwrite or duplicate')
    if mr.get('web_url') != f'{WEB}/-/merge_requests/{mr["iid"]}':
        raise HandoffError('unexpected MR URL')


def submit(m, reports, api, receipt, save):
    root = f'projects/{PROJECT}'
    project = api.request('GET', root)
    if project.get('path_with_namespace') != PROJECT_PATH or project.get('visibility') != 'private':
        raise HandoffError('project identity/privacy mismatch')
    if branch_head(api, m['source_branch']) != m['head']:
        raise HandoffError('remote branch head mismatch; push reviewed authored source separately')
    target = branch_head(api, m['target_branch'])
    if target != m['base']:
        raise HandoffError('target advanced; revalidate base/stack and prepare a fresh manifest')
    matches = listing(api, root + '/merge_requests?' + urlencode(
        {'state': 'all', 'source_branch': m['source_branch']}))
    if len(matches) > 1:
        raise HandoffError('multiple MRs for source branch; reconcile manually')
    if matches:
        mr = api.request('GET', root + f'/merge_requests/{matches[0]["iid"]}')
        validate_mr(mr, m)
    else:
        if receipt.get('pending'):
            raise HandoffError('unresolved publication; inspect GitLab before retry')
        receipt['pending'] = 'create-mr'
        save(receipt)
        api.request('POST', root + '/merge_requests', {
            'source_branch': m['source_branch'], 'target_branch': m['target_branch'],
            'title': 'Draft: ' + m['title'].removeprefix('Draft: '),
            'description': description(m), 'remove_source_branch': False})
        # Ignore mutation response as proof; use an independent read.
        matches = listing(api, root + '/merge_requests?' + urlencode(
            {'state': 'all', 'source_branch': m['source_branch']}))
        if len(matches) != 1:
            raise HandoffError('MR creation uncertain; inspect GitLab before retry')
        mr = api.request('GET', root + f'/merge_requests/{matches[0]["iid"]}')
        validate_mr(mr, m)
    receipt.update(mr_url=mr['web_url'], iid=mr['iid'])
    if receipt.get('pending') == 'create-mr':
        receipt.pop('pending')
    save(receipt)
    endpoint = root + f'/merge_requests/{mr["iid"]}/notes'
    notes = listing(api, endpoint)
    for name, data, sha in reports:
        tag = f'<!-- fdisbull-report:{m["key"]}:{m["head"]}:{sha} -->'
        found = [n for n in notes if tag in n.get('body', '')]
        record = receipt.setdefault('attachments', {}).setdefault(sha, {})
        if len(found) > 1:
            raise HandoffError('duplicate attachment notes; reconcile manually')
        if found:
            match = re.search(r'\(/uploads/([0-9a-f]{32})/([A-Za-z0-9_.-]+)\)', found[0]['body'])
            if not match:
                raise HandoffError('attachment note missing valid upload reference')
            upload_path = '/uploads/' + match[1] + '/' + match[2]
            record.update(path=upload_path, note_id=found[0]['id'])
        elif not record.get('path'):
            if receipt.get('pending'):
                raise HandoffError('upload outcome uncertain; reconcile receipt before retry')
            receipt['pending'] = f'upload:{sha}'
            save(receipt)
            upload = api.request('POST', root + '/uploads', data=data, filename=name)
            path = upload.get('url', '')
            if not re.fullmatch(r'/uploads/[0-9a-f]{32}/' + re.escape(name), path):
                raise HandoffError('upload response uncertain')
            record['path'] = path
            receipt.pop('pending')
            save(receipt)
        path = record['path']
        if not re.fullmatch(r'/uploads/[0-9a-f]{32}/[A-Za-z0-9_.-]+', path):
            raise HandoffError('invalid receipt upload path')
        returned = api.request('GET', root + path, raw=True)
        if digest(returned) != sha:
            raise HandoffError('upload readback hash mismatch')
        if not found:
            if receipt.get('pending'):
                raise HandoffError('note outcome uncertain; inspect before retry')
            receipt['pending'] = f'note:{sha}'
            save(receipt)
            api.request('POST', endpoint, {'body': f'{tag}\n\nReviewed report for `{m["head"]}`: '
                        f'[{name}]({path})\n\nSHA-256: `{sha}`'})
            verified = [n for n in listing(api, endpoint) if tag in n.get('body', '')]
            if len(verified) != 1 or f']({path})' not in verified[0]['body']:
                raise HandoffError('attachment note readback failed')
            record['note_id'] = verified[0]['id']
        if receipt.get('pending') == f'note:{sha}':
            receipt.pop('pending')
        record.update(url=WEB + path, sha256=sha, verified=True)
        save(receipt)
    validate_mr(api.request('GET', root + f'/merge_requests/{mr["iid"]}'), m)
    if branch_head(api, m['source_branch']) != m['head']:
        raise HandoffError('branch moved during publication; receipt is partial')
    receipt['status'] = 'verified'
    save(receipt)
    return receipt


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise HandoffError('another publisher holds this receipt') from exc
        yield


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--receipt', type=Path)
    p.add_argument('--publish', action='store_true', help='Publish using existing glab access')
    args = p.parse_args(argv)
    receipt = {'schema': 1, 'status': 'blocked'}
    try:
        m, reports = load_manifest(args.manifest)
        receipt.update(key=m['key'], source_branch=m['source_branch'], target_branch=m['target_branch'],
                       head=m['head'], base=m['base'], origin=m['origin'], tests=m['tests'],
                       limitations=m['limitations'])
        if not args.publish:
            receipt['status'] = 'preview'
            receipt['description'] = description(m)
            receipt['reports'] = [{'name': n, 'sha256': h, 'bytes': len(d)} for n, d, h in reports]
        else:
            if args.receipt is None:
                raise HandoffError('--publish requires a durable --receipt outside the checkout')
            with locked(args.receipt):
                if args.receipt.exists():
                    old = json.loads(args.receipt.read_text())
                    if any(old.get(k) != receipt[k] for k in ('key', 'head', 'base', 'target_branch')):
                        raise HandoffError('receipt identity mismatch; keep old receipt, choose a new path')
                    receipt = old
                receipt['status'] = 'partial'
                try:
                    submit(m, reports, Glab(), receipt, lambda v: write_json(args.receipt, v))
                except (HandoffError, OSError, ValueError, KeyError, TypeError):
                    receipt['status'] = 'partial' if receipt.get('iid') or receipt.get('pending') else 'blocked'
                    write_json(args.receipt, receipt)
                    raise
        print(json.dumps(receipt, indent=2))
        return 0
    except (HandoffError, OSError, ValueError, KeyError, TypeError) as exc:
        # Failure details are bounded and authored here; do not include server/CLI payloads.
        receipt['status'] = 'partial' if receipt.get('iid') or receipt.get('pending') else 'blocked'
        receipt['error'] = str(exc) if isinstance(exc, HandoffError) else 'invalid/unavailable local or API data'
        print(json.dumps(receipt, indent=2))
        return 2


if __name__ == '__main__':
    sys.exit(main())
