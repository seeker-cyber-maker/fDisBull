"""Bounded first-divergence reporting with explicit missing-value semantics."""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from .model import Refused


@dataclass(frozen=True)
class Difference:
    event: int
    field: str
    expected_present: bool
    actual_present: bool
    expected: object
    actual: object
    reason: str


def first_difference(expected:Iterable[Mapping],actual:Iterable[Mapping],
                     fields:tuple[str,...],max_events:int=10000)->Difference|None:
    """Compare exact ordered observations; do not align away missing events.

    None means equal only within complete input streams and the selected fields.
    Reaching the event budget with remaining data refuses rather than passing.
    """
    if not fields or len(set(fields))!=len(fields) or any(not isinstance(x,str) for x in fields):
        raise Refused('unique named observation fields are required')
    if type(max_events)is not int or max_events<0:
        raise Refused('invalid comparison budget')
    left,right=iter(expected),iter(actual)
    missing=object()
    for index in range(max_events+1):
        a=next(left,missing);b=next(right,missing)
        if a is missing and b is missing:return None
        if index==max_events:raise Refused('observation budget exhausted before both streams ended')
        if a is missing or b is missing:
            return Difference(index,'<event>',a is not missing,b is not missing,
                              None if a is missing else a,None if b is missing else b,'event count')
        if not isinstance(a,Mapping) or not isinstance(b,Mapping):
            raise Refused('observation must be a mapping')
        for field in fields:
            av=a.get(field,missing);bv=b.get(field,missing)
            if av is missing or bv is missing:
                return Difference(index,field,av is not missing,bv is not missing,
                                  None if av is missing else av,None if bv is missing else bv,'missing observation')
            if type(av)!=type(bv) or av!=bv:
                return Difference(index,field,True,True,av,bv,'type or value')
    raise AssertionError('unreachable')
