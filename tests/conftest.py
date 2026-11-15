"""Keep explicit native acceptance from succeeding through missing-backend skips."""
import os
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))


def pytest_addoption(parser):
    parser.addoption('--require-native',action='store_true',default=False,
                     help='Fail before collection unless FDISBULL_DOSBOX names an executable backend')


def pytest_configure(config):
    if not config.getoption('--require-native'):
        return
    configured=os.environ.get('FDISBULL_DOSBOX')
    if not configured:
        raise pytest.UsageError('--require-native requires FDISBULL_DOSBOX; native acceptance cannot be skipped')
    backend=Path(configured).expanduser()
    if not backend.is_file() or not os.access(backend,os.X_OK):
        raise pytest.UsageError('FDISBULL_DOSBOX must name an executable file for --require-native')


@pytest.fixture(scope='session')
def descriptor_alias_supported(tmp_path_factory):
    """Measure the private backup capability; never infer it from the OS name."""
    import importlib.util
    import sqlite3
    script = TESTS.parent/'scripts/fdb_backup.py'
    spec = importlib.util.spec_from_file_location('_fdb_capability_probe', script)
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)
    probe = tmp_path_factory.mktemp('sqlite-descriptor-alias')
    source = probe/'source'; source.mkdir(); database = source/'probe.fdb'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE authored(value TEXT)')
        connection.execute("INSERT INTO authored VALUES ('capability probe')")
    try:
        backup.capture_fdb(database, [], probe/'backup', 20)
    except ValueError as error:
        if 'descriptor-alias namespace' in str(error):
            return False
        raise
    return True


@pytest.fixture
def require_descriptor_alias(descriptor_alias_supported):
    if not descriptor_alias_supported:
        pytest.skip('Measured SQLite VFS canonicalizes descriptor aliases; private backup is fail-closed on this host')
