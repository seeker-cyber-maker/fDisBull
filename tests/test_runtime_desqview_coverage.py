"""Authored stopped-manager evidence; no original bytes or guest execution."""
from copy import deepcopy
import struct

import pytest

from fdisbull import runtime_desqview as dv
from test_runtime_desqview import native  # Reuse the source-qualified authored fixture.


def supervisor(native):
    native.observed['address_state'].update(cpu_mode='protected',code_bits=32)
    native.observed['address_state']['segments']['cs']=dict(selector='0x10',base='0x0')
    native.observed['registers']['cpu_mode']='protected'
    native.observed['registers']['registers']['eip']='0x123456'


def test_valid_lifecycle_coverage_survives_unrelated_protected_cpu_context(native):
    provider=dv.discover(native);supervisor(native);before=bytes(native.ram)
    with pytest.raises(dv.DesqviewProviderError):provider.current_identity()
    result=provider.validate_coverage()
    assert not isinstance(result,dict) or 'handle' not in result
    assert bytes(native.ram)==before  # Pure observation; not an injected task query.


@pytest.mark.parametrize('change',['fingerprint','vector','run','multi_cpu','incoherent'])
def test_invalid_coverage_at_protected_stop_refuses(native,change):
    provider=dv.discover(native);supervisor(native)
    if change=='fingerprint':native.ram[native.base+dv.FINGERPRINTS[0][0]]^=1
    if change=='vector':native.ram[0x54:0x58]=struct.pack('<HH',0x100,0x3000)
    if change=='run':native.run_id='another-run'
    if change=='multi_cpu':native.observed['address_state']['machine_vcpus']=2
    if change=='incoherent':native.observed['address_state']['register_context_match']=False
    with pytest.raises(dv.DesqviewProviderError):provider.validate_coverage()


def test_changed_protected_stop_during_validation_is_not_coverage(native,monkeypatch):
    provider=dv.discover(native);supervisor(native);count=0
    def paused(session):
        nonlocal count
        count+=1;observed=deepcopy(session.observed)
        if count>1:observed['registers']['registers']['eip']='0x123457'
        return observed
    monkeypatch.setattr(dv,'_paused',paused)
    with pytest.raises(dv.DesqviewProviderError,match='changed CPU stop'):provider.validate_coverage()
