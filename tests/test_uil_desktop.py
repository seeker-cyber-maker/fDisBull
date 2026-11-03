"""Common UIL reaches real native arena/selection/host boundaries."""
from copy import deepcopy
import ctypes
import os
from pathlib import Path
import platform
import shutil
import subprocess
import threading

import pytest

from fixtures_common_uil import memory_bundle, mini_snake_program, mini_initial, package
from fdisbull.common_uil import digest
from fdisbull.uil_desktop import (build_desktop_shell, emit_desktop_shell, compile_desktop_shell,
    encode_desktop_study, decode_desktop_study, validate_desktop_plan, PLAN)


def desktop_fixture():
    legacy=mini_snake_program();functions=[];constants=[]
    for name in ('step','render'):
        program,presentation=memory_bundle(legacy,name)
        functions.append(program['functions'][0]);constants.append(presentation['functions'][0]['constants'])
    program,presentation=package(functions,constants)
    catalog={'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]}
    orchestration={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(program),
                   'bindings':[],'ownership':'copy-in-copy-out','max_call_depth':8}
    initial=mini_initial();initial[7]=1
    plan={'format':PLAN,'title':'Common UIL test','help':'Arrows and pointer are supplied through adapters.',
          'function_names':['step','render'],'initialize':0,'inputs':list(range(20,27)),
          'outputs':{'0':[[0,7]],'1':[[32,20]]},'commit_ranges':[[0,8],[32,20]],
          'replace_ranges':[[0,8]],'scratch_ranges':[[10,1]],
          'guards':[{'index':3,'min':0,'max':1}], 'array_guards':[],
          'render':{'function':1,'when_nonzero':7},
          'frame':{'offset':32,'width':5,'height':4,'palette':{'0':[0,0,0],'1':[0,255,0],'2':[255,0,0]}},
          'events':dict(function=0,kind=20,ascii=21,scan=22,x=23,y=24,buttons=25,clock=26,
                        quit_index=9,keyboard_kind=1,pointer_kind=2,clock_kind=0,tick_ms=54.92549323064085),
          'keymap':{'ArrowUp':{'ascii':0,'scan':72},'KeyW':{'ascii':119,'scan':0}}}
    return program,presentation,catalog,orchestration,plan,initial


@pytest.fixture
def desktop_root(tmp_path):
    external=os.environ.get('FDISBULL_NATIVE_TEST_ROOT')
    if external:
        import tempfile
        root=Path(external);root.mkdir(parents=True,exist_ok=True)
        return Path(tempfile.mkdtemp(prefix='desktop-',dir=root))
    return tmp_path


@pytest.fixture
def native_desktop(desktop_root):
    if platform.system()=='Darwin' and platform.machine()=='arm64':target='macos-arm64'
    elif platform.system()=='Linux' and platform.machine() in ('x86_64','amd64'):target='linux-x64'
    else:pytest.skip('native common desktop compiler host required')
    compiler=os.environ.get('FDISBULL_NATIVE_TEST_COMPILER') or shutil.which('clang' if target=='macos-arm64' else 'gcc')
    if not compiler:pytest.skip('native compiler unavailable')
    root=desktop_root/'build';manifest=build_desktop_shell(*desktop_fixture(),root,target,c_compiler=compiler)
    return root,manifest


def test_desktop_validates_memory_contract_before_creating_output(desktop_root):
    args=list(desktop_fixture());args[4]['inputs'][0]=0
    with pytest.raises(ValueError,match='overlap'):
        emit_desktop_shell(*args,desktop_root/'bad')
    assert not (desktop_root/'bad').exists()
    args=list(desktop_fixture());args[4]['events']['x']=args[4]['events']['y']
    with pytest.raises(ValueError,match='distinct'):
        emit_desktop_shell(*args,desktop_root/'bad')


def test_desktop_missing_intrinsic_requirement_refuses_before_output(desktop_root):
    variants=[{'name':'needs-v2','label':'Requires missing service','arithmetic':'portable-c',
               'module_requirements':{'functions':{'0':{'requires':[{'intrinsic':'sound.play','version':2}]}}}}]
    with pytest.raises(ValueError):emit_desktop_shell(*desktop_fixture(),desktop_root/'bad',variants=variants)
    assert not (desktop_root/'bad').exists()


def test_desktop_initial_shape_and_palette_are_admitted(desktop_root):
    args=list(desktop_fixture());args[-1]=args[-1][:-1]
    with pytest.raises(ValueError,match='initial arena'):emit_desktop_shell(*args,desktop_root/'bad')
    args=list(desktop_fixture());args[-1][32]=99
    with pytest.raises(ValueError,match='palette'):emit_desktop_shell(*args,desktop_root/'bad')


def test_desktop_selected_platform_selector_limit_is_checked_before_emission(desktop_root):
    docs=list(desktop_fixture());program,presentation,catalog,orchestration,plan,initial=deepcopy(docs)
    while len(program['functions'])<17:
        program['functions'].append(deepcopy(program['functions'][0]))
        presentation['functions'].append(deepcopy(presentation['functions'][0]))
    presentation['program_sha256']=orchestration['program_sha256']=digest(program)
    plan['function_names']=['function'+str(i) for i in range(17)]
    plan['outputs'].update({str(i):[[0,7]] for i in range(2,17)})
    with pytest.raises(ValueError,match='selector budget'):
        emit_desktop_shell(program,presentation,catalog,orchestration,plan,initial,desktop_root/'bad','windows-x64')
    assert not (desktop_root/'bad').exists()


def test_desktop_native_selectors_commit_and_refuse_atomically(native_desktop):
    root,m=native_desktop;library=ctypes.CDLL(str(root/m['library']))
    library.fdb_words.restype=ctypes.POINTER(ctypes.c_uint32)
    library.fdb_revision.restype=ctypes.c_uint64
    library.fdb_arithmetic_invocation_count.restype=ctypes.c_uint64
    snapshot=lambda:list(library.fdb_words()[:64])
    assert library.fdb_initialize(0)==0
    assert snapshot()[:7]==[2,1,0,1,1,2,1]
    first=snapshot();revision=library.fdb_revision()
    assert library.fdb_select_region(0,1)==0
    assert snapshot()==first and library.fdb_revision()==revision
    assert library.fdb_dispatch(None,None,0,1)==0
    assert snapshot()[:7]==[3,1,0,1,1,2,1]
    assert library.fdb_region_invocation_count(0,0)==1
    assert library.fdb_region_invocation_count(0,1)==1
    assert library.fdb_arithmetic_invocation_count(0,1,0)>0
    assert library.fdb_arithmetic_invocation_count(1,0,0)>0
    before=snapshot();revision=library.fdb_revision()
    assert library.fdb_select_region(0,99)!=0
    bad=(ctypes.c_uint32*1)(32);value=(ctypes.c_uint32*1)(2)
    assert library.fdb_call(0,bad,value,1,1)!=0
    assert snapshot()==before and library.fdb_revision()==revision
    results=[]
    t=threading.Thread(target=lambda:results.append(library.fdb_dispatch(None,None,0,1)))
    t.start();t.join();assert results==[1] and snapshot()==before
    library.fdb_close();assert library.fdb_closed()==1
    assert library.fdb_dispatch(None,None,0,1)!=0


def test_desktop_probe_uses_owned_arena_and_selected_compiled_backing(native_desktop):
    root,m=native_desktop
    commands=[{'kind':0,'flags':3},{'kind':4,'a':0,'b':1},
              {'kind':1,'a':0,'c':1,'clock':4,'flags':3},
              {'kind':1,'a':0,'b':2,'c':1,'clock':4,'flags':3}]
    incoming=root/'events.bin';outgoing=root/'observations.bin'
    incoming.write_bytes(encode_desktop_study(m,commands))
    done=subprocess.run([str(root/m['probe']),'--adapter-test',str(incoming),str(outgoing)],capture_output=True,timeout=30)
    assert done.returncode==0,done.stderr
    raw=outgoing.read_bytes();rows=decode_desktop_study(m,raw)
    # Opening the host and the study-header initialization are explicit calls.
    # This arithmetic microfixture deliberately uses a non-idempotent initializer.
    assert list(rows[0]['words'])[:2]==[3,1]
    assert list(rows[2]['words'])[:2]==[4,1]
    assert rows[2]['region_counts']['step']=={'portable-c':2,'native-asm':1}
    assert not rows[3]['accepted'] and not rows[3]['committed']
    assert rows[3]['words']==rows[2]['words']
    assert rows[2]['frame_rgba']==rows[2]['view_rgba']
    for broken in (raw[:-1],raw+b'x'):
        with pytest.raises(ValueError):decode_desktop_study(m,broken)


def test_desktop_sealer_rejects_tampered_sources(desktop_root):
    args=desktop_fixture();root=desktop_root/'emit';m=emit_desktop_shell(*args,root)
    assert m['program_sha256']==digest(args[0])
    assert m['core_realizations'][0]['link_lock_sha256']!=m['core_realizations'][1]['link_lock_sha256']
    assert m['core_realizations'][0]['legacy_arena_adapter']['functions']==[{'index':0,'words':64},{'index':1,'words':64}]
    (root/'memory-runtime.c').write_text('invalid replacement')
    with pytest.raises(ValueError,match='source changed'):compile_desktop_shell(root,c_compiler='/nonexistent')


@pytest.mark.parametrize('field,value',[('words',1),('execution',True),('host_effect_execution',True),('unearned_runtime_parity',True)])
def test_desktop_admission_rejects_forged_metadata(desktop_root,field,value):
    import json
    from fdisbull.uil_desktop import _seal_desktop_document
    root=desktop_root/'emit';m=emit_desktop_shell(*desktop_fixture(),root)
    m[field]=value
    (root/'source-shell.json').write_text(json.dumps(_seal_desktop_document(m)))
    with pytest.raises(ValueError,match='metadata|fields'):
        compile_desktop_shell(root,c_compiler='/nonexistent')


@pytest.mark.parametrize('target',['macos-arm64','linux-x64','windows-x64'])
def test_desktop_image_admission_refuses_header_only_images(desktop_root,target):
    import struct
    from fdisbull.uil_desktop import _image
    if target=='macos-arm64':raw=struct.pack('<8I',0xfeedfacf,0x100000c,0,2,0,0,0,0)
    elif target=='linux-x64':
        raw=bytearray(64);raw[:6]=b'\x7fELF\x02\x01';struct.pack_into('<HH',raw,16,3,62);raw=bytes(raw)
    else:
        raw=bytearray(160);raw[:2]=b'MZ';struct.pack_into('<I',raw,60,64);raw[64:68]=b'PE\0\0'
        struct.pack_into('<H',raw,68,0x8664);struct.pack_into('<H',raw,88,0x20b);raw=bytes(raw)
    path=desktop_root/'fake';path.write_bytes(raw)
    with pytest.raises(ValueError):_image(path,target)


def test_desktop_native_writer_stops_at_output_budget(native_desktop):
    root,m=native_desktop
    # Compile only this authored probe with a tiny cap. Production defaults stay
    # fixed, and its ordinary sealed artifacts are neither replaced nor resealed.
    limited=root/'limited-probe'
    command=list(m['compile_commands'][-2]);assert command[-1]==m['probe']
    command[0]=m['compiler']['path'];command[-1]=str(limited)
    command.insert(1,'-DFDB_ADAPTER_OUTPUT_LIMIT=1024')
    p=subprocess.run(command,cwd=root,env=dict(os.environ,TMPDIR=str(root/'tmp')),capture_output=True,timeout=60)
    assert p.returncode==0,p.stderr
    incoming=root/'budget.input';outgoing=root/'budget.output'
    incoming.write_bytes(encode_desktop_study(m,[{'kind':0,'flags':3}]*3))
    p=subprocess.run([str(limited),'--adapter-test',str(incoming),str(outgoing)],capture_output=True,timeout=15)
    assert p.returncode==3
    assert outgoing.exists() and 0<outgoing.stat().st_size<=1024
    with pytest.raises(ValueError,match='incomplete'):decode_desktop_study(m,outgoing.read_bytes())


def test_desktop_native_reader_refuses_oversized_regular_file_before_output(native_desktop):
    root,m=native_desktop;incoming=root/'oversized.input';outgoing=root/'oversized.output'
    with incoming.open('xb') as f:
        f.write(encode_desktop_study(m,[]))
        f.seek(134217728);f.write(b'x')  # Sparse, bounded allocation: size admission only.
    p=subprocess.run([str(root/m['probe']),'--adapter-test',str(incoming),str(outgoing)],capture_output=True,timeout=15)
    assert p.returncode==2 and not outgoing.exists()
