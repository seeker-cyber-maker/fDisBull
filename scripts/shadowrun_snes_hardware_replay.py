"""Validate private raw environmental observations for an input-conditioned replay.

This module never supplies an observed seed, RNG result or later gameplay state
to the runtime. Those fields independently check the recovered transform and
continuity. Only four read bytes and the source caller identity enter a batch.
"""
from collections import Counter
import hashlib
import json

from fdisbull.shadowrun_snes_hardware import input_batch

FORMAT='snes-shadowrun-hardware-journal-1'
READ_ORDER=[{'pc':0x80c536,'address':0x2137,'field':'latch'},
            {'pc':0x80c53c,'address':0x7e1c92,'field':'nmi_low'},
            {'pc':0x80c542,'address':0x213c,'field':'beam_h'},
            {'pc':0x80c549,'address':0x7e1c93,'field':'nmi_high'},
            {'pc':0x80c54f,'address':0x213d,'field':'beam_v'}]
RAW_FIELDS=('caller','context','nmi_low','nmi_high','beam_h','beam_v')


def sha(raw):return hashlib.sha256(raw).hexdigest()


class HardwareReplay:
    def __init__(self,root,receipt,controller_bytes,rom,title):
        self.root=root
        raw=(root/'hardware_journal.json').read_bytes();data=json.loads(raw)
        if (receipt.get('snes_hardware_journal_sha256')!=sha(raw) or
            data.get('format')!=FORMAT or data.get('rom_sha256')!=sha(rom) or
            data.get('core_sha256')!=receipt.get('core_sha256') or
            data.get('controller_journal_sha256')!=sha(controller_bytes) or
            data.get('read_order')!=READ_ORDER or
            any(data.get(key)!=0 for key in ('dropped','modal_dropped','incomplete_at_end'))):
            raise ValueError('hardware journal identity, read phase or completeness mismatch')
        self.controller=[row for row in json.loads(controller_bytes)['samples'] if row['kind']!='player']
        self.by_boundary={};self.modals={};self.used_modals=set();self.consumed=0;self.last_boundary=-1
        self.seed=title[0x1d04];self.boot_count=0;self.validated=0
        last=(0,0,0,0);previous_seed=None
        for row in data['samples']:
            fields=('ordinal','serial','boundary','video_frame',*RAW_FIELDS)
            if any(type(row.get(key)) is not int for key in fields):
                raise ValueError('hardware record fields must be integers')
            ordinal,serial,boundary,frame=(row[key] for key in ('ordinal','serial','boundary','video_frame'))
            if (ordinal!=last[0]+1 or serial<last[1] or boundary<last[2] or frame<last[3] or
                boundary>len(self.controller) or min(serial,boundary,frame)<0):
                raise ValueError('hardware record order or controller boundary mismatch')
            input_batch([{key:row[key] for key in RAW_FIELDS}],ordinal=0)
            if boundary:
                sample=self.controller[boundary-1]
                if sample['serial']!=serial or sample['video_frame']>frame:
                    raise ValueError('hardware record is outside its source input interval')
                if boundary<len(self.controller) and frame>self.controller[boundary]['video_frame']:
                    raise ValueError('hardware record extends beyond its source input interval')
            elif serial:
                raise ValueError('hardware record has serial without a controller boundary')
            v=row.get('verification',{})
            if (any(type(v.get(key)) is not int for key in ('seed_before','seed_after','result','seen','latch')) or
                v['seen']!=31 or not 0<=v['seed_before']<=255 or not 0<=v['seed_after']<=255 or
                not 0<=v['result']<=65535 or not 0<=v['latch']<=255):
                raise ValueError('hardware observation did not complete every source read')
            if (v.get('return_pc')!={1:0xff11,2:0xc504,3:0xf4d2}[row['caller']] or
                (row['caller']==3 and row['context']!=v.get('task'))):
                raise ValueError('hardware caller identity disagrees with its source stack/task')
            seed=v['seed_before']
            low=rom[0x455d+seed]^row['nmi_low']
            high=rom[0x455d+(low^row['beam_h'])]^row['nmi_high']
            next_seed=high^row['beam_v']
            if next_seed==seed:next_seed=(next_seed+1)&255
            if v['result']!=low|(high<<8) or v['seed_after']!=next_seed:
                raise ValueError('source RNG transform disagrees with its raw observations')
            if previous_seed is not None and seed!=previous_seed:
                raise ValueError('source RNG seed continuity is unexplained')
            previous_seed=next_seed;last=(ordinal,serial,boundary,frame);self.validated+=1
            if frame<=839:
                self.boot_count+=1
                if boundary:raise ValueError('controller replay began before the title seed')
                continue
            if not self.by_boundary and self.consumed==0 and seed!=self.seed:
                raise ValueError('first replay draw does not derive from the title seed')
            self.by_boundary.setdefault(boundary,[]).append(row)
        for row in data.get('modals',[]):
            boundary=row.get('boundary')
            if (type(boundary) is not int or not 1<=boundary<=len(self.controller) or
                boundary in self.modals or row.get('file')!=f'modal-{boundary:06d}.bin' or
                row.get('size')!=131072):
                raise ValueError('invalid or duplicate source modal snapshot')
            sample=self.controller[boundary-1]
            kind={'modal':3,'conversation':{'primary':4,'keyword':5,'exit':6}.get(sample.get('context'))}.get(sample['kind'])
            if (kind!=row.get('kind') or sample.get('pc')!=row.get('pc') or
                sample['serial']!=row.get('serial') or sample['video_frame']!=row.get('video_frame')):
                raise ValueError('source modal snapshot context mismatch')
            self.modals[boundary]=row
        expected_modals={i for i,row in enumerate(self.controller,1) if row['kind'] in ('modal','conversation')}
        if set(self.modals)!=expected_modals:
            raise ValueError('source modal snapshot coverage is incomplete')
        self.rows=data['samples'];self.journal_sha256=sha(raw)

    def prepare(self,boundary,machine,native):
        if boundary!=self.last_boundary+1:
            raise ValueError('hardware replay input boundaries must be consecutive')
        records=self.by_boundary.get(boundary,[])
        state=input_batch([{key:row[key] for key in RAW_FIELDS} for row in records],ordinal=self.consumed)
        machine.set_state(state)
        for name,value in state.items():
            for index,item in enumerate(value if isinstance(value,list) else [value]):
                if native.lib.fdisbull_state_set(native.ctx,name.encode(),index,item):
                    raise ValueError('native hardware input port unavailable')
        self.last_boundary=boundary
        return records

    def complete(self,reader,records):
        expected=self.consumed+len(records)
        if (reader.get('hardware_input_index')!=len(records) or
            reader.get('hardware_ordinal')!=expected):
            raise ValueError('native hardware journal consumption mismatch')
        if records:self.seed=records[-1]['verification']['seed_after']
        if reader.byte(0x1d04)!=self.seed:
            raise ValueError('native RNG seed is not derived continuously from the title')
        self.consumed=expected

    def modal_source(self,boundary):
        row=self.modals.get(boundary)
        if row is None:raise ValueError('source modal snapshot missing')
        raw=(self.root/row['file']).read_bytes()
        if len(raw)!=131072 or sha(raw)!=row['sha256']:
            raise ValueError('source modal snapshot changed')
        self.used_modals.add(boundary)
        return raw

    def changed_modal_files(self):
        return [str(self.root/self.modals[b]['file']) for b in sorted(self.used_modals)
                if not (self.root/self.modals[b]['file']).is_file() or
                sha((self.root/self.modals[b]['file']).read_bytes())!=self.modals[b]['sha256']]

    def summary(self):
        retained=[row for boundary,rows in sorted(self.by_boundary.items()) if boundary<=self.last_boundary for row in rows][:self.consumed]
        return {'journal_sha256':self.journal_sha256,'validated_source_draws':self.validated,
                'pre_title_draws':self.boot_count,'consumed_draws':self.consumed,
                'caller_counts':dict(Counter(str(row['caller']) for row in retained)),
                'last_input_boundary':self.last_boundary,'captured_modal_snapshots':len(self.modals),
                'compared_modal_snapshots':len(self.used_modals),
                'scope':'exact comparisons conditioned on ordered raw external observations; no autonomous SNES clock claim'}
