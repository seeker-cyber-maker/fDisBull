"""Keep explicit native acceptance from succeeding through missing-backend skips."""
import os
from pathlib import Path

import pytest


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
