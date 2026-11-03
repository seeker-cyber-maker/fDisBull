from hashlib import sha256
from types import SimpleNamespace
import pytest
from examples.agi import dragon_inside_probe as inside
from test_agi_dragon_mirror_route import probe_fixture, stop, memory_read, word


def fixture(tmp_path, monkeypatch):
    o, old = probe_fixture(tmp_path, monkeypatch, 'water')
    o.remove_watch()
    code=bytearray(o.resources[51].code)
    code[0x429:0x430]=bytes((101,33,94,26,7,3,2))
    payload=len(code).to_bytes(2,'little')+code
    o.resources[51]=SimpleNamespace(code=bytes(code),payload=payload,resource_sha256=sha256(payload).hexdigest())
    o.d.memory[o.ds+0x4000:o.ds+0x4000+len(code)]=code
    monkeypatch.setattr(inside,'read',memory_read)
    monkeypatch.setattr(inside,'DROP_SHA',sha256(b'D'*28).hexdigest())
    monkeypatch.setattr(inside,'SUB_SHA',sha256(b'S'*13).hexdigest())
    monkeypatch.setattr(inside,'logic_layout',lambda _: {'instructions':{0x42d,0x42f}})
    p=inside.InsideWaterProbe(o);p.start();return o,p


def boundary_stop(o,p,stage):
    out=stop(o,p,stage)
    word(o.d,0x40108,0x442d)
    if stage=='return':o.d.register_state['general']['eax']='0x442d'
    if stage=='subtract':o.d.register_state['general']['esi']='0x4430'
    return out


def test_original_order_and_delta(tmp_path,monkeypatch):
    o,p=fixture(tmp_path,monkeypatch)
    for stage in ('drop','return','subtract'):p.handle_stop(boundary_stop(o,p,stage))
    assert p.proof['status']=='verified' and p.proof['complete']
    assert p.proof['known_effects']=={'score':13,'item_location':0}
    assert p.proof['order']==['drop','return','subtract'] and not o.d.runs


@pytest.mark.parametrize('stage',['drop','return','subtract'])
def test_foreign_stop_latches(tmp_path,monkeypatch,stage):
    o,p=fixture(tmp_path,monkeypatch)
    for prior in p.order[:p.order.index(stage)]:p.handle_stop(boundary_stop(o,p,prior))
    bad=boundary_stop(o,p,stage);bad['session']['stop_reason']['breakpoint_id']='foreign'
    with pytest.raises(RuntimeError):p.handle_stop(bad)
    assert p.failed and o.execution_blocked and not p.proof['complete'] and not o.d.runs


from copy import deepcopy
from examples.agi.verify_dragon_boundary import cpu_equal

def test_exact_saved_transient_data_segment_is_valid():
    cpu={'cpu_mode':'real','general':{'eax':'0x1'},'segments':{'cs':'0x0EFB','ds':'0x28F2'},'instruction_pointer':'0x982A','flags':'0x246'}
    assert cpu_equal(cpu,deepcopy(cpu))
    for key,value in [('cpu_mode','protected'),('instruction_pointer','0x982B'),('flags','0x247')]:
        other=deepcopy(cpu);other[key]=value;assert not cpu_equal(cpu,other)
    other=deepcopy(cpu);other['segments']['ds']='0x18F0';assert not cpu_equal(cpu,other)
    other=deepcopy(cpu);other['general']['eax']='0x2';assert not cpu_equal(cpu,other)
    other=deepcopy(cpu);del other['flags'];assert not cpu_equal(cpu,other)
