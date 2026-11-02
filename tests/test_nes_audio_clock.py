"""Authored6502 clock scenarios; optional explicit prepared toolchain."""
import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture(scope='module')
def clock_receipt(tmp_path_factory):
    root=os.environ.get('FDISBULL_CC65_ROOT')
    if not root:
        pytest.skip('FDISBULL_CC65_ROOT must select the prepared sim65 toolchain')
    script=Path(__file__).resolve().parents[1]/'scripts/check_nes_audio_clock.py'
    spec=importlib.util.spec_from_file_location('clock_contract_check',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.verify(root,tmp_path_factory.mktemp('nes-clock')/'result')


@pytest.mark.parametrize('scenario',[
    'future-half','lost-half-catchup','no-retroactive-request','producer-phase2',
    'fifo-coincident','fifo-head-blocks','counter-wrap','counter-wrap-nmi',
    'nmi-during-tick','nmi-during-request','bounded-four','nmi-every-tick-bounded',
    'debug-bypass','half-range-ambiguous','ring-wrap-fifo',
])
def test_actual_6502_service_clock_scenario(clock_receipt,scenario):
    assert clock_receipt['passed']
    assert scenario in clock_receipt['cases']


@pytest.mark.parametrize('mutation',[
    'future-half','retroactive-stamp','stale-frontier','unbounded-five',
])
def test_clock_scenarios_reject_known_bad_implementations(clock_receipt,mutation):
    result=next(item for item in clock_receipt['negative_controls'] if item['variant']==mutation)
    assert result['exit_code']!=0
    assert result['observed_failure'].startswith('FAIL ')
