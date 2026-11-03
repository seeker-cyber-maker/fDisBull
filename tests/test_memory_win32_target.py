"""i686 source/artifact admission; synthetic PE headers are never executed.

The authored memory model comes from the shared desktop fixture. The PE images
below only exercise container admission: they do not qualify a compiler, source
realization, Windows execution, graphics, or input behavior.
"""
import json
import struct

import pytest

from fdisbull.udc_memory_desktop import emit_memory_desktop_shell, seal_memory_desktop_shell
from test_memory_desktop import fixture_sources


def test_win32_emission_keeps_uil_and_uses_i686_winapi_adapter(tmp_path):
    win32=tmp_path/'win32'/'sources';win64=tmp_path/'win64'/'sources'
    actual=fixture_sources(win32,'windows-x86')
    previous=fixture_sources(win64,'windows-x64')
    assert actual['target']=='windows-x86-memory-1'
    assert actual['profile']=='windows-x86-memory-win32-1'
    assert actual['architecture']=='x86-32'
    assert actual['stage']=='source-only' and actual['native_execution'] is False
    assert actual['source_to_uil'] is False
    for field in ('program','execution_program','module_uil_sha256','module_udl_sha256',
                  'execution_uil_sha256','plan','plan_sha256','cuts','regions','runtime'):
        assert actual[field]==previous[field]
    assert all(value['target']==actual['target'] for value in actual['realizations'].values())
    assert all(command[0]=='i686-w64-mingw32-gcc' for command in actual['commands'])
    assert [command[1:] for command in actual['commands']]==[command[1:] for command in previous['commands']]
    for name in actual['source_artifacts']:
        if name!='memory-runtime.c':
            assert (win32/name).read_bytes()==(win64/name).read_bytes()
    runtime=(win32/'memory-runtime.c').read_text()
    assert 'GetCurrentThreadId()' in runtime and 'pthread_self()' not in runtime
    assert json.loads((win32/'native-shell.json').read_text())==actual


@pytest.mark.parametrize('target',['win32','windows-i686','windows-x86-64',32,None])
def test_win32_does_not_alias_unknown_target_names(tmp_path,target):
    with pytest.raises(ValueError,match='windows-x86'):
        emit_memory_desktop_shell(None,None,None,None,tmp_path/'sources',target=target)
    assert not (tmp_path/'sources').exists()


def test_win32_architecture_is_bound_before_build_or_sealing(tmp_path):
    destination=tmp_path/'sources';manifest=fixture_sources(destination,'windows-x86')
    manifest['architecture']='x86-64'
    (destination/'native-shell.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='architecture'):
        seal_memory_desktop_shell(destination)


def pe_container(*,machine=0x14c,magic=0x10b,dll=False,subsystem=3):
    """Authored one-section container with a RET byte; never run this fixture."""
    data=bytearray(1024);data[:2]=b'MZ';struct.pack_into('<I',data,0x3c,0x80)
    data[0x80:0x84]=b'PE\0\0';optional=0x98
    size=224 if magic==0x10b else 240
    struct.pack_into('<HHIIIHH',data,0x84,machine,1,0,0,0,size,0x102|(0x2000 if dll else 0))
    struct.pack_into('<H',data,optional,magic)
    struct.pack_into('<I',data,optional+4,0x200)
    struct.pack_into('<II',data,optional+16,0x1000,0x1000)
    if magic==0x10b:
        struct.pack_into('<I',data,optional+28,0x400000)
        struct.pack_into('<IIIII',data,optional+72,0x100000,0x1000,0x100000,0x1000,0)
        struct.pack_into('<I',data,optional+92,16)
    else:
        struct.pack_into('<Q',data,optional+24,0x140000000)
        struct.pack_into('<QQQQI',data,optional+72,0x100000,0x1000,0x100000,0x1000,0)
        struct.pack_into('<I',data,optional+108,16)
    struct.pack_into('<II',data,optional+32,0x1000,0x200)
    struct.pack_into('<HH',data,optional+40,4,0)
    struct.pack_into('<HH',data,optional+48,4,0)
    struct.pack_into('<II',data,optional+56,0x2000,0x200)
    struct.pack_into('<H',data,optional+68,subsystem)
    section=optional+size;data[section:section+8]=b'.text\0\0\0'
    struct.pack_into('<IIII',data,section+8,1,0x1000,0x200,0x200)
    struct.pack_into('<I',data,section+36,0x60000020);data[0x200]=0xc3
    return bytes(data)


def format_only_artifacts(destination,manifest):
    """Populate only the independently parsed artifact shape, without execution."""
    (destination/'memory-runtime.o').write_bytes(b'authored format-admission object placeholder')
    (destination/manifest['library']).write_bytes(pe_container(dll=True))
    (destination/manifest['application']).write_bytes(pe_container(subsystem=2))
    (destination/manifest['probe']).write_bytes(pe_container())


def test_win32_pe32_admission_remains_separate_from_native_execution(tmp_path):
    destination=tmp_path/'sources';manifest=fixture_sources(destination,'windows-x86')
    source_receipt=(destination/'source-shell.json').read_bytes()
    format_only_artifacts(destination,manifest)
    evidence={'kind':'authored PE container fixture; never executed; compiler lineage unqualified'}
    admitted=seal_memory_desktop_shell(destination,compiler_evidence=evidence)
    assert admitted['architecture']=='x86-32' and admitted['stage']=='compiled'
    assert admitted['native_execution'] is False and admitted['source_to_uil'] is False
    assert admitted['compiler']==evidence
    assert (destination/'source-shell.json').read_bytes()==source_receipt
    assert seal_memory_desktop_shell(destination)==admitted
    with (destination/manifest['probe']).open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='immutable'):
        seal_memory_desktop_shell(destination)


@pytest.mark.parametrize('artifact,kwargs,message',[
    ('library',{'machine':0x8664,'dll':True},'I386'),
    ('library',{'magic':0x20b,'dll':True},'PE32'),
    ('library',{'dll':False},'kind differs'),
    ('application',{'dll':True,'subsystem':2},'kind differs'),
    ('application',{'subsystem':3},'GUI subsystem'),
    ('probe',{'subsystem':2},'console subsystem'),
])
def test_win32_refuses_wrong_pe_architecture_magic_kind_or_subsystem(tmp_path,artifact,kwargs,message):
    destination=tmp_path/'sources';manifest=fixture_sources(destination,'windows-x86')
    format_only_artifacts(destination,manifest)
    (destination/manifest[artifact]).write_bytes(pe_container(**kwargs))
    source_receipt=(destination/'native-shell.json').read_bytes()
    with pytest.raises(ValueError,match=message):seal_memory_desktop_shell(destination)
    assert (destination/'native-shell.json').read_bytes()==source_receipt
