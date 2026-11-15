"""Source-derived FreeDOS kernel-2043 memory layout tests."""
import struct
import pytest
from fdisbull.dos_workspace_guest import observe_guest_files,SFT_SIZE


def fixture():
    mem=bytearray(0x100000)
    def word(a,v): struct.pack_into('<H',mem,a,v)
    def far(a,seg,off): struct.pack_into('<HH',mem,a,off,seg)
    lol=0x1000; psp=0x2000; sft=0x3000; buf=0x4000
    mem[psp:psp+2]=b'\xcd\x20';word(psp+0x32,20);far(psp+0x34,0x200,0x18)
    mem[psp+0x18:psp+0x18+20]=bytes([0,1]+[255]*18)
    far(lol+4,0x300,0);word(lol+0x3f,2);far(lol+0x47,0x400,0)
    far(sft,0xffff,0xffff);word(sft+4,2)
    device=sft+6;word(device,1);word(device+5,0x80)
    item=device+SFT_SIZE;word(item,1);word(item+2,2);word(item+5,2)
    struct.pack_into('<I',mem,item+0x11,123);struct.pack_into('<I',mem,item+0x15,42)
    mem[item+0x20:item+0x2b]=b'SAVE    DAT';word(item+0x31,0x200)
    word(buf,0x200);mem[buf+4]=2;mem[buf+5]=0x20
    word(buf+0x200,0);mem[buf+0x204]=2;mem[buf+0x205]=0x60
    return mem,lambda address,length:bytes(mem[address:address+length])


def test_source_derived_handles_and_dirty_buffers():
    mem,read=fixture();result=observe_guest_files(read,0x100,0,0x200)
    assert [h['kind'] for h in result['handles']]==['device','file']
    file=result['handles'][1]
    assert (file['dos_name'],file['drive'],file['access'],file['size'],file['position'])==('SAVE.DAT',2,'read-write',123,42)
    assert file['path'] is None and file['sharing']=='unknown'
    assert result['ordinary_open_count']==1 and result['dirty_buffer_count']==1
    assert result['flush_boundary']=='unknown' and result['coherent']=='unknown'


def test_all_sft_files_count_even_if_not_child_handles():
    mem,read=fixture();mem[0x2019]=255
    result=observe_guest_files(read,0x100,0,0x200)
    assert len(result['handles'])==1 and result['ordinary_open_count']==1


@pytest.mark.parametrize('change', ['bad_jft','bad_sft','bad_buffer','hma','short'])
def test_rejects_ambiguous_or_incomplete_memory(change):
    mem,read=fixture()
    if change=='bad_jft': mem[0x2018]=7
    if change=='bad_sft': struct.pack_into('<HH',mem,0x3000,0,0x300)
    if change=='bad_buffer': struct.pack_into('<H',mem,0x4000,0)
    if change=='hma': struct.pack_into('<HH',mem,0x1047,0x20,0xffff)
    if change=='short': read=lambda address,length:b''
    with pytest.raises(ValueError): observe_guest_files(read,0x100,0,0x200)


def test_observation_change_is_rejected():
    mem,read=fixture(); calls=0
    # Change the dirty bit at the start of the second observation.
    def change_buffer(address,length):
        nonlocal calls
        calls+=1
        if calls==8: mem[0x4205]^=0x40
        return read(address,length)
    with pytest.raises(ValueError,match='changed'): observe_guest_files(change_buffer,0x100,0,0x200)
