"""Host-only replay of synthetic native save-operation transcripts."""
from copy import deepcopy
import hashlib
import pytest
from fdisbull.dos_save_operations import FORMAT,MODEL,replay,validate_document,validate_packet


def event(fn,before,after,*,path='',destination='',mode=0,seek=0,handle=5,ax=0,dx=0,requested=0,accepted=0):
    return dict(sequence=0,function=fn,handle=handle,ax=ax,dx=dx,requested=requested,accepted=accepted,
                carry=False,**{'caller-pc':0x1000,'return-pc':0x1002,'path':path,'destination':destination,
                'offset-before':before[0],'size-before':before[1],'offset-after':after[0],'size-after':after[1],
                'mode':mode,'seek-offset':seek})


def packet(events,stream,final,*,initial=None,temp='',created=True):
    for i,e in enumerate(events,1):e['sequence']=i
    return {'api-version':2,'model':MODEL,'operation-policy':'save-v2','active':True,'valid':True,
        'pending':False,'epoch':1,'generation':1,'event-count':len(events),'write-count':sum(e['function']==0x40 for e in events),
        'bytes-written':len(stream),'child-psp':0x200,'created-handle':5,'int21-vector':0x12345678,'hardware-interrupt-depth':0,
        'initial-exists':initial is not None,'initial-payload-hex':(initial or b'').hex(),
        'payload-hex':stream.hex(),'token':'owner-token','dos-path':'D:\\SAVE.DAT','temporary-path':temp,
        'current-path':'D:\\SAVE.DAT','file-exists':True,'file-open':False,'final-exists':True,'temporary-exists':False,
        'file-offset':events[-1]['offset-after'],'final-size':len(final),'phase':'ready','create-seen':created,
        'close-seen':True,'flush-seen':True,'commit-seen':False,'source-ranges':[{'start':0x1000,'size':0x100}],
        'events':events}


def create():
    f='D:\\SAVE.DAT'
    events=[event(0x5b,(0,0),(0,0),path=f,ax=5),
            event(0x40,(0,0),(3,3),requested=3,accepted=3,ax=3),
            event(0x3e,(3,3),(3,3)),event(0x0d,(3,3),(3,3))]
    return packet(events,b'abc',b'abc')


def test_create_and_document():
    p=create();assert replay(p)==b'abc'
    doc=dict(format=FORMAT,path='SAVE.DAT',native=p,observer_token='owner-token',size=3,
             payload_sha256=hashlib.sha256(b'abc').hexdigest(),binding=dict(mode='save',initial_exists=False,
             initial_payload_hex='',temporary_path=None,path='SAVE.DAT',observer_token='owner-token',
             child_psp=0x200,int21_vector=0x12345678,source_ranges=p['source-ranges']))
    assert validate_document(doc)==p
    doc['payload_sha256']='0'*64
    with pytest.raises(ValueError):validate_document(doc)


def test_open_seek_overwrite_and_truncate():
    f='D:\\SAVE.DAT'; es=[event(0x3d,(0,4),(0,4),path=f,mode=2,ax=5),
       event(0x42,(0,4),(1,4),mode=0,seek=1,ax=1),
       event(0x40,(1,4),(3,4),requested=2,accepted=2,ax=2),
       event(0x40,(3,4),(3,3)),event(0x3e,(3,3),(3,3)),event(0x0d,(3,3),(3,3))]
    assert replay(packet(es,b'XY',b'aXY',initial=b'abcd',created=False))==b'aXY'


def test_temp_replace_old_final_via_observed_delete_and_rename():
    f='D:\\SAVE.DAT'; t='D:\\TEMP.TMP';es=[event(0x5b,(0,3),(0,0),path=t,ax=5),
        event(0x40,(0,0),(3,3),requested=3,accepted=3,ax=3),event(0x3e,(3,3),(3,3)),
        event(0x41,(3,3),(3,3),path=f),event(0x56,(3,3),(3,3),path=t,destination=f),
        event(0x0d,(3,3),(3,3))]
    assert replay(packet(es,b'new',b'new',initial=b'old',temp=t))==b'new'


@pytest.mark.parametrize('change',['invalid','stream','order','short','seek','offset','caller','pending','size','open'])
def test_tampered_transcript_refused(change):
    p=create();e=p['events']
    if change=='invalid':p['valid']=False
    elif change=='stream':p['payload-hex']='00'
    elif change=='order':e[1]['function']=0x3e
    elif change=='short':e[1]['accepted']=2
    elif change=='seek':e[1]['function']=0x42;e[1]['mode']=3
    elif change=='offset':e[1]['offset-after']=2
    elif change=='caller':e[1]['caller-pc']=0x2000
    elif change=='pending':p['pending']=True
    elif change=='size':p['final-size']=2
    else:p['file-open']=True
    with pytest.raises(ValueError):replay(p)


def test_hole_write_and_read_are_refused():
    f='D:\\SAVE.DAT';es=[event(0x3d,(0,1),(0,1),path=f,mode=1,ax=5),
        event(0x42,(0,1),(3,1),mode=0,seek=3,ax=3),
        event(0x40,(3,1),(4,4),requested=1,accepted=1,ax=1),
        event(0x3e,(4,4),(4,4)),event(0x0d,(4,4),(4,4))]
    with pytest.raises(ValueError,match='gap'):replay(packet(es,b'x',b'????',initial=b'a',created=False))
    p=create();p['events'][1]['function']=0x3f
    with pytest.raises(ValueError):replay(p)


def test_source_mapping_may_exceed_file_payload_limit():
    p=create();p['source-ranges']=[{'start':0x1000,'size':0x20000}]
    assert replay(p)==b'abc'


def test_uint64_owner_counters_and_invalid_handle_sentinel():
    p=create();p['epoch']=(1<<32)+3;p['generation']=(1<<32)+7
    assert replay(p)==b'abc'
    p['events'][0]['ax']=p['events'][0]['handle']=0xffff
    with pytest.raises(ValueError,match='create'): replay(p)
