"""Owned native windows/input around the common indexed UIL arena ABI.

Adapters contain platform services, never game rules. Source emission, building,
sealing, original correspondence and window/input qualification are separate.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import math
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import struct
import subprocess

from .common_uil import canonical_bytes, digest, validate_realization
from .uil_native import _private, _regular, _write_new, _sha, _FLAGS

FORMAT = 'fdisbull-common-uil-desktop-1'
PLAN = 'fdisbull-common-uil-desktop-plan-1'
_METADATA_LIMIT = 16 * 1024 * 1024
_ARTIFACT_LIMIT = 128 * 1024 * 1024
TARGETS = {
    'macos-arm64': {'compiler':'clang','flags':['--target=arm64-apple-macos13.0'],
                    'adapter':'memory-appkit.m','application':'CommonUIL.app/Contents/MacOS/program',
                    'library':'memory-runtime.dylib','probe':'probe','system':'AppKit','max_functions':64},
    'linux-x64': {'compiler':'gcc','flags':[],'adapter':'memory-x11.c',
                  'application':'program','library':'memory-runtime.so','probe':'probe','system':'X11','max_functions':32},
    'windows-x64': {'compiler':'x86_64-w64-mingw32-gcc','flags':[],
                    'adapter':'memory-win32.c','application':'program.exe',
                    'library':'memory-runtime.dll','probe':'probe.exe','system':'Win32','max_functions':16},
}
RUNTIME_HEADER = '''#ifndef FDISBULL_MEMORY_RUNTIME_1
#define FDISBULL_MEMORY_RUNTIME_1
#include <stddef.h>
#include <stdint.h>
size_t fdb_word_count(void);
const uint32_t *fdb_words(void);
int fdb_copy_words(uint32_t *,size_t);
int fdb_function_index(const char *);
int fdb_call(size_t,const uint32_t *,const uint32_t *,size_t,int);
int fdb_dispatch(const uint32_t *,const uint32_t *,size_t,int);
int fdb_initialize(uint32_t);
int fdb_select_region(size_t,size_t);
int fdb_selected_region(size_t);
int fdb_replace_words(const uint32_t *,size_t);
uint64_t fdb_revision(void);
uint64_t fdb_invocation_count(size_t);
uint64_t fdb_region_invocation_count(size_t,size_t);
uint64_t fdb_arithmetic_invocation_count(size_t,size_t,size_t);
uint32_t fdb_last_steps(void);
const char *fdb_last_error(void);
const char *fdb_config_sha256(void);
void fdb_close(void);
int fdb_closed(void);
#endif
'''


def _host_bytes(document):
    """Finite host metadata permits fractional clock periods; UIL stays integer."""
    stack=[(document,0)];count=0
    while stack:
        value,depth=stack.pop();count+=1
        if count>1000000 or depth>80:raise ValueError('desktop metadata node/depth budget exceeded')
        if type(value) is dict:
            if any(type(k) is not str for k in value):raise ValueError('desktop metadata keys must be strings')
            stack.extend((v,depth+1) for v in value.values())
        elif type(value) is list:stack.extend((v,depth+1) for v in value)
        elif type(value) is float:
            if not math.isfinite(value):raise ValueError('desktop metadata must be finite')
        elif value is not None and type(value) not in (str,bool,int):raise ValueError('invalid desktop metadata value')
        elif type(value) is int and abs(value)>(1<<64):raise ValueError('desktop metadata integer exceeds bounds')
    try:raw=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf8')
    except (ValueError,TypeError,RecursionError,UnicodeError) as e:raise ValueError('invalid desktop metadata JSON') from e
    if len(raw)>16*1024*1024:raise ValueError('desktop metadata byte budget exceeded')
    return raw


def _host_digest(document):
    return hashlib.sha256(_host_bytes(document)).hexdigest()


def _seal_desktop_document(document):
    document=deepcopy(document);document.pop('realization_sha256',None)
    document['realization_sha256']=_host_digest(document);return document


def _bounded_bytes(path, limit, label):
    path = Path(path)
    try:
        before = path.stat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise ValueError('desktop ' + label + ' must be a regular file')
        if before.st_size > limit:
            raise ValueError('desktop ' + label + ' byte budget exceeded')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, 'rb') as stream:
            current = os.fstat(stream.fileno())
            if (not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)):
                raise ValueError('desktop ' + label + ' file identity changed')
            if current.st_size > limit:
                raise ValueError('desktop ' + label + ' byte budget exceeded')
            raw = stream.read(limit + 1)
    except OSError as error:
        raise ValueError('desktop ' + label + ' regular file unavailable') from error
    if len(raw) > limit:
        raise ValueError('desktop ' + label + ' byte budget exceeded')
    return raw


def _owned_regular(root, name):
    path = root / name
    try:
        if not path.is_relative_to(root) or path.parent.resolve(strict=True) != path.parent:
            raise ValueError('desktop source/artifact ancestor containment differs')
    except (OSError, RuntimeError) as error:
        raise ValueError('desktop source/artifact ancestor containment differs') from error
    return _regular(path)


def load_desktop_json(path):
    raw=_bounded_bytes(path, _METADATA_LIMIT, 'metadata')
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('duplicate desktop JSON key')
            out[k]=v
        return out
    result=json.loads(raw,object_pairs_hook=pairs);_host_bytes(result);return result


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('invalid desktop ' + label)
    return value


def _text(value, limit, label):
    if type(value) is not str or not value or len(value) > limit or '\0' in value:
        raise ValueError('invalid desktop ' + label)
    return value


def _ranges(values, words):
    if type(values) is not list or not 1 <= len(values) <= 128:
        raise ValueError('nonempty bounded desktop ranges required')
    selected = set()
    for pair in values:
        if type(pair) is not list or len(pair) != 2:
            raise ValueError('invalid desktop range')
        start = _integer(pair[0], 0, words-1, 'range start')
        count = _integer(pair[1], 1, words-start, 'range count')
        cells = set(range(start, start+count))
        if cells & selected:
            raise ValueError('overlapping desktop ranges')
        selected |= cells
    return selected


def validate_desktop_plan(plan, program):
    """Validate the numeric UIL bindings and declared host memory footprints."""
    required = {'format','title','help','function_names','initialize','inputs','outputs',
                'commit_ranges','replace_ranges','scratch_ranges','guards','array_guards',
                'render','frame','events','keymap'}
    if type(plan) is not dict or set(plan) != required or plan['format'] != PLAN:
        raise ValueError('invalid common UIL desktop plan')
    count = len(program['functions'])
    if not 1 <= count <= 64:
        raise ValueError('desktop function budget exceeded')
    entry = program['functions'][program['entry']]
    ports = [entry['variables'][i] for i in entry['inputs']]
    if len(ports) != 1 or ports[0]['type'] != 'u32-array':
        raise ValueError('desktop requires one u32 array entry')
    words = _integer(ports[0]['length'], 1, 1048576, 'arena length')
    for fn in program['functions']:
        for side in ('inputs','outputs'):
            if [fn['variables'][i] for i in fn[side]] != ports:
                raise ValueError('every desktop function needs the same arena interface')
    _text(plan['title'],100,'title'); _text(plan['help'],2048,'help')
    names = plan['function_names']
    if type(names) is not list or len(names) != count or len(set(names)) != count:
        raise ValueError('desktop function names must be unique and complete')
    for name in names:
        _text(name,64,'function name')
    fn_index = lambda i: _integer(i,0,count-1,'function index')
    index = lambda i: _integer(i,0,words-1,'word index')
    fn_index(plan['initialize'])
    if type(plan['inputs']) is not list or len(plan['inputs']) > 256:
        raise ValueError('invalid desktop input indices')
    for i in plan['inputs']: index(i)
    if len(set(plan['inputs'])) != len(plan['inputs']):
        raise ValueError('duplicate desktop input index')
    committed = _ranges(plan['commit_ranges'],words)
    replacement = _ranges(plan['replace_ranges'],words)
    scratch = _ranges(plan['scratch_ranges'],words)
    if not replacement <= committed or committed & scratch or set(plan['inputs']) & (committed | scratch):
        raise ValueError('desktop inputs, commits and scratch overlap')
    if type(plan['outputs']) is not dict or set(plan['outputs']) != {str(i) for i in range(count)}:
        raise ValueError('each desktop function needs an output footprint')
    for ranges in plan['outputs'].values():
        if not _ranges(ranges,words) <= committed | scratch:
            raise ValueError('desktop output outside commit/scratch ranges')
    if type(plan['guards']) is not list or len(plan['guards']) > 1024:
        raise ValueError('invalid desktop guards')
    for guard in plan['guards']:
        if type(guard) is not dict or set(guard) != {'index','min','max'}:
            raise ValueError('invalid desktop guard')
        index(guard['index']); _integer(guard['min'],0,0xffffffff,'guard minimum')
        _integer(guard['max'],guard['min'],0xffffffff,'guard maximum')
    if type(plan['array_guards']) is not list or len(plan['array_guards']) > 32:
        raise ValueError('invalid desktop array guards')
    for guard in plan['array_guards']:
        if type(guard) is not dict or set(guard) != {'offset','length_index','capacity','min','max','unique','adjacent_columns','exclude'}:
            raise ValueError('invalid desktop array guard')
        index(guard['offset']); index(guard['length_index'])
        _integer(guard['capacity'],1,words-guard['offset'],'array capacity')
        _integer(guard['min'],0,0xffffffff,'array minimum')
        _integer(guard['max'],guard['min'],0xffffffff,'array maximum')
        _integer(guard['adjacent_columns'],1,1024,'array columns')
        if type(guard['unique']) is not bool:
            raise ValueError('invalid desktop uniqueness guard')
        e = guard['exclude']
        if type(e) is not dict or set(e) != {'index','when_index','when_value'}:
            raise ValueError('invalid desktop exclusion guard')
        index(e['index']); index(e['when_index'])
        _integer(e['when_value'],0,0xffffffff,'exclusion value')
    render = plan['render']
    if type(render) is not dict or set(render) != {'function','when_nonzero'}:
        raise ValueError('invalid desktop render binding')
    fn_index(render['function']); index(render['when_nonzero'])
    frame = plan['frame']
    if type(frame) is not dict or set(frame) != {'offset','width','height','palette'}:
        raise ValueError('invalid desktop frame')
    width = _integer(frame['width'],1,1024,'frame width')
    height = _integer(frame['height'],1,1024,'frame height')
    offset = _integer(frame['offset'],0,words-width*height,'frame offset')
    if not set(range(offset,offset+width*height)) <= committed:
        raise ValueError('desktop frame must be committed output')
    palette = frame['palette']
    if type(palette) is not dict or '0' not in palette or len(palette) > 256:
        raise ValueError('invalid desktop palette')
    for key,rgb in palette.items():
        if type(key) is not str or not key.isdigit() or str(int(key)) != key or not 0 <= int(key) <= 255:
            raise ValueError('invalid desktop palette index')
        if type(rgb) is not list or len(rgb) != 3:
            raise ValueError('invalid desktop palette color')
        for channel in rgb: _integer(channel,0,255,'palette channel')
    events = plan['events']
    if type(events) is not dict or set(events) != {'function','kind','ascii','scan','x','y','buttons','clock','quit_index','keyboard_kind','pointer_kind','clock_kind','tick_ms'}:
        raise ValueError('invalid desktop event binding')
    fn_index(events['function']); index(events['quit_index'])
    cells = [events[k] for k in ('kind','ascii','scan','x','y','buttons','clock')]
    for cell in cells: index(cell)
    if len(set(cells)) != 7 or not set(cells) <= set(plan['inputs']):
        raise ValueError('desktop event fields must be distinct admitted inputs')
    kinds = [events[k] for k in ('keyboard_kind','pointer_kind','clock_kind')]
    for kind in kinds: _integer(kind,0,0xffffffff,'event kind')
    if len(set(kinds)) != 3 or type(events['tick_ms']) not in (int,float) or not math.isfinite(events['tick_ms']) or not 1 <= events['tick_ms'] <= 1000:
        raise ValueError('invalid desktop clock/kind profile')
    if type(plan['keymap']) is not dict or not 1 <= len(plan['keymap']) <= 256:
        raise ValueError('invalid desktop key map')
    for code,binding in plan['keymap'].items():
        _text(code,64,'physical key')
        if not re.fullmatch('[A-Za-z0-9]+',code) or type(binding) is not dict or set(binding) != {'ascii','scan'}:
            raise ValueError('invalid desktop physical key binding')
        for v in binding.values(): _integer(v,0,255,'key byte')
    return deepcopy(plan), words


def validate_desktop_arena(plan, words):
    for guard in plan['guards']:
        if not guard['min'] <= words[guard['index']] <= guard['max']:
            raise ValueError('desktop arena fails state guard')
    for g in plan['array_guards']:
        n = words[g['length_index']]
        if n > g['capacity']:
            raise ValueError('desktop array exceeds capacity')
        values = words[g['offset']:g['offset']+n]
        if any(not g['min'] <= x <= g['max'] for x in values) or g['unique'] and len(set(values)) != n:
            raise ValueError('desktop array domain/uniqueness refused')
        col = g['adjacent_columns']
        if any(not (abs(a-b) == col or abs(a-b) == 1 and a//col == b//col) for a,b in zip(values,values[1:])):
            raise ValueError('desktop array adjacency refused')
        e = g['exclude']; x = words[e['index']]
        if words[e['when_index']] == e['when_value'] and (not g['min'] <= x <= g['max'] or x in values):
            raise ValueError('desktop array exclusion refused')
    frame = plan['frame']
    if any(str(x) not in frame['palette'] for x in words[frame['offset']:frame['offset']+frame['width']*frame['height']]):
        raise ValueError('desktop frame palette refused')


def _cstr(text):
    return '"'+''.join(chr(b) if 32 <= b < 127 and b not in (34,92) else '\\%03o' % b for b in text.encode('utf8'))+'"'


def _cranges(name, values):
    return 'static const FdbRange '+name+'[]={'+','.join('{%du,%du}' % tuple(v) for v in values)+'};'


def _runtime(plan, initial, controls, variants, config_sha, target, emitted):
    n = len(plan['function_names']); words = len(initial); nv = len(variants)
    owner = ['#include <pthread.h>','static pthread_t owner;__attribute__((constructor)) static void capture_owner(void){owner=pthread_self();}',
             'static int owner_thread(void){return pthread_equal(pthread_self(),owner);}']
    if target == 'windows-x64':
        owner = ['#include <windows.h>','static DWORD owner;__attribute__((constructor)) static void capture_owner(void){owner=GetCurrentThreadId();}',
                 'static int owner_thread(void){return GetCurrentThreadId()==owner;}']
    lines = ['#include "memory-runtime.h"','#include "native-core.h"','#include <stdlib.h>','#include <string.h>',*owner,
             'typedef struct{uint32_t start,count;}FdbRange;',f'enum{{N={words},NF={n},NV={nv}}};',
             'static uint32_t arena[N]={'+','.join(str(x)+'u' for x in initial)+'};',
             'static uint32_t choices[NF];static uint64_t revision,epoch,calls[NF],variant_calls[NF][NV],arithmetic_calls[NF][NV][6];',
             'static int closed,busy;static uint32_t last_steps;static _Thread_local const char *error="";',
             'static const char *names[]={'+','.join(_cstr(x) for x in plan['function_names'])+'};',
             'static int fail(const char *text){error=text;return 1;}',
             'static int admit(void){if(!owner_thread()){return fail("Owner thread required");}if(closed){return fail("Shell closed");}if(busy){return fail("Reentrant operation");}return 0;}',
             'static int inside(uint32_t i,const FdbRange*r,size_t n){for(size_t j=0;j<n;j++){if(i>=r[j].start&&i-r[j].start<r[j].count){return 1;}}return 0;}',
             'static int compare_words(const void*a,const void*b){uint32_t x=*(const uint32_t*)a,y=*(const uint32_t*)b;return(x>y)-(x<y);}',
             _cranges('commits',plan['commit_ranges']),_cranges('replacements',plan['replace_ranges']),
             'static const uint32_t input_indices[]={'+','.join(str(i)+'u' for i in plan['inputs'])+'};']
    for i in range(n): lines.append(_cranges('outputs_'+str(i),plan['outputs'][str(i)]))
    for v in range(nv):
        lines += [f'FdbBlockResult fdb_v{v}_function_block_limit(uint32_t,uint32_t*,uint32_t);',f'uint64_t fdb_v{v}_math_count(unsigned,unsigned);']
    lines += ['typedef FdbBlockResult(*Block)(uint32_t,uint32_t*,uint32_t);typedef uint64_t(*Count)(unsigned,unsigned);',
              'static Block blocks[]={'+','.join(f'fdb_v{v}_function_block_limit' for v in range(nv))+'};',
              'static Count counts[]={'+','.join(f'fdb_v{v}_math_count' for v in range(nv))+'};',
              'static int validate(const uint32_t*w){']
    for g in plan['guards']:
        if g['min']: lines.append(f'if(w[{g["index"]}]<{g["min"]}u){{return fail("State guard refused");}}')
        if g['max']<0xffffffff:lines.append(f'if(w[{g["index"]}]>{g["max"]}u){{return fail("State guard refused");}}')
    for g in plan['array_guards']:
        off=g['offset'];col=g['adjacent_columns'];e=g['exclude']
        lines += [f'{{uint32_t len=w[{g["length_index"]}];if(len>{g["capacity"]}u){{return fail("Array length refused");}}',
                  f'for(uint32_t i=0;i<len;i++){{uint32_t v=w[{off}u+i];']
        if g['min']:lines.append(f'if(v<{g["min"]}u){{return fail("Array domain refused");}}')
        if g['max']<0xffffffff:lines.append(f'if(v>{g["max"]}u){{return fail("Array domain refused");}}')
        lines += [f'if(i){{uint32_t p=w[{off}u+i-1],d=v>p?v-p:p-v;if(!(d=={col}u||(d==1u&&v/{col}u==p/{col}u))){{return fail("Array adjacency refused");}}}}}}']
        if g['unique']:
            lines += [f'uint32_t*copy=malloc((len?len:1u)*4u);if(!copy){{return fail("Allocation refused");}}memcpy(copy,w+{off}u,len*4u);qsort(copy,len,4,compare_words);',
                      'int duplicate=0;for(uint32_t i=1;i<len;i++){if(copy[i-1]==copy[i]){duplicate=1;}}free(copy);if(duplicate){return fail("Array uniqueness refused");}']
        lines.append(f'if(w[{e["when_index"]}]=={e["when_value"]}u){{uint32_t v=w[{e["index"]}];')
        if g['min']:lines.append(f'if(v<{g["min"]}u){{return fail("Excluded value refused");}}')
        if g['max']<0xffffffff:lines.append(f'if(v>{g["max"]}u){{return fail("Excluded value refused");}}')
        lines += [f'for(uint32_t i=0;i<len;i++){{if(w[{off}u+i]==v){{return fail("Excluded overlap refused");}}}}}}}}']
    frame=plan['frame']
    lines += ['{static const uint32_t colors[]={'+','.join(str(int(k))+'u' for k in frame['palette'])+'};',
              f'for(uint32_t i={frame["offset"]}u;i<{frame["offset"]+frame["width"]*frame["height"]}u;i++){{int found=0;for(size_t j=0;j<sizeof(colors)/4;j++){{if(w[i]==colors[j]){{found=1;}}}}if(!found){{return fail("Palette index refused");}}}}}}return 0;}}',
              'static FdbBlockResult run(uint32_t fn,uint32_t*w,const uint32_t*selected,uint32_t remaining){',
              'FdbBlockResult r={1u,0u,0u};if(fn>=NF||!remaining){return r;}uint32_t choice=selected[fn];if(choice>=NV||calls[fn]==UINT64_MAX||variant_calls[fn][choice]==UINT64_MAX){return r;}',
              'uint32_t*before=malloc(sizeof(arena));if(!before){return r;}memcpy(before,w,sizeof(arena));calls[fn]++;variant_calls[fn][choice]++;r=blocks[choice](fn,w,remaining);',
              'for(unsigned op=0;op<6;op++){uint64_t total=0;']
    for v, item in enumerate(emitted):
        lines.append(('if' if v==0 else 'else if')+f'(choice=={v}u){{for(unsigned m=0;m<{len(item["arithmetic_bindings"])//6}u;m++){{total+=counts[choice](m,op);}}}}')
    lines += ['if(total>UINT64_MAX-arithmetic_calls[fn][choice][op]){r.status=1u;}else{arithmetic_calls[fn][choice][op]+=total;}}',
              'if(r.cut){r.status=1u;}switch(fn){']
    for i in range(n):
        lines.append(f'case {i}:if(!r.status){{for(uint32_t j=0;j<N;j++){{if(!inside(j,outputs_{i},{len(plan["outputs"][str(i)])}u)&&w[j]!=before[j]){{r.status=1u;fail("Output footprint refused");break;}}}}}}break;')
    lines += ['default:r.status=1u;}free(before);return r;}',
              'size_t fdb_word_count(void){return N;}const uint32_t*fdb_words(void){return owner_thread()&&!closed&&!busy?arena:NULL;}',
              'const char*fdb_config_sha256(void){return '+_cstr(config_sha)+';}',
              'const char*fdb_last_error(void){return error;}int fdb_closed(void){return !owner_thread()||closed;}',
              'uint64_t fdb_revision(void){return owner_thread()?revision:0;}uint32_t fdb_last_steps(void){return owner_thread()?last_steps:0;}',
              'uint64_t fdb_invocation_count(size_t fn){return owner_thread()&&fn<NF?calls[fn]:0;}',
              'uint64_t fdb_region_invocation_count(size_t fn,size_t v){return owner_thread()&&fn<NF&&v<NV?variant_calls[fn][v]:0;}',
              'uint64_t fdb_arithmetic_invocation_count(size_t fn,size_t v,size_t op){return owner_thread()&&fn<NF&&v<NV&&op<6?arithmetic_calls[fn][v][op]:0;}',
              'int fdb_function_index(const char*name){if(!name){return -1;}for(int i=0;i<NF;i++){if(!strcmp(name,names[i])){return i;}}return -1;}',
              'int fdb_copy_words(uint32_t*out,size_t n){if(admit()){return 1;}if(!out||n!=N){return fail("Snapshot length differs");}memmove(out,arena,sizeof(arena));return 0;}',
              'int fdb_selected_region(size_t fn){return owner_thread()&&!closed&&fn<NF?(int)choices[fn]:-1;}',
              'int fdb_select_region(size_t fn,size_t v){if(admit()){return 1;}if(fn>=NF||v>=NV||epoch==UINT64_MAX){return fail("Selection refused");}choices[fn]=(uint32_t)v;epoch++;error="";return 0;}',
              'int fdb_replace_words(const uint32_t*w,size_t n){if(admit()){return 1;}if(!w||n!=N||epoch==UINT64_MAX||revision==UINT64_MAX){return fail("Replacement refused");}if(validate(w)){return 1;}',
              f'for(uint32_t i=0;i<N;i++){{if(!inside(i,replacements,{len(plan["replace_ranges"])}u)&&w[i]!=arena[i]){{return fail("Immutable word replacement refused");}}}}',
              'memmove(arena,w,sizeof(arena));revision++;epoch++;error="";return 0;}',
              'int fdb_call(size_t fn,const uint32_t*indices,const uint32_t*values,size_t count,int render){',
              'if(admit()){return 1;}error="";if(fn>=NF||count>N||(count&&(!indices||!values))||(render!=0&&render!=1)||revision==UINT64_MAX){return fail("Call refused");}',
              'for(size_t i=0;i<count;i++){int allowed=0;for(size_t j=0;j<sizeof(input_indices)/4;j++){if(indices[i]==input_indices[j]){allowed=1;}}if(!allowed){return fail("Input patch refused");}for(size_t j=0;j<i;j++){if(indices[j]==indices[i]){return fail("Duplicate input patch");}}}',
              'uint32_t*w=malloc(sizeof(arena));if(!w){return fail("Allocation refused");}memcpy(w,arena,sizeof(arena));for(size_t i=0;i<count;i++){w[indices[i]]=values[i];}',
              'uint32_t selected[NF];memcpy(selected,choices,sizeof(choices));uint64_t before_epoch=epoch;busy=1;',
              'int failed=validate(w);FdbBlockResult r={1u,0u,0u};uint64_t total=0;if(!failed){r=run((uint32_t)fn,w,selected,4000000u);total=r.steps;failed=(int)r.status;}if(!failed){failed=validate(w);}',
              f'if(!failed&&render&&fn!={plan["render"]["function"]}u&&w[{plan["render"]["when_nonzero"]}]){{if(total>=4000000u){{failed=fail("Transaction step budget exhausted");}}else{{r=run({plan["render"]["function"]}u,w,selected,(uint32_t)(4000000u-total));total+=r.steps;failed=(int)r.status;if(!failed){{failed=validate(w);}}}}}}',
              'last_steps=(uint32_t)(total>4000000u?4000000u:total);if(total>4000000u){failed=fail("Transaction step budget exhausted");}if(before_epoch!=epoch||closed){failed=fail("Stale operation");}',
              f'if(!failed){{for(size_t i=0;i<{len(plan["commit_ranges"])}u;i++){{memcpy(arena+commits[i].start,w+commits[i].start,commits[i].count*4u);}}revision++;}}',
              'free(w);busy=0;if(failed&&!*error){fail("Native block refused");}return failed?1:0;}',
              f'int fdb_dispatch(const uint32_t*i,const uint32_t*v,size_t n,int render){{return fdb_call({plan["events"]["function"]}u,i,v,n,render);}}',
              f'int fdb_initialize(uint32_t clock){{uint32_t i={plan["events"]["clock"]}u;clock&=65535u;return fdb_call({plan["initialize"]}u,&i,&clock,1,1);}}',
              'void fdb_close(void){if(!owner_thread()||busy||closed){return;}closed=1;memset(arena,0,sizeof(arena));}']
    return '\n'.join(lines)+'\n'


def _host_config(plan, words, controls, config_sha):
    keys=sorted(plan['keymap']);frame=plan['frame'];events=plan['events']
    lines=['/* Platform-independent presentation and input bindings. */',
           'static const FdbHostKey fdb_keys[]={'+','.join('{'+_cstr(k)+','+str(plan['keymap'][k]['ascii'])+'u,'+str(plan['keymap'][k]['scan'])+'u}' for k in keys)+'};',
           'static const FdbHostColor fdb_colors[]={'+','.join('{'+str(int(k))+'u,'+','.join(map(str,v))+'}' for k,v in sorted(frame['palette'].items(),key=lambda p:int(p[0])))+'};']
    for i,c in enumerate(controls):
        for field in ('name','label'):
            lines.append(f'static const char*const region_{i}_{field}s[]={{'+','.join(_cstr(v[field]) for v in c['variants'])+'};')
    lines += ['static const FdbHostRegion fdb_regions[]={'+','.join('{'+_cstr(c['name'])+','+_cstr(c['label'])+','+str(len(c['variants']))+'u,0u,region_'+str(i)+'_names,region_'+str(i)+'_labels}' for i,c in enumerate(controls))+'};',
              'static const char*const fdb_names[]={'+','.join(_cstr(x) for x in plan['function_names'])+'};']
    values={'words':words,'width':frame['width'],'height':frame['height'],'frame_offset':frame['offset'],'tick_ms':events['tick_ms'],
            **{k:events[k] for k in ('kind','ascii','scan','x','y','buttons','clock','quit_index','keyboard_kind','pointer_kind','clock_kind')},
            'key_count':len(keys),'color_count':len(frame['palette']),'region_count':len(controls),'function_count':len(controls)}
    lines.append('static const FdbHostConfig fdb_config={'+','.join('.'+k+'='+str(v)+('' if k=='tick_ms' else 'u') for k,v in values.items())+
                 ',.keys=fdb_keys,.colors=fdb_colors,.regions=fdb_regions,.function_names=fdb_names,.title='+_cstr(plan['title'])+',.help='+_cstr(plan['help'])+',.config_sha256='+_cstr(config_sha)+'};')
    return '\n'.join(lines)+'\n'


PROBE = '''#include "memory-desktop.h"
#include <string.h>
static int command(void*context,const FdbHostCommand*c,const uint32_t*payload){
 FdbHost*h=context;(void)payload;switch(c->kind){
 case FDB_CMD_KEY:return fdb_host_key(h,c->a,c->b,(int)c->c,c->clock);
 case FDB_CMD_POINTER:return fdb_host_pointer(h,c->a,c->b,(int32_t)c->c,(int32_t)c->d,c->clock);
 case FDB_CMD_CLOCK:return fdb_host_tick(h,c->clock);
 case FDB_CMD_SELECT:return fdb_host_select(h,c->a,c->b);
 case FDB_CMD_RESIZE:return fdb_host_resize(h,(int)c->a,(int)c->b);
 case FDB_CMD_FOCUS:return fdb_host_focus(h,(int)c->a,c->clock);
 default:return 1;}}
static int capture(void*context,uint8_t*out,uint32_t w,uint32_t h){return fdb_host_render(context,out,w,h);}
int main(int argc,char**argv){if(argc!=4||strcmp(argv[1],"--adapter-test")){return 2;}
 FdbHost h;if(fdb_host_open(&h,0)){return 3;}FdbHostPlatform p={command,capture};
 int result=fdb_host_study(&h,argv[2],argv[3],&p,&h);fdb_host_destroy(&h);return result;}
'''


def _variants(values):
    if values is None:
        values=[{'name':'portable-c','label':'Portable C','arithmetic':'portable-c'},
                {'name':'native-asm','label':'Native arithmetic','arithmetic':'native-asm'}]
    if type(values) is not list or not 1 <= len(values) <= 8:
        raise ValueError('choose one to eight desktop backings')
    seen=set()
    for v in values:
        if type(v) is not dict or not {'name','label','arithmetic'} <= set(v) or set(v)-{'name','label','arithmetic','module_requirements'}:
            raise ValueError('invalid desktop backing')
        _text(v['name'],64,'backing name');_text(v['label'],160,'backing label')
        if v['name'] in seen or not re.fullmatch('[a-z][a-z0-9-]*',v['name']) or v['arithmetic'] not in ('portable-c','native-asm'):
            raise ValueError('invalid/duplicate desktop backing name or provider')
        seen.add(v['name'])
    return deepcopy(values)


def _payloads(program,presentation,catalog,orchestration,plan,initial,target,variants):
    from .uil_link import resolve_native_link
    from .uil_native_codegen import emit_native_sources
    if target not in TARGETS:raise ValueError('choose macos-arm64, linux-x64 or windows-x64')
    validate_realization(program,presentation,catalog,orchestration)
    plan,words=validate_desktop_plan(plan,program);variants=_variants(variants)
    if len(plan['function_names'])>TARGETS[target]['max_functions']:
        raise ValueError('desktop function selector budget exceeded for selected platform')
    if type(initial) is not list or len(initial)!=words or any(type(x) is not int or not 0<=x<=0xffffffff for x in initial):
        raise ValueError('desktop initial arena must contain exact owned u32 words')
    validate_desktop_arena(plan,initial)
    controls=[{'name':name,'label':name,'default_index':0,
               'variants':[{'name':v['name'],'label':v['label']} for v in variants]} for name in plan['function_names']]
    config={'plan':plan,'region_controls':controls,'module_uil_sha256':digest(program)}
    config_bytes=_host_bytes(config)+b'\n';config_sha=hashlib.sha256(config_bytes).hexdigest()
    payloads={};emitted=[]
    for i,v in enumerate(variants):
        lock=resolve_native_link(program,presentation,catalog,orchestration,target,arithmetic=v['arithmetic'],module_requirements=v.get('module_requirements'))
        item=emit_native_sources(program,presentation,catalog,orchestration,target=target,link_lock=lock)
        adapter=item['legacy_arena_adapter']
        if not adapter['available'] or adapter['words']!=words or adapter.get('functions')!=[{'index':j,'words':words} for j in range(len(controls))]:
            raise ValueError('desktop closure requires every indexed arena function and no planned effects')
        mapping={'fdb_block':f'fdb_v{i}_block','fdb_function_block':f'fdb_v{i}_function_block',
                 'fdb_function_block_limit':f'fdb_v{i}_function_block_limit',
                 'fdb_math_reset':f'fdb_v{i}_math_reset','fdb_math_count':f'fdb_v{i}_math_count'}
        mapping.update({b['helper']:f'fdb_v{i}_'+b['helper'] for b in item['arithmetic_bindings']})
        namespace='/* Deterministic native symbol ownership; UIL is unchanged. */\n'+'\n'.join('#define '+k+' '+value for k,value in sorted(mapping.items()))+'\n'
        for name,text in item['sources'].items():payloads[f'v{i}/'+name]=text.encode()
        payloads[f'v{i}/namespace.h']=namespace.encode();emitted.append(item)
    payloads.update({'memory-runtime.h':RUNTIME_HEADER.encode(),
        'memory-runtime.c':_runtime(plan,initial,controls,variants,config_sha,target,emitted).encode(),
        'native-core.h':emitted[0]['sources']['native-core.h'].encode(),
        'memory-host-config.h':_host_config(plan,words,controls,config_sha).encode(),
        'memory-desktop-probe.c':PROBE.encode(),'config.json':config_bytes,'initial.json':canonical_bytes(initial)+b'\n'})
    for name in ('memory-desktop.h','memory-desktop.c',TARGETS[target]['adapter']):
        payloads[name]=files('fdisbull').joinpath('native_runtime/'+name).read_bytes()
    if target=='macos-arm64':
        payloads['CommonUIL.app/Contents/Resources/native-config.json']=config_bytes
        payloads['CommonUIL.app/Contents/Info.plist']=plistlib.dumps({'CFBundleExecutable':'program','CFBundleName':plan['title'],
            'CFBundleIdentifier':'org.fdisbull.commonuil.'+digest(program)[:16],'CFBundlePackageType':'APPL',
            'CFBundleShortVersionString':'1.0','NSHighResolutionCapable':True,'LSMinimumSystemVersion':'13.0'})
    if sum(map(len,payloads.values()))>64*1024*1024:raise ValueError('desktop source allocation budget exceeded')
    runtime={'function_order':plan['function_names'],'region_controls':controls,'key_order':sorted(plan['keymap']),
             'config_sha256':config_sha,'ownership':'one owner thread; synchronous staged events; owned snapshots',
             'study_protocol':'fdisbull-native-adapter-study-1' if target=='macos-arm64' else 'fdisbull-native-desktop-study-1',
             'intrinsics':{'window.present':1,'input.keyboard':1,'input.pointer':1,'clock.low16':1}}
    return payloads,runtime,emitted


def _commands(target,variant_count):
    spec=TARGETS[target];cc=spec['compiler'];base=[cc,*spec['flags'],*_FLAGS]
    if target!='windows-x64':base+=['-fPIC']
    objects=[];commands=[]
    for i in range(variant_count):
        for name in ('program','numeric'):
            src=f'v{i}/{name}.c';obj=f'v{i}/{name}.o';objects.append(obj)
            commands.append([*base,'-DFDB_NATIVE_NO_MAIN','-include',f'v{i}/namespace.h','-c',src,'-o',obj])
    commands.append([*base,'-c','memory-runtime.c','-o','memory-runtime.o'])
    objects.append('memory-runtime.o')
    links=['-pthread'] if target!='windows-x64' else ['-static-libgcc','-Wl,--no-insert-timestamp']
    commands.append([cc,*spec['flags'],'-dynamiclib' if target=='macos-arm64' else '-shared',*objects,*links,
                     *(['-Wl,--export-all-symbols'] if target=='windows-x64' else []),'-o',spec['library']])
    commands.append([*base,'memory-desktop-probe.c','memory-desktop.c',*objects,*links,'-o',spec['probe']])
    if target=='macos-arm64':
        commands.append([cc,*spec['flags'],'-fobjc-arc','-O1','-Wall','-Wextra','-I.',spec['adapter'],*objects,'-framework','AppKit','-o',spec['application']])
    else:
        commands.append([*base,spec['adapter'],'memory-desktop.c',*objects,*links,
                         *(['-lX11'] if target=='linux-x64' else ['-mwindows','-lgdi32','-luser32']),'-o',spec['application']])
    return commands,objects


def emit_desktop_shell(program,presentation,catalog,orchestration,plan,initial,output_dir,
                       target='macos-arm64',*,variants=None):
    """Emit a complete new private shell; no tools, targets or windows run."""
    args=deepcopy((program,presentation,catalog,orchestration,plan,initial));variants=_variants(variants)
    payloads,runtime,emitted=_payloads(*args,target,variants)
    root=_private(output_dir,new=True);commands,objects=_commands(target,len(variants))
    document={'format':FORMAT,'stage':'source-emitted','target':target,'target_profile':deepcopy(TARGETS[target]),
              **dict(zip(('program','presentation','catalog','orchestration','plan','initial'),args)),
              'program_sha256':digest(program),'presentation_sha256':digest(presentation),
              'catalog_sha256':digest(catalog),'orchestration_sha256':digest(orchestration),'plan_sha256':_host_digest(plan),
              'variants':variants,'runtime':runtime,'words':len(initial),
              'core_realizations':[{k:deepcopy(e[k]) for k in ('closure_sha256','link_lock_sha256','link_lock','arithmetic_bindings','legacy_arena_adapter')} for e in emitted],
              'sources':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(payloads.items())},
              'compile_commands':commands,'objects':objects,**{k:TARGETS[target][k] for k in ('application','probe','library')},
              'builder_sha256':_sha(__file__),'generator_sha256':_sha(Path(__file__).with_name('uil_native_codegen.py')),
              'execution':False,'host_effect_execution':False,
              'scope':'common UIL native windows/input source; compilation and original/platform observations are separate'}
    document=_seal_desktop_document(document);root.mkdir(mode=0o700);(root/'tmp').mkdir()
    for name,data in payloads.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(data)
    (root/TARGETS[target]['application']).parent.mkdir(parents=True,exist_ok=True)
    _write_new(root/'source-shell.json',document)
    return document


def _admit(directory):
    root=_private(directory);m=load_desktop_json(_owned_regular(root,'source-shell.json'))
    expected_fields={'format','stage','target','target_profile','program','presentation','catalog','orchestration',
                     'plan','initial','program_sha256','presentation_sha256','catalog_sha256','orchestration_sha256',
                     'plan_sha256','variants','runtime','words','core_realizations','sources','compile_commands',
                     'objects','application','probe','library','builder_sha256','generator_sha256','execution',
                     'host_effect_execution','scope','realization_sha256'}
    if type(m) is not dict or set(m)!=expected_fields:
        raise ValueError('desktop manifest fields differ')
    if m.get('format')!=FORMAT or m.get('stage')!='source-emitted' or m.get('target') not in TARGETS or m.get('realization_sha256')!=_seal_desktop_document(m)['realization_sha256']:
        raise ValueError('invalid desktop source manifest')
    if (m.get('execution') is not False or m.get('host_effect_execution') is not False
            or type(m.get('words')) is not int or m['words']!=len(m['initial'])
            or m.get('scope')!='common UIL native windows/input source; compilation and original/platform observations are separate'):
        raise ValueError('desktop admission metadata differs')
    if m.get('builder_sha256')!=_sha(__file__) or m.get('generator_sha256')!=_sha(Path(__file__).with_name('uil_native_codegen.py')):
        raise ValueError('desktop generator profile changed; emit a new realization')
    payloads,runtime,cores=_payloads(*(m[k] for k in ('program','presentation','catalog','orchestration','plan','initial')),m['target'],m['variants'])
    expected={n:hashlib.sha256(v).hexdigest() for n,v in sorted(payloads.items())}
    commands,objects=_commands(m['target'],len(m['variants']))
    if m.get('sources')!=expected or m.get('runtime')!=runtime or m.get('compile_commands')!=commands or m.get('objects')!=objects:
        raise ValueError('desktop source contract differs')
    if m.get('target_profile')!=TARGETS[m['target']] or any(m.get(k)!=TARGETS[m['target']][k] for k in ('application','probe','library')):
        raise ValueError('desktop target paths differ')
    for k in ('program','presentation','catalog','orchestration'):
        if m.get(k+'_sha256')!=digest(m[k]):raise ValueError('desktop closure identity differs')
    if m.get('plan_sha256')!=_host_digest(m['plan']):raise ValueError('desktop plan identity differs')
    profile=[{k:e[k] for k in ('closure_sha256','link_lock_sha256','link_lock','arithmetic_bindings','legacy_arena_adapter')} for e in cores]
    if m.get('core_realizations')!=profile:raise ValueError('desktop core realizations differ')
    for name,value in expected.items():
        if _sha(_owned_regular(root,name))!=value:raise ValueError('desktop source changed: '+name)
    tmp=root/'tmp'
    if tmp.is_symlink() or not tmp.is_dir() or tmp.resolve()!=tmp:
        raise ValueError('desktop temporary directory ownership differs')
    return root,m


def _image(path,target,*,library=False,subsystem=None):
    import lief
    raw=_bounded_bytes(_regular(path),_ARTIFACT_LIMIT,'compiled image')
    if target=='macos-arm64':
        parsed=lief.MachO.parse(raw)
        if parsed is None or len(parsed)!=1:raise ValueError('expected one ARM64 Mach-O image')
        image=parsed.at(0)
        if (len(raw)<32 or image.header.cpu_type!=lief.MachO.Header.CPU_TYPE.ARM64
                or int(image.header.file_type)!=(6 if library else 2)
                or not image.header.nb_cmds or 32+image.header.sizeof_cmds>len(raw)):
            raise ValueError('expected ARM64 Mach-O image')
        segments=[s for s in image.segments if int(s.init_protection)&4 and s.file_size>0
                  and s.file_offset+s.file_size<=len(raw) and len(s.content)>=s.file_size]
        if not segments or not library and not any(s.virtual_address<=image.entrypoint<s.virtual_address+s.file_size for s in segments):
            raise ValueError('Mach-O lacks a file-backed executable entry/segment')
    elif target=='linux-x64':
        image=lief.ELF.parse(raw)
        if (image is None or len(raw)<64 or raw[:6]!=b'\x7fELF\x02\x01' or image.header.machine_type!=lief.ELF.ARCH.X86_64
                or int(image.header.file_type) not in ((3,) if library else (2,3))):
            raise ValueError('expected little-endian ELF64 x86-64 image')
        if library and image.has_interpreter or not library and (not image.entrypoint or int(image.header.file_type)==3 and not image.has_interpreter):
            raise ValueError('ELF shared-library/executable role differs')
        segments=[s for s in image.segments if int(s.type)==1 and int(s.flags)&1 and s.physical_size>0
                  and s.file_offset+s.physical_size<=len(raw) and len(s.content)>=s.physical_size]
        if not segments or not library and not any(s.virtual_address<=image.entrypoint<s.virtual_address+s.physical_size for s in segments):
            raise ValueError('ELF lacks a file-backed executable entry/segment')
    else:
        if len(raw)<64 or raw[:2]!=b'MZ':raise ValueError('expected Windows image')
        at=struct.unpack_from('<I',raw,60)[0]
        if at+96>len(raw) or raw[at:at+4]!=b'PE\0\0' or struct.unpack_from('<H',raw,at+4)[0]!=0x8664 or struct.unpack_from('<H',raw,at+24)[0]!=0x20b:
            raise ValueError('expected AMD64 PE32+ image')
        is_library=bool(struct.unpack_from('<H',raw,at+22)[0]&0x2000)
        if is_library!=library:raise ValueError('Windows image kind differs')
        image=lief.PE.parse(raw)
        if image is None or subsystem is not None and int(image.optional_header.subsystem)!=subsystem:
            raise ValueError('Windows image subsystem differs')
        sections=[s for s in image.sections if int(s.characteristics)&0x20000000 and s.sizeof_raw_data>0
                  and s.pointerto_raw_data+s.sizeof_raw_data<=len(raw) and len(s.content)>0]
        ep=image.optional_header.addressof_entrypoint
        if not sections or not library and not any(s.virtual_address<=ep<s.virtual_address+min(s.virtual_size,s.sizeof_raw_data) for s in sections):
            raise ValueError('PE lacks a file-backed executable entry/section')
    return hashlib.sha256(raw).hexdigest()


def _object(path,target):
    """Admit one bounded object snapshot without reopening it in the parser."""
    import lief
    raw=_bounded_bytes(_regular(path),_ARTIFACT_LIMIT,'compiled object')
    if target=='macos-arm64':
        parsed=lief.MachO.parse(raw)
        if parsed is None or len(parsed)!=1:
            raise ValueError('native object is not one Mach-O image')
        image=parsed.at(0)
        if image.header.cpu_type!=lief.MachO.Header.CPU_TYPE.ARM64 or image.header.file_type!=lief.MachO.Header.FILE_TYPE.OBJECT:
            raise ValueError('native object architecture/kind differs')
    elif target=='linux-x64':
        image=lief.ELF.parse(raw)
        if (image is None or image.header.machine_type!=lief.ELF.ARCH.X86_64
                or int(image.header.identity_class)!=2 or int(image.header.identity_data)!=1
                or int(image.header.file_type)!=1):
            raise ValueError('native object is not ELF64 x86-64 relocatable')
    else:
        if len(raw)<20:
            raise ValueError('native COFF object is truncated')
        machine,count,_,_,_,optional,_=struct.unpack_from('<HHIIIHH',raw)
        if machine!=0x8664 or not 1<=count<=65535 or optional!=0 or 20+count*40>len(raw):
            raise ValueError('native object is not a standard AMD64 COFF object')
    return hashlib.sha256(raw).hexdigest()


def seal_desktop_shell(output_dir,*,compiler_evidence=None):
    root,m=_admit(output_dir)
    names=[*m['objects'],m['application'],m['probe'],m['library']]
    for name in names:
        path=_owned_regular(root,name)
        if path.stat().st_size>_ARTIFACT_LIMIT:
            raise ValueError('desktop compiled artifact byte budget exceeded')
    artifacts=dict(m['sources'])
    for name in m['objects']:
        artifacts[name]=_object(_owned_regular(root,name),m['target'])
    for name in (m['application'],m['probe'],m['library']):
        subsystem=(2 if name==m['application'] else 3) if m['target']=='windows-x64' and name!=m['library'] else None
        artifacts[name]=_image(_owned_regular(root,name),m['target'],library=name==m['library'],subsystem=subsystem)
    result=_seal_desktop_document({**m,'stage':'compiled','source_manifest_sha256':_sha(root/'source-shell.json'),
            'artifacts':artifacts,'compiler':deepcopy(compiler_evidence),'execution':False,'host_effect_execution':False,
            'scope':'sealed source/image identities; compiler correspondence, native callbacks and original comparisons require execution evidence'})
    _write_new(root/'desktop-shell.json',result);return result


def compile_desktop_shell(output_dir,*,c_compiler=None):
    root,m=_admit(output_dir)
    if (root/'desktop-shell.json').exists():raise ValueError('desktop output is already sealed')
    for name in ('compiler-log.json','compile-failure.json','desktop-shell.json'):
        if os.path.lexists(root/name):raise ValueError('refusing existing desktop report')
    for name in [*m['objects'],m['application'],m['probe'],m['library']]:
        path=root/name
        if os.path.lexists(path):raise ValueError('refusing to overwrite desktop artifact')
        if path.parent.is_symlink() or path.parent.resolve()!=path.parent:raise ValueError('desktop artifact parent differs')
    env=dict(os.environ,TMPDIR=str(root/'tmp'))
    from .uil_native import _compiler
    compiler,compiler_info=_compiler(c_compiler or shutil.which(TARGETS[m['target']]['compiler']),m['target'],env)
    done=[]
    for command in m['compile_commands']:
        argv=[str(compiler),*command[1:]]
        try:r=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True,timeout=180)
        except (OSError,subprocess.TimeoutExpired) as e:
            _write_new(root/'compile-failure.json',{'command':command,'error':type(e).__name__});raise ValueError('desktop compilation failed') from e
        done.append({'command':argv,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        if r.returncode:
            _write_new(root/'compile-failure.json',{'steps':done});raise ValueError('desktop compilation failed: '+r.stderr[:3000])
    _write_new(root/'compiler-log.json',done)
    return seal_desktop_shell(root,compiler_evidence={**compiler_info,
                                'log_sha256':_sha(root/'compiler-log.json'),'correspondence':'locally invoked explicit commands; runtime acceptance separate'})


def build_desktop_shell(program,presentation,catalog,orchestration,plan,initial,output_dir,
                        target='macos-arm64',*,variants=None,c_compiler=None):
    emit_desktop_shell(program,presentation,catalog,orchestration,plan,initial,output_dir,target,variants=variants)
    return compile_desktop_shell(output_dir,c_compiler=c_compiler)


def encode_desktop_study(manifest,commands,*,clock=0,x=0,y=0,buttons=0):
    """Encode owned, bounded numeric commands for X11/Win32/probe callbacks.

    These are deliberate programmatic events, not physical hardware evidence.
    AppKit retains its platform-native JSON event protocol.
    """
    if type(commands) is not list or len(commands)>4096:raise ValueError('invalid desktop command count')
    frame=manifest['plan']['frame'];words=manifest['words']
    for v,lo,hi,label in ((clock,0,65535,'clock'),(x,0,frame['width']-1,'pointer x'),(y,0,frame['height']-1,'pointer y'),(buttons,0,7,'buttons')):
        _integer(v,lo,hi,label)
    data=bytearray(b'FDBEVT1\0'+struct.pack('<6I',words,len(commands),clock,x,y,buttons))
    names=('kind','a','b','c','d','e','clock','flags')
    minimum_output=24+4*len(manifest['runtime']['region_controls'])
    for command in commands:
        if type(command) is not dict or 'kind' not in command or set(command)-set(names)-{'payload','id'}:raise ValueError('invalid desktop command')
        fields=[]
        for name in names:
            v=command.get(name,0);_integer(v,-2147483648 if name in ('c','d') else 0,0xffffffff,'command field');fields.append(v&0xffffffff)
        payload=command.get('payload',[])
        if type(payload) is not list or len(payload)>words*2 or any(type(v) is not int or not 0<=v<=0xffffffff for v in payload):raise ValueError('invalid desktop payload')
        if fields[0]>10 or fields[6]>65535 or fields[7]&~7 or payload and fields[0] not in (6,10):raise ValueError('invalid desktop command kind/flags/clock')
        controls=manifest['runtime']['region_controls']
        minimum_output+=48+4*len(controls)+8*len(manifest['runtime']['function_order'])+8*sum(len(c['variants']) for c in controls)+words*4
        if fields[7]&1:minimum_output+=frame['width']*frame['height']*4
        if fields[7]&2:minimum_output+=4  # The native writer admits the actual viewport before capture.
        if minimum_output>268435456:raise ValueError('desktop output byte budget exceeded')
        data.extend(struct.pack('<9I',*fields,len(payload)))
        if payload:data.extend(struct.pack('<'+str(len(payload))+'I',*payload))
        if len(data)>134217728:raise ValueError('desktop input byte budget exceeded')
    return bytes(data)


def decode_desktop_study(manifest,data):
    """Reject truncated/trailing native records; large arenas use owned u32s."""
    from array import array
    import sys
    if type(data) is not bytes or not 24<=len(data)<=268435456 or data[:8]!=b'FDBOUT1\0':raise ValueError('invalid desktop result magic/budget')
    view=memoryview(data);at=8
    def take(n):
        nonlocal at
        if n<0 or at+n>len(view):raise ValueError('incomplete desktop result')
        result=view[at:at+n];at+=n;return result
    def u32():return struct.unpack('<I',take(4))[0]
    n,count,regions,functions=[u32() for _ in range(4)]
    controls=manifest['runtime']['region_controls'];order=manifest['runtime']['function_order']
    if n!=manifest['words'] or count>4096 or regions!=len(controls) or functions!=len(order):raise ValueError('desktop result shape differs')
    sizes=[u32() for _ in range(regions)]
    if sizes!=[len(c['variants']) for c in controls]:raise ValueError('desktop backing shape differs')
    rows=[];frame=manifest['plan']['frame']
    for row_index in range(count):
        values=struct.unpack('<12I',take(48));kind,accepted,committed,closed,low,high,x,y,buttons,width,height,flags=values
        if kind>10 or max(accepted,committed,closed)>1 or committed>accepted or buttons>7 or x>=frame['width'] or y>=frame['height'] or not 1<=width<=4096 or not 1<=height<=4096 or flags&~7:
            raise ValueError('invalid desktop observation fields')
        selected=[struct.unpack('<i',take(4))[0] for _ in range(regions)]
        if any(v!=-1 if closed else not 0<=v<sizes[i] for i,v in enumerate(selected)):raise ValueError('invalid desktop selection')
        counts={name:struct.unpack('<Q',take(8))[0] for name in order}
        variants={c['name']:{v['name']:struct.unpack('<Q',take(8))[0] for v in c['variants']} for c in controls}
        words=array('I');words.frombytes(take(n*4))
        if words.itemsize!=4:raise ValueError('host u32 carrier differs')
        if sys.byteorder!='little':words.byteswap()
        row={'index':row_index,'kind':kind,'accepted':bool(accepted),'committed':bool(committed),'closed':bool(closed),
             'revision':low|(high<<32),'mouse_x':x,'mouse_y':y,'buttons':buttons,'width':width,'height':height,'flags':flags,
             'selected':selected,'words':words,'invocation_counts':counts,'region_counts':variants}
        if flags&1:row['frame_rgba']=bytes(take(frame['width']*frame['height']*4))
        if flags&2:row['view_rgba']=bytes(take(width*height*4))
        rows.append(row)
    if at!=len(data):raise ValueError('trailing desktop observation bytes')
    return rows
