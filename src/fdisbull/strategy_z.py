"""Parameterized strategy-game observations and guarded Z action plans.

This consumes caller-supplied public witnesses. It does not read game memory,
invent game rules, dispatch native input or certify the witness's truth.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def screen_catalog():
    return json.loads((Path(__file__).parent/'data/civd-z-screen-families.json').read_text())


def _text(value, limit=4096):
    if not isinstance(value, str) or not value or len(value.encode()) > limit:
        raise ValueError('invalid strategy text/identifier')
    return value


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value)-set(required)-set(optional) or set(required)-set(value):
        raise ValueError('strategy record has missing/unknown fields')


def validate_witness(witness):
    if len(_encoded(witness)) > 65536:
        raise ValueError('strategy witness exceeds 64 KiB')
    _fields(witness, ('format','session','revision','complete','partial','views','title',
                      'description','facts','controls'))
    if witness['format']!='fdisbull-strategy-witness-1':
        raise ValueError('unknown strategy witness format')
    _text(witness['session'],128); _text(witness['title']); _text(witness['description'])
    if type(witness['revision']) is not int or witness['revision']<0:
        raise ValueError('invalid observation revision')
    if any(type(witness[k]) is not bool for k in ('complete','partial')):
        raise ValueError('recognition and coverage need explicit booleans')
    families = {f['id']:f for f in screen_catalog()['families']}
    if not isinstance(witness['views'],list) or not 1<=len(witness['views'])<=8:
        raise ValueError('strategy view stack needs 1..8 entries')
    for view in witness['views']:
        _fields(view, ('scene','parameters','instance'))
        if view['scene'] not in families:
            raise ValueError('unknown strategy scene family')
        family = families[view['scene']]
        if not isinstance(view['parameters'],dict) or set(view['parameters'])-set(family['parameters']):
            raise ValueError('scene parameters must match the family')
        if set(family['required_parameters'])-set(view['parameters']):
            raise ValueError('scene is missing required identity parameters')
        for value in view['parameters'].values():
            if type(value) is not int and not isinstance(value,str):
                raise ValueError('scene parameters need scalar identities')
            if isinstance(value,str): _text(value,160)
        _text(view['instance'],160)
    facts, controls = witness['facts'], witness['controls']
    if not isinstance(facts,list) or len(facts)>64 or not isinstance(controls,list) or len(controls)>128:
        raise ValueError('strategy observation needs bounded facts/controls')
    for fact in facts:
        _fields(fact, ('label','value'))
        _text(fact['label'],160); _text(fact['value'],1024)
    seen=set()
    for control in controls:
        _fields(control, ('id','label','aliases','description','visible','enabled','verb','intent','arguments'))
        for key in ('id','label','description','verb','intent'): _text(control[key])
        if control['id'] in seen:
            raise ValueError('duplicate strategy control identity')
        seen.add(control['id'])
        if not isinstance(control['aliases'],list) or len(control['aliases'])>16:
            raise ValueError('control aliases need a bounded list')
        for value in control['aliases']: _text(value,160)
        if any(v is not None and type(v) is not bool for v in (control['visible'],control['enabled'])):
            raise ValueError('control visibility/readiness need true/false/unknown')
        if (control['visible'] is None or control['enabled'] is None) and not witness['partial']:
            raise ValueError('unknown controls require partial coverage')
        if control['intent'] not in families[witness['views'][-1]['scene']]['actions']:
            raise ValueError('control intent is absent from the active scene family')
        if (not isinstance(control['arguments'],dict) or len(control['arguments'])>8
                or any(not isinstance(k,str) or type(v) not in (str,int,bool)
                       for k,v in control['arguments'].items())):
            raise ValueError('action arguments must be bounded logical scalars')
        if any(len(str(v))>160 for v in control['arguments'].values()):
            raise ValueError('action argument exceeds its identity budget')
    return witness


def project_observation(witness):
    """One scene type across every selected city; stack/parameters bind freshness."""
    validate_witness(witness)
    objects=[]
    for control in witness['controls']:
        if control['visible'] is not True:
            continue
        objects.append({k:deepcopy(control[k]) for k in ('id','label','aliases','description')} |
                       {'verbs':[control['verb']] if control['enabled'] is True else []})
    current=witness['views'][-1]
    text=witness['description']+'\n'+'\n'.join(f"{f['label']}: {f['value']}" for f in witness['facts'])
    # Token observes only the active public projection plus its source binding,
    # session and complete parent stack. Hidden row data never enters a token.
    visible_bindings=[{k:c[k] for k in ('id','intent','arguments','enabled')}
                      for c in witness['controls'] if c['visible'] is True]
    identity=dict(session=witness['session'],revision=witness['revision'],views=witness['views'],
                  objects=objects,title=witness['title'],description=text,bindings=visible_bindings,
                  complete=witness['complete'],partial=witness['partial'])
    token=hashlib.sha256(_encoded(identity)).hexdigest()
    return dict(complete=witness['complete'],coverage={'partial':witness['partial']},
                session_token=witness['session'],context=dict(id=current['scene'],token=token,
                    title=witness['title'],description=text.rstrip()),objects=objects,inventory=[])


def plan_action(witness, request):
    """Validate exact observed targets; return an unexecuted logical intent."""
    observation=project_observation(witness)
    _fields(request, ('context_token','verb','target'), ('item',))
    if request.get('item') is not None:
        raise ValueError('strategy control does not admit an implicit inventory item')
    if (not observation['complete']
            or request['context_token']!=observation['context']['token']):
        raise ValueError('stale or incomplete strategy observation')
    selected=[c for c in witness['controls'] if c['id']==request['target']
              and c['visible'] is True and c['enabled'] is True and c['verb']==request['verb']]
    if len(selected)!=1:
        raise ValueError('strategy target is hidden, unknown, disabled or unsupported')
    control=selected[0]
    return dict(format='fdisbull-strategy-action-plan-1',status='pending_adapter',
                native_dispatched=False,session=witness['session'],revision=witness['revision'],
                observation_token=request['context_token'],view=deepcopy(witness['views'][-1]),
                intent=control['intent'],arguments=deepcopy(control['arguments']),
                scope='unexecuted logical plan; a qualified native adapter must verify consumption and effects')


class WitnessBackend:
    """Read/plan-only Z service for reviewing a supplied observation."""
    def __init__(self,witness):
        self.witness=deepcopy(validate_witness(witness)); self.plans=[]

    def observe(self):
        return project_observation(self.witness)

    def act(self,request):
        try:
            plan=plan_action(self.witness,request)
        except ValueError as exc:
            return dict(status='rejected',complete=True,message=str(exc),effects='none-confirmed')
        self.plans.append(plan)
        return dict(status='incomplete',complete=False,effects='none-confirmed',plan=plan,
                    message='Control planned. No native action was sent; a qualified game adapter is required.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--witness',required=True,type=Path)
    args=parser.parse_args(argv)
    if args.witness.stat().st_size>65536:
        raise ValueError('strategy witness exceeds 64 KiB')
    backend=WitnessBackend(json.loads(args.witness.read_text()))
    while True:
        line=sys.stdin.buffer.readline(65538)
        if not line: break
        if len(line)>65536 or not line.endswith(b'\n'):
            raise ValueError('strategy request exceeds bounded line protocol')
        try:
            request=json.loads(line)
            if not isinstance(request,dict):
                raise ValueError('strategy request must be an object')
            if request.get('op')=='observe':
                _fields(request,('op',))
                result=backend.observe()
            elif request.get('op')=='act':
                _fields(request,('op','action'))
                result=backend.act(request['action'])
            else:
                result=dict(status='rejected',complete=True,message='Read/plan-only service; persistence is unsupported.')
        except (ValueError,KeyError,TypeError) as exc:
            result=dict(status='rejected',complete=True,message=str(exc))
        sys.stdout.write(json.dumps(result,separators=(',',':'))+'\n'); sys.stdout.flush()


if __name__=='__main__':
    main()
