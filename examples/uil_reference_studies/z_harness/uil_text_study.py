"""Executable, experimental UIL text-value profile recovered from real examples.

This is a study profile, not an addition accepted by common-uil-1 validators.
It models typed values and staged text output. It neither calls native backings
nor emulates source buffers, fonts, DOS, graphics, or all printf conversions.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re

PROFILE = 'uil-text-study-1'
INTEGER = re.compile(r'([iu])(8|16|32|64)\Z')
MAX_TEXT_BYTES = 4096

class Refused(ValueError):
    """A modeled operation cannot complete inside its admitted domain."""

def integer_type(typ):
    if type(typ) is not str: raise ValueError('Type name required')
    match = INTEGER.fullmatch(typ)
    if not match:
        raise ValueError(f'Not an integer type: {typ}')
    return match[1] == 'i', int(match[2])

def wrap(value, typ):
    signed, bits = integer_type(typ)
    value %= 1 << bits
    return value - (1 << bits) if signed and value >= (1 << (bits - 1)) else value

def admit(value, typ):
    if typ == 'text':
        if type(value) is not str or len(value.encode('utf-8')) > MAX_TEXT_BYTES:
            raise ValueError('Invalid or oversized text value')
    elif typ == 'bool':
        if type(value) is not bool:
            raise ValueError('Boolean value required')
    elif type(value) is not int or wrap(value, typ) != value:
        raise ValueError(f'Value is not in {typ}: {value!r}')
    return value

def index(value, table):
    if type(value) is not int or not 0 <= value < len(table):
        raise ValueError('Reference is not a valid zero-based index')
    return table[value]

def exact(obj, required, optional=()):
    if type(obj) is not dict or not set(required) <= obj.keys() or set(obj) - set(required) - set(optional):
        raise ValueError('Unexpected or missing fields')

def validate(document):
    exact(document, ('format','program','bindings'), ('description','source_evidence'))
    if document['format'] != PROFILE:
        raise ValueError('Unsupported study profile')
    p, b = document['program'], document['bindings']
    exact(p, ('variables','constants','inputs','outputs','max_steps','body'))
    exact(b, ('initial','constants'))
    for table in (p['variables'],p['constants']):
        if type(table) is not list: raise ValueError('Typed table required')
        for descriptor in table:
            exact(descriptor, ('type',))
            typ = descriptor['type']
            if typ not in ('bool','text'): integer_type(typ)
    for fields, values in ((p['variables'],b['initial']),(p['constants'],b['constants'])):
        if type(values) is not list: raise ValueError('Binding list required')
        if len(fields) != len(values): raise ValueError('Every slot must be bound')
        for descriptor, value in zip(fields,values): admit(value,descriptor['type'])
    for port in ('inputs','outputs'):
        if type(p[port]) is not list: raise ValueError('Port list required')
        for slot in p[port]: index(slot,p['variables'])
        if len(set(p[port])) != len(p[port]): raise ValueError('Duplicate port')
    if type(p['max_steps']) is not int or not 1 <= p['max_steps'] <= 10000:
        raise ValueError('Invalid step budget')

    def expression(node, depth=0):
        if depth > 32: raise ValueError('Expression depth exceeded')
        if type(node) is not dict: raise ValueError('Expression object required')
        if set(node) == {'var'}: return index(node['var'],p['variables'])['type']
        if set(node) == {'const'}: return index(node['const'],p['constants'])['type']
        if node.get('op') == 'text.format':
            exact(node, ('op','parts'))
            if type(node['parts']) is not list or len(node['parts']) > 128:
                raise ValueError('Invalid template parts')
            for part in node['parts']:
                if type(part) is not dict: raise ValueError('Template part object required')
                if 'text' in part:
                    exact(part, ('text',))
                    if expression(part['text'],depth+1) != 'text': raise ValueError('Text part required')
                else:
                    exact(part, ('decimal','width','pad'))
                    integer_type(expression(part['decimal'],depth+1))
                    if type(part['width']) is not int or not 0 <= part['width'] <= 128 or part['pad'] not in ('0',' '):
                        raise ValueError('Invalid decimal field')
            return 'text'
        exact(node, ('op','type','args'))
        if type(node['args']) is not list: raise ValueError('Argument list required')
        ts = [expression(arg,depth+1) for arg in node['args']]
        op, typ = node['op'], node['type']
        if op in ('add','sub','mul','div','mod','and'):
            integer_type(typ)
            if ts != [typ,typ]: raise ValueError('Arithmetic type mismatch')
        elif op == 'neg':
            integer_type(typ)
            if ts != [typ]: raise ValueError('Negation type mismatch')
        elif op in ('lt','eq'):
            if len(ts)!=2 or ts[0]!=ts[1] or typ!='bool': raise ValueError('Comparison type mismatch')
            if op=='lt': integer_type(ts[0])
        elif op == 'select':
            if ts != ['bool',typ,typ]: raise ValueError('Select type mismatch')
        else:
            raise ValueError('Unsupported expression: '+str(op))
        return typ

    def statements(body,depth=0):
        if depth > 16 or type(body) is not list or len(body) > 256: raise ValueError('Invalid statement list')
        for node in body:
            if type(node) is not dict: raise ValueError('Statement object required')
            op=node.get('op')
            if op=='set':
                exact(node, ('op','dst','value'))
                if expression(node['value']) != index(node['dst'],p['variables'])['type']: raise ValueError('Assignment type mismatch')
            elif op=='if':
                exact(node, ('op','condition','then','else'))
                if expression(node['condition'])!='bool': raise ValueError('Boolean condition required')
                statements(node['then'],depth+1);statements(node['else'],depth+1)
            elif op=='require':
                exact(node, ('op','condition'))
                if expression(node['condition'])!='bool': raise ValueError('Boolean requirement required')
            elif op=='effect':
                exact(node, ('op','service','value'))
                if node['service']!='text.display' or expression(node['value'])!='text':
                    raise ValueError('Only text.display(text) is supported')
            else: raise ValueError('Unsupported statement: '+str(op))
    statements(p['body'])
    return True

def run(document, inputs):
    validate(document)
    p,b=document['program'],document['bindings']
    if type(inputs) is not list: raise ValueError('Live inputs must be a JSON array')
    if len(inputs)!=len(p['inputs']): raise ValueError('Wrong input arity')
    state=deepcopy(b['initial'])
    for slot,value in zip(p['inputs'],inputs): state[slot]=admit(value,p['variables'][slot]['type'])
    committed=deepcopy(state)
    events=[]
    steps=0

    def evaluate(node):
        if 'var' in node:return state[node['var']]
        if 'const' in node:return b['constants'][node['const']]
        op=node['op']
        if op=='text.format':
            parts=[]
            for part in node['parts']:
                if 'text' in part: parts.append(evaluate(part['text']));continue
                value=evaluate(part['decimal'])
                negative=value<0
                digits=str(abs(value))
                padding=part['pad']*max(0,part['width']-len(digits)-int(negative))
                sign='-' if negative else ''
                parts.append(sign+padding+digits if part['pad']=='0' else padding+sign+digits)
            text=''.join(parts)
            if len(text.encode('utf-8'))>MAX_TEXT_BYTES:raise Refused('Text size budget exceeded')
            return text
        args=[evaluate(arg) for arg in node['args']] # Eager, including both select arms.
        if op=='select':return args[1] if args[0] else args[2]
        if op=='lt':return args[0]<args[1]
        if op=='eq':return args[0]==args[1]
        if op=='neg':result=-args[0]
        elif op=='add':result=args[0]+args[1]
        elif op=='sub':result=args[0]-args[1]
        elif op=='mul':result=args[0]*args[1]
        elif op=='and':result=args[0]&args[1]
        else:
            dividend,divisor=args
            if divisor==0:raise Refused('Division by zero')
            q=abs(dividend)//abs(divisor)
            if (dividend<0)!=(divisor<0):q=-q
            result=q if op=='div' else dividend-q*divisor
        return wrap(result,node['type'])

    def execute(body):
        nonlocal steps
        for node in body:
            steps+=1
            if steps>p['max_steps']:raise Refused('Step budget exceeded')
            op=node['op']
            if op=='set':state[node['dst']]=evaluate(node['value'])
            elif op=='if':execute(node['then'] if evaluate(node['condition']) else node['else'])
            elif op=='require':
                if not evaluate(node['condition']):raise Refused('Requirement failed')
            else:events.append({'service':'text.display','text':evaluate(node['value'])})
    try:execute(p['body'])
    except Refused as exc:return {'status':'refused','state':committed,'outputs':[],'events':[],'reason':str(exc),'steps':steps}
    if events:return {'status':'pending_host','state':committed,'proposed_state':state,'outputs':[],'events':events,'steps':steps}
    return {'status':'complete','state':state,'outputs':[state[i] for i in p['outputs']],'events':[],'steps':steps}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('document',type=Path)
    parser.add_argument('--inputs',default='[]',help='JSON array of typed live input values')
    args=parser.parse_args()
    result=run(json.loads(args.document.read_text()),json.loads(args.inputs))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(2 if result['status']=='refused' else 0)
