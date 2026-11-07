"""Authored DOS/BIOS API facts, separate from native instruction facts.

Descriptions are documented contracts, not evidence that a call succeeded.
No service-specific register preservation is assumed by the static solver.
"""
from __future__ import annotations

from copy import deepcopy

DOS_REFERENCE = 'https://www.pcjs.org/documents/books/mspl13/msdos/encyclopedia/section5/'
BIOS_REFERENCE = 'https://www.pcjs.org/documents/manuals/ibm/pc/techref/'


def _entry(name, inputs, outputs, *, buffer=None, terminates=False):
    return dict(name=name, inputs=inputs, outputs=outputs, buffer=buffer, terminates=terminates)


_DOS = {
    0x00: _entry('terminate', {}, {}, terminates=True),
    0x02: _entry('character_output', {'dl': 'character'}, {}),
    0x09: _entry('string_output', {'ds:dx': 'dollar_terminated_string'}, {}, buffer=('read','ds','dx',None,'dollar_terminated')),
    0x1a: _entry('set_dta', {'ds:dx': 'disk_transfer_area'}, {}),
    0x25: _entry('set_interrupt_vector', {'al': 'vector', 'ds:dx': 'handler'}, {}),
    0x2a: _entry('get_date', {}, {'cx': 'year','dh': 'month','dl': 'day','al': 'weekday'}),
    0x2b: _entry('set_date', {'cx': 'year', 'dh': 'month', 'dl': 'day'}, {'al': '00h=success, FFh=invalid date'}),
    0x2c: _entry('get_time', {}, {'ch':'hour','cl':'minute','dh':'second','dl':'hundredths'}),
    0x2f: _entry('get_dta', {}, {'es:bx':'disk_transfer_area'}),
    0x30: _entry('get_version', {}, {'al':'major','ah':'minor','bx':'version_specific','cx':'version_specific'}),
    0x31: _entry('terminate_resident', {'al':'exit_code','dx':'retained_paragraphs'}, {}, terminates=True),
    0x35: _entry('get_interrupt_vector', {'al':'vector'}, {'es:bx':'handler'}),
    0x3c: _entry('create_file', {'ds:dx':'path','cx':'attributes'}, {'ax':'handle_or_error','cf':'error_if_set'}, buffer=('read','ds','dx',None,'nul_terminated')),
    0x3d: _entry('open_file', {'ds:dx':'path','al':'access_and_sharing'}, {'ax':'handle_or_error','cf':'error_if_set'}, buffer=('read','ds','dx',None,'nul_terminated')),
    0x3e: _entry('close_file', {'bx':'handle'}, {'ax':'error_if_carry','cf':'error_if_set'}),
    0x3f: _entry('read_file', {'bx':'handle','cx':'requested_bytes','ds:dx':'buffer'}, {'ax':'actual_bytes_or_error','cf':'error_if_set'}, buffer=('write','ds','dx','cx','upper_bound_on_success')),
    0x40: _entry('write_file', {'bx':'handle','cx':'requested_bytes','ds:dx':'buffer'}, {'ax':'actual_bytes_or_error','cf':'error_if_set'}, buffer=('read','ds','dx','cx','requested_buffer')),
    0x41: _entry('delete_file', {'ds:dx':'path'}, {'ax':'error_if_carry','cf':'error_if_set'}, buffer=('read','ds','dx',None,'nul_terminated')),
    0x42: _entry('seek_file', {'bx':'handle','al':'origin','cx:dx':'signed_offset'}, {'dx:ax':'position_on_success','ax':'error_if_carry','cf':'error_if_set'}),
    0x43: _entry('file_attributes', {'al':'subfunction','ds:dx':'path','cx':'attributes_for_set'}, {'cx':'attributes_for_get','ax':'error_if_carry','cf':'error_if_set'}, buffer=('read','ds','dx',None,'nul_terminated')),
    0x48: _entry('allocate_memory', {'bx':'paragraphs'}, {'ax':'segment_or_error','bx':'largest_block_on_failure','cf':'error_if_set'}),
    0x49: _entry('free_memory', {'es':'block_segment'}, {'ax':'error_if_carry','cf':'error_if_set'}),
    0x4a: _entry('resize_memory', {'es':'block_segment','bx':'paragraphs'}, {'ax':'error_if_carry','bx':'available_on_failure','cf':'error_if_set'}),
    0x4b: _entry('execute_program', {'al':'subfunction','ds:dx':'path','es:bx':'parameter_block'}, {'ax':'error_if_carry','cf':'error_if_set'}, buffer=('read','ds','dx',None,'nul_terminated')),
    0x4c: _entry('exit', {'al':'exit_code'}, {}, terminates=True),
    0x4d: _entry('child_exit_status', {}, {'al':'exit_code','ah':'termination_kind'}),
    0x4e: _entry('find_first', {'ds:dx':'pattern','cx':'attributes'}, {'ax':'error_if_carry','cf':'error_if_set'}, buffer=('read','ds','dx',None,'nul_terminated')),
    0x4f: _entry('find_next', {}, {'ax':'error_if_carry','cf':'error_if_set'}),
}
_BIOS = {
    (0x10,0x00): _entry('set_video_mode', {'al':'mode'}, {}),
    (0x10,0x02): _entry('set_cursor', {'bh':'page','dh':'row','dl':'column'}, {}),
    (0x10,0x03): _entry('get_cursor', {'bh':'page'}, {'dh':'row','dl':'column','ch':'cursor_start','cl':'cursor_end'}),
    (0x10,0x0e): _entry('teletype_output', {'al':'character','bh':'page','bl':'graphics_color'}, {}),
    (0x10,0x0f): _entry('get_video_mode', {}, {'al':'mode','ah':'columns','bh':'page'}),
    (0x16,0x00): _entry('read_key', {}, {'al':'character','ah':'scan_code'}),
    (0x16,0x01): _entry('check_key', {}, {'zf':'no_key_if_set','al':'character_if_available','ah':'scan_code_if_available'}),
    (0x16,0x02): _entry('keyboard_flags', {}, {'al':'shift_flags'}),
    (0x1a,0x00): _entry('read_clock_ticks', {}, {'cx:dx':'ticks_since_midnight','al':'midnight_indicator'}),
}


def _register(name, registers):
    if ':' in name:
        values=[_register(part,registers) for part in name.split(':')]
        return values
    value=registers.get(name)
    if type(value) is int:return value
    if len(name)==2 and name[0] in 'abcd' and name[1] in 'hl':
        value=registers.get(name[0]+'x')
        if type(value) is int:return (value>>(8 if name[1]=='h' else 0))&255
    return None


def describe_interrupt(vector, registers=None):
    """Describe only a known selector; ambiguous/missing selectors stay unknown."""
    registers=registers or {}
    from .desqview import describe_interrupt as describe_desqview
    desqview = describe_desqview(vector, registers)
    if desqview is not None:
        return desqview
    if vector==0x66:
        from .audio_services import DIGPAK, MIDPAK, REFERENCE, SAMPLE_DESCRIPTOR
        function=_register('ax',registers)
        if function is None:
            hi,lo=_register('ah',registers),_register('al',registers)
            if type(hi) is int and type(lo) is int and 0<=hi<=255 and 0<=lo<=255:
                function=hi*256+lo
        family='digpak' if function in DIGPAK else 'midpak' if function in MIDPAK else 'audio_multiplex'
        contract=DIGPAK.get(function) or MIDPAK.get(function)
        result=dict(vector='0x66',function=hex(function) if type(function) is int else None,
            family=family,known=contract is not None,name=contract[0] if contract else None,
            source=REFERENCE+(f'66{function:04x}.html' if contract else 'index.html'),
            evidence='documented API selected by pre-instruction register facts; candidate handler contract',
            runtime_observed=False,handler_verified=False,outcome='unknown',terminates=False,
            inputs={},outputs={},memory_effects=[],memory_effects_complete=False,
            contract_details='documented subset; unspecified registers remain unmodeled',
            assumptions=['INT66 implements DIGPAK/MIDPAK; custom handlers can use the same vector and selectors.',
                'Installed driver/version and capability support must be verified separately.',
                'A service name does not establish execution, success, playback or completion.'])
        if contract:
            if function==0x692:
                result['source']='https://github.com/jratcliff63367/digpak/blob/master/SHELL.ASM'
            result['inputs']={r:dict(role=role,value=_register(r,registers)) for r,role in contract[1].items()}
            result['outputs']=dict(contract[2])
            if function in (0x688,0x68a,0x68b,0x694,0x695):
                result['argument_layouts']={'ds:si':deepcopy(SAMPLE_DESCRIPTOR)}
            if function in (0x688,0x68b,0x694,0x695,0x702,0x703,0x70b):
                result['completion_evidence']='Bound request/return plus matching playback state or callback; filename reads alone are insufficient.'
        else:
            result['reason']='unknown, ambiguous or unimplemented full AX selector'
        return result
    function=_register('ah',registers)
    entry=_DOS.get(function) if vector==0x21 else _BIOS.get((vector,function))
    family='dos' if vector in (0x20,0x21) else 'bios' if vector in (0x10,0x16,0x1a) else None
    if family is None:return None
    if vector==0x20:entry=_entry('terminate',{}, {},terminates=True);function=None
    result=dict(vector=hex(vector),function=hex(function) if type(function) is int else None,
                family=family,known=entry is not None,source=DOS_REFERENCE if family=='dos' else BIOS_REFERENCE,
                evidence='documented API selected by stored pre-instruction register facts',
                runtime_observed=False,assumptions=['Original DOS/BIOS interrupt handler implements this API; custom handlers may differ.'])
    if entry is None:
        return dict(result,name=None,reason='unknown selector or unimplemented service',inputs={},outputs={},memory_effects=[])
    result.update(name=entry['name'],terminates=entry['terminates'],
        inputs={register:dict(role=role,value=_register(register,registers)) for register,role in entry['inputs'].items()},
        outputs=dict(entry['outputs']),memory_effects=[])
    if entry['buffer']:
        access,segment,offset,length,extent=entry['buffer']
        seg,off=_register(segment,registers),_register(offset,registers)
        address=seg*16+off if type(seg) is int and type(off) is int and seg*16+off<0x100000 else None
        result['memory_effects'].append(dict(access=access,pointer=f'{segment}:{offset}',address=hex(address) if address is not None else None,
            length=_register(length,registers) if length else None,extent=extent,
            actual_transfer='unknown until return status and actual byte count are observed'))
    return result


def service_catalog():
    entries=[describe_interrupt(0x21,{'ah':function}) for function in _DOS]
    entries.extend(describe_interrupt(vector,{'ah':function}) for vector,function in _BIOS)
    entries.append(describe_interrupt(0x20))
    from .audio_services import DIGPAK, MIDPAK
    entries.extend(describe_interrupt(0x66,{'ax':function}) for function in (*DIGPAK,*MIDPAK))
    from .desqview import service_catalog as desqview_catalog
    entries.extend(desqview_catalog())
    return dict(format='fdisbull-dos-services-1',entries=deepcopy(entries),
                scope='Explicit DOS/BIOS/DIGPAK/MIDPAK/DESQview documented subset; no automatic interrupt-handler verification')
