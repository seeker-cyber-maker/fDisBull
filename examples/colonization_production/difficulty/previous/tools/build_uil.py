"""Source-reviewed DOS and Win16 definitions in the supplied common UIL format.

These are authored semantic recoveries, not decompiler output. Source/backing
identities are separately retained. Function names are explanatory port labels.
"""
from pathlib import Path
import json,copy
from fdisbull.common_uil import digest,validate_program,validate_presentation
R=Path(__file__).resolve().parents[1]

def E(op,typ,*args):return {'op':op,'type':typ,'args':list(args)}
def S(dst,value):return {'op':'set','dst':dst,'value':value}
def IF(cond,yes,no=()):return {'op':'if','condition':cond,'then':list(yes),'else':list(no)}
def CALL(fn,inputs,outputs):return {'op':'call','function':fn,'inputs':inputs,'outputs':outputs}
class F:
 def __init__(self,ports,locals_,outputs):
  self.names=[x[0] for x in ports+locals_];self.types=[x[1] for x in ports+locals_];self.const=[];self.values=[]
  self.fn={'variables':[{'type':t} for t in self.types],'constants':self.const,'inputs':list(range(len(ports))),'outputs':[self.names.index(x) for x in outputs],'max_steps':512,'body':[]}
 def v(self,n):return {'var':self.names.index(n)}
 def i(self,n):return self.names.index(n)
 def k(self,value,typ='i16'):
  # Keep source expressions explicit; identical typed constants reuse one entry.
  for i,(d,v) in enumerate(zip(self.const,self.values)):
   if d['type']==typ and type(value)==type(v) and value==v:return {'const':i}
  self.const.append({'type':typ});self.values.append(value);return {'const':len(self.const)-1}
 def set(self,n,v):return S(self.i(n),v)
 def presentation(self):return {'constants':[v if type(v)==bool else str(v) for v in self.values],'initial':[False if t=='bool' else '0' for t in self.types]}

def balance(edition):
 f=F([('supply','i16'),('demand','i16'),('available','i16')],[('consumed','i16'),('shortage','i16'),('unmet','i16'),('total','i16')],['consumed','shortage','unmet'])
 v=f.v;k=f.k
 last=E('sub','i16',E('sub','i16',v('demand'),v('available')),v('supply')) if edition=='DOS' else E('sub','i16',v('demand'),v('total'))
 f.fn['body']=[f.set('consumed',v('demand')),f.set('shortage',k(0)),f.set('unmet',k(0)),IF(E('gt','bool',v('demand'),v('supply')),[f.set('shortage',E('sub','i16',v('demand'),v('supply')))]),f.set('total',E('add','i16',v('supply'),v('available'))),IF(E('lt','bool',v('total'),v('demand')),[f.set('unmet',last)])]
 return f

def net():
 f=F([('produced','i16'),('consumed','i16'),('has_adjustment','bool'),('adjustment','i16'),('has_report','bool'),('prior_report','i16')],[('net','i16'),('report','i16'),('written','bool')],['net','report','written']);v=f.v;k=f.k
 f.fn['body']=[f.set('net',E('sub','i16',v('produced'),v('consumed'))),f.set('report',v('prior_report')),f.set('written',k(False,'bool')),IF(v('has_adjustment'),[f.set('net',E('sub','i16',v('net'),v('adjustment'))),IF(v('has_report'),[f.set('report',v('adjustment')),f.set('written',k(True,'bool'))])])]
 return f

def capacity(edition):
 f=F([('level','u8')],[('capacity','i16')],['capacity']);v=f.v;k=f.k;x=E('cast','i16',v('level'))
 value=E('mul','i16',E('add','i16',x,k(1)),k(100)) if edition=='DOS' else E('add','i16',k(100),E('mul','i16',x,k(100)))
 f.fn['body']=[f.set('capacity',k(100)),IF(E('ne','bool',v('level'),k(0,'u8')),[f.set('capacity',value)])]
 return f

def surplus():
 f=F([('stock','i16'),('produced','i16'),('consumed','i16')],[('available','bool')],['available']);v=f.v
 f.fn['body']=[f.set('available',E('gt','bool',E('add','i16',v('stock'),v('produced')),v('consumed')))];return f

def packed():
 f=F([('population','i8'),('index','u16'),('packed_byte','u8')],[('value','u8')],['value']);v=f.v;k=f.k
 f.fn['body']=[{'op':'require','condition':E('lt','bool',v('index'),k(32,'u16'))},f.set('value',k(0,'u8')),IF(E('gt','bool',E('cast','i16',v('population')),E('cast','i16',v('index'))),[f.set('value',v('packed_byte')),IF(E('ne','bool',E('and','u16',v('index'),k(1,'u16')),k(0,'u16')),[f.set('value',E('shr','u8',v('value'),k(4,'u8')))]),f.set('value',E('and','u8',v('value'),k(15,'u8')))])]
 return f

def recipe(edition):
 f=F([('supply','i16'),('stock','i16'),('production','i16'),('building_count','u8')],[('scaled','i16'),('consumed','i16'),('shortage','i16'),('unmet','i16'),('net','i16'),('report','i16'),('written','bool')],['consumed','shortage','unmet','net']);v=f.v;k=f.k
 f.fn['body']=[{'op':'require','condition':E('le','bool',v('building_count'),k(3,'u8'))},f.set('scaled',v('production')),IF(E('gt','bool',v('building_count'),k(2,'u8')),[f.set('scaled',E('div','i16',E('mul','i16',v('production'),k(2)),k(3)))]),CALL(0,[v('supply'),v('scaled'),v('stock')],[f.i(n) for n in ['consumed','shortage','unmet']])]
 if edition=='DOS':
  f.fn['body'].append(IF(E('ne','bool',v('unmet'),k(0)),[IF(E('ne','bool',v('production'),v('scaled')),[IF(E('eq','bool',v('unmet'),v('scaled')),[f.set('unmet',v('production'))],[f.set('unmet',E('div','i16',E('mul','i16',v('unmet'),k(3)),k(2)))])])]))
 # Explicit composition with the paired original net helper, fixed mapped input class.
 f.fn['body'].append(CALL(1,[v('production'),k(0),k(True,'bool'),v('unmet'),k(False,'bool'),k(0)],[f.i('net'),f.i('report'),f.i('written')]))
 return f

def suite():
 f=F([('level','u8'),('stock','i16'),('supply','i16'),('demand','i16'),('population','i8'),('index','u16'),('packed_byte','u8'),('production','i16'),('building_count','u8')],[('capacity','i16'),('available','bool'),('nibble','u8'),('consumed','i16'),('shortage','i16'),('unmet','i16'),('net','i16')],['capacity','available','nibble','consumed','shortage','unmet','net']);v=f.v
 f.fn['body']=[CALL(2,[v('level')],[f.i('capacity')]),CALL(3,[v('stock'),v('supply'),v('demand')],[f.i('available')]),CALL(4,[v('population'),v('index'),v('packed_byte')],[f.i('nibble')]),CALL(5,[v('supply'),v('stock'),v('production'),v('building_count')],[f.i(n) for n in ['consumed','shortage','unmet','net']])]
 return f

NAMES=['input_balance','net_production','capacity_from_level','stock_available','packed_slot_read','production_input_pipeline','comparison_suite']
def make(edition):
 fs=[balance(edition),net(),capacity(edition),surplus(),packed(),recipe(edition),suite()]
 program={'format':'fdisbull-common-uil-1','capabilities':['core.scalar@1','core.calls@1'],'imports':[],'functions':[f.fn for f in fs],'entry':6}
 presentation={'format':'fdisbull-uil-presentation-1','program_sha256':digest(program),'functions':[f.presentation() for f in fs],'resources':[]}
 validate_program(program);validate_presentation(program,presentation)
 names={n:{'slots':f.names,'inputs':[f.names[i] for i in f.fn['inputs']],'outputs':[f.names[i] for i in f.fn['outputs']]} for n,f in zip(NAMES,fs)}
 return program,presentation,names

def entry(program,presentation,index):
 p=copy.deepcopy(program);v=copy.deepcopy(presentation);p['entry']=index;v['program_sha256']=digest(p);return p,v

if __name__=='__main__':
 for edition in ['DOS','WIN']:
  p,v,names=make(edition);out=R/'deliverable/representations'/edition.lower();out.mkdir(parents=True,exist_ok=True)
  for file,doc in [('program.uil.json',p),('presentation.json',v),('labels.json',names)]: (out/file).write_text(json.dumps(doc,indent=2)+'\n')
 print('Both per-edition programs validate; source addresses remain in bindings.')
