"""Capacity thresholds do not gate mirrors; identities still do."""
import json
from pathlib import Path
import pytest
from test_mirror_sync_service import branch, cmd, mirrors, oid, publish, worker

@pytest.mark.parametrize('legacy', [None, {'reserve_bytes': 40000000000}, {'checker':'/missing/helper.py'}, {'mode':'none'}])
def test_capacity_helpers_not_required(mirrors, legacy):
    m = mirrors
    cfg = json.loads(m['config'].read_text())
    checker = Path(cfg['storage']['checker'])
    checker.write_text("raise RuntimeError('capacity helper must never execute')\n")
    if legacy is None:
        cfg.pop('storage')
    else:
        cfg['storage'] = legacy
    m['config'].write_text(json.dumps(cfg))
    assert worker(m, initialize=True).returncode == 0
    commit = branch(m, m['base'], 'no reserve gate')
    publish(m, 'hub', commit, 'refs/heads/no-reserve')
    result = worker(m)
    assert result.returncode == 0, result.stdout
    assert oid(m, 'remote', 'refs/heads/no-reserve') == commit
    # The same worker still refuses a rewind of a published branch.
    cmd('git', '--git-dir='+str(m['hub']), 'update-ref', 'refs/heads/no-reserve', m['base'], env=m['env'])
    result = worker(m)
    assert oid(m, 'remote', 'refs/heads/no-reserve') == commit

@pytest.mark.parametrize('url', ['https://github.com/fixture/inactive.git',
                               'ssh://ssh.github.com/fixture/inactive.git'])
def test_github_destination_refused_before_any_contact(mirrors, url):
    m = mirrors
    cfg = json.loads(m['config'].read_text())
    cfg['gitlab'] = url
    m['config'].write_text(json.dumps(cfg))
    result = worker(m, initialize=True)
    assert result.returncode == 2 and 'GitHub mirror is inactive' in result.stdout
    assert not m['cache'].exists()
