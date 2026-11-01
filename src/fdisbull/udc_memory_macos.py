"""Native AppKit shell over source-bound bounded-memory UIL realizations.

The source model and orchestration are shared with the browser profile. This
consumer explicitly retargets them through the ARM64 C backend; it neither runs
the browser nor reinterprets source selection target metadata as native output.
"""
from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

from .udc_layers import digest
from .udc_macos import DEFAULT_TARGET, _compiler
from .udc_memory_native import NATIVE_MEMORY_HEADER, emit_memory_function, TARGET
from .udc_memory_shell import resolve_memory_shell

FORMAT = 'fdisbull-memory-macos-shell-1'
PROFILE = 'macos-arm64-memory-appkit-1'
HEADER = r'''#ifndef FDISBULL_MEMORY_RUNTIME_1
#define FDISBULL_MEMORY_RUNTIME_1
#include <stddef.h>
#include <stdint.h>
size_t fdb_word_count(void);
const uint32_t *fdb_words(void);
int fdb_copy_words(uint32_t *, size_t);
int fdb_function_index(const char *);
int fdb_call(size_t, const uint32_t *, const uint32_t *, size_t, int);
int fdb_dispatch(const uint32_t *, const uint32_t *, size_t, int);
int fdb_initialize(uint32_t);
int fdb_select_region(size_t, size_t);
int fdb_selected_region(size_t);
int fdb_replace_words(const uint32_t *, size_t);
uint64_t fdb_revision(void);
uint64_t fdb_invocation_count(size_t);
uint64_t fdb_region_invocation_count(size_t, size_t);
uint32_t fdb_last_steps(void);
const char *fdb_last_error(void);
const char *fdb_config_sha256(void);
void fdb_close(void);
int fdb_closed(void);
#endif
'''


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()+b'\n'


def _ranges(name, values):
    return 'static const FdbRange '+name+'[] = {'+','.join('{'+str(start)+'u,'+str(count)+'u}' for start,count in values)+'};'


def _runtime(prepared, controls, config_sha, *, target=TARGET, owner_prelude=None):
    program=prepared['program'];execution=prepared['execution_program'];plan=prepared['plan']
    functions=sorted(execution['functions']);indices={name:i for i,name in enumerate(functions)}
    slots=prepared['regions']['slots'] if prepared['regions'] else {}
    words=program['memory']['words'];lowered=prepared['cuts']['functions'] if prepared['cuts'] else {}
    sources=[];realizations={};symbols={};phase_symbols={};region_symbols={}
    def emit(model, function, label, capture=None):
        symbol='fdb_native_'+str(len(sources))
        text=emit_memory_function(model,function,symbol,capture_local=capture)
        sources.append(text);realizations[label]={'symbol':symbol,'module_uil_sha256':digest(model),
            'source_sha256':hashlib.sha256(text.encode()).hexdigest(),'target':target,'function':function}
        return symbol
    for function in functions:
        if function in slots:
            region_symbols[function]={}
            for variant in sorted(slots[function]['variants']):
                spec=slots[function]['variants'][variant]
                region_symbols[function][variant]=emit(spec['program'],function,'region/'+function+'/'+variant)
        elif function in lowered:
            phase_symbols[function]={}
            for phase,spec in lowered[function]['phases'].items():
                phase_symbols[function][phase]=emit(spec['program'],function,'phase/'+function+'/'+phase,lowered[function]['token_local'])
        else:symbols[function]=emit(program,function,'function/'+function)
    if owner_prelude is None:
        owner_prelude=['#include <pthread.h>',
            'static int fdb_owner_thread(void) { return pthread_main_np(); }']
    lines=[NATIVE_MEMORY_HEADER,'#include "memory-runtime.h"',*owner_prelude,
        'typedef struct { uint32_t start,count; } FdbRange;',
        f'enum {{ FDB_WORDS={words}, FDB_FUNCTIONS={len(functions)}, FDB_REGIONS={len(controls)} }};',
        'static uint32_t g_words[FDB_WORDS] = {'+','.join(str(v)+'u' for v in prepared['initial'])+'};',
        'static uint64_t g_revision=0,g_epoch=0,g_calls[FDB_FUNCTIONS];',
        'static int g_closed=0,g_busy=0; static uint32_t g_last_steps=0;',
        'static _Thread_local const char *g_error="";',
        'static const char *g_names[] = {'+','.join(json.dumps(fn) for fn in functions)+'};',
        'static int fail(const char *message) { g_error=message; return 1; }',
        'static int admit(void) { if(!fdb_owner_thread()) return fail("Main-thread owner required"); if(g_closed) return fail("Shell closed"); if(g_busy) return fail("Reentrant shell operation"); return 0; }',
        'static int inside(uint32_t i,const FdbRange *r,size_t n) { for(size_t j=0;j<n;j++) if(i>=r[j].start && i-r[j].start<r[j].count) return 1; return 0; }',
        'static int compare_words(const void *a,const void *b) { uint32_t x=*(const uint32_t*)a,y=*(const uint32_t*)b; return (x>y)-(x<y); }',
        _ranges('commit_ranges',plan['commit_ranges']),_ranges('replace_ranges',plan['replace_ranges']),
        'static const uint32_t input_indices[] = {'+','.join(str(i)+'u' for i in plan['inputs'])+'};']
    for function in functions:lines.append(_ranges('outputs_'+str(indices[function]),plan['outputs'][function]))
    for slot,control in enumerate(controls):
        lines.append(f'static uint32_t g_choice_{slot}={control["default_index"]}u; static uint64_t g_region_calls_{slot}[{len(control["variants"])}];')
    lines+=['static int validate(const uint32_t *w) {']
    for guard in plan['guards']:
        lines.append(f'if(w[{guard["index"]}]<{guard["min"]}u || w[{guard["index"]}]>{guard["max"]}u) return fail("State guard refused");')
    for guard in plan.get('array_guards',[]):
        off=guard['offset'];n=f'w[{guard["length_index"]}]';col=guard['adjacent_columns'];exc=guard['exclude']
        lines += [f'{{ uint32_t n={n}; if(n>{guard["capacity"]}u) return fail("Array length refused");',
            f'for(uint32_t i=0;i<n;i++) {{ uint32_t value=w[{off}u+i]; if(value<{guard["min"]}u || value>{guard["max"]}u) return fail("Array value refused");',
            f'if(i) {{ uint32_t previous=w[{off}u+i-1],distance=value>previous?value-previous:previous-value;',
            f'if(!(distance=={col}u || (distance==1u && value/{col}u==previous/{col}u))) return fail("Array adjacency refused"); }} }}']
        if guard['unique']:
            lines += [f'uint32_t *copy=(uint32_t*)malloc((n?n:1u)*sizeof(uint32_t)); if(!copy) return fail("Allocation refused"); memcpy(copy,w+{off}u,n*sizeof(uint32_t)); qsort(copy,n,sizeof(uint32_t),compare_words);',
                'int duplicate=0; for(uint32_t i=1;i<n;i++) if(copy[i-1]==copy[i]) duplicate=1; free(copy); if(duplicate) return fail("Duplicate array value");']
        lines += [f'if(w[{exc["when_index"]}]=={exc["when_value"]}u) {{ uint32_t value=w[{exc["index"]}]; if(value<{guard["min"]}u || value>{guard["max"]}u) return fail("Excluded value refused");',
            f'for(uint32_t i=0;i<n;i++) if(w[{off}u+i]==value) return fail("Excluded value overlaps array"); }} }}']
    frame=plan['frame'];allowed=','.join(str(int(key))+'u' for key in frame['palette'])
    lines += ['{ static const uint32_t colors[]={'+allowed+'};',
        f'for(uint32_t i={frame["offset"]}u;i<{frame["offset"]+frame["width"]*frame["height"]}u;i++) {{ int found=0; for(size_t j=0;j<sizeof(colors)/sizeof(colors[0]);j++) if(w[i]==colors[j]) found=1; if(!found) return fail("Palette index refused"); }} }}',
        'return 0; }']
    lines+=sources
    lines += ['static FdbBlockResult run_function(uint32_t fn,uint32_t *w,const uint32_t *choices,uint32_t depth);']
    for function,cut in lowered.items():
        index=indices[function];phase_order=list(cut['phases']);phase_ids={name:i for i,name in enumerate(phase_order)}
        lines += [f'static FdbBlockResult owner_{index}(uint32_t *w,const uint32_t *choices,uint32_t depth) {{',
            f'uint32_t phase={phase_ids["entry"]}u; uint64_t total=0;',
            f'for(uint32_t hops=0;hops<={len(cut["yields"])}u;hops++) {{ FdbBlockResult r={{1u,0u,0u}}; switch(phase) {{']
        for phase,symbol in phase_symbols[function].items():lines.append(f'case {phase_ids[phase]}u:r={symbol}(w);break;')
        lines += ['default:return (FdbBlockResult){1u,0u,0u}; }',
            f'if(r.status) {{ total+=r.steps;return (FdbBlockResult){{1u,(uint32_t)(total>{cut["max_steps"]}u?{cut["max_steps"]}u:total),0u}}; }}',f'if(!r.cut) {{ total+=r.steps; if(total>{cut["max_steps"]}u) {{ fail("Canonical caller budget exhausted"); return (FdbBlockResult){{1u,{cut["max_steps"]}u,0u}}; }} return (FdbBlockResult){{0u,(uint32_t)total,0u}}; }}',
            'if(r.steps<2u) return (FdbBlockResult){1u,0u,0u}; total+=r.steps-2u;',
            f'if(total>{cut["max_steps"]}u) {{ fail("Canonical caller budget exhausted"); return (FdbBlockResult){{1u,{cut["max_steps"]}u,0u}}; }}',
            'uint32_t child=0; switch(r.cut) {']
        for token,next_ in cut['yields'].items():lines.append(f'case {token}u:child={indices[next_["callee"]]}u;phase={phase_ids[next_["resume"]]}u;break;')
        lines += ['default:return (FdbBlockResult){1u,0u,0u}; }',
            f'FdbBlockResult c=run_function(child,w,choices,depth+1u); total+=c.steps; if(c.status) return (FdbBlockResult){{1u,(uint32_t)(total>{cut["max_steps"]}u?{cut["max_steps"]}u:total),0u}};',
            f'if(total>{cut["max_steps"]}u) {{ fail("Canonical caller budget exhausted"); return (FdbBlockResult){{1u,{cut["max_steps"]}u,0u}}; }}',
            '} return (FdbBlockResult){1u,0u,0u}; }']
    lines += ['static FdbBlockResult run_function(uint32_t fn,uint32_t *w,const uint32_t *choices,uint32_t depth) {',
        'if(depth>=16u || fn>=FDB_FUNCTIONS) return (FdbBlockResult){1u,0u,0u};',
        'if(g_calls[fn]==UINT64_MAX) return (FdbBlockResult){1u,0u,0u}; ++g_calls[fn];',
        'uint32_t *before=(uint32_t*)malloc(FDB_WORDS*sizeof(uint32_t)); if(!before) return (FdbBlockResult){1u,0u,0u}; memcpy(before,w,FDB_WORDS*sizeof(uint32_t));',
        'FdbBlockResult r={1u,0u,0u}; switch(fn) {']
    control_indices={c['name']:i for i,c in enumerate(controls)}
    for function in functions:
        index=indices[function];lines.append(f'case {index}u:')
        if function in slots:
            slot=control_indices[function];lines.append(f'switch(choices[{slot}]) {{')
            for variant,spec in enumerate(controls[slot]['variants']):
                name=spec['name'];lines.append(f'case {variant}u: if(g_region_calls_{slot}[{variant}]==UINT64_MAX) break; ++g_region_calls_{slot}[{variant}]; r={region_symbols[function][name]}(w); break;')
            output=slots[function]['region']['output']
            lines += ['default:break; }',f'if(!r.status && (r.steps!=1u || w[{output["index"]}]<{output["min"]}u || w[{output["index"]}]>{output["max"]}u)) {{ r.status=1u; fail("Region output domain refused"); }}']
        elif function in lowered:lines.append(f'r=owner_{index}(w,choices,depth);')
        else:lines.append(f'r={symbols[function]}(w);')
        count=len(plan['outputs'][function]);lines += [f'if(!r.status) for(uint32_t i=0;i<FDB_WORDS;i++) if(!inside(i,outputs_{index},{count}u) && w[i]!=before[i]) {{ r.status=1u; fail("Kernel wrote outside declared output"); break; }}','break;']
    lines += ['default:break; } free(before); return r; }',
        'size_t fdb_word_count(void) { return FDB_WORDS; }',
        'const uint32_t *fdb_words(void) { return fdb_owner_thread()&&!g_closed?g_words:NULL; }',
        'const char *fdb_last_error(void) { return g_error; }',
        'const char *fdb_config_sha256(void) { return "'+config_sha+'"; }',
        'int fdb_closed(void) { return !fdb_owner_thread() || g_closed; }',
        'uint64_t fdb_revision(void) { return fdb_owner_thread()?g_revision:0; }',
        'uint32_t fdb_last_steps(void) { return fdb_owner_thread()?g_last_steps:0; }',
        'uint64_t fdb_invocation_count(size_t fn) { return fdb_owner_thread()&&fn<FDB_FUNCTIONS?g_calls[fn]:0; }',
        'int fdb_function_index(const char *name) { if(!name) return -1; for(int i=0;i<FDB_FUNCTIONS;i++) if(!strcmp(name,g_names[i])) return i; return -1; }',
        'int fdb_copy_words(uint32_t *out,size_t n) { if(admit()) return 1; if(!out || n!=FDB_WORDS) return fail("Snapshot length differs"); memmove(out,g_words,sizeof(g_words)); return 0; }',
        'int fdb_selected_region(size_t slot) { if(!fdb_owner_thread() || g_closed) return -1; switch(slot) {']
    for slot in range(len(controls)):lines.append(f'case {slot}:return (int)g_choice_{slot};')
    lines += ['default:return -1; } }','uint64_t fdb_region_invocation_count(size_t slot,size_t variant) { if(!fdb_owner_thread()) return 0; switch(slot) {']
    for slot,control in enumerate(controls):lines.append(f'case {slot}:return variant<{len(control["variants"])}u?g_region_calls_{slot}[variant]:0;')
    lines += ['default:return 0; } }','int fdb_select_region(size_t slot,size_t variant) { if(admit()) return 1; if(g_epoch==UINT64_MAX) return fail("Epoch exhausted"); switch(slot) {']
    for slot,control in enumerate(controls):lines.append(f'case {slot}:if(variant>={len(control["variants"])}u) return fail("Unknown region variant"); g_choice_{slot}=(uint32_t)variant;break;')
    lines += ['default:return fail("Unknown region"); } ++g_epoch;g_error="";return 0; }',
        'int fdb_replace_words(const uint32_t *w,size_t n) { if(admit()) return 1; if(!w || n!=FDB_WORDS) return fail("Replacement length differs"); if(g_revision==UINT64_MAX || g_epoch==UINT64_MAX) return fail("Revision exhausted"); if(validate(w)) return 1;',
        f'for(uint32_t i=0;i<FDB_WORDS;i++) if(!inside(i,replace_ranges,{len(plan["replace_ranges"])}u) && w[i]!=g_words[i]) return fail("Replacement touched immutable input");',
        'memmove(g_words,w,sizeof(g_words));++g_revision;++g_epoch;g_error="";return 0; }',
        'int fdb_call(size_t fn,const uint32_t *indices,const uint32_t *values,size_t count,int render) {',
        'if(admit()) return 1;g_error="";if(fn>=FDB_FUNCTIONS || count>FDB_WORDS || (count&&(!indices||!values)) || (render!=0&&render!=1)) return fail("Invalid native call");',
        'if(g_revision==UINT64_MAX) return fail("Revision exhausted");',
        'for(size_t i=0;i<count;i++) { int allowed=0; for(size_t j=0;j<sizeof(input_indices)/sizeof(input_indices[0]);j++) if(indices[i]==input_indices[j]) allowed=1; if(!allowed) return fail("Invalid input patch"); for(size_t j=0;j<i;j++) if(indices[j]==indices[i]) return fail("Duplicate input patch"); }',
        'uint32_t *w=(uint32_t*)malloc(sizeof(g_words));if(!w) return fail("Allocation refused");memcpy(w,g_words,sizeof(g_words));for(size_t i=0;i<count;i++) w[indices[i]]=values[i];',
        'uint32_t choices['+str(max(1,len(controls)))+']={'+(','.join('g_choice_'+str(i) for i in range(len(controls))) or '0u')+'};uint64_t epoch=g_epoch;g_busy=1;',
        'FdbBlockResult r=run_function((uint32_t)fn,w,choices,0u);g_last_steps=r.steps;',
        'int failed=(int)r.status;if(!failed) failed=validate(w);',
        f'if(!failed && render && fn!={indices[plan["render"]["function"]]}u && w[{plan["render"]["when_nonzero"]}]!=0u) {{ r=run_function({indices[plan["render"]["function"]]}u,w,choices,0u);failed=(int)r.status; if(!failed) failed=validate(w); }}',
        'if(epoch!=g_epoch || g_closed) failed=fail("Stale operation");',
        f'if(!failed) {{ for(size_t i=0;i<{len(plan["commit_ranges"])}u;i++) memcpy(g_words+commit_ranges[i].start,w+commit_ranges[i].start,commit_ranges[i].count*sizeof(uint32_t)); ++g_revision; }}',
        'free(w);g_busy=0;if(failed && !*g_error) fail("Native block refused");return failed?1:0; }',
        f'int fdb_dispatch(const uint32_t *i,const uint32_t *v,size_t n,int render) {{ return fdb_call({indices[plan["events"]["function"]]}u,i,v,n,render); }}',
        f'int fdb_initialize(uint32_t clock) {{ uint32_t index={plan["events"]["clock"]}u;return fdb_call({indices[plan["initialize"]]}u,&index,&clock,1u,1); }}',
        'void fdb_close(void) { if(!fdb_owner_thread() || g_busy || g_closed) return;g_closed=1;memset(g_words,0,sizeof(g_words)); }']
    return '\n'.join(lines)+'\n',realizations,functions


def build_memory_macos_shell(project,selections,plan,initial,destination,*,cuts=None,regions=None,c_compiler=None,with_app=True):
    """Emit native artifacts; original/UIL/native and GUI evidence is separate."""
    if type(with_app) is not bool:raise ValueError('with_app must be explicit boolean')
    prepared=resolve_memory_shell(project,selections,plan,initial,cuts=cuts,regions=regions)
    destination=Path(destination).expanduser().absolute()
    if os.path.lexists(destination):raise ValueError('choose a new private native shell output')
    destination=destination.resolve()
    if any((p/'.git').exists() for p in (destination,*destination.parents)):raise ValueError('native shell output must be outside Git')
    compiler,compiler_info=_compiler(c_compiler or shutil.which('clang'))
    controls=[]
    for name,slot in sorted((prepared['regions']['slots'] if prepared['regions'] else {}).items()):
        order=sorted(slot['variants']);controls.append({'name':name,'label':slot['label'],
            'default_index':order.index(slot['default']),
            'variants':[{'name':key,'label':slot['variants'][key]['label']} for key in order]})
    config={'plan':prepared['plan'],'region_controls':controls,'module_uil_sha256':digest(prepared['program'])}
    config_bytes=_json(config);config_sha=hashlib.sha256(config_bytes).hexdigest()
    source,realizations,functions=_runtime(prepared,controls,config_sha)
    destination.mkdir(parents=True,mode=0o700)
    (destination/'memory-runtime.h').write_text(HEADER);(destination/'memory-runtime.c').write_text(source)
    (destination/'config.json').write_bytes(config_bytes);(destination/'initial.json').write_bytes(_json(initial))
    commands=[]
    def compile_(arguments):
        command=[str(compiler),*arguments];commands.append(command)
        run=subprocess.run(command,cwd=destination,capture_output=True,timeout=120)
        if run.returncode:raise ValueError('native memory compilation failed: '+run.stderr.decode(errors='replace')[:3000])
    compile_(['-target',DEFAULT_TARGET,'-std=c11','-O1','-fPIC','-c','memory-runtime.c','-o','memory-runtime.o'])
    compile_(['-target',DEFAULT_TARGET,'-dynamiclib','memory-runtime.o','-o','memory-runtime.dylib'])
    app_relative=None
    if with_app:
        adapter=files('fdisbull').joinpath('native_runtime/memory-appkit.m').read_bytes()
        (destination/'memory-appkit.m').write_bytes(adapter)
        app=destination/'MemoryGame.app'/'Contents';(app/'MacOS').mkdir(parents=True);(app/'Resources').mkdir()
        (app/'Resources/native-config.json').write_bytes(config_bytes)
        (app/'Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable':'program','CFBundleName':plan['title'],
            'CFBundleIdentifier':'org.fdisbull.memory.'+digest(prepared['program'])[:16],'CFBundlePackageType':'APPL',
            'CFBundleShortVersionString':'1.0','NSHighResolutionCapable':True,'LSMinimumSystemVersion':'11.0'}))
        app_relative='MemoryGame.app/Contents/MacOS/program'
        compile_(['-target',DEFAULT_TARGET,'-fobjc-arc','-O1','-I.','memory-appkit.m','memory-runtime.o',
            '-framework','AppKit','-o',app_relative])
    import lief
    for name in ['memory-runtime.dylib']+([app_relative] if app_relative else []):
        image=lief.MachO.parse(str(destination/name)).at(0)
        if image.header.cpu_type!=lief.MachO.Header.CPU_TYPE.ARM64:raise ValueError('native output is not ARM64')
    artifacts={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}
    manifest={'format':FORMAT,'profile':PROFILE,'target':TARGET,'architecture':'arm64','program':prepared['program'],
        'module_uil_sha256':digest(prepared['program']),'module_udl_sha256':digest({**prepared['program'],'role':'udl'}),
        'execution_uil_sha256':digest(prepared['execution_program']),'execution_program':prepared['execution_program'],
        'plan':prepared['plan'],'plan_sha256':digest(prepared['plan']),'regions':prepared['regions'],'cuts':prepared['cuts'],
        'source_selections':prepared['source_selections'],'source_endpoints':prepared['endpoints'],
        'runtime':{'function_order':functions,'region_controls':controls,'ownership':'synchronous main-thread owner',
            'input_and_drawing':'AppKit adapters over unchanged memory UIL','config_sha256':config_sha},
        'realizations':realizations,'library':'memory-runtime.dylib','initial_file':'initial.json','application':app_relative,
        'compiler':compiler_info,'commands':commands,'artifacts':artifacts,
        'native_execution':False,'source_to_uil':False,'scope':'native generated memory blocks and owned AppKit shell; qualification separate'}
    (destination/'native-shell.json').write_bytes(_json(manifest))
    return manifest
