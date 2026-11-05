"""Compare retained source observations with an independently expressed specification."""
from pathlib import Path
import json,struct,hashlib,collections,argparse

def w16(n):return ((n+32768)&65535)-32768

def expected(words,edition):
 ident,d,p,sol,n,c,status,t,rate,expert,bits,g,s,stock,use=words
 human=n<4 and c==0
 tories=(p*(100-sol)+50)//100 if human else 0
 div=10-d if human else 10
 modifier=-(tories//div)+bool(status&4)+bool(status&2)
 if t==24:base=0
 elif t in (1,17,9):base=1
 elif t in (27,28) or 8<=t<24:base=2
 else:base=3
 food=base+(2 if d==0 else 1 if d==1 else 0)
 count={1:1,3:2,7:3}[bits]
 work=rate+modifier
 if count>1:work+=rate
 if count>2:work+=work//2
 if expert:work*=2
 work=max(0,work)
 if use:g=work
 demand=(w16(g*2)//3) if count>2 else g
 # Corpus uses nonnegative gross, supplies and stock; truncation is exact here.
 shortage=max(0,demand-s)
 unmet=max(0,demand-s-stock)
 if edition=='DOS' and unmet and g!=demand:
  unmet=g if unmet==demand else (unmet*3)//2
 net=w16(g-unmet)
 return [ident,tories,div,modifier,food,int(d==0),work,demand,shortage,unmet,net,d]

def run(directory,result):
 rows=json.loads((directory/'cases.json').read_text());streams={}
 mismatches={}
 for ed in ('DOS','WIN'):
  raw=(directory/f'{ed}DIFF.BIN').read_bytes()
  records=[list(x) for x in struct.iter_unpack('<12H',raw)]
  assert len(records)==len(rows)
  bad=[]
  for row,record in zip(rows,records):
   want=[v&65535 for v in expected(row['words'],ed)]
   if record!=want:
    bad.append({'case':row,'observed':record,'expected':want})
  mismatches[ed]=bad;streams[ed]=records
 grid=collections.defaultdict(lambda: {'cases':0,'differences':0,'affected_fields':set()})
 changed_fields=set();whole_differences=0
 for row,dos,win in zip(rows,streams['DOS'],streams['WIN']):
  fields={i for i,(a,b) in enumerate(zip(dos,win)) if a!=b}
  if fields:whole_differences+=1;changed_fields|=fields
  if row['kind']=='fixed-production-grid':
   d=row['words'][1];g=grid[d];g['cases']+=1;g['differences']+=bool(fields);g['affected_fields']|=fields
 for g in grid.values():g['affected_fields']=sorted(g['affected_fields'])
 thresholds=[]
 for d in range(5):
  selected=[]
  for row,r in zip(rows,streams['DOS']):
   words=row['words']
   if row['kind']=='human-morale-exhaustive' and words[1]==d and words[3]==0 and r[3]&0x8000:selected.append(words[2])
  thresholds.append(min(selected))
 demos=[]
 for d in range(5):
  pairs=[]
  for row,dos,win in zip(rows,streams['DOS'],streams['WIN']):
   w=row['words']
   if row['kind']=='coupled-worker-pipeline' and w[1]==d and w[2]==12 and w[3]==0 and w[8]==3 and w[9]==0 and w[10]==7:
    demos.append({'difficulty':d,'tories':dos[1],'modifier':w16(dos[3]),'gross':dos[6],'dos_net':w16(dos[10]),'win_net':w16(win[10])})
 result.parent.mkdir(parents=True,exist_ok=True)
 out={'cases_per_edition':len(rows),'case_categories':dict(collections.Counter(x['kind'] for x in rows)),
      'model_mismatches':{k:len(v) for k,v in mismatches.items()},'first_mismatches':{k:v[:5] for k,v in mismatches.items()},
      'paired_differing_cases':whole_differences,'paired_differing_field_indices':sorted(changed_fields),
      'fixed_input_grid_by_difficulty':dict(grid),'first_penalty_tories':thresholds,'coupled_example_population_12':demos,
      'result_sha256':{e:hashlib.sha256((directory/f'{e}DIFF.BIN').read_bytes()).hexdigest() for e in streams}}
 result.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
 return not any(mismatches.values())
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('--native-dir',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args();raise SystemExit(0 if run(v.native_dir,v.output) else 1)
