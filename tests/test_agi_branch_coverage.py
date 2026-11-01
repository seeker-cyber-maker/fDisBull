from copy import deepcopy

import pytest

from fdisbull.agi_coverage import aggregate_native_coverage

SHA='a'*64

def projection(same=False):
    return {'format':'fdisbull-agi-state-projection-3','source':{'resource_sha256':SHA},
      'uil':{'entry':'a','continuations':{
          'a':{'transfer':{'op':'if','then':'b','else':'b' if same else 'c'}},
          'b':{'transfer':{'op':'goto','target':'c'}},
          'c':{'transfer':{'op':'return'}}}},
      'block_sources':{'a':{'offset':0},'b':{'offset':1},'c':{'offset':2}},
      'effect_operations':[{'offset':1}]}

def receipt(path,epoch='one'):
    identity={'format':'fdisbull-agi-dos-monitor-1','session_id':'session','epoch':epoch,'resource_sha256':SHA}
    attempts=[]
    for i,offset in enumerate(path):
        item={'offset':offset,'identity':deepcopy(identity),'native_execution':True,
              'status':'returned' if i==len(path)-1 else 'completed','stop':{'outcome':'breakpoint'}}
        if i<len(path)-1:item['next_offset']=path[i+1]
        attempts.append(item)
    return {'format':'fdisbull-agi-original-host-trial-1','status':'verified','complete':True,
            'native_execution':True,'identity':identity,'source_offsets':path,'attempts':attempts,'differences':[]}

def test_coverage_uses_complete_native_paths():
    out=aggregate_native_coverage(projection(),[receipt([0,1,2]),receipt([0,2],'two')])
    assert out['complete'] and out['source']['observed']==3 and out['effects']['observed']==1 and out['branches']['observed']==2
    assert 'not authenticated' in out['qualification']

def test_missing_and_ambiguous_branch():
    out=aggregate_native_coverage(projection(),[receipt([0,1,2])])
    assert not out['complete'] and out['branches']['missing']==[{'offset':0,'outcome':'else'}]
    out=aggregate_native_coverage(projection(True),[receipt([0,1,2])])
    assert not out['complete'] and out['branches']['observed']==0 and out['branches']['same_target_unknown']==[0]

@pytest.mark.parametrize('change',[
    lambda x:x.update(status='incomplete'), lambda x:x.update(native_execution=False),
    lambda x:x['identity'].update(resource_sha256='b'*64),
    lambda x:x['attempts'].pop(),lambda x:x['attempts'][0].pop('stop'),lambda x:x['attempts'][0].update(next_offset=2),
    lambda x:x['attempts'][0]['identity'].update(epoch='different'),
    lambda x:x.update(differences=[{'field':'x'}]),
])
def test_refuses_bad_receipts(change):
    r=receipt([0,1,2]);change(r)
    with pytest.raises(ValueError):aggregate_native_coverage(projection(),[r])

def test_duplicate_or_invalid_transition_rejected():
    with pytest.raises(ValueError):aggregate_native_coverage(projection(),[receipt([0,1,2]),receipt([0,1,2])])
    with pytest.raises(ValueError):aggregate_native_coverage(projection(),[receipt([0,2,1,2])])
