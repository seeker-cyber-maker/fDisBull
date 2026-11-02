"""Authored burst/load test, NOT simulated Syndicate combat or FPS measurement."""
from pathlib import Path
import argparse,hashlib,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'examples/syndicate_z_scene/tools'))
from world_history import WorldHistory,HistoryBackend,render_summary

def run(output):
    output=Path(output);output.mkdir(exist_ok=False,parents=True);n=10000
    event={'kind':'damage','guest_tick':1,'victim_id':'authored','health_before':8,'health_after':7,'amount':1,
           'cause':{'actor_id':'authored-shooter','damage_type':'authored'},'certainty':'synthetic-load',
           'observation_basis':'identical payload stress; NOT a health trajectory'}
    start=time.monotonic();path=output/'authored.sqlite3';ids=[];notices=[]
    with WorldHistory(path,max_events=20000) as h:
        h.stream('synthetic',metadata={'purpose':'10,000 repeated identical records, not a native game'})
        for i in range(n):
            if i in (0,5000,9999):
                notices.append(h.append('synthetic','notice',str(i),{'kind':'objective-notice','message':f'Authored notice {i}'}))
            ids.append(h.append('synthetic','hits',str(i),event)['id'])
        high=h.high_watermark;last=0;total=0;groups=0;rows=[]
        while last<high:
            page=h.summarize(after=last,through=high,max_rows=4,scan_limit=2000)
            if page['consumed_through']<=last:raise AssertionError('Nonadvancing page')
            last=page['consumed_through'];groups+=len(page['groups'])
            total+=sum(g['count'] for g in page['groups']);rows.extend(g['example']['kind'] for g in page['groups'])
        assert total==n+3 and len(set(ids))==n and rows.count('objective-notice')==3
        text=render_summary(h.summarize(max_rows=4),max_chars=1000);assert len(text)<=1000
        retained=h.recent(notices_only=True);assert len(retained)==3
        stable_ids=[h.get(ids[0])['id'],h.get(ids[-1])['id']]
    with WorldHistory(path) as h:
        assert h.high_watermark==n+3 and [h.get(ids[0])['id'],h.get(ids[-1])['id']]==stable_ids
    result={'kind':'authored-burst-load-test','native_game':False,'identical_hit_records':n,'same_guest_tick':True,
            'other_notices':3,'unique_hit_ids':len(set(ids)),'records_after_reopen':n+3,
            'paginated_records_accounted':total,'display_groups_across_all_pages':groups,
            'notices_retained_across_burst':len(retained),'sample_display_chars':len(text),
            'display_bound':1000,'seconds':time.monotonic()-start,'status':'passed',
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');(output/'sample.txt').write_text(text+'\n')
    print(json.dumps(result,indent=2));return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);run(p.parse_args().output)
