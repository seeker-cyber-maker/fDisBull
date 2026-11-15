"""Independent bounded replay of qualified native DOS save-operation evidence."""
import hashlib
import re

MODEL = 'qemu-pc-dos-save-witness-v2'
FORMAT = 'fdisbull-dos-save-operations-1'
MAX = 65536
_SAFE = {1,2,6,7,8,9,10,11,12,0x19,0x1a,0x2f,0x30,0x34,0x35,0x36,0x4e,0x4f,0x52,0x59}


def _name(value):
    if (not isinstance(value,str) or not re.fullmatch(r"[A-Z0-9_~!#$%&'()@^`{}-]{1,8}(?:\.[A-Z0-9_~!#$%&'()@^`{}-]{1,3})?",value)
            or value.split('.')[0] in ('CON','PRN','AUX','NUL','CLOCK$')
            or re.fullmatch(r'(COM|LPT)[1-9]',value.split('.')[0])):
        raise ValueError('Invalid save-operation DOS name')
    return value


def _int(value, name, low=0, high=(1<<32)-1):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid save-operation ' + name)
    return value


def _bytes(value, name):
    if not isinstance(value,str) or len(value)>MAX*2 or len(value)%2:
        raise ValueError('Invalid save-operation ' + name)
    try:
        result=bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError('Invalid save-operation ' + name) from exc
    if len(value)!=2*len(result):
        raise ValueError('Noncanonical save-operation ' + name)
    return result


def validate_packet(info):
    if (not isinstance(info,dict) or info.get('api-version') != 2 or info.get('model') != MODEL
            or info.get('operation-policy') != 'save-v2'):
        raise ValueError('Unsupported native save-operation packet')
    for key in ('active','valid','pending','initial-exists','file-exists','file-open',
                'final-exists','temporary-exists','create-seen','close-seen','flush-seen','commit-seen'):
        if type(info.get(key)) is not bool: raise ValueError('Invalid save-operation '+key)
    for key in ('epoch','generation'):
        _int(info.get(key),key,0,(1<<64)-1)
    for key in ('event-count','write-count','bytes-written','child-psp','created-handle','int21-vector',
                'file-offset','final-size','hardware-interrupt-depth'):
        _int(info.get(key),key)
    if (not info['epoch'] or not info['generation'] or not 1<=info['child-psp']<=0xffff
            or not info['int21-vector'] or info['created-handle']>0xffff
            or info['bytes-written']>MAX or info['file-offset']>MAX or info['final-size']>MAX
            or info['hardware-interrupt-depth']>16):
        raise ValueError('Save-operation native limits exceeded')
    for key in ('token','dos-path','temporary-path','current-path'):
        if not isinstance(info.get(key),str): raise ValueError('Invalid save-operation '+key)
    if not info['token'] or not info['dos-path'].startswith('D:\\'):
        raise ValueError('Missing save-operation owner/path')
    final=info['dos-path'];temp=info['temporary-path']
    if temp and (not temp.startswith('D:\\') or temp == final): raise ValueError('Invalid temporary path')
    if final != 'D:\\'+_name(final[3:]) or (temp and temp != 'D:\\'+_name(temp[3:])):
        raise ValueError('Noncanonical save-operation path')
    initial=_bytes(info.get('initial-payload-hex'),'initial payload')
    stream=_bytes(info.get('payload-hex'),'write stream')
    if (not info['initial-exists'] and initial) or len(stream)!=info['bytes-written']:
        raise ValueError('Save-operation payload bounds differ')
    ranges=info.get('source-ranges')
    if not isinstance(ranges,list) or not 1<=len(ranges)<=32:
        raise ValueError('Missing save-operation source ranges')
    end=0
    for region in ranges:
        if not isinstance(region,dict): raise ValueError('Invalid save-operation source range')
        start=_int(region.get('start'),'range start',0,0x9ffff)
        size=_int(region.get('size'),'range size',1,0xa0000)
        if start<end or start+size>0xa0000: raise ValueError('Invalid save-operation range extent')
        end=start+size
    events=info.get('events')
    if not isinstance(events,list) or len(events)>256 or len(events)!=info['event-count']:
        raise ValueError('Incomplete save-operation event stream')
    for sequence,event in enumerate(events,1):
        if (not isinstance(event,dict) or type(event.get('sequence')) is not int
                or event.get('sequence')!=sequence or type(event.get('carry')) is not bool):
            raise ValueError('Invalid save-operation event sequence')
        for key in ('function','handle','ax','requested','accepted','caller-pc','return-pc','dx',
                    'offset-before','offset-after','size-before','size-after','mode'):
            _int(event.get(key),key)
        for key in ('handle','ax','requested','accepted','dx'):
            _int(event[key],key,0,0xffff)
        for key in ('function','mode'):
            _int(event[key],key,0,0xff)
        for key in ('offset-before','offset-after','size-before','size-after'):
            _int(event[key],key,0,MAX)
        _int(event.get('seek-offset'),'seek offset',-(1<<31),(1<<31)-1)
        if any(not isinstance(event.get(k),str) for k in ('path','destination')):
            raise ValueError('Invalid save-operation event path')
        if any(not any(r['start']<=event[k]<r['start']+r['size'] for r in ranges) for k in ('caller-pc','return-pc')):
            raise ValueError('Save-operation event is outside source owner')
    return None


def replay(info):
    validate_packet(info)
    if (not info['active'] or not info['valid'] or info.get('phase')!='ready' or info['pending']
            or info['hardware-interrupt-depth'] or not info['flush-seen'] or not info['close-seen']):
        raise ValueError('Save-operation witness is not ready')
    final=info['dos-path'];temp=info['temporary-path']
    initial=_bytes(info['initial-payload-hex'],'initial payload')
    stream=_bytes(info['payload-hex'],'write stream')
    images={final:initial} if info['initial-exists'] else {}
    current=final if info['initial-exists'] else ''
    offset=0;handle=None;opened=False;closed=False;flushed=False;committed=False
    writes=0;consumed=0;created=False
    for e in info['events']:
        fn=e['function']; path=e['path']; dest=e['destination']
        if fn in _SAFE: continue
        if fn in (0x51,0x62):
            if e['handle']!=info['child-psp']: raise ValueError('Save-operation PSP differs')
            continue
        size=len(images[current]) if current else 0
        if e['offset-before']!=offset or e['size-before']!=size:
            raise ValueError('Save-operation event preimage differs')
        if fn!=0x0d and e['carry']: raise ValueError('DOS save operation failed')
        if fn in (0x5b,0x3c):
            if opened or e['handle']!=e['ax'] or e['ax']==0xffff or path not in (final,temp) or not path or (fn==0x5b and path in images):
                raise ValueError('Unqualified save create')
            if path != current and path in images: raise ValueError('Cannot replace shadow save')
            images[path]=b'';current=path;offset=0;handle=e['ax'];opened=True
            closed=flushed=committed=False;created=True
        elif fn==0x3d:
            if opened or e['handle']!=e['ax'] or e['ax']==0xffff or not current or path!=current or path not in images or e['mode'] not in (1,2):
                raise ValueError('Unqualified save open')
            handle=e['ax'];offset=0;opened=True;closed=flushed=committed=False
        elif fn==0x40:
            n=e['requested']
            if not opened or e['handle']!=handle or n>65535 or e['accepted']!=n or e['ax']!=n:
                raise ValueError('Unqualified save write')
            data=images[current]
            if offset>len(data): raise ValueError('Save write cannot introduce a gap')
            if n:
                if consumed+n>len(stream) or offset+n>MAX: raise ValueError('Save write exceeds bounds')
                data=data[:offset]+stream[consumed:consumed+n]+data[offset+n:]
                consumed+=n;offset+=n
            else: data=data[:offset]
            images[current]=data;writes+=1;flushed=committed=False
        elif fn==0x42:
            if not opened or e['handle']!=handle or e['mode'] not in (0,1,2): raise ValueError('Unqualified save seek')
            new=(0,offset,len(images[current]))[e['mode']]+e['seek-offset']
            if not 0<=new<=MAX or (e['dx']<<16|e['ax'])!=new: raise ValueError('Save seek result differs')
            offset=new
        elif fn==0x68:
            if not opened or e['handle']!=handle: raise ValueError('Unqualified save commit')
            committed=True
        elif fn==0x3e:
            if not opened or e['handle']!=handle: raise ValueError('Unqualified save close')
            opened=False;closed=True
        elif fn==0x41:
            if path not in images or (path==current and opened): raise ValueError('Unqualified save delete')
            del images[path];flushed=False
            if path==current: current='';offset=0;closed=False
        elif fn==0x56:
            if opened or not current or path!=current or dest not in (final,temp) or not dest or dest in images:
                raise ValueError('Unqualified save rename')
            images[dest]=images.pop(current);current=dest;flushed=False
        elif fn==0x0d:
            if opened or not current or not closed: raise ValueError('Unqualified save flush')
            flushed=True
        else: raise ValueError('Unsupported save-operation event')
        size=len(images[current]) if current else 0
        if e['offset-after']!=offset or e['size-after']!=size:
            raise ValueError('Save-operation event result differs')
    if (current!=final or not closed or not flushed or opened or temp in images and bool(temp)
            or final not in images or consumed!=len(stream) or writes!=info['write-count']
            or info['file-exists'] is not True or info['file-open'] is not False
            or info['final-exists'] is not True or info['temporary-exists'] is not False
            or info['current-path']!=current or info['file-offset']!=offset
            or info['final-size']!=len(images[final]) or info['commit-seen']!=committed
            or info['create-seen']!=created or info['created-handle']!=handle):
        raise ValueError('Save-operation final state differs')
    return images[final]


def validate_document(doc):
    if not isinstance(doc,dict) or doc.get('format')!=FORMAT:
        raise ValueError('Invalid save-operation document')
    info=doc.get('native');value=replay(info)
    binding=doc.get('binding')
    path=_name(doc.get('path'))
    temporary=binding.get('temporary_path') if isinstance(binding,dict) else None
    temporary_native='D:\\'+_name(temporary) if temporary is not None else ''
    if (not isinstance(binding,dict) or binding.get('mode')!='save' or binding.get('host_fault')
            or type(binding.get('initial_exists')) is not bool
            or binding.get('path')!=path or binding.get('observer_token')!=info['token']
            or binding.get('child_psp')!=info['child-psp']
            or binding.get('source_ranges')!=info['source-ranges']
            or binding.get('int21_vector')!=info['int21-vector']
            or binding.get('initial_exists')!=info['initial-exists']
            or binding.get('initial_payload_hex')!=info['initial-payload-hex']
            or temporary_native!=info['temporary-path']
            or doc.get('observer_token')!=info['token'] or 'D:\\'+path!=info['dos-path']
            or doc.get('size')!=len(value) or doc.get('payload_sha256')!=hashlib.sha256(value).hexdigest()):
        raise ValueError('Save-operation document binding differs')
    return info
