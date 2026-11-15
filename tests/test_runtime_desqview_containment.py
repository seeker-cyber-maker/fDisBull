"""Authored native-record doubles; source layout/native execution are separate."""
from copy import deepcopy
import struct

import pytest

from fdisbull import runtime_desqview as dv
from test_runtime_desqview import native


def test_current_process_uses_agreeing_task_and_mapping_routes(native):
    provider=dv.discover(native)
    identity=provider.current_identity();process=identity['process_identity']
    assert process['record']==dict(segment=0x7000,offset=0x100,linear=0x70100)
    assert process['mapping_context']==native.mapping
    assert process['key']==f'desqview-process:{native.mapping:04x}:00070100'
    relation=identity['process_membership']
    assert relation['qualified'] and relation['task_record']==identity['record']
    assert relation['owner_process_record']==process['record']
    assert 'physical' not in process and 'reusable' in process['qualification']
    # Native task paragraph alias and canonical record need not be the same
    # numeric linear address. The original resolver follows the backpointer.
    assert identity['record']['linear']!=native.handle*16


def test_two_task_handles_share_one_process_key(native):
    provider=dv.discover(native);first=provider.current_identity()['process_identity']
    native.add_task(0x9345,native.mapping,0x1800,0x7000,0x100)
    native.select_task(0x9345,native.mapping,0x1800)
    second=provider.current_identity()
    assert second['handle']==0x9345 and second['process_identity']==first


def test_unrelated_process_end_exposes_its_actual_target(native):
    provider=dv.discover(native);old_process=provider.current_identity()['process_identity']
    native.add_task(0x9345,0x1c00,0x1800,0x7100,0x200)
    native.select_task(0x9345,0x1c00,0x1800)
    registers=native.hook(5)
    registers['registers'].update(edx='0x9345',ebx='0x1c00')
    native.observed['registers']=deepcopy(registers)
    event=provider.interpret_event(registers)
    assert event['kind']=='process-end' and event['containment_qualified']
    assert event['target_relation']['task_handle']==0x9345
    assert event['process_identity']['record']['linear']==0x71200
    assert event['process_identity']['key']!=old_process['key']


def test_event_target_never_falls_back_to_a_mismatched_current_owner(native):
    provider=dv.discover(native)
    native.add_task(0x9345,0x1c00,0x1800,0x7100,0x200)
    registers=native.hook(5);registers['registers']['ebx']='0x1c00'
    native.observed['registers']=deepcopy(registers)
    event=provider.interpret_event(registers)
    assert event['current_identity']['process_identity']['mapping_context']==native.mapping
    assert not event['containment_qualified'] and event['process_identity'] is None
    assert event['target_relation']['qualified'] is False
    assert 'disagrees' in event['target_relation']['reason']


@pytest.mark.parametrize('event',[0x0c,0x0d])
def test_swap_targets_process_mapping_not_system_emitter_task(native,event):
    provider=dv.discover(native)
    native.add_task(0x9345,0x1c00,0x1800,0x7100,0x200)
    registers=native.hook(event);registers['registers']['ebx']='0x1c00'
    native.observed['registers']=deepcopy(registers)
    result=provider.interpret_event(registers)
    assert result['containment_qualified']
    assert result['handle']==native.handle
    assert result['process_identity']['mapping_context']==0x1c00
    assert result['current_identity']['process_identity']['mapping_context']==native.mapping
    assert result['target_relation']['kind']=='process-mapping'
    assert result['target_relation']['method']=='original-dv2.8-process-mapping-crosscheck'
    assert 'task_handle' not in result['target_relation']


@pytest.mark.parametrize('field',['task_process','mapping_process','alias_marker','alias_manager','canonical_backpointer'])
def test_partial_corrupt_or_unrelated_owner_fields_are_not_qualified(native,field):
    provider=dv.discover(native);record=native.data_segment*16+native.task_offset
    if field=='task_process':native.ram[record+dv.TASK_PROCESS]^=1
    if field=='mapping_process':native.ram[native.data_segment*16+native.mapping+dv.MAPPING_PROCESS]^=1
    if field=='alias_marker':native.ram[native.handle*16+4]^=1
    if field=='alias_manager':native.ram[native.handle*16+14]^=1
    if field=='canonical_backpointer':native.ram[record+12]^=1
    with pytest.raises(dv.DesqviewProviderError):provider.current_identity()
    result=provider.interpret_event(native.hook(5))
    assert not result['containment_qualified'] and result['process_identity'] is None
    assert dv.discover(native) is None


def test_native_record_key_does_not_encode_cr3_or_physical_placement(native):
    provider=dv.discover(native);before=provider.current_identity()['process_identity']
    native.observed['address_state']['control']={'CR3':'0x999000'}
    after=provider.current_identity()['process_identity']
    assert before==after
    # A repeated native record address is deliberately a repeated key, not a
    # new process lifetime; only tracker lifecycle generations can disambiguate.
    assert provider.current_identity()['process_identity']['key']==before['key']


def test_global_manager_end_remains_explicit_when_task_owner_is_gone(native):
    provider=dv.discover(native)
    struct.pack_into('<HH',native.ram,native.data_segment*16+native.mapping+dv.MAPPING_PROCESS,0,0)
    result=provider.interpret_event(native.hook(3))
    assert result['kind']=='dv-end' and result['process_identity'] is None
    assert result['containment_qualified'] is False
    assert result['current_identity'] is None


@pytest.mark.parametrize('span',dv.FINGERPRINTS[-3:])
def test_new_original_layout_consumer_fingerprint_changes_refuse(native,span):
    provider=dv.discover(native);native.ram[native.base+span[0]]^=1
    with pytest.raises(dv.DesqviewProviderError,match='fingerprint'):provider.current_identity()
    assert dv.discover(native) is None
