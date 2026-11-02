"""Import the three verified D006 condition traces into a new semantic review log.

This is a retrospective transformation of recorded native evidence, NOT a live
collector or a new game replay. The original projectile journal is copied, never
edited. The selected trace forms and source-reference interpretation are bounded
research bindings, not generic game knowledge in WorldHistory.
"""
from __future__ import annotations
import argparse, hashlib, json, sqlite3, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'examples/syndicate_z_scene/tools'))
from world_history import WorldHistory, canonical, render_summary

PROFILES = {
    'laser-delivered': ('laser',16,39,'0x33003','0x33009'),
    'flame-delivered': ('flame',8,33,'0x32d1b','0x32d21'),
    'car-delivered': ('vehicle-contact',1,13,'0x32fa0','0x32fa6'),
}

def build(evidence:Path, projectiles:Path, output:Path):
    if not evidence.is_file() or not projectiles.is_file():
        raise ValueError('Both retained evidence inputs are required')
    if output.exists():raise FileExistsError('Use a new output directory')
    data=json.loads(evidence.read_text()); digest=hashlib.sha256(evidence.read_bytes()).hexdigest()
    if set(data)!=set(PROFILES):raise ValueError('Unexpected trace set')
    output.mkdir(parents=True)
    target=output/'review-history.sqlite3'
    with sqlite3.connect(projectiles.resolve().as_uri()+'?mode=ro',uri=True) as src:
        with sqlite3.connect(target) as dest:src.backup(dest)
    results={}
    with WorldHistory(target) as h:
        initial=h.high_watermark
        for name,(family,mask,subtype,before,after) in PROFILES.items():
            trace=data[name]; events=trace['events']
            stream='recorded-'+name
            h.stream(stream,metadata={'evidence_sha256':digest,'evidence_case':name,
                'provenance':'retrospective import of existing original-code observations, not another execution',
                'preparation':trace.get('writes',trace.get('preparation')),
                'coverage':'selected condition episode only; contact contribution not separated'})
            h.append(stream,'import','start',{'kind':'evidence-import','message':f'Recorded {family} condition episode; not a fresh run.'})
            parents=[]
            for i,e in enumerate(events):
                if e['pc']!='0x12b83':continue
                if e.get('mask',e.get('applied_mask'))!=mask:raise ValueError('Mask mismatch')
                source=e['source'];victim=e['victim']
                if source['subtype']!=subtype or victim['id']!='person-0':raise ValueError('Identity/type mismatch')
                actor=None
                if family=='vehicle-contact':
                    if source['kind']!=2 or source['id']!='vehicle-0':raise ValueError('Not the selected car')
                else:
                    if source['kind']!=3 or source.get('owner_field_raw')!=1014:raise ValueError('Unqualified effect owner')
                    actor='person-11'
                event={'kind':'damage-contact','guest_tick':e['tick'],'victim_id':victim['id'],
                    'cause':{'actor_id':actor,'source_entity_id':source['id'],'damage_type':family},
                    'certainty':'recorded-native-contact','observation_basis':'source-bound original contact application',
                    'mask_raw':mask,'health_raw':victim.get('hp',victim.get('hp_word')),
                    'last_source_raw':victim.get('last_source',victim.get('last_source_ref')),
                    'message':'Contact observation; not another numeric health-loss event',
                    'evidence_row':i,'evidence_sha256':digest}
                parents.append(h.append(stream,'contact',str(i),event)['id'])
            pre=[e for e in events if e['pc']==before];post=[e for e in events if e['pc']==after]
            if len(pre)!=1 or len(post)!=1 or not parents:raise ValueError('Missing unique health transition')
            old=pre[0]['victim'].get('hp',pre[0]['victim'].get('hp_word'))
            new=post[0]['victim'].get('hp',post[0]['victim'].get('hp_word'))
            if (old,new)!=(16,-1):raise ValueError('Not the qualified terminal sentinel')
            terminal={'kind':'terminal-state','guest_tick':post[0]['tick'],'victim_id':'person-0',
                'health_before_raw':old,'health_after_raw':new,'health_word_after':65535,
                'cause':{'actor_id':None if family=='vehicle-contact' else 'person-11',
                         'source_entity_id':'vehicle-0' if family=='vehicle-contact' else None,'damage_type':family},
                'causal_parents':parents,'certainty':'recorded condition episode; individual contact contribution unresolved',
                'message':f'{family}: health word 16 -> FFFF; terminal sentinel, not 17 HP damage.',
                'before_pc':before,'after_pc':after,'evidence_sha256':digest}
            h.append(stream,'health','terminal',terminal)
            h.append(stream,'import','end',{'kind':'evidence-import-end','message':f'{len(parents)} contact observations and one terminal-state transition retained.'})
            results[name]={'contacts':len(parents),'terminal_transitions':1,'arithmetic_damage_events':0}
        h.export_jsonl(output/'review-events.jsonl')
        text=render_summary(h.summarize(max_rows=50),max_chars=20000)
        (output/'review-summary.txt').write_text(text+'\n')
        final=h.high_watermark
    result={'input_projectile_records':initial,'output_records':final,'cases':results,
            'native_replayed':False,'original_journal_modified':False,'evidence_sha256':digest,
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('evidence',type=Path);p.add_argument('projectiles',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();print(json.dumps(build(a.evidence,a.projectiles,a.output),indent=2))
