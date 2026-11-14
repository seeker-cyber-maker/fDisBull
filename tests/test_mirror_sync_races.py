"""Deterministic remote-ref races at the mirror worker's Git push boundary."""

import json
from pathlib import Path

from test_mirror_sync_service import branch, git, mirrors, oid, publish, worker


def _intercept_gitlab_push(m, ref, replacement):
    """Mutate a fake GitLab ref after snapshot/fetch, just before real Git push.

    ``replacement=None`` deletes the destination. The wrapper does not act until
    its trigger file is created after the worker's initialization and test setup.
    """
    wrapper = m['root'] / 'git-race-wrapper'
    trigger = m['root'] / 'mutate-before-push'
    witnessed = m['root'] / 'mutation-observed'
    # Use the same Git executable selected by the fixture, not a different Git
    # installation whose push-option behavior might differ.
    configured_git = json.loads(m['config'].read_text())['git']
    assert Path(configured_git).is_file()
    operation = (['update-ref', '-d', ref] if replacement is None
                 else ['update-ref', ref, replacement])
    wrapper.write_text(
        '#!/usr/bin/env python3\n'
        'import os, pathlib, subprocess, sys\n'
        f'git = {configured_git!r}\n'
        f'remote = {str(m["remote"])!r}\n'
        f'trigger = pathlib.Path({str(trigger)!r})\n'
        f'witnessed = pathlib.Path({str(witnessed)!r})\n'
        'args = sys.argv[1:]\n'
        'if trigger.exists() and "push" in args and "gitlab" in args:\n'
        f'    subprocess.run([git, "--git-dir", remote, *{operation!r}], check=True)\n'
        f'    observed = subprocess.run([git, "--git-dir", remote, "rev-parse", "--verify", {ref!r}], capture_output=True, text=True)\n'
        '    witnessed.write_text(observed.stdout.strip() if observed.returncode == 0 else "absent")\n'
        '    trigger.unlink()\n'
        'os.execv(git, [git, *args])\n'
    )
    wrapper.chmod(0o700)
    config = json.loads(m['config'].read_text())
    config['git'] = str(wrapper)
    m['config'].write_text(json.dumps(config))
    return trigger, witnessed


def _held(report, ref):
    return any(item.get('ref') == ref for item in report.get('pending', []))


def _intercept_lost_ack(m, ref):
    """Let one real push land, then report transport failure to the worker."""
    wrapper = m['root'] / 'git-lost-update-ack'
    trigger = m['root'] / 'lose-update-ack'
    witnessed = m['root'] / 'landed-before-ack-loss'
    configured_git = json.loads(m['config'].read_text())['git']
    wrapper.write_text(
        '#!/usr/bin/env python3\n'
        'import os, pathlib, subprocess, sys\n'
        f'git = {configured_git!r}\n'
        f'remote = {str(m["remote"])!r}\n'
        f'trigger = pathlib.Path({str(trigger)!r})\n'
        f'witnessed = pathlib.Path({str(witnessed)!r})\n'
        'args = sys.argv[1:]\n'
        'if trigger.exists() and "push" in args and "gitlab" in args:\n'
        '    result = subprocess.run([git, *args], capture_output=True, text=True)\n'
        '    if result.returncode != 0:\n'
        '        sys.exit(result.returncode)\n'
        f'    observed = subprocess.run([git, "--git-dir", remote, "rev-parse", "--verify", {ref!r}], capture_output=True, text=True)\n'
        '    witnessed.write_text(observed.stdout.strip() if observed.returncode == 0 else "absent")\n'
        '    trigger.unlink()\n'
        '    sys.exit(1)\n'
        'os.execv(git, [git, *args])\n'
    )
    wrapper.chmod(0o700)
    config = json.loads(m['config'].read_text())
    config['git'] = str(wrapper)
    m['config'].write_text(json.dumps(config))
    return trigger, witnessed


def test_deleted_existing_destination_is_not_recreated_by_stale_push(mirrors):
    m = mirrors
    ref = 'refs/heads/main'
    trigger, witnessed = _intercept_gitlab_push(m, ref, None)
    assert worker(m, initialize=True).returncode == 0
    source = branch(m, m['base'], 'hub advances before destination deletion')
    publish(m, 'hub', source, ref)
    trigger.touch()

    result = worker(m)
    report = json.loads(result.stdout)
    assert witnessed.read_text() == 'absent'
    assert oid(m, 'remote', ref) is None
    assert oid(m, 'hub', ref) == source
    assert _held(report, ref)
    assert not any(action.get('ref') == ref and action.get('result') == 'fast-forwarded'
                   for action in report.get('actions', []))
    restarted = json.loads(worker(m).stdout)
    assert oid(m, 'remote', ref) is None
    assert _held(restarted, ref)


def test_concurrent_destination_rewind_is_not_replaced_by_stale_push(mirrors):
    m = mirrors
    ref = 'refs/heads/main'
    trigger, witnessed = _intercept_gitlab_push(m, ref, m['base'])
    assert worker(m, initialize=True).returncode == 0
    middle = branch(m, m['base'], 'snapshot destination')
    source = branch(m, middle, 'hub source after snapshot destination')
    publish(m, 'remote', middle, ref)
    publish(m, 'hub', source, ref)
    trigger.touch()

    result = worker(m)
    report = json.loads(result.stdout)
    assert witnessed.read_text() == m['base']
    assert oid(m, 'remote', ref) == m['base']
    assert oid(m, 'hub', ref) == source
    assert _held(report, ref)
    assert not any(action.get('ref') == ref and action.get('result') == 'fast-forwarded'
                   for action in report.get('actions', []))
    restarted = json.loads(worker(m).stdout)
    assert oid(m, 'remote', ref) == m['base']
    assert _held(restarted, ref)


def test_concurrently_created_ref_is_not_advanced_by_stale_create(mirrors):
    m = mirrors
    ref = 'refs/heads/concurrent-create'
    middle = branch(m, m['base'], 'unadvertised middle')
    source = branch(m, middle, 'hub source for absent destination')
    # The fixture-only ref makes the middle object available on GitLab without
    # advertising the tested branch in the worker's heads/tags snapshot.
    publish(m, 'remote', middle, 'refs/fixture/hidden-middle')
    trigger, witnessed = _intercept_gitlab_push(m, ref, middle)
    assert worker(m, initialize=True).returncode == 0
    publish(m, 'hub', source, ref)
    trigger.touch()

    result = worker(m)
    report = json.loads(result.stdout)
    assert witnessed.read_text() == middle
    assert oid(m, 'remote', ref) == middle
    assert oid(m, 'hub', ref) == source
    assert _held(report, ref)
    assert not any(action.get('ref') == ref and action.get('result') == 'fast-forwarded'
                   for action in report.get('actions', []))
    restarted = json.loads(worker(m).stdout)
    assert oid(m, 'remote', ref) == middle
    assert _held(restarted, ref)


def test_lost_ack_for_existing_update_then_deletion_is_not_replayed(mirrors):
    m = mirrors
    ref = 'refs/heads/main'
    trigger, witnessed = _intercept_lost_ack(m, ref)
    assert worker(m, initialize=True).returncode == 0
    source = branch(m, m['base'], 'existing ref update with lost acknowledgment')
    publish(m, 'hub', source, ref)
    trigger.touch()

    interrupted = json.loads(worker(m).stdout)
    assert witnessed.read_text() == source
    assert oid(m, 'remote', ref) == source
    assert _held(interrupted, ref)
    git(m, 'update-ref', '-d', ref, repo='remote')

    restarted = json.loads(worker(m).stdout)
    assert oid(m, 'remote', ref) is None
    assert oid(m, 'hub', ref) == source
    assert _held(restarted, ref)
