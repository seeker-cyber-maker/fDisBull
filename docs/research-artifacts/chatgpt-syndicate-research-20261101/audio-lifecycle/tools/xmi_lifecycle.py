"""Bounded, source-informed XMIDI event census for this Syndicate study.

This is not a player. Delay totals are event-clock units, not wall time.
Raw resource bytes are never written by the census. Original GAMEFM semantics
motivated explicit statuses, additive delay bytes and duration VLQs on notes.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

class FormatError(ValueError): pass

def chunks(data: bytes, lo: int = 0, hi: int | None = None, depth: int = 0):
    if hi is None: hi = len(data)
    if depth > 12 or not 0 <= lo <= hi <= len(data): raise FormatError('invalid chunk bounds')
    p = lo
    while p < hi:
        if p + 8 > hi: raise FormatError('truncated IFF chunk')
        kind = data[p:p+4]; size = int.from_bytes(data[p+4:p+8], 'big'); end = p+8+size
        if end > hi: raise FormatError('chunk exceeds parent')
        if kind in (b'FORM', b'CAT ', b'LIST'):
            if size < 4: raise FormatError('container missing form type')
            yield from chunks(data, p+12, end, depth+1)
        elif kind == b'EVNT': yield p+8, data[p+8:end]
        p = end + (size & 1)
    if p != hi: raise FormatError('missing IFF alignment byte')

def events(data: bytes):
    p = 0; rows = []
    def need(n):
        if p+n > len(data): raise FormatError('truncated event')
    def vlq():
        nonlocal p
        value = 0
        for _ in range(4):
            need(1); b = data[p]; p += 1; value = (value << 7) | (b & 127)
            if not b & 128: return value
        raise FormatError('VLQ exceeds admitted four bytes')
    while p < len(data):
        start=p; b=data[p]; p+=1; row={'offset':start}
        if b < 128: row.update(kind='delay',ticks=b)
        elif b == 255:
            need(1); kind=data[p];p+=1;n=vlq();need(n);p+=n
            row.update(kind='meta',meta=kind,payload_size=n)
            if kind==47:
                if n != 0: raise FormatError('nonempty EOT outside profile')
                row['size']=p-start;rows.append(row)
                return rows, {'eot_offset':start,'parsed_bytes':p,'tail_size':len(data)-p,'tail_all_zero':not any(data[p:])}
        elif b >= 240:
            if b not in (240,247): raise FormatError('unsupported system event')
            n=vlq();need(n);p+=n;row.update(kind='sysex',payload_size=n)
        else:
            kind=b>>4;n=1 if kind in (12,13) else 2
            need(n);payload=data[p:p+n];p+=n
            if any(x>=128 for x in payload): raise FormatError('non-data byte in event operands')
            row.update(kind='channel',channel=b&15,command=kind)
            if kind in (8,9): row['duration']=vlq()
            if kind==11: row.update(controller=payload[0],value=payload[1])
        row['size']=p-start;rows.append(row)
        if len(rows)>1000000:raise FormatError('event budget')
    raise FormatError('no end-of-track within EVNT')

def analyze(data: bytes):
    rows,end=events(data); stack=[];loops=[];errors=[]
    for i,r in enumerate(rows):
        if r.get('controller')==116:
            if len(stack)>=4:errors.append('more than four lexical repeat slots')
            stack.append((i,r))
        elif r.get('controller')==117 and r['value']>=64:
            if not stack:errors.append('repeat end without lexical begin');continue
            begin_i,begin=stack.pop();body=rows[begin_i+1:i]
            loops.append({'begin_offset':begin['offset'],'body_offset':begin['offset']+begin['size'],
                'end_offset':r['offset'],'count':begin['value'],'end_value':r['value'],
                'positive_delay_records':sum(x['kind']=='delay' and x['ticks']>0 for x in body),
                'delay_ticks_linear_body':sum(x.get('ticks',0) for x in body),
                'unbounded_by_zero_count':begin['value']==0})
    if stack:errors.append('unclosed lexical repeat')
    return {'event_records':len(rows),'delay_records':sum(x['kind']=='delay' for x in rows),
      'delay_ticks_linear_pass':sum(x.get('ticks',0) for x in rows),**end,'loops':loops,
      'lexical_issues':errors,'scope':'Bounded linear parse and lexical repeat census, not runtime reachability, timing or arbitrary branch execution.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('inputs',nargs='+',type=Path);ap.add_argument('--output',required=True,type=Path);a=ap.parse_args()
    if a.output.exists(): raise FileExistsError('Refusing to overwrite an earlier receipt')
    result=[]
    for path in a.inputs:
        data=path.read_bytes()
        if len(data)>16*1024*1024:raise FormatError('input too large')
        result.append({'name':path.name,'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),
          'streams':[{'file_payload_offset':off,'size':len(ev),'sha256':hashlib.sha256(ev).hexdigest(),**analyze(ev)} for off,ev in chunks(data)]})
    with a.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps({'files':result},indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
