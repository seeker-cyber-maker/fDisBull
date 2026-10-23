"""Explicit edits to an isolated, stopped native checkpoint before recapture."""
from __future__ import annotations

import base64
import re

REGISTERS = {'eax','ebx','ecx','edx','esi','edi','ebp','esp','eip','cs','ds','es','ss','fs','gs','flags'}


def integer(value):
    if isinstance(value,str) and re.fullmatch(r'0x[0-9a-fA-F]{1,8}',value):
        return int(value,16)
    if type(value) is int and 0 <= value <= 0xffffffff:
        return value
    raise ValueError('Register values must be unsigned integers or explicit 0x hex strings')


def byte_string(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}){1,65536}',value):
        raise ValueError('Memory edits require nonempty hex bytes, at most 65536 bytes')
    return bytes.fromhex(value)


def validate_edits(memory, registers):
    total = 0
    for edit in memory:
        if not isinstance(edit,dict) or set(edit) not in ({'address','expected_hex','data_hex'},{'address','cs','expected_hex','data_hex'}):
            raise ValueError('Memory edit requires address, expected_hex, data_hex, and optional cs')
        before = byte_string(edit['expected_hex']); after = byte_string(edit['data_hex'])
        if len(before)!=len(after):
            raise ValueError('A state memory edit cannot resize memory')
        total += len(before)
    if total>65536:
        raise ValueError('Combined state memory edits exceed 65536 bytes')
    for name, change in registers.items():
        if name not in REGISTERS or not isinstance(change,dict) or set(change)!={'expected','value'}:
            raise ValueError('Register edit requires a supported lowercase name and expected/value')
        limit = 0xffff if name in ('eip','cs','ds','es','ss','fs','gs','flags') else 0xffffffff
        if integer(change['expected'])>limit or integer(change['value'])>limit:
            raise ValueError('Register edit exceeds real-mode width')


def register_value(snapshot,name):
    if name in snapshot['general']:
        return int(snapshot['general'][name],16)
    if name in snapshot['segments']:
        return int(snapshot['segments'][name],16)
    return int(snapshot['instruction_pointer' if name=='eip' else 'flags'],16)


def apply_edits(debug, memory, registers):
    # Preflight the entire edit set before any mutation; overlap makes provenance ambiguous.
    if registers and not debug.rpc.capabilities.get('register_edit'):
        raise ValueError('Backend lacks structured register editing')
    plans = []; ranges = []
    for edit in memory:
        address, _ = debug.project._dos_parse_address(edit['address'],edit.get('cs'))
        data = byte_string(edit['data_hex']); expected = byte_string(edit['expected_hex'])
        end = address+len(data)
        if any(address < hi and lo < end for lo,hi in ranges):
            raise ValueError('State memory edit ranges overlap')
        ranges.append((address,end))
        observed = debug.memory(edit['address'],cs=edit.get('cs'),length=len(data))
        if observed['hex']!=expected.hex():
            raise ValueError('State memory edit expected bytes mismatch at '+hex(address))
        plans.append((address,observed,data))
    snapshot = debug.registers()
    if snapshot['cpu_mode']!='real':
        raise ValueError('State editing currently requires real mode')
    for name,change in registers.items():
        if register_value(snapshot,name)!=integer(change['expected']):
            raise ValueError('State register edit expected value mismatch: '+name)
    evidence = {'memory':[],'registers':[]}
    for address,observed,data in plans:
        debug.call('memory.write',{'address':observed['address'],'expected_sha256':observed['sha256'],
                                  'data_base64':base64.b64encode(data).decode()})
        actual = debug.memory(hex(address),length=len(data))
        if actual['hex']!=data.hex():
            raise ValueError('State memory edit readback mismatch')
        evidence['memory'].append({'project_address':hex(address),'before_hex':observed['hex'],
                                   'after_hex':actual['hex'],'verified':True})
    for name,change in registers.items():
        debug.call('state.set_register',{'register':name.upper(),'value':integer(change['value'])})
        actual = register_value(debug.registers(),name)
        if actual!=integer(change['value']):
            raise ValueError('State register edit readback mismatch: '+name)
        evidence['registers'].append({'register':name,'before':hex(integer(change['expected'])),
                                      'after':hex(actual),'verified':True})
    debug._event('state-edits',evidence)
    return evidence
