"""PE32 width, relocation and original-image contracts, independent of a VM."""
import struct
import time

import pytest

from fixtures_formats import pe64
from fdisbull.project import Project
from fdisbull.wine_arch import REGISTERS32, validate_context
from fdisbull.wine_debugger import PEDebugSession
from fdisbull.wine_state import validate_edits
from fdisbull.wine_watch import access_facts, check_fetch_watch_alias


def pe32_relocated():
    """An authored I386 image with one independently specified HIGHLOW fixup."""
    data=bytearray(pe64());optional=0x98
    directories=bytes(data[optional+112:optional+240]);section=bytes(data[optional+240:optional+280])
    data[optional:optional+280]=bytes(280)
    struct.pack_into('<H',data,0x84,0x14c)
    struct.pack_into('<H',data,0x94,224)
    struct.pack_into('<H',data,optional,0x10b)
    struct.pack_into('<I',data,optional+16,0x1000)
    struct.pack_into('<I',data,optional+28,0x400000)
    struct.pack_into('<II',data,optional+32,0x1000,0x200)
    struct.pack_into('<II',data,optional+56,0x2000,0x200)
    struct.pack_into('<H',data,optional+68,3)
    struct.pack_into('<I',data,optional+92,16)
    data[optional+96:optional+224]=directories
    data[optional+224:optional+264]=section
    struct.pack_into('<II',data,optional+96+5*8,0x1180,12)
    struct.pack_into('<IIHH',data,0x380,0x1000,12,0x31b0,0)
    struct.pack_into('<I',data,0x3b0,0x401123)
    return bytes(data)


def context32():
    return {'eip':'0x401000','eflags':'0x202','thread':17,
            'general':{name:'0x0' for name in REGISTERS32-{'eip','eflags'}}}


def test_pe32_context_has_real_width_and_no_fake_64_bit_names():
    value=context32();assert validate_context(value,32) is value
    with pytest.raises(ValueError,match='architecture'):validate_context(value,64)
    value['general']['eax']='0x100000000'
    with pytest.raises(ValueError,match='exceeds'):validate_context(value,32)
    value=context32();value['general']['rax']='0x1'
    with pytest.raises(ValueError,match='mixed-width'):validate_context(value,32)


def test_pe32_expected_relocation_is_four_bytes_and_original_bytes_remain(tmp_path):
    path=tmp_path/'original.exe';original=pe32_relocated();path.write_bytes(original)
    with Project.create(tmp_path/'image.fdb',path) as project:
        assert project.bits==32 and project.meta['entry']==0x401000
        session=PEDebugSession.__new__(PEDebugSession)
        session.project=project;session.version=project.version(1);session.bits=32;session.static_base=0x400000;session.delta=0x100000
        session.regions=project.regions(1)
        session._expected={r.start:bytearray(r.data) for r in session.regions}
        session._relocate_expected()
        assert struct.unpack_from('<I',session._expected[0x401000],0x1b0)[0]==0x501123
        assert struct.unpack_from('<I',next(r.data for r in project.regions(1) if r.start==0x401000),0x1b0)[0]==0x401123
        assert path.read_bytes()==original


def test_pe32_watch_classification_uses_eax_and_32_bit_addressing():
    regs=context32();regs['general']['eax']='0x403000'
    facts=access_facts(bytes.fromhex('830001'),regs,0x403001,1)
    assert facts['ranges']==[{'address':0x403000,'length':4,'read':True,'write':True}]
    regs['general']['eax']='0x401080'
    with pytest.raises(ValueError,match='shares the fetched'):
        check_fetch_watch_alias(bytes.fromhex('8b00'),regs,0x401000,[(0x401080,0x401084)])


def test_pe32_checked_register_edits_refuse_wrong_names_widths_and_control_flags():
    validate_edits([],{'eax':{'expected':0,'value':0xffffffff}},bits=32)
    with pytest.raises(ValueError,match='register edit'):
        validate_edits([],{'rax':{'expected':0,'value':1}},bits=32)
    with pytest.raises(ValueError,match='register values'):
        validate_edits([],{'eax':{'expected':0,'value':0x100000000}},bits=32)
    with pytest.raises(ValueError,match='control flags'):
        validate_edits([],{'eflags':{'expected':0x202,'value':0x302}},bits=32)


@pytest.mark.parametrize('operation',['registers','step','trace','run','watch'])
def test_flat_pe32_decoder_and_execution_refuse_ldt_context_before_fetch_or_resume(operation):
    session=PEDebugSession.__new__(PEDebugSession);session.bits=32;closed=[];calls=[]
    raw=context32();raw.update(eip='0xf9',cs='0x2ef')
    session._pending_exec=None;session._execution={};session._layer_setup=lambda:None
    session.close=lambda:closed.append(True)
    def call(method,*args,**kwargs):
        calls.append(method)
        if method=='registers':return raw
        if method=='status':return {'stop_reason':{'kind':'entry'}}
        pytest.fail('Unsupported segmented PE32 context reached '+method)
    session.call=call
    with pytest.raises(Exception,match='Win16 NE adapter'):
        if operation=='registers':session.registers()
        elif operation=='step':session._step_instruction(time.monotonic()+1)
        elif operation=='trace':session._trace_native(1,time.monotonic()+1)
        elif operation=='run':session._continue_native(time.monotonic()+1)
        else:session._watch_stop({'stop_reason':{'kind':'memory-access'}})
    assert closed==[True] and set(calls)<= {'registers','status'}
