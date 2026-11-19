from copy import copy, deepcopy
import pytest
from test_qemu_dos_source_admission import owned
from test_qemu_runtime_memory import ram, ADDRESS
from test_qemu_movement import moving
from test_qemu_scenes import save, definition


def test_replaced_owner_after_clock_is_never_locked(moving):
    o=moving;s=o.session;save(o)
    original=s.vm;replacement=copy(original);replacement.process=copy(original.process)
    class ForeignLock:
        calls=0
        def acquire(self, **kwargs):self.calls+=1;return True
        def release(self):pass
    replacement.lock=ForeignLock()
    clock=s.clock_observe
    def replaced():
        result=clock();s.vm=replacement;return result
    s.clock_observe=replaced
    try:
        with pytest.raises(ValueError,match='owner|epoch'):s.scene_check('room')
        assert replacement.lock.calls==0,'scene acquired a replacement owner lock before rejecting identity change'
        assert not o.runs and not o.writes and not o.closed
    finally:s.vm=original


def test_compact_unknown_binding_preserves_explicit_incomplete_scope(moving):
    o=moving;save(o)
    o.session._invalidate_runtime_bindings()
    result=o.session.scene_check('room',object='actor',compact=True)
    assert result['status']=='unavailable' and result['complete'] is False
    assert result['observation_profile']=={'kind':'runtime-memory','version':1}
    assert result['completion_scope']=='declared-runtime-predicates'
    assert result['capture_context_verified'] is False and 'frame' not in result
    assert result['memory_captures_count']==0
    assert not o.runs and not o.writes


def test_first_capture_failure_does_not_probe_later_bindings(moving):
    o=moving;doc=definition();doc['match']={'all':[
        {'runtime_memory':dict(binding='unknown-first',length=1,hex='00')},
        {'runtime_memory':dict(binding='move-state',offset=2,length=1,hex='00')} ]}
    save(o,doc);before=len(o.reads)
    result=o.session.scene_check('room')
    assert result['status']=='unavailable' and not result['complete']
    assert len(o.reads)==before and result['evaluation_budget']['stopped']
    assert not o.runs and not o.writes
