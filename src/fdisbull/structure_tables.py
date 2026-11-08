"""Content-only table candidates. No game names, record sizes or offsets.

These readers identify regularity, not domain types. Full row/name payloads are
private results; publication should use counts and source identities instead.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from hashlib import sha256
import re

_TEXT = re.compile(rb'[A-Za-z][A-Za-z0-9 ,\x27()\-/+]{2,47}\x00')


def string_anchors(data: bytes, *, limit=10000):
    """Bounded readable NUL-terminated spans; these are not all game strings."""
    result=[]
    for m in _TEXT.finditer(data):
        # Do not accept a suffix of a longer printable string.
        if m.start() and 32<=data[m.start()-1]<127:continue
        result.append({'offset':m.start(),'length':len(m[0]),'text':m[0][:-1].decode('ascii')})
        if len(result)>=limit:break
    return result


def record_candidates(data: bytes, *, max_stride=512, min_rows=5, limit=12):
    """Infer repeated label-bearing records from spacing and padded row starts.

    No known file names or counts. Empty rows remain part of the extent when a
    proposed stride partitions the file. Multiples/submultiples are alternatives,
    not independent confirmed layouts. No occupancy inference is made.
    """
    anchors=string_anchors(data);starts=[a['offset'] for a in anchors]
    if len(starts)<min_rows:return []
    gaps=Counter()
    for i,a in enumerate(starts):
        for b in starts[i+1:i+9]:
            d=b-a
            if 4<=d<=max_stride:gaps[d]+=1
    candidates=[]
    for stride,votes in sorted(gaps.items(),key=lambda x:(-x[1],x[0]))[:64]:
        residue=defaultdict(list)
        for a in anchors:residue[a['offset']%stride].append(a)
        for rem,group in residue.items():
            if len(group)<min_rows:continue
            intervals=Counter((b['offset']-a['offset'])//stride for a,b in zip(group,group[1:]))
            adjacent=intervals[1]
            if adjacent<min_rows-1:continue
            labels=[]
            for a in group:
                end=a['offset']+a['length'];pad=data[end:min(end+3,len(data))]
                if pad and not any(pad):labels.append(a)
            if len(labels)<min_rows:continue
            # A row-local name must fit inside that proposed row. Bitmap runs
            # often accidentally spell the same printable sequence repeatedly.
            # Requiring four varied labels deliberately favors readable-name
            # candidates; short/numeric-only tables remain unrecognized here.
            if any(rem+a['length']+2>stride for a in labels):continue
            distinct={a['text'].casefold() for a in labels}
            diverse=[t for t in distinct if len(set(c for c in t if c.isalpha()))>=4]
            if len(distinct)<4 or len(diverse)<4 or len(distinct)/len(labels)<0.5:continue
            partitions=len(data)%stride==0
            coverage=len(labels)/max(1,len(data)//stride)
            if coverage>1:continue
            evidence={'stride':stride,'label_residue':rem,'label_count':len(labels),
                      'adjacent_spacing_witnesses':adjacent,'file_partition':partitions,
                      'record_positions':len(data)//stride if partitions else None,
                      'first_label':labels[0]['offset'],'last_label':labels[-1]['offset'],
                      'label_coverage':round(coverage,6),'examples':labels[:4]}
            # Ranking is a deterministic priority heuristic, not a probability.
            evidence['rank']=min(85,45+min(adjacent,20)+(10 if partitions else 0)+(5 if rem==0 else 0))
            candidates.append(evidence)
    candidates.sort(key=lambda x:(-x['rank'],-x['label_count'],x['stride'],x['label_residue']))
    # Keep mathematically coarser fits as alternatives instead of pretending
    # that a 54-byte row and a 108-byte pair are two independent discoveries.
    primary=[]
    for candidate in candidates:
        covered=next((p for p in primary if candidate['stride']%p['stride']==0
                      and candidate['label_residue']%p['stride']==p['label_residue']
                      and p['first_label']<=candidate['first_label']<=candidate['last_label']<=p['last_label']),None)
        if covered is not None:
            covered.setdefault('coarser_alternatives',[]).append({k:v for k,v in candidate.items() if k!='examples'})
        else:primary.append(candidate)
    return primary[:limit]


def pointer_string_tables(data: bytes, *, min_entries=6, max_pair_checks=500000, limit=64):
    """Infer same-base 16-bit pointer runs into readable strings.

    A pointer's unknown segment base is inferred by two adjacent strings and
    then checked on the entire run. This is a data-layout hypothesis, not a
    runtime DS binding or proof that the program reads the table.
    """
    anchors=string_anchors(data);strings={a['offset']:a for a in anchors}
    differences=defaultdict(list)
    for a,b in zip(anchors,anchors[1:]):
        delta=b['offset']-a['offset']
        if 3<=delta<=64:differences[delta].append(a['offset'])
    found=[];seen=set();checks=0;exhausted=False
    for at in range(0,len(data)-4,2):
        a=int.from_bytes(data[at:at+2],'little');b=int.from_bytes(data[at+2:at+4],'little')
        for addr in differences.get(b-a,()):
            checks+=1
            if checks>max_pair_checks:exhausted=True;break
            bias=addr-a
            if bias<0 or bias%16:continue
            if at>=2 and int.from_bytes(data[at-2:at],'little')+bias in strings:continue
            pos=at;targets=[]
            while pos+2<=len(data) and len(targets)<1024:
                target=int.from_bytes(data[pos:pos+2],'little')+bias
                if target not in strings:break
                targets.append(target);pos+=2
            if len(targets)<min_entries or len(set(targets))<min_entries:continue
            key=(at,bias,len(targets))
            if key in seen:continue
            seen.add(key)
            found.append({'offset':at,'count':len(targets),'entry_bytes':2,'endian':'little',
                          'candidate_base':bias,'targets':targets,
                          'labels':[strings[t]['text'] for t in targets],
                          'consumer_qualified':False,'runtime_base_qualified':False})
            if len(found)>=limit:exhausted=True;break
        if exhausted:break
    return {'tables':found,'pair_checks':min(checks,max_pair_checks),'budget_exhausted':exhausted}
