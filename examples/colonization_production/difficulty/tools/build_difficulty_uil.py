"""Add explicit difficulty modifiers to the previous two edition representations.
Source-backed, authored recovery. This is not automatic decompiler output.
"""
from pathlib import Path
import sys,json,copy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'previous/tools'))
from build_uil import F,E,IF,CALL,make as earlier_make
from fdisbull.common_uil import digest,validate_program,validate_presentation

def require(condition):return {'op':'require','condition':condition}

def morale():
 f=F([('difficulty','u8'),('population','u8'),('rebel_percent','u8'),('human_european','bool'),('majority_flag','bool'),('unanimous_flag','bool')], [('tories','u16'),('divisor','u16'),('modifier','i16')],['tories','divisor','modifier'])
 v,k=f.v,f.k;cast=lambda n:E('cast','u16',v(n))
 f.fn['body']=[require(E('le','bool',v('difficulty'),k(4,'u8'))),require(E('le','bool',v('population'),k(31,'u8'))),require(E('le','bool',v('rebel_percent'),k(100,'u8'))),
 f.set('tories',E('div','u16',E('add','u16',E('mul','u16',cast('population'),E('sub','u16',k(100,'u16'),cast('rebel_percent'))),k(50,'u16')),k(100,'u16'))),
 f.set('divisor',k(10,'u16')),IF(v('human_european'),[f.set('divisor',E('sub','u16',k(10,'u16'),cast('difficulty')))],[f.set('tories',k(0,'u16'))]),
 f.set('modifier',E('sub','i16',k(0),E('cast','i16',E('div','u16',v('tories'),v('divisor'))))),
 IF(v('majority_flag'),[f.set('modifier',E('add','i16',v('modifier'),k(1)))]),IF(v('unanimous_flag'),[f.set('modifier',E('add','i16',v('modifier'),k(1)))])]
 return f

def food():
 f=F([('difficulty','u8'),('terrain','i16')],[('food','u8')],['food']);v,k=f.v,f.k
 eq=lambda n:E('eq','bool',v('terrain'),k(n))
 ors=lambda *terms:E('select','bool',terms[0],k(True,'bool'),terms[1] if len(terms)==2 else ors(*terms[1:]))
 middle=ors(eq(27),eq(28),E('select','bool',E('ge','bool',v('terrain'),k(8)),E('lt','bool',v('terrain'),k(24)),k(False,'bool')))
 f.fn['body']=[require(E('le','bool',v('difficulty'),k(4,'u8'))),f.set('food',k(3,'u8')),IF(eq(24),[f.set('food',k(0,'u8'))],[IF(ors(eq(1),eq(17),eq(9)),[f.set('food',k(1,'u8'))],[IF(middle,[f.set('food',k(2,'u8'))])])]),IF(E('eq','bool',v('difficulty'),k(0,'u8')),[f.set('food',E('add','u8',v('food'),k(2,'u8')))]),IF(E('eq','bool',v('difficulty'),k(1,'u8')),[f.set('food',E('add','u8',v('food'),k(1,'u8')))])]
 return f

def secondary():
 f=F([('difficulty','u8')],[('bonus','u8')],['bonus']);v,k=f.v,f.k
 f.fn['body']=[require(E('le','bool',v('difficulty'),k(4,'u8'))),f.set('bonus',k(0,'u8')),IF(E('eq','bool',v('difficulty'),k(0,'u8')),[f.set('bonus',k(1,'u8'))])];return f

def manufacturing():
 f=F([('rate','u8'),('modifier','i16'),('building_count','u8'),('expert','bool')],[('production','i16')],['production']);v,k=f.v,f.k
 f.fn['body']=[require(E('ge','bool',v('rate'),k(1,'u8'))),require(E('le','bool',v('rate'),k(3,'u8'))),require(E('ge','bool',v('modifier'),k(-5))),require(E('le','bool',v('modifier'),k(2))),require(E('ge','bool',v('building_count'),k(1,'u8'))),require(E('le','bool',v('building_count'),k(3,'u8'))),
 f.set('production',E('add','i16',E('cast','i16',v('rate')),v('modifier'))),
 IF(E('gt','bool',v('building_count'),k(1,'u8')),[f.set('production',E('add','i16',v('production'),E('cast','i16',v('rate'))))]),
 IF(E('gt','bool',v('building_count'),k(2,'u8')),[f.set('production',E('add','i16',v('production'),E('shr','i16',v('production'),k(1))))]),
 IF(v('expert'),[f.set('production',E('mul','i16',v('production'),k(2)))]),IF(E('lt','bool',v('production'),k(0)),[f.set('production',k(0))])]
 return f

def suite():
 ports=[('difficulty','u8'),('population','u8'),('rebel_percent','u8'),('nation','u8'),('controller','u8'),('status_flags','u8'),('terrain','i16'),('rate','u8'),('expert','bool'),('building_count','u8'),('fixed_production','i16'),('supply','i16'),('stock','i16'),('use_worker','bool')]
 locals_=[('tories','u16'),('divisor','u16'),('modifier','i16'),('center_food','u8'),('secondary_bonus','u8'),('worker_output','i16'),('production','i16'),('consumed','i16'),('shortage','i16'),('unmet','i16'),('net','i16')]
 f=F(ports,locals_,['tories','divisor','modifier','center_food','secondary_bonus','worker_output','consumed','shortage','unmet','net']);v,k=f.v,f.k
 human=E('select','bool',E('lt','bool',v('nation'),k(4,'u8')),E('eq','bool',v('controller'),k(0,'u8')),k(False,'bool'))
 flag=lambda mask:E('ne','bool',E('and','u8',v('status_flags'),k(mask,'u8')),k(0,'u8'))
 f.fn['body']=[require(E('le','bool',v('nation'),k(4,'u8'))),require(E('le','bool',v('controller'),k(2,'u8'))),
 CALL(7,[v('difficulty'),v('population'),v('rebel_percent'),human,flag(4),flag(2)],[f.i(n) for n in ['tories','divisor','modifier']]),
 CALL(8,[v('difficulty'),v('terrain')],[f.i('center_food')]),CALL(9,[v('difficulty')],[f.i('secondary_bonus')]),
 CALL(10,[v('rate'),v('modifier'),v('building_count'),v('expert')],[f.i('worker_output')]),
 f.set('production',v('fixed_production')),IF(v('use_worker'),[f.set('production',v('worker_output'))]),
 CALL(5,[v('supply'),v('stock'),v('production'),v('building_count')],[f.i(n) for n in ['consumed','shortage','unmet','net']])]
 return f

NAMES=['difficulty_morale','center_food_stage','center_secondary_bonus','manufacturing_worker_output','difficulty_composition']
def make(edition):
 p,v,names=earlier_make(edition)
 fs=[morale(),food(),secondary(),manufacturing(),suite()]
 p['functions'] += [f.fn for f in fs];p['entry']=11
 v['functions'] += [f.presentation() for f in fs];v['program_sha256']=digest(p)
 for name,f in zip(NAMES,fs):names[name]={'slots':f.names,'inputs':[f.names[i] for i in f.fn['inputs']],'outputs':[f.names[i] for i in f.fn['outputs']]}
 validate_program(p);validate_presentation(p,v)
 return p,v,names

def input_row(row):
 _,d,p,sol,n,c,status,t,rate,expert,bits,g,s,stock,use=row
 return [d,p,sol,n,c,status,t,rate,bool(expert),bits.bit_count(),g,s,stock,bool(use)]

if __name__=='__main__':
 for edition in ('DOS','WIN'):
  p,v,n=make(edition);out=ROOT/'representations'/edition.lower();out.mkdir(parents=True,exist_ok=True)
  docs={'program.uil.json':p,'presentation.json':v,'labels.json':n,'catalog.json':{'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]},'orchestration.json':{'format':'fdisbull-uil-orchestration-1','program_sha256':digest(p),'bindings':[],'ownership':'copy-in-copy-out','max_call_depth':32}}
  for name,doc in docs.items():(out/name).write_text(json.dumps(doc,indent=2)+'\n')
 print('Validated both expanded editions')
