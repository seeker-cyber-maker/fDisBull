"""Real local-Git witnesses for the mirror service (no network or real mirrors)."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

class RedactedEnvironment(dict):
    def __repr__(self):
        return '<Git test environment>'


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / 'scripts' / 'mirror_sync_service.py'


def cmd(*args, cwd=None, env=None, check=True):
    result = subprocess.run([str(x) for x in args], cwd=cwd, env=env,
        text=True, capture_output=True, timeout=70)
    if check:
        assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result


@pytest.fixture
def mirrors(tmp_path):
    env = RedactedEnvironment(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
        GIT_TERMINAL_PROMPT='0', PYTHONDONTWRITEBYTECODE='1',
        TMPDIR='/Volumes/CODEX/fdb-checkpoint-tmp')
    hub, remote, seed = (tmp_path / item for item in ('hub.git', 'gitlab.git', 'seed'))
    for path in (hub, remote):
        cmd('git', 'init', '--bare', path, env=env)
    cmd('git', '--git-dir', remote, 'config', 'receive.advertisePushOptions', 'true', env=env)
    hook = remote / 'hooks' / 'pre-receive'
    hook.write_text('#!/bin/sh\n[ "$GIT_PUSH_OPTION_COUNT" = 1 ] && [ "$GIT_PUSH_OPTION_0" = ci.skip ] || exit 1\nprintf "%s\\n" "$GIT_PUSH_OPTION_0" >> push-options.log\ncat >/dev/null\n')
    hook.chmod(0o755)
    cmd('git', 'init', seed, env=env)
    cmd('git', '-C', seed, 'config', 'user.name', 'Authored test', env=env)
    cmd('git', '-C', seed, 'config', 'user.email', 'test@example.invalid', env=env)
    (seed / 'authored.txt').write_text('fixture\n')
    cmd('git', '-C', seed, 'add', 'authored.txt', env=env)
    cmd('git', '-C', seed, 'commit', '-m', 'authored root', env=env)
    base = cmd('git', '-C', seed, 'rev-parse', 'HEAD', env=env).stdout.strip()
    cmd('git', '-C', seed, 'push', hub, f'{base}:refs/heads/main', env=env)
    cmd('git', '-C', seed, 'push', '-o', 'ci.skip', remote, f'{base}:refs/heads/main', env=env)
    config = tmp_path / 'config.json'
    cache, state = tmp_path / 'cache.git', tmp_path / 'state'
    config.write_text(json.dumps(dict(format='fdisbull-mirror-sync-1', git=cmd('which','git',env=env).stdout.strip(),
        hub=str(hub), gitlab=str(remote), cache=str(cache), state_dir=str(state), volumes=[],
        command_timeout_s=45, run_timeout_s=55)))
    return dict(env=env, hub=hub, remote=remote, seed=seed, base=base, config=config,
                cache=cache, state=state, root=tmp_path)


def git(m, *args, repo='seed', check=True):
    return cmd('git', '-C' if repo == 'seed' else '--git-dir', m[repo], *args,
               env=m['env'], check=check)


def branch(m, parent, message):
    tree = git(m, 'rev-parse', parent + '^{tree}').stdout.strip()
    return git(m, 'commit-tree', tree, '-p', parent, '-m', message).stdout.strip()


def publish(m, repo, oid, ref):
    extra = ['-o', 'ci.skip'] if repo == 'remote' else []
    cmd('git', '-C', m['seed'], 'push', *extra, m[repo], f'{oid}:{ref}', env=m['env'])


def oid(m, repo, ref):
    result = git(m, 'rev-parse', '--verify', ref, repo=repo, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def worker(m, *, initialize=False):
    args = [sys.executable, WORKER, '--config', m['config']]
    if initialize: args.append('--initialize')
    return cmd(*args, env=m['env'], check=False)


def refs(m, repo):
    result = git(m, 'for-each-ref', '--format=%(refname) %(objectname)', repo=repo)
    return dict(line.split(' ', 1) for line in result.stdout.splitlines())


def test_two_way_fast_forward_and_push_options(mirrors):
    m = mirrors
    init = worker(m, initialize=True)
    assert init.returncode == 0, (init.stdout, init.stderr)
    first = branch(m, m['base'], 'from hub')
    publish(m, 'hub', first, 'refs/heads/from-hub')
    result = worker(m)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert oid(m, 'remote', 'refs/heads/from-hub') == first
    second = branch(m, first, 'from gitlab')
    publish(m, 'remote', second, 'refs/heads/from-hub')
    result = worker(m)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert oid(m, 'hub', 'refs/heads/from-hub') == second
    archived = {oid for ref, oid in refs(m, 'cache').items() if ref.startswith('refs/mirror-sync/archive/')}
    assert {m['base'], first, second} <= archived
    assert set((m['remote'] / 'push-options.log').read_text().splitlines()) == {'ci.skip'}
    assert all(not ref.startswith(('refs/remotes/', 'refs/archive/', 'refs/mirror-sync/')) for ref in refs(m, 'remote'))


def test_conflicts_tags_and_deletion_do_not_overwrite(mirrors):
    m = mirrors
    init = worker(m, initialize=True)
    assert init.returncode == 0, (init.stdout, init.stderr)
    left = branch(m, m['base'], 'hub divergent')
    right = branch(m, m['base'], 'gitlab divergent')
    publish(m, 'hub', left, 'refs/heads/diverged')
    publish(m, 'remote', right, 'refs/heads/diverged')
    publish(m, 'hub', left, 'refs/tags/immutable')
    publish(m, 'remote', right, 'refs/tags/immutable')
    publish(m, 'hub', left, 'refs/tags/new-tag')
    worker(m)
    assert oid(m, 'hub', 'refs/heads/diverged') == left
    assert oid(m, 'remote', 'refs/heads/diverged') == right
    assert oid(m, 'hub', 'refs/tags/immutable') == left
    assert oid(m, 'remote', 'refs/tags/immutable') == right
    assert oid(m, 'remote', 'refs/tags/new-tag') == left
    cache_refs = refs(m, 'cache')
    archived = {oid for ref, oid in cache_refs.items() if ref.startswith('refs/mirror-sync/archive/')}
    assert {left, right} <= archived
    assert not any('archive' in ref or ref.startswith(('refs/remotes/', 'refs/mirror-sync/')) for ref in refs(m, 'remote'))
    stable = branch(m, m['base'], 'deletion witness')
    publish(m, 'hub', stable, 'refs/heads/deleted-later')
    worker(m)
    assert oid(m, 'remote', 'refs/heads/deleted-later') == stable
    git(m, 'update-ref', '-d', 'refs/heads/deleted-later', repo='remote')
    worker(m)
    assert oid(m, 'remote', 'refs/heads/deleted-later') is None
    assert oid(m, 'hub', 'refs/heads/deleted-later') == stable


def test_checked_out_and_prunable_worktrees_refuse_incoming_but_other_branch_syncs(mirrors):
    m = mirrors
    git(m, 'symbolic-ref', 'HEAD', 'refs/heads/main', repo='hub')
    init = worker(m, initialize=True)
    assert init.returncode == 0, (init.stdout, init.stderr)
    git(m, 'update-ref', 'refs/heads/checked', m['base'], repo='hub')
    git(m, 'update-ref', 'refs/heads/prunable', m['base'], repo='hub')
    checked, missing = m['root'] / 'checked', m['root'] / 'missing-worktree'
    git(m, 'worktree', 'add', checked, 'checked', repo='hub')
    git(m, 'worktree', 'add', missing, 'prunable', repo='hub')
    (checked / 'dirty.txt').write_text('do not overwrite\n')
    (checked / 'authored.txt').write_text('tracked dirty edit\n')
    missing.rename(m['root'] / 'retained-prunable-worktree')
    incoming = branch(m, m['base'], 'remote updates')
    for name in ('checked', 'prunable', 'independent'):
        publish(m, 'remote', incoming, 'refs/heads/' + name)
    worker(m)
    assert oid(m, 'hub', 'refs/heads/checked') == m['base']
    assert oid(m, 'hub', 'refs/heads/prunable') == m['base']
    assert oid(m, 'hub', 'refs/heads/independent') == incoming
    assert (checked / 'dirty.txt').read_text() == 'do not overwrite\n'
    assert (checked / 'authored.txt').read_text() == 'tracked dirty edit\n'
    assert cmd('git', '-C', checked, 'rev-parse', 'HEAD', env=m['env']).stdout.strip() == m['base']


def test_offline_fetch_does_not_push_stale_snapshot(mirrors):
    m = mirrors
    init = worker(m, initialize=True)
    assert init.returncode == 0, (init.stdout, init.stderr)
    pending = branch(m, m['base'], 'not published while offline')
    publish(m, 'hub', pending, 'refs/heads/offline')
    remote_ref_before = refs(m, 'remote')
    away = m['root'] / 'offline-remote-retained.git'
    m['remote'].rename(away)
    try:
        result = worker(m)
        assert result.returncode != 0
        assert oid(m, 'hub', 'refs/heads/offline') == pending
    finally:
        away.rename(m['remote'])
    assert refs(m, 'remote') == remote_ref_before
    assert oid(m, 'remote', 'refs/heads/offline') is None


def test_worker_lock_prevents_overlapping_runs(mirrors):
    m = mirrors
    settings = json.loads(m['config'].read_text())
    real_git = settings['git']
    wrapper = m['root'] / 'controlled-git'
    marker, release, block = (m['root'] / name for name in ('git-entered', 'release-git', 'block-git'))
    wrapper.write_text('#!/bin/sh\ncase " $* " in *" ls-remote "*) '
        f'if [ -f "{block}" ]; then touch "{marker}"; while [ ! -f "{release}" ]; do sleep .1; done; fi;; esac\n'
        f'exec "{real_git}" "$@"\n')
    wrapper.chmod(0o755)
    settings['git'] = str(wrapper)
    m['config'].write_text(json.dumps(settings))
    init = worker(m, initialize=True)
    assert init.returncode == 0, (init.stdout, init.stderr)
    block.touch()
    process = subprocess.Popen([sys.executable, str(WORKER), '--config', str(m['config'])],
        env=m['env'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    import time
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        assert marker.exists(), process.communicate(timeout=2) if process.poll() is not None else 'worker did not start git'
        second = worker(m)
        assert second.returncode == 3, (second.stdout, second.stderr)
    finally:
        release.touch()
        stdout, stderr = process.communicate(timeout=60)
    assert process.returncode == 0, (stdout, stderr)


def test_missing_mount_refuses_without_creating_external_cache(mirrors):
    m = mirrors
    settings = json.loads(m['config'].read_text())
    missing = m['root'] / 'not-mounted'
    settings['cache'] = str(missing / 'cache-parent' / 'cache.git')
    settings['volumes'] = [dict(path=str(missing), uuid='MISSING')]
    m['config'].write_text(json.dumps(settings))
    result = worker(m, initialize=True)
    assert result.returncode == 2 and 'expected mounted volume is unavailable' in result.stdout
    assert not missing.exists()
    assert oid(m, 'hub', 'refs/heads/main') == m['base']


def test_lost_expected_mount_refuses_before_existing_mirrors_change(mirrors):
    m = mirrors
    result = worker(m, initialize=True)
    assert result.returncode == 0, (result.stdout, result.stderr)
    settings = json.loads(m['config'].read_text())
    settings['volumes'] = [dict(path=str(m['root'] / 'not-mounted'), uuid='MISSING')]
    m['config'].write_text(json.dumps(settings))
    before = refs(m, 'hub'), refs(m, 'remote')
    result = worker(m)
    assert result.returncode == 2 and 'expected mounted volume is unavailable' in result.stdout
    assert (refs(m, 'hub'), refs(m, 'remote')) == before


def reject_branch(m, name):
    hook = m['remote'] / 'hooks' / 'pre-receive'
    hook.write_text('#!/bin/sh\n'
        '[ "$GIT_PUSH_OPTION_COUNT" = 1 ] && [ "$GIT_PUSH_OPTION_0" = ci.skip ] || exit 1\n'
        'while read old new ref; do\n'
        f'  [ "$ref" != refs/heads/{name} ] || exit 1\n'
        'done\nexit 0\n')
    hook.chmod(0o755)


def test_rejected_branch_does_not_block_independent_branch(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    commit = branch(m, m['base'], 'independent after rejected push')
    publish(m, 'hub', commit, 'refs/heads/a-rejected')
    publish(m, 'hub', commit, 'refs/heads/z-independent')
    reject_branch(m, 'a-rejected')
    worker(m)
    assert oid(m, 'remote', 'refs/heads/a-rejected') is None
    assert oid(m, 'remote', 'refs/heads/z-independent') == commit
    assert oid(m, 'hub', 'refs/heads/a-rejected') == commit


def test_tombstone_survives_an_unrelated_push_failure_and_restart(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    commit = branch(m, m['base'], 'observed before deletion')
    publish(m, 'hub', commit, 'refs/heads/previously-seen')
    assert worker(m).returncode == 0
    assert oid(m, 'remote', 'refs/heads/previously-seen') == commit
    git(m, 'update-ref', '-d', 'refs/heads/previously-seen', repo='remote')
    publish(m, 'hub', commit, 'refs/heads/a-rejected')
    reject_branch(m, 'a-rejected')
    failed = worker(m)
    assert any(entry.get('reason') == 'push-failed' and entry.get('ref') == 'refs/heads/a-rejected'
               for entry in json.loads(failed.stdout).get('pending', []))
    assert oid(m, 'remote', 'refs/heads/previously-seen') is None
    reject_branch(m, 'never-matches')
    resumed = worker(m)  # a fresh process retains the deletion and uncertain creation
    assert oid(m, 'remote', 'refs/heads/previously-seen') is None
    assert oid(m, 'hub', 'refs/heads/previously-seen') == commit
    assert oid(m, 'remote', 'refs/heads/a-rejected') is None
    assert any(entry.get('ref') == 'refs/heads/a-rejected'
               for entry in json.loads(resumed.stdout).get('pending', []))


def test_changed_cache_remote_refuses_before_any_push(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    pending = branch(m, m['base'], 'must not publish after cache tampering')
    publish(m, 'hub', pending, 'refs/heads/pending')
    git(m, 'remote', 'set-url', 'gitlab', str(m['root'] / 'other.git'), repo='cache')
    before = refs(m, 'hub'), refs(m, 'remote')
    result = worker(m)
    assert result.returncode != 0
    assert (refs(m, 'hub'), refs(m, 'remote')) == before
    assert oid(m, 'remote', 'refs/heads/pending') is None


def test_interrupted_offline_initialization_can_resume_owned_cache(mirrors):
    m = mirrors
    away = m['root'] / 'retained-offline-remote.git'
    m['remote'].rename(away)
    try:
        result = worker(m, initialize=True)
        assert result.returncode != 0
        assert m['cache'].is_dir()
    finally:
        away.rename(m['remote'])
    resumed = worker(m, initialize=True)
    assert resumed.returncode == 0, (resumed.stdout, resumed.stderr)
    assert worker(m).returncode == 0
    assert oid(m, 'hub', 'refs/heads/main') == oid(m, 'remote', 'refs/heads/main') == m['base']


def test_initialize_refuses_foreign_unmarked_bare_cache(mirrors):
    m = mirrors
    cmd('git', 'init', '--bare', m['cache'], env=m['env'])
    before = refs(m, 'cache'), refs(m, 'hub'), refs(m, 'remote')
    result = worker(m, initialize=True)
    assert result.returncode != 0
    assert (refs(m, 'cache'), refs(m, 'hub'), refs(m, 'remote')) == before
    assert git(m, 'remote', repo='cache').stdout.strip() == ''


def test_extra_push_url_refuses_before_either_destination_changes(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    hub_commit = branch(m, m['base'], 'hub change before bad push URL')
    remote_commit = branch(m, m['base'], 'remote change before bad push URL')
    publish(m, 'hub', hub_commit, 'refs/heads/from-hub')
    publish(m, 'remote', remote_commit, 'refs/heads/from-remote')
    git(m, 'config', '--add', 'remote.gitlab.pushurl', str(m['remote']), repo='cache')
    git(m, 'config', '--add', 'remote.gitlab.pushurl', str(m['root'] / 'unauthorized.git'), repo='cache')
    before = refs(m, 'hub'), refs(m, 'remote')
    result = worker(m)
    assert result.returncode != 0
    assert (refs(m, 'hub'), refs(m, 'remote')) == before
    assert oid(m, 'remote', 'refs/heads/from-hub') is None
    assert oid(m, 'hub', 'refs/heads/from-remote') is None


def test_followtags_config_cannot_publish_unselected_cache_tag(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    commit = branch(m, m['base'], 'commit pointed to by stray annotated tag')
    publish(m, 'hub', commit, 'refs/heads/push-only-branch')
    git(m, 'fetch', '--no-tags', 'hub', 'refs/heads/push-only-branch', repo='cache')
    git(m, 'config', 'user.name', 'Authored test', repo='cache')
    git(m, 'config', 'user.email', 'test@example.invalid', repo='cache')
    git(m, 'config', 'push.followTags', 'true', repo='cache')
    git(m, 'tag', '-a', 'stray-local-tag', '-m', 'must stay in cache', commit, repo='cache')
    result = worker(m)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert oid(m, 'remote', 'refs/heads/push-only-branch') == commit
    assert oid(m, 'remote', 'refs/tags/stray-local-tag') is None
    assert oid(m, 'hub', 'refs/tags/stray-local-tag') is None
    assert oid(m, 'cache', 'refs/tags/stray-local-tag') is not None


def test_valid_branch_name_containing_plus_syncs(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    commit = branch(m, m['base'], 'valid plus in branch')
    publish(m, 'hub', commit, 'refs/heads/feature/a+b')
    result = worker(m)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert oid(m, 'remote', 'refs/heads/feature/a+b') == commit


def test_lost_ack_created_ref_is_not_recreated_after_deletion(mirrors):
    m = mirrors
    settings = json.loads(m['config'].read_text())
    real_git = settings['git']
    wrapper = m['root'] / 'git-lost-ack'
    enabled, fired = m['root'] / 'lose-next-push', m['root'] / 'lost-push-ack'
    wrapper.write_text('#!/bin/sh\ncase " $* " in *" push "*) '
        f'if [ -f "{enabled}" ] && [ ! -f "{fired}" ]; then '
        f'"{real_git}" "$@" || exit $?; touch "{fired}"; exit 1; fi;; esac\n'
        f'exec "{real_git}" "$@"\n')
    wrapper.chmod(0o755)
    settings['git'] = str(wrapper)
    m['config'].write_text(json.dumps(settings))
    assert worker(m, initialize=True).returncode == 0
    commit = branch(m, m['base'], 'remote created despite lost acknowledgment')
    publish(m, 'hub', commit, 'refs/heads/lost-ack')
    enabled.touch()
    worker(m)
    assert fired.exists() and oid(m, 'remote', 'refs/heads/lost-ack') == commit
    git(m, 'update-ref', '-d', 'refs/heads/lost-ack', repo='remote')
    worker(m)
    assert oid(m, 'remote', 'refs/heads/lost-ack') is None
    assert oid(m, 'hub', 'refs/heads/lost-ack') == commit


def test_remote_readback_descendant_is_fetched_archived_and_reconciled(mirrors):
    m = mirrors
    assert worker(m, initialize=True).returncode == 0
    sent = branch(m, m['base'], 'outbound race base')
    advanced = branch(m, sent, 'remote concurrent descendant')
    # The remote owns this descendant before the run, but its fixture-only ref
    # is outside the worker's heads/tags snapshots and must not seed the cache.
    publish(m, 'remote', advanced, 'refs/fixture/hidden-descendant')
    publish(m, 'hub', sent, 'refs/heads/raced')
    assert git(m, 'cat-file', '-e', advanced + '^{commit}', repo='cache', check=False).returncode != 0
    hook = m['remote'] / 'hooks' / 'post-receive'
    hook.write_text('#!/bin/sh\nwhile read old new ref; do\n'
        f'  if [ "$ref" = refs/heads/raced ] && [ "$new" = {sent} ]; then\n'
        f'    git update-ref refs/heads/raced {advanced} {sent} || exit 1\n'
        '  fi\ndone\n')
    hook.chmod(0o755)
    result = worker(m)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert oid(m, 'remote', 'refs/heads/raced') == advanced
    archived = {oid for ref, oid in refs(m, 'cache').items() if ref.startswith('refs/mirror-sync/archive/')}
    assert advanced in archived
    assert oid(m, 'hub', 'refs/heads/raced') == sent
    result = worker(m)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert oid(m, 'hub', 'refs/heads/raced') == advanced
    assert oid(m, 'remote', 'refs/heads/raced') == advanced
    assert 'refs/fixture/hidden-descendant' not in refs(m, 'hub')
