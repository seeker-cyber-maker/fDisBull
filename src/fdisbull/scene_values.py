"""Typed scene relations and reads whose lifetime is one stopped observation."""
import re


def scalar_type(value):
    if not isinstance(value,str) or not re.fullmatch(r'[ui](8|16|32|64)',value):
        raise ValueError('Scene scalar type must be u8/i8/u16/i16/u32/i32/u64/i64')
    return int(value[1:])//8,value.startswith('i')


def memory_ref(value):
    if not isinstance(value,dict) or set(value)-{'address','type','endian','cs'}:
        raise ValueError('Invalid typed memory reference')
    if not isinstance(value.get('address'),str):raise ValueError('Typed memory needs a project address')
    scalar_type(value.get('type'))
    if value.get('endian','little') not in ('little','big'):raise ValueError('Invalid scene byte order')


def expression(value, *, allow_before=False, depth=0):
    if depth>8:raise ValueError('Scene expression is too deep')
    if type(value) is int:
        if not -(1<<64)<=value<(1<<64):raise ValueError('Scene integer is out of range')
        return
    if not isinstance(value,dict) or len(value)!=1:raise ValueError('Invalid scene scalar expression')
    op,data=next(iter(value.items()))
    if op=='memory':memory_ref(data)
    elif op=='before':
        if not allow_before or not isinstance(data,dict) or set(data)!={'memory'}:
            raise ValueError('before memory is only valid in an action outcome')
        memory_ref(data['memory'])
    elif op in ('add','sub'):
        if not isinstance(data,list) or len(data)!=2:raise ValueError('Arithmetic needs two operands')
        for child in data:expression(child,allow_before=allow_before,depth=depth+1)
    elif op=='wrap':
        if not isinstance(data,dict) or set(data)!={'type','value'}:raise ValueError('wrap needs type and value')
        scalar_type(data['type']);expression(data['value'],allow_before=allow_before,depth=depth+1)
    else:raise ValueError('Unknown scalar operator '+op)


def comparison(value, *, allow_before=False):
    if not isinstance(value,dict) or set(value)!={'left','op','right'}:raise ValueError('compare needs left, op and right')
    if value['op'] not in ('eq','ne','lt','le','gt','ge'):raise ValueError('Invalid comparison operator')
    for key in ('left','right'):expression(value[key],allow_before=allow_before)


def before_refs(value):
    if isinstance(value,dict):
        if set(value)=={'before'}:
            yield value['before']['memory']
        else:
            for child in value.values():yield from before_refs(child)
    elif isinstance(value,list):
        for child in value:yield from before_refs(child)


class ObservationReads:
    def __init__(self,session):
        self.session=session;self.captures={};self.evaluations=0;self.hits=0

    def key(self,address,length,cs=None):
        linear,_=self.session.project._dos_parse_address(address,cs)
        return f'{linear:x}/{length}'

    def read(self,address,length,cs=None):
        self.evaluations+=1
        key=self.key(address,length,cs)
        if key in self.captures:self.hits+=1
        else:
            capture=dict(id='m'+str(len(self.captures)+1),project_address='0x'+key.split('/')[0],length=length)
            try:
                result=self.session.memory(address,length=length,**({'cs':cs} if cs is not None else {}))
                data=bytes.fromhex(result['hex'])
                if len(data)!=length:raise ValueError('Incomplete scene memory capture')
                capture['hex']=data.hex()
            except Exception as error:capture['error']=str(error)
            self.captures[key]=capture
        capture=self.captures[key]
        if 'error' in capture:raise ValueError(capture['error'])
        return bytes.fromhex(capture['hex']),capture['id']

    def scalar_key(self,ref):
        length,_=scalar_type(ref['type'])
        return self.key(ref['address'],length,ref.get('cs'))+'/'+ref['type']+'/'+ref.get('endian','little')

    def scalar(self,ref):
        length,signed=scalar_type(ref['type'])
        data,_=self.read(ref['address'],length,ref.get('cs'))
        return int.from_bytes(data,ref.get('endian','little'),signed=signed)

    def freeze(self,refs,binding):
        values={}
        for ref in refs:
            key=self.scalar_key(ref)
            if key in values:continue
            try:values[key]={'value':self.scalar(ref)}
            except Exception as error:values[key]={'error':str(error)}
        return dict(binding,values=values)

    def stats(self):
        return dict(evaluations=self.evaluations,unique_reads=len(self.captures),cache_hits=self.hits)


def evaluate_expression(value,reads,baseline):
    if type(value) is int:return value
    op,data=next(iter(value.items()))
    if op=='memory':return reads.scalar(data)
    if op=='before':
        if baseline is None:raise ValueError('Missing pre-action baseline')
        captured=baseline['values'].get(reads.scalar_key(data['memory']))
        if captured is None or 'error' in captured:raise ValueError('Incomplete pre-action memory capture')
        return captured['value']
    if op=='wrap':
        length,signed=scalar_type(data['type']);bits=length*8
        result=evaluate_expression(data['value'],reads,baseline)&((1<<bits)-1)
        return result-(1<<bits) if signed and result&(1<<(bits-1)) else result
    left,right=(evaluate_expression(v,reads,baseline) for v in data)
    return left+right if op=='add' else left-right


def evaluate_comparison(value,reads,baseline):
    left=evaluate_expression(value['left'],reads,baseline);right=evaluate_expression(value['right'],reads,baseline)
    result={'eq':lambda:left==right,'ne':lambda:left!=right,'lt':lambda:left<right,
            'le':lambda:left<=right,'gt':lambda:left>right,'ge':lambda:left>=right}[value['op']]()
    return result,left,right


def compact_result(result):
    """Present a retained observation without repeated specs/samples/poll records."""
    def view(value):
        if isinstance(value,list):return [view(v) for v in value]
        if not isinstance(value,dict):return value
        out={k:view(v) for k,v in value.items() if k not in ('evidence','memory_captures','samples','polls','baseline')}
        for key in ('evidence','memory_captures','samples','polls'):
            if key in value:out[key+'_count']=len(value[key])
        if 'baseline' in value:out['baseline_retained']=True
        return out
    return dict(view(result),reply_format='fdisbull-scene-compact-1')
