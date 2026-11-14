"""Authored source/CPU/FAT doubles; these tests do not execute a DOS manager."""
import base64
import copy
import hashlib
import re
import struct
from types import SimpleNamespace

import pytest

from fdisbull.project import Project
from fdisbull.le import load_le
from fdisbull.qemm_runtime import _FATVolume
from fdisbull.runtime_source_matching import SourceMatchError, discover
from test_le_loader import le_file
from fixtures_runtime_mapping_le import bound_le
from test_qemm_runtime import fat_image


def authored_com():
    # Entry writes a CS-qualified display byte, then loops without entering the
    # buffer. The file is intentionally the size of a small ordinary DOS app.
    code=bytes.fromhex('2ec606ea0230b80100b90200ba0300be0400bf050090ebfe')
    return code+bytes((i*37+11)&255 for i in range(734-len(code)))


class Session:
    def __init__(self,p,*,base=0x18000,ip=0x100,mode='v86',bits=16):
        self.project=p;self.version=p.version(1);self.metadata=dict(backend='qemu-machine',source_sha256=p.source_sha256());self.regions=[];self.reads=[];self.calls=0;self.drift=False
        cs=base>>4 if bits==16 else 8
        self.regs=dict(cpu_mode=mode,registers=dict(cs=hex(cs),eip=hex(ip)),address_state=dict(register_context_match=True,code_bits=bits,segments={'cs':dict(selector=hex(cs),base=hex(base if bits==16 else 0))}))
        self.vm=SimpleNamespace(qmp=SimpleNamespace(call=lambda *a:'GDT= 00000800 00000017'))
    def registers(self):
        self.calls+=1;r=copy.deepcopy(self.regs)
        if self.drift and self.calls>1:r['registers']['eip']=hex(int(r['registers']['eip'],16)+1)
        return r
    def put(self,address,data):self.regions.append((address,bytes(data)))
    def memory(self,address,*,length,space):
        assert space=='virtual';self.reads.append((address,length))
        for base,data in reversed(self.regions):
            if base<=address and address+length<=base+len(data):return {'hex':data[address-base:address-base+length].hex()}
        return {'hex':bytes(length).hex()}


def project(tmp_path,data,*,image='com',name='program.com'):
    source=tmp_path/name;source.write_bytes(data)
    return Project.create(tmp_path/'program.fdb',source,image=image)


def direct(p,data):
    s=Session(p);s.runtime_base=0x18100;s.static_base=p.runtime_objects()['objects'][0]['preferred_start'];s.expected=data;s.put(s.runtime_base,data);return s


def add_coms(raw,program,*,duplicate=False,cycle=False,other_program=None):
    raw=bytearray(raw);v=_FATVolume(raw);fat=bytearray(v.fat)
    def setfat(cluster,value):
        at=cluster+cluster//2;old=int.from_bytes(fat[at:at+2],'little');struct.pack_into('<H',fat,at,(old&15)|(value<<4) if cluster&1 else (old&0xf000)|value)
    fragments=[]
    programs=[(10,b'MS      COM',program)]+([(20,b'OTHER   COM',program)] if duplicate else [])+([(100,b'OTHER   COM',other_program)] if other_program is not None else [])
    for first,name,content in programs:
        clusters=[first+i*3 for i in range((len(content)+511)//512)]
        for i,cluster in enumerate(clusters):setfat(cluster,cluster if cycle and i==0 else clusters[i+1] if i+1<len(clusters) else 0xfff)
        for index,cluster in enumerate(clusters):
            at=v.data_offset+(cluster-2)*512;part=content[index*512:(index+1)*512];raw[at:at+len(part)]=part
            if first==10:fragments.append((at,len(part)))
        row=bytearray(32);row[:11]=name;row[11]=0x20;struct.pack_into('<HI',row,26,first,len(content))
        root=(1+18)*512;slot=root+(64 if first==10 else 96);raw[slot:slot+32]=row
    raw[512:512+len(fat)]=fat;raw[512+len(fat):512+2*len(fat)]=fat
    return bytes(raw),fragments


def test_direct_com_keeps_code_spans_and_reports_mutable_data(tmp_path):
    data=authored_com()
    with project(tmp_path,data) as p:
        s=direct(p,data);baseline=discover(s)[0];changed=bytearray(data);changed[490]=ord('9');s.put(s.runtime_base,changed)
        result=discover(s)[0]
        assert [(x['name'],x['address'],x['length'],x['expected_sha256']) for x in result['source_spans']]==[(x['name'],x['address'],x['length'],x['expected_sha256']) for x in baseline['source_spans']]
        assert result['identity_evidence']['whole_file_equal'] is False
        assert result['identity_evidence']['changed_data']==[dict(offset=490,length=1)]
        assert result['identity_evidence']['source_write_candidates'][0]['source_offset']==490
        assert not result['identity_evidence']['lifetime_qualified']
        assert all(x['expected_sha256']==x['observed_sha256'] for x in result['source_spans'])


def test_changed_reachable_code_refuses_without_database_writes(tmp_path):
    data=authored_com()
    with project(tmp_path,data) as p:
        s=direct(p,data);changed=bytearray(data);changed[8]^=1;s.put(s.runtime_base,changed);before=p.db.total_changes
        with pytest.raises(SourceMatchError,match='changed reachable'):discover(s)
        assert p.db.total_changes==before


def test_current_pc_outside_original_code_does_not_adopt_resident_bytes(tmp_path):
    data=authored_com()
    with project(tmp_path,data) as p:
        s=direct(p,data);s.regs['registers']['eip']='0x400'
        assert discover(s)==[] and s.reads==[]


def test_normal_dosbox_read_contract_uses_runtime_linear_addresses(tmp_path):
    data=authored_com()
    with project(tmp_path,data) as p:
        s=direct(p,data);s.metadata['backend']='dosbox';s.regs=dict(cpu_mode='real',code_bits=16,segments={'cs':'0x1800'},instruction_pointer='0x100')
        def call(method,params):
            assert method=='memory.read' and params['address']['space']=='linear'
            assert re.fullmatch(r'0x[0-9A-F]{8}',params['address']['offset'])
            raw=bytes.fromhex(s.memory(int(params['address']['offset'],0),length=params['length'],space='virtual')['hex'])
            return {'data_base64':base64.b64encode(raw).decode()}
        s.call=call
        assert discover(s)[0]['identity_evidence']['runtime_base']==0x18100


def test_dosbox_protected_segmented_reads_use_fixed_rpc_widths(tmp_path):
    from fdisbull.runtime_source_matching import _Budget
    data=authored_com()
    with project(tmp_path,data) as p:
        s=direct(p,data);s.metadata['backend']='dosbox'
        def call(method,params):
            assert method=='memory.read'
            assert params['address']==dict(space='segmented',segment='0x0170',offset='0x00123456')
            return dict(data_base64=base64.b64encode(b'authored').decode())
        s.call=call
        assert _Budget(s,128,128).read(0x123456,8,segment=0x170)==b'authored'


def mz_program():
    code=bytes.fromhex('b83412b90102ba0304be0506bf070890909090909090ebfe')
    module=code+bytes(600-len(code));header=bytearray(64);size=len(header)+len(module)
    struct.pack_into('<14H',header,0,0x5a4d,size%512,(size+511)//512,1,4,0,0xffff,0,600,0,0,0,28,0)
    struct.pack_into('<HH',header,28,1,0)
    return bytes(header)+module


def test_normal_mz_expected_relocations_and_source_hash_remain_distinct(tmp_path):
    source=mz_program()
    with project(tmp_path,source,image='mz',name='sample.exe') as p:
        s=Session(p,base=0x18000,ip=0);s.runtime_base=0x18000;s.static_base=p.runtime_objects()['objects'][0]['preferred_start']
        expected=bytearray(source[64:]);struct.pack_into('<H',expected,1,0x1234+0x1800);s.expected=expected;s.put(s.runtime_base,expected)
        result=discover(s)[0];span=result['source_spans'][0]
        assert span['expected_sha256']!=span['observed_sha256'] and span['fixups']==[dict(offset=1,length=2)]
        assert result['identity_evidence']['runtime_module_equal'] is True
        assert result['identity_evidence']['whole_file_equal'] is False


@pytest.mark.parametrize('kind',['compare','scan','context','source','version'])
def test_bounds_and_identity_fail_closed(tmp_path,kind):
    data=authored_com()
    with project(tmp_path,data) as p:
        s=direct(p,data);kw={}
        if kind=='compare':kw['max_compare_bytes']=100
        if kind=='scan':kw['max_scan_bytes']=0
        if kind=='context':s.drift=True
        if kind=='source':s.metadata['source_sha256']='ab'*32
        if kind=='version':s.version={'id':p.patch(0x10100,'90')['version']}
        with pytest.raises((SourceMatchError,ValueError)):discover(s,**kw)


def test_disk_is_not_guessed_as_an_executable_import(tmp_path):
    data=authored_com();raw,fragments=add_coms(fat_image(),data)
    with pytest.raises(ValueError,match='declare --arch'):
        project(tmp_path,raw,image=None,name='disk.img')


def raw_project(tmp_path,raw):
    path=tmp_path/'disk.img';path.write_bytes(raw)
    return Project.create(tmp_path/'disk.fdb',path,arch='x86',bits=32,base=0,entry=0)


def test_raw_fragmented_com_byte_and_fragment_provenance(tmp_path):
    data=authored_com();raw,fragments=add_coms(fat_image(),data)
    with raw_project(tmp_path,raw) as p:
        s=Session(p);native=bytearray(data);native[490]^=1;s.put(0x18100,native)
        result=discover(s)[0]
        assert result['source_identity']['path']=='\\MS.COM'
        assert result['source_identity']['carrier_sha256']==hashlib.sha256(data).hexdigest()
        for span in result['source_spans']:
            assert span['object_id']=='region:0'
            rebuilt=b''.join(raw[f['object_offset']:f['object_offset']+f['length']] for f in span['fragments'])
            assert hashlib.sha256(rebuilt).hexdigest()==span['expected_sha256']==span['observed_sha256']
        assert result['identity_evidence']['changed_data']==[dict(offset=490,length=1)]


def test_raw_mz_maps_only_exact_nonfixup_fat_extents(tmp_path):
    source=mz_program();raw,_=add_coms(fat_image(),source)
    with raw_project(tmp_path,raw) as p:
        s=Session(p,base=0x18000,ip=0);native=bytearray(source[64:]);struct.pack_into('<H',native,1,0x1234+0x1800);s.put(0x18000,native)
        result=discover(s)[0]
        assert result['source_identity']['format']=='MZ'
        assert result['identity_evidence']['excluded_loader_fixups']==[dict(offset=1,length=2)]
        for span in result['source_spans']:
            assert span['object_id']=='region:0' and not span['fixups']
            assert span['expected_sha256']==span['observed_sha256']
            actual=b''.join(raw[f['object_offset']:f['object_offset']+f['length']] for f in span['fragments'])
            assert hashlib.sha256(actual).hexdigest()==span['expected_sha256']


@pytest.mark.parametrize('kind',['duplicate','cycle','scan','unrelated'])
def test_raw_fat_refusals_and_unrelated_pc(tmp_path,kind):
    data=authored_com();raw,_=add_coms(fat_image(),data,duplicate=kind=='duplicate',cycle=kind=='cycle')
    with raw_project(tmp_path,raw) as p:
        s=Session(p);s.put(0x18100,bytes(len(data)) if kind=='unrelated' else data)
        if kind=='unrelated':assert discover(s)==[]
        else:
            with pytest.raises(SourceMatchError):discover(s,**({'max_scan_bytes':100} if kind=='scan' else {}))


def test_fat_directory_materialization_consumes_global_scan_budget(tmp_path):
    # This disk contains a subdirectory but no COM/EXE members. Charging only
    # program files would incorrectly return [] under this one-byte budget.
    with raw_project(tmp_path,fat_image()) as p:
        with pytest.raises(SourceMatchError,match='scan budget'):discover(Session(p),max_scan_bytes=1)


def test_unrelated_large_program_is_prefiltered_before_code_budget(tmp_path):
    # Recursive decoding of this unrelated first member would exhaust 4096
    # instructions. Its unrelated bytes must not block the current small app.
    unrelated=b'\x90'*5000+b'\xeb\xfe';target=authored_com();raw,_=add_coms(fat_image(),unrelated,other_program=target)
    with raw_project(tmp_path,raw) as p:
        s=Session(p);native=bytearray(target);native[490]^=1;s.put(0x18100,native)
        result=discover(s)[0]
        assert result['source_identity']['path']=='\\OTHER.COM'
        assert result['identity_evidence']['changed_data']==[dict(offset=490,length=1)]


def test_fat_crosslinked_directory_tail_refuses(tmp_path):
    raw=bytearray(fat_image());v=_FATVolume(raw);existing=struct.unpack_from('<H',v._entry(v.root,'QEMM'),26)[0]
    fat=bytearray(v.fat);cluster=8;at=cluster+cluster//2;old=int.from_bytes(fat[at:at+2],'little');struct.pack_into('<H',fat,at,(old&0xf000)|existing)
    raw[512:512+len(fat)]=fat;raw[512+len(fat):512+2*len(fat)]=fat
    row=bytearray(32);row[:11]=b'ALIAS      ';row[11]=16;struct.pack_into('<H',row,26,cluster);raw[(1+18)*512+64:(1+18)*512+96]=row
    with raw_project(tmp_path,bytes(raw)) as p:
        with pytest.raises(SourceMatchError,match='crosslinked'):discover(Session(p))


def descriptor(base,limit,bits):
    flags=0x40 if bits==32 else 0
    if limit>65535:limit>>=12;flags|=128
    return struct.pack('<HHBBBB',limit&65535,base&65535,(base>>16)&255,0x9a,flags|((limit>>16)&15),(base>>24)&255)


def protected(p,image,*,bridge=None):
    s=Session(p,base=0,ip=0x50040,mode='protected',bits=32)
    table=bytes(8)+descriptor(0,0xffffffff,32)+(descriptor(0x91000,len(bridge)-1,16) if bridge is not None else bytes(8))
    s.put(0x800,table);code=bytearray(image.regions[0].data)
    for fixup in image.metadata['le']['fixups']:
        if fixup['source_type']=='offset32':struct.pack_into('<I',code,fixup['source_offset'],0x70000+fixup['target_offset'])
    s.put(0x50000,code)
    if bridge is not None:s.put(0x91000,bridge)
    else:s.put(0x70000,image.regions[1].data)
    return s


def test_protected_same_carrier_le_code_and_eight_data_fixups(tmp_path):
    code=b''.join(b'\xb8'+bytes(4)+b'\x90'*3 for _ in range(8))+b''.join(bytes([0x6a,i]) for i in range(80))
    fixups=b''.join(struct.pack('<BBhBH',7,0,i*8+1,2,i) for i in range(8))
    source=bound_le(le_file(code=code,data=b'abcdefghijklmnopqrstuvwxyz0123456789'*3,fixups=[fixups,b'']))
    image=load_le(source)
    with project(tmp_path,source,image='mz',name='bound.exe') as p:
        s=protected(p,image);result=discover(s)[0]
        assert {x['object_id'] for x in result['source_spans']}=={'le:1','le:2'}
        proof=result['identity_evidence']['object_proofs'][0]
        assert len(proof['offset32_sites'])==8 and proof['runtime_base']==0x70000
        assert next(x for x in result['source_spans'] if x['name']=='entry-code')['object_offset']==0
        assert result['identity_evidence']['current_pc_source_match']['object_offset']==64
        assert result['identity_evidence']['current_pc_source_match']['expected_sha256']==result['identity_evidence']['current_pc_source_match']['observed_sha256']
        s.put(0x50000+1,struct.pack('<I',0x71000))
        with pytest.raises(SourceMatchError,match='inconsistent'):discover(s)


def test_protected_bridge_excludes_only_declared_symbolic_bytes(tmp_path):
    code=b'\x90'*64+b''.join(bytes([0x6a,i]) for i in range(80))
    bridge=bytes.fromhex('b81122bb3344b95566ba77889090b80000be99aabfbbcc90c3')
    fixup=struct.pack('<BBhBH',5,0,15,2,2)
    source=bound_le(le_file(code=code,data=bridge,fixups=[b'',fixup],object_sizes=(len(code),25),object_flags=(0x2045,0x1045)))
    image=load_le(source);native=bytearray(bridge);native[15:17]=b'\x02\xf0'
    with project(tmp_path,source,image='mz',name='bound.exe') as p:
        s=protected(p,image,bridge=bytes(native));result=discover(s)[0]
        span=next(x for x in result['source_spans'] if x['name'].startswith('bridge'))
        assert span['compared_bytes']==23 and span['fixups']==[dict(offset=15,length=2)]
        assert span['expected_sha256']!=span['observed_sha256']
        assert result['identity_evidence']['object_proofs'][0]['execution_observed'] is False
        native[0]^=1;s.put(0x91000,native)
        assert all(not x['name'].startswith('bridge') for x in discover(s)[0]['source_spans'])


@pytest.mark.parametrize('kind',['descriptor-ambiguous','descriptor-cache','table-budget','comparison-budget'])
def test_protected_ambiguity_descriptor_and_budget_refusals(tmp_path,kind):
    code=b'\x90'*64+b''.join(bytes([0x6a,i]) for i in range(80));bridge=bytes.fromhex('b81122bb3344b95566ba77889090b80000be99aabfbbcc90c3')
    source=bound_le(le_file(code=code,data=bridge,fixups=[b'',b''],object_sizes=(len(code),25),object_flags=(0x2045,0x1045)));image=load_le(source)
    with project(tmp_path,source,image='mz',name='bound.exe') as p:
        s=protected(p,image,bridge=bridge);kw={}
        if kind=='descriptor-ambiguous':
            s.vm.qmp.call=lambda *a:'GDT= 00000800 0000001f';s.put(0x800,bytes(8)+descriptor(0,0xffffffff,32)+descriptor(0x91000,24,16)+descriptor(0x92000,24,16));s.put(0x92000,bridge)
        if kind=='descriptor-cache':s.regs['address_state']['segments']['cs']['base']='0x10'
        if kind=='table-budget':s.vm.qmp.call=lambda *a:'GDT= 00000800 00010000'
        if kind=='comparison-budget':kw['max_compare_bytes']=100
        before=p.db.total_changes
        with pytest.raises(SourceMatchError):discover(s,**kw)
        assert p.db.total_changes==before


def test_raw_nested_le_uses_exact_carrier_fragments_without_inventing_le_ids(tmp_path):
    code=b''.join(bytes([0x6a,i]) for i in range(110));bridge=bytes.fromhex('b81122bb3344b95566ba77889090b80000be99aabfbbcc90c3');fixup=struct.pack('<BBhBH',5,0,15,2,2)
    source=bound_le(le_file(code=code,data=bridge,fixups=[b'',fixup],object_sizes=(len(code),25),object_flags=(0x2045,0x1045)));image=load_le(source);raw,_=add_coms(fat_image(),source)
    with raw_project(tmp_path,raw) as p:
        native=bytearray(bridge);native[15:17]=b'\xaa\xbb';s=protected(p,image,bridge=bytes(native));result=discover(s)[0]
        assert all(span['object_id']=='region:0' for span in result['source_spans'])
        assert sum(span['length'] for span in result['source_spans'] if span['name'].startswith('bridge'))==23
        for span in result['source_spans']:
            actual=b''.join(raw[f['object_offset']:f['object_offset']+f['length']] for f in span['fragments'])
            assert hashlib.sha256(actual).hexdigest()==span['expected_sha256']==span['observed_sha256']
