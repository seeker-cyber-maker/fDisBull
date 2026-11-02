"""Source-bound Win16 NE shell with paged u32 storage and C89 native blocks."""
from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import struct
import zlib

from .udc_layers import digest
from .udc_memory_shell import resolve_memory_shell
from .udc_memory_desktop import _controls
from .udc_memory_macos import _json
from .udc_memory_win16 import (WIN16_MEMORY_HEADER,emit_win16_memory_function,
    win16_function_receipt,segmented_layout,TARGET)

FORMAT='fdisbull-memory-win16-shell-1'
PROFILE='windows-x86-16-memory-win16-1'


def _text(value):
    if '\0' in value:raise ValueError('Win16 chrome cannot contain NUL')
    try:data=value.encode('cp1252')
    except UnicodeEncodeError as error:raise ValueError('Win16 chrome requires representable CP1252 text') from error
    return '"'+''.join(chr(b) if 32<=b<127 and b not in (34,92) else '\\'+format(b,'03o') for b in data)+'"'


def _ranges(name,values):
    return 'static const Fdb16Range '+name+'[] = {'+','.join('{'+str(a)+'UL,'+str(n)+'UL}' for a,n in values)+'};'


def _configuration(prepared,controls,functions,sha,crc):
    p=prepared['plan'];e=p['events'];f=p['frame'];keys=sorted(p['keymap'])
    lines=['/* Generated source-bound Win16 configuration, ANSI CP1252 chrome. */']
    lines.append('static const Fdb16Key fdb_keys[] = {'+(','.join('{'+_text(k)+','+str(p['keymap'][k]['ascii'])+'UL,'+str(p['keymap'][k]['scan'])+'UL}' for k in keys) or '{0}')+'};')
    lines.append('static const Fdb16Color fdb_colors[] = {'+','.join('{'+str(int(k))+'UL,'+','.join(map(str,v))+'}' for k,v in sorted(f['palette'].items(),key=lambda x:int(x[0])))+'};')
    for i,c in enumerate(controls):
        for field in ('name','label'):
            lines.append('static const char *const region_'+str(i)+'_'+field+'s[] = {'+','.join(_text(v[field]) for v in c['variants'])+'};')
    lines.append('static const Fdb16Region fdb_regions[] = {'+(','.join('{'+_text(c['name'])+','+_text(c['label'])+','+str(len(c['variants']))+','+str(c['default_index'])+',region_'+str(i)+'_names,region_'+str(i)+'_labels}' for i,c in enumerate(controls)) or '{0}')+'};')
    lines.append('static const char *const function_names[] = {'+','.join(_text(x) for x in functions)+'};')
    numbers=[prepared['program']['memory']['words'],f['offset'],f['width'],f['height'],e['tick_ms']]
    numbers += [e[k] for k in ('kind','ascii','scan','x','y','buttons','clock','quit_index','keyboard_kind','pointer_kind','clock_kind')]
    numbers += [len(keys),len(f['palette']),len(controls),len(functions)]
    lines.append('static const Fdb16Config configuration = {'+','.join(format(v,'.17g') if i==4 else str(v)+'UL' for i,v in enumerate(numbers))+',fdb_keys,fdb_colors,fdb_regions,function_names,'+_text(p['title'])+','+_text(p['help'])+','+_text(sha)+','+str(crc)+'UL};')
    return '\n'.join(lines)+'\n'


CORE_PREFIX=r'''#include "M16HOST.H"
#include <stdlib.h>
#include <string.h>
#include "M16CFG.H"
#include "M16FUN.H"
#pragma code_seg("FDBCORE")
static Fdb16Arena *live_arena;
static HTASK owner_task;
static int opened,closed,busy;
static const char *last_error="";
static Fdb16Count revision,epoch;
const Fdb16Config *fdb16_config(void) { return &configuration; }
static int fail(const char *message) { last_error=message; return 1; }
static int owner(void) { return opened && GetCurrentTask()==owner_task; }
static int admit(void) {
    if(!owner())return fail("Owner task required");
    if(closed)return fail("Core closed");
    if(busy)return fail("Reentrant operation");
    return 0;
}
static int exhausted(Fdb16Count n) { return n.low==4294967295UL && n.high==4294967295UL; }
static void increment(Fdb16Count *n) { ++n->low;if(!n->low)++n->high; }
static int same_count(Fdb16Count a,Fdb16Count b) { return a.low==b.low && a.high==b.high; }
static FdbBlockResult result(FdbU32 status,FdbU32 steps,FdbU32 cut) {
    FdbBlockResult r;r.status=status;r.steps=steps;r.cut=cut;return r;
}
static int add_steps(FdbU32 *total,FdbU32 amount,FdbU32 limit) {
    if(*total>limit || amount>limit-*total)return 1;
    *total+=amount;return 0;
}
static int read_word(const Fdb16Arena *w,FdbU32 index,FdbU32 *value) {
    if(fdb16_read(w,index,value))return fail("Arena read failed");return 0;
}
static int compare_words(const void *a,const void *b) {
    FdbU32 x,y;x=*(const FdbU32*)a;y=*(const FdbU32*)b;return (x>y)-(x<y);
}
const char *fdb16_core_error(void) { return last_error; }
const Fdb16Arena *fdb16_core_words(void) { return owner()&&!closed?live_arena:NULL; }
Fdb16Count fdb16_core_revision(void) { Fdb16Count zero;zero.low=zero.high=0UL;return owner()?revision:zero; }
'''


def _core(prepared,controls,functions,symbols,phases,region_symbols):
    p=prepared['plan'];slots=prepared['regions']['slots'] if prepared['regions'] else {}
    cuts=prepared['cuts']['functions'] if prepared['cuts'] else {};indices={n:i for i,n in enumerate(functions)}
    out=[CORE_PREFIX,'static Fdb16Count calls['+str(len(functions))+'];']
    out += [_ranges('commits',p['commit_ranges']),_ranges('replacements',p['replace_ranges'])]
    out.append('static const FdbU32 inputs[] = {'+','.join(str(x)+'UL' for x in p['inputs'])+'};')
    for n in functions:out.append(_ranges('outputs_'+str(indices[n]),p['outputs'][n]))
    for i,c in enumerate(controls):
        out.append('static FdbU16 choice_'+str(i)+'='+str(c['default_index'])+';')
        out.append('static Fdb16Count region_calls_'+str(i)+'['+str(len(c['variants']))+'];')
    out += ['static int validate(const Fdb16Arena *w) {',
        'FdbU32 value,previous,n,i,j,distance;FdbU32 *copy;int found,duplicate;',
        '(void)previous;(void)n;(void)i;(void)j;(void)distance;(void)copy;(void)found;(void)duplicate;']
    for g in p['guards']:
        out.append('if(read_word(w,'+str(g['index'])+'UL,&value))return 1;')
        bounds=[]
        if g['min']>0:bounds.append('value<'+str(g['min'])+'UL')
        if g['max']<4294967295:bounds.append('value>'+str(g['max'])+'UL')
        if bounds:out.append('if('+ ' || '.join(bounds)+')return fail("State guard refused");')
    for g in p.get('array_guards',[]):
        if g['capacity']>4096:raise ValueError('Win16 array guard scratch budget exceeded')
        out += ['if(read_word(w,'+str(g['length_index'])+'UL,&n))return 1;',
            'if(n>'+str(g['capacity'])+'UL)return fail("Array length refused");',
            'copy=(FdbU32*)malloc((unsigned int)((n?n:1UL)*4UL));if(!copy)return fail("Allocation refused");',
            'for(i=0UL;i<n;i++) {',
            'if(read_word(w,'+str(g['offset'])+'UL+i,&value)){free(copy);return 1;}',
            'if(value<'+str(g['min'])+'UL || value>'+str(g['max'])+'UL){free(copy);return fail("Array value refused");}',
            'copy[(unsigned int)i]=value;',
            'if(i) {previous=copy[(unsigned int)(i-1UL)];distance=value>previous?value-previous:previous-value;',
            'if(!(distance=='+str(g['adjacent_columns'])+'UL || (distance==1UL && value/'+str(g['adjacent_columns'])+'UL==previous/'+str(g['adjacent_columns'])+'UL))){free(copy);return fail("Array adjacency refused");}}','}']
        if g['unique']:
            out += ['qsort(copy,(unsigned int)n,sizeof(FdbU32),compare_words);duplicate=0;',
                'for(i=1UL;i<n;i++)if(copy[(unsigned int)(i-1UL)]==copy[(unsigned int)i])duplicate=1;',
                'if(duplicate){free(copy);return fail("Duplicate array value");}']
        e=g['exclude']
        out += ['if(read_word(w,'+str(e['when_index'])+'UL,&value)){free(copy);return 1;}',
            'if(value=='+str(e['when_value'])+'UL) {',
            'if(read_word(w,'+str(e['index'])+'UL,&value)){free(copy);return 1;}',
            'if(value<'+str(g['min'])+'UL || value>'+str(g['max'])+'UL){free(copy);return fail("Excluded value refused");}',
            'for(i=0UL;i<n;i++)if(copy[(unsigned int)i]==value){free(copy);return fail("Excluded value overlaps array");}',
            '} free(copy);']
    f=p['frame']
    out += ['for(i='+str(f['offset'])+'UL;i<'+str(f['offset']+f['width']*f['height'])+'UL;i++) {',
        'if(read_word(w,i,&value))return 1;found=0;',
        'for(j=0UL;j<(FdbU32)configuration.color_count;j++)if(value==configuration.colors[(unsigned int)j].index)found=1;',
        'if(!found)return fail("Palette index refused");','} return 0; }',
        'static FdbBlockResult run_function(FdbU16,Fdb16Arena*,const FdbU16*,FdbU16);']
    for n,cut in cuts.items():
        idx=indices[n];ids={name:i for i,name in enumerate(cut['phases'])};budget=str(cut['max_steps'])+'UL'
        out += ['static FdbBlockResult owner_'+str(idx)+'(Fdb16Arena *w,const FdbU16 *choices,FdbU16 depth) {',
            'FdbU32 total,hops;FdbU16 phase,child;FdbBlockResult r,c;',
            'total=0UL;phase='+str(ids['entry'])+';',
            'for(hops=0UL;hops<='+str(len(cut['yields']))+'UL;hops++) {','switch(phase) {']
        for phase,symbol in phases[n].items():out.append('case '+str(ids[phase])+':r='+symbol+'(w);break;')
        out += ['default:return result(1UL,total,0UL);}',
            'if(r.status){if(add_steps(&total,r.steps,'+budget+'))total='+budget+';return result(r.status,total,0UL);}',
            'if(!r.cut){if(add_steps(&total,r.steps,'+budget+'))return result(1UL,'+budget+',0UL);return result(0UL,total,0UL);}',
            'if(r.steps<2UL)return result(1UL,total,0UL);',
            'if(add_steps(&total,r.steps-2UL,'+budget+'))return result(1UL,'+budget+',0UL);','child=0;switch(r.cut) {']
        for token,v in cut['yields'].items():out.append('case '+str(token)+'UL:child='+str(indices[v['callee']])+';phase='+str(ids[v['resume']])+';break;')
        out += ['default:return result(1UL,total,0UL);}',
            'c=run_function(child,w,choices,(FdbU16)(depth+1));',
            'if(add_steps(&total,c.steps,'+budget+'))return result(1UL,'+budget+',0UL);',
            'if(c.status)return result(c.status,total,0UL);','}return result(1UL,total,0UL); }']
    out += ['static FdbBlockResult run_function(FdbU16 fn,Fdb16Arena *w,const FdbU16 *choices,FdbU16 depth) {',
        'Fdb16Arena *before;FdbBlockResult r;FdbU32 value;',
        'if(depth>=16 || fn>='+str(len(functions))+')return result(1UL,0UL,0UL);',
        'if(exhausted(calls[fn]))return result(1UL,0UL,0UL);increment(&calls[fn]);',
        'before=fdb16_clone(w);if(!before)return result(2UL,0UL,0UL);r=result(1UL,0UL,0UL);',
        '(void)choices;(void)value;switch(fn) {']
    control_ids={c['name']:i for i,c in enumerate(controls)}
    for n in functions:
        idx=indices[n];out.append('case '+str(idx)+':')
        if n in slots:
            slot=control_ids[n];out.append('switch(choices['+str(slot)+']) {')
            for v,spec in enumerate(controls[slot]['variants']):
                out.append('case '+str(v)+':if(exhausted(region_calls_'+str(slot)+'['+str(v)+']))break;increment(&region_calls_'+str(slot)+'['+str(v)+']);r='+region_symbols[n][spec['name']]+'(w);break;')
            g=slots[n]['region']['output']
            out += ['default:break;}',
                'if(!r.status && (r.steps!=1UL || read_word(w,'+str(g['index'])+'UL,&value) || value<'+str(g['min'])+'UL || value>'+str(g['max'])+'UL)){r.status=1UL;fail("Region domain refused");}']
        elif n in cuts:out.append('r=owner_'+str(idx)+'(w,choices,depth);')
        else:out.append('r='+symbols[n]+'(w);')
        out += ['if(!r.status && fdb16_footprint(before,w,outputs_'+str(idx)+','+str(len(p['outputs'][n]))+')){r.status=1UL;fail("Kernel output footprint refused");}','break;']
    out += ['default:break;}fdb16_release(before);return r;}',
        'int fdb16_core_open(const char *path) {',
        'if(opened || closed)return fail("Core already opened");owner_task=GetCurrentTask();',
        'live_arena=fdb16_load_initial(path,configuration.words,configuration.initial_crc32);',
        'if(!live_arena)return fail("Initial arena admission failed");',
        'if(validate(live_arena)){fdb16_release(live_arena);live_arena=NULL;return 1;}opened=1;return 0;}',
        'int fdb16_core_selected(FdbU16 slot){if(!owner() || closed)return -1;switch(slot){']
    for i in range(len(controls)):out.append('case '+str(i)+':return choice_'+str(i)+';')
    out += ['default:return -1;}}',
        'Fdb16Count fdb16_core_calls(FdbU16 fn){Fdb16Count z;z.low=z.high=0UL;return owner() && fn<'+str(len(functions))+'?calls[fn]:z;}',
        'Fdb16Count fdb16_core_region_calls(FdbU16 slot,FdbU16 variant){Fdb16Count z;z.low=z.high=0UL;if(!owner())return z;switch(slot){']
    for i,c in enumerate(controls):out.append('case '+str(i)+':return variant<'+str(len(c['variants']))+'?region_calls_'+str(i)+'[variant]:z;')
    out += ['default:return z;}}',
        'int fdb16_core_select(FdbU16 slot,FdbU16 variant){if(admit())return 1;if(exhausted(epoch))return fail("Epoch exhausted");switch(slot){']
    for i,c in enumerate(controls):out.append('case '+str(i)+':if(variant>='+str(len(c['variants']))+')return fail("Unknown region variant");choice_'+str(i)+'=variant;break;')
    out += ['default:return fail("Unknown region");}increment(&epoch);last_error="";return 0;}',
        'int fdb16_core_replace(const Fdb16Arena *w) {',
        'Fdb16Arena *replacement,*old;',
        'if(admit())return 1;if(exhausted(revision) || exhausted(epoch))return fail("Revision exhausted");',
        'if(!w || fdb16_word_count(w)!=configuration.words || validate(w))return 1;',
        'if(fdb16_footprint(live_arena,w,replacements,'+str(len(p['replace_ranges']))+'))return fail("Immutable replacement refused");',
        'replacement=fdb16_clone(w);if(!replacement)return fail("Allocation refused");',
        'old=live_arena;live_arena=replacement;increment(&revision);increment(&epoch);fdb16_release(old);last_error="";return 0;}',
        'int fdb16_core_call(FdbU16 fn,const Fdb16Arena *patch,FdbU32 count,int render) {',
        'Fdb16Arena *w,*next,*old;FdbU32 i,j,index,value,other;FdbU16 choices['+str(max(1,len(controls)))+'];Fdb16Count captured;FdbBlockResult r;int failed,allowed;',
        'if(admit())return 1;last_error="";',
        'if(fn>='+str(len(functions))+' || count>'+str(len(p['inputs']))+'UL || (render!=0 && render!=1) || (count && (!patch || fdb16_word_count(patch)!=count*2UL)))return fail("Invalid native call");',
        'if(exhausted(revision))return fail("Revision exhausted");',
        'for(i=0UL;i<count;i++){if(read_word(patch,i*2UL,&index))return 1;allowed=0;',
        'for(j=0UL;j<'+str(len(p['inputs']))+'UL;j++)if(index==inputs[(unsigned int)j])allowed=1;',
        'if(!allowed)return fail("Invalid input patch");',
        'for(j=0UL;j<i;j++){if(read_word(patch,j*2UL,&other))return 1;if(index==other)return fail("Duplicate input patch");}}',
        'w=fdb16_clone(live_arena);if(!w)return fail("Allocation refused");',
        'for(i=0UL;i<count;i++){if(read_word(patch,i*2UL,&index) || read_word(patch,i*2UL+1UL,&value) || fdb16_write(w,index,value)){fdb16_release(w);return fail("Input carrier failure");}}']
    if controls:
        for i in range(len(controls)):out.append('choices['+str(i)+']=choice_'+str(i)+';')
    else:out.append('choices[0]=0;')
    render=indices[p['render']['function']]
    out += ['captured=epoch;busy=1;next=NULL;r=run_function(fn,w,choices,0);failed=(int)r.status;',
        'if(!failed)failed=validate(w);',
        'if(!failed && render && fn!='+str(render)+'){if(read_word(w,'+str(p['render']['when_nonzero'])+'UL,&value))failed=1;else if(value){r=run_function('+str(render)+',w,choices,0);failed=(int)r.status;if(!failed)failed=validate(w);}}',
        'if(!same_count(captured,epoch) || closed)failed=fail("Stale operation");',
        'if(!failed){next=fdb16_clone(live_arena);if(!next)failed=fail("Allocation refused");else if(fdb16_copy_ranges(next,w,commits,'+str(len(p['commit_ranges']))+'))failed=fail("Commit carrier failure");}',
        'if(!failed){old=live_arena;live_arena=next;next=NULL;increment(&revision);fdb16_release(old);}',
        'fdb16_release(next);fdb16_release(w);busy=0;if(failed && !*last_error)fail("Native block refused");return failed?1:0;}',
        'int fdb16_core_initialize(FdbU32 clock){Fdb16Arena *p;int r;p=fdb16_create(2UL);if(!p)return 1;',
        'if(fdb16_write(p,0UL,'+str(p['events']['clock'])+'UL) || fdb16_write(p,1UL,clock&65535UL)){fdb16_release(p);return 1;}',
        'r=fdb16_core_call('+str(indices[p['initialize']])+',p,1UL,1);fdb16_release(p);return r;}',
        'int fdb16_core_dispatch(FdbU32 kind,FdbU32 ascii,FdbU32 scan,FdbU32 x,FdbU32 y,FdbU32 buttons,FdbU32 clock){',
        'Fdb16Arena *p;int r;p=fdb16_create(14UL);if(!p)return 1;']
    for i,key in enumerate(('kind','ascii','scan','x','y','buttons','clock')):
        out.append('if(fdb16_write(p,'+str(2*i)+'UL,'+str(p['events'][key])+'UL) || fdb16_write(p,'+str(2*i+1)+'UL,'+(key+'&65535UL' if key=='clock' else key)+')){fdb16_release(p);return 1;}')
    out += ['r=fdb16_core_call('+str(indices[p['events']['function']])+',p,7UL,1);fdb16_release(p);return r;}',
        'void fdb16_core_close(void){if(!owner() || closed || busy)return;closed=1;fdb16_release(live_arena);live_arena=NULL;}']
    return '\n'.join(out)+'\n'


def emit_memory_win16_shell(project,selections,plan,initial,destination,*,cuts=None,regions=None):
    prepared=resolve_memory_shell(project,selections,plan,initial,cuts=cuts,regions=regions)
    p=prepared['plan'];frame=p['frame'];words=prepared['program']['memory']['words']
    if words>131072:raise ValueError('Win16 logical arena exceeds paged profile')
    if ((frame['width']+3)//4)*4*frame['height']>65520:raise ValueError('Win16 indexed frame exceeds one segment')
    if len(p['functions'] if 'functions' in p else prepared['execution_program']['functions'])>256:raise ValueError('Win16 function budget exceeded')
    if len(set(p['events'][k] for k in ('kind','ascii','scan','x','y','buttons','clock')))!=7:raise ValueError('Win16 event fields must be distinct')
    destination=Path(destination).expanduser().absolute()
    if os.path.lexists(destination):raise ValueError('choose a new private Win16 output')
    destination=destination.resolve()
    if any((x/'.git').exists() for x in (destination,*destination.parents)):raise ValueError('Win16 output must stay outside Git')
    controls=_controls(prepared)
    if len(controls)>16 or any(len(c['variants'])>64 for c in controls):raise ValueError('Win16 selector budget exceeded')
    functions=sorted(prepared['execution_program']['functions']);slots=prepared['regions']['slots'] if prepared['regions'] else {}
    lower=prepared['cuts']['functions'] if prepared['cuts'] else {}
    payloads={'M16ABI.H':WIN16_MEMORY_HEADER.encode()};symbols={};phases={};region_symbols={};realizations={};prototypes=[]
    def emit(model,function,label,capture=None):
        number=len(realizations)
        if number>=4096:raise ValueError('Win16 native realization budget exceeded')
        symbol='fdb16_n'+str(number);filename='N'+str(number).zfill(3)+'.C'
        text=emit_win16_memory_function(model,function,symbol,capture_local=capture,atomic=False,max_automatic_bytes=8192)
        source='#include "M16ABI.H"\n#pragma code_seg("FDBN'+str(number)+'")\n'+text
        payloads[filename]=source.encode();prototypes.append('FdbBlockResult '+symbol+'(Fdb16Arena*);')
        realizations[label]={**win16_function_receipt(model,function,symbol,capture_local=capture,atomic=False,max_automatic_bytes=8192),'file':filename,'target':TARGET}
        return symbol
    for function in functions:
        if function in slots:
            region_symbols[function]={}
            for variant in sorted(slots[function]['variants']):
                region_symbols[function][variant]=emit(slots[function]['variants'][variant]['program'],function,'region/'+function+'/'+variant)
        elif function in lower:
            phases[function]={}
            for phase,spec in lower[function]['phases'].items():phases[function][phase]=emit(spec['program'],function,'phase/'+function+'/'+phase,lower[function]['token_local'])
        else:symbols[function]=emit(prepared['program'],function,'function/'+function)
    raw=struct.pack('<'+str(words)+'I',*initial);crc=zlib.crc32(raw)
    config={'plan':p,'region_controls':controls,'module_uil_sha256':digest(prepared['program'])}
    config_bytes=_json(config);config_sha=hashlib.sha256(config_bytes).hexdigest()
    payloads.update({'initial.json':_json(initial),'M16PROB.C':PROBE.encode(),'INITIAL.BIN':b'FDBINI1\0'+struct.pack('<I',words)+raw,'CONFIG.JSON':config_bytes,
        'M16CFG.H':_configuration(prepared,controls,functions,config_sha,crc).encode(),
        'M16FUN.H':('\n'.join(prototypes)+'\n').encode(),
        'M16CORE.C':_core(prepared,controls,functions,symbols,phases,region_symbols).encode()})
    for source,name in [('memory-win16.h','M16HOST.H'),('memory-win16-common.c','M16COMM.C'),('memory-win16.c','M16GUI.C')]:
        payloads[name]=files('fdisbull').joinpath('native_runtime/'+source).read_bytes()
    manifest={'format':FORMAT,'stage':'source-only','platform':'windows-x86-16','target':TARGET,'profile':PROFILE,'architecture':'x86-16',
        'program':prepared['program'],'execution_program':prepared['execution_program'],'module_uil_sha256':digest(prepared['program']),
        'module_udl_sha256':digest({**prepared['program'],'role':'udl'}),'execution_uil_sha256':digest(prepared['execution_program']),
        'plan':p,'plan_sha256':digest(p),'cuts':prepared['cuts'],'regions':prepared['regions'],
        'source_selections':prepared['source_selections'],'source_endpoints':prepared['endpoints'],
        'runtime':{'function_order':functions,'region_controls':controls,'key_order':sorted(p['keymap']),
            'config_sha256':config_sha,'ownership':'cooperative owner task; private paged transactions; owned snapshots',
            'study_protocol':'fdisbull-native-desktop-study-1','chrome_encoding':'cp1252','initial_data_crc32':crc},
        'storage':segmented_layout(prepared['program']),'realizations':realizations,
        'application':'PROGRAM.EXE','probe':'PROBE.EXE','initial_data':'INITIAL.BIN',
        'source_artifacts':{name:hashlib.sha256(data).hexdigest() for name,data in payloads.items()},
        'native_execution':False,'source_to_uil':False,'scope':'source-only Win16 NE recipe; actual compiler/segments/ABI/GDI/input must be qualified'}
    manifest['commands']=_win16_recipe(manifest)
    destination.mkdir(parents=True,mode=0o700)
    for name,data in payloads.items():(destination/name).write_bytes(data)
    (destination/'native-shell.json').write_bytes(_json(manifest));(destination/'source-shell.json').write_bytes(_json(manifest))
    return manifest


PROBE=r'''#include "M16HOST.H"
#include <stdlib.h>
#pragma code_seg("FDBPROBE")
static int signed_coordinate(FdbU32 value,int *out) {
    if(value>32767UL && value<4294934528UL)return 1;
    *out=(int)(short)(FdbU16)(value&65535UL);return 0;
}
static int command(void *context,const Fdb16Command *c,const Fdb16Arena *payload) {
    Fdb16Host *h;int x,y;const Fdb16Config *cfg;
    (void)payload;h=(Fdb16Host*)context;cfg=fdb16_config();
    switch(c->kind) {
    case FDB_CMD_KEY:
        if(c->a>=cfg->key_count || c->c>1UL)return 1;
        return fdb16_host_key(h,(FdbU16)c->a,c->b,(int)c->c,c->clock);
    case FDB_CMD_POINTER:
        if(c->a>3UL || c->b>2UL || signed_coordinate(c->c,&x) || signed_coordinate(c->d,&y))return 1;
        return fdb16_host_pointer(h,(FdbU16)c->a,(FdbU16)c->b,x,y,c->clock);
    case FDB_CMD_CLOCK:return fdb16_host_tick(h,c->clock);
    case FDB_CMD_SELECT:
        if(c->a>=cfg->region_count || c->b>=cfg->regions[(unsigned int)c->a].count)return 1;
        return fdb16_host_select(h,(FdbU16)c->a,(FdbU16)c->b);
    case FDB_CMD_RESIZE:
        if(c->a<1UL || c->a>4096UL || c->b<1UL || c->b>4096UL)return 1;
        return fdb16_host_resize(h,(int)c->a,(int)c->b);
    case FDB_CMD_FOCUS:if(c->a>1UL)return 1;return fdb16_host_focus(h,(int)c->a,c->clock);
    default:return 1;
    }
}
static int capture(void *context,Fdb16File *out,FdbU16 width,FdbU16 height) {
    Fdb16Host *h;unsigned char *bgr,*rgba;FdbU32 stride;FdbU16 top,y,x,rows,capacity;int failed;
    h=(Fdb16Host*)context;stride=((FdbU32)width*3UL+3UL)&~3UL;
    capacity=(FdbU16)(32760UL/stride);if(!capacity)return 1;
    bgr=(unsigned char*)malloc((unsigned int)(stride*(FdbU32)capacity));
    rgba=(unsigned char*)malloc((unsigned int)((FdbU32)width*4UL));
    if(!bgr || !rgba){free(bgr);free(rgba);return 1;}
    failed=0;top=0;
    while(top<height && !failed){rows=(FdbU16)(height-top);if(rows>capacity)rows=capacity;
        if(fdb16_host_bgr(h,bgr,width,height,top,rows)){failed=1;break;}
        for(y=0;y<rows && !failed;y++){
            for(x=0;x<width;x++){
                FdbU32 at,dest;
                at=(FdbU32)(rows-1-y)*stride+(FdbU32)x*3UL;dest=(FdbU32)x*4UL;
                rgba[(unsigned int)dest]=bgr[(unsigned int)(at+2UL)];
                rgba[(unsigned int)(dest+1UL)]=bgr[(unsigned int)(at+1UL)];
                rgba[(unsigned int)(dest+2UL)]=bgr[(unsigned int)at];rgba[(unsigned int)(dest+3UL)]=255;
            }
            if(fdb16_write_bytes(out,rgba,(FdbU32)width*4UL))failed=1;
        }top=(FdbU16)(top+rows);
    }free(bgr);free(rgba);return failed;
}
int PASCAL WinMain(HINSTANCE instance,HINSTANCE previous,LPSTR line,int show) {
    Fdb16Host host;Fdb16Platform platform;char initial[256],input[256],output[256];int status;
    (void)previous;(void)show;
    if(fdb16_arguments(line,input,output)!=1 || fdb16_initial_path(instance,initial))return 2;
    if(fdb16_host_open(&host,initial,0UL))return 3;
    platform.command=command;platform.capture_view=capture;
    status=fdb16_host_study(&host,input,output,&platform,&host);fdb16_host_destroy(&host);return status;
}
'''


def _win16_recipe(manifest):
    sources=sorted(n for n in manifest['source_artifacts'] if n.endswith('.C') and n not in ('M16GUI.C','M16PROB.C'))
    common=['wcc','-bt=windows','-ml','-zW','-os','-w3','-i=/opt/watcom/h','-i=/opt/watcom/h/win']
    commands=[]
    for source in [*sources,'M16GUI.C','M16PROB.C']:
        commands.append([*common,'-fo='+source[:-2]+'.OBJ',source])
    objects=[n[:-2]+'.OBJ' for n in sources]
    for name,entry in [('PROGRAM.EXE','M16GUI.OBJ'),('PROBE.EXE','M16PROB.OBJ')]:
        commands.append(['wlink','system','windows','option','quiet','option','map='+name[:-4]+'.MAP',
            'option','stack=16384','option','heapsize=8192','name',name,'file',','.join([*objects,entry])])
    return commands


def inspect_windows_ne(data):
    """Read bounded Windows NE image/segment facts, without executing the image."""
    if type(data) is not bytes or len(data)<64 or data[:2]!=b'MZ':
        raise ValueError('expected MZ with Windows NE header')
    offset=struct.unpack_from('<I',data,60)[0]
    if offset<64 or offset+64>len(data) or data[offset:offset+2]!=b'NE':
        raise ValueError('expected bounded Windows NE header')
    u16=lambda at:struct.unpack_from('<H',data,offset+at)[0]
    flags=u16(12);count=u16(28);alignment=u16(50)
    if data[offset+54]!=2 or flags&0x8000 or not count or alignment>16:
        raise ValueError('expected Windows NE executable, not a DLL or other target')
    table=offset+u16(34)
    if u16(34)<64 or table+count*8>len(data):raise ValueError('invalid NE segment table')
    segments=[]
    for index in range(count):
        sector,size,kind,allocated=struct.unpack_from('<4H',data,table+index*8)
        size=size or 65536;allocated=allocated or 65536
        start=sector<<alignment
        if not sector or start<table+count*8 or start+size>len(data) or allocated<size:
            raise ValueError('invalid NE segment payload/allocation')
        segments.append({'index':index+1,'file_offset':start,'file_bytes':size,
                         'minimum_allocation':allocated,'flags':kind,'data':bool(kind&1)})
    ip,cs,sp,ss=(u16(n) for n in (20,22,24,26))
    dgroup=u16(14)
    if not 1<=cs<=count or segments[cs-1]['data'] or ip>=segments[cs-1]['file_bytes']:
        raise ValueError('invalid NE code entry')
    if not 1<=ss<=count or not segments[ss-1]['data'] or not 1<=dgroup<=count or not segments[dgroup-1]['data']:
        raise ValueError('invalid NE stack/data group')
    # SP=0 represents the top of a64KB stack. The loader owns stack/heap growth.
    if sp and sp>65535:raise ValueError('invalid NE stack pointer')
    return {'format':'NE','target_os':'Windows','flags':flags,'entry':{'segment':cs,'offset':ip},
            'stack_segment':ss,'automatic_data_segment':dgroup,'stack_bytes':u16(18),
            'heap_bytes':u16(16),'expected_windows_version':u16(62),'segments':segments}


def _admit_win16_build(destination):
    directory=Path(destination).expanduser().absolute()
    if directory.is_symlink() or not directory.is_dir() or any((p/'.git').exists() for p in (directory.resolve(),*directory.resolve().parents)):
        raise ValueError('owned private Win16 build directory required')
    def regular(name):
        if Path(name).name!=name:raise ValueError('flat Win16 artifact name required')
        p=directory/name
        if p.is_symlink() or not p.is_file() or p.stat().st_nlink!=1:raise ValueError('owned regular Win16 artifact required: '+name)
        return p
    m=json.loads(regular('native-shell.json').read_bytes())
    if (m.get('format')!=FORMAT or m.get('stage') not in ('source-only','compiled') or
        m.get('target')!=TARGET or m.get('profile')!=PROFILE or m.get('platform')!='windows-x86-16' or
        m.get('architecture')!='x86-16' or m.get('application')!='PROGRAM.EXE' or m.get('probe')!='PROBE.EXE' or
        m.get('initial_data')!='INITIAL.BIN'):
        raise ValueError('unsupported Win16 build profile')
    if (digest(m['program'])!=m['module_uil_sha256'] or digest({**m['program'],'role':'udl'})!=m['module_udl_sha256'] or
        digest(m['execution_program'])!=m['execution_uil_sha256'] or digest(m['plan'])!=m['plan_sha256']):
        raise ValueError('Win16 source identity differs')
    fixed={'M16ABI.H','M16CFG.H','M16FUN.H','M16CORE.C','M16HOST.H','M16COMM.C',
           'M16GUI.C','M16PROB.C','CONFIG.JSON','INITIAL.BIN','initial.json'}
    realizations=m.get('realizations',{})
    native_files={'N'+str(i).zfill(3)+'.C' for i in range(len(realizations))}
    if (not isinstance(realizations,dict) or not 1<=len(realizations)<=4096 or
        {r.get('file') for r in realizations.values()}!=native_files or
        set(m.get('source_artifacts',{}))!=fixed|native_files):
        raise ValueError('Win16 source artifact set differs from emitted profile')
    if m.get('commands')!=_win16_recipe(m):raise ValueError('Win16 compiler recipe differs')
    for name,expected in m['source_artifacts'].items():
        if hashlib.sha256(regular(name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Win16 source artifact changed: '+name)
    retained=regular('source-shell.json').read_bytes()
    original=json.loads(retained)
    if original.get('stage')!='source-only':raise ValueError('source-only Win16 receipt required')
    if m['stage']=='source-only' and retained!=regular('native-shell.json').read_bytes():
        raise ValueError('Win16 source manifest differs')
    if m['stage']=='compiled':
        for key,value in original.items():
            if key not in ('stage','scope') and m.get(key)!=value:
                raise ValueError('compiled Win16 source manifest differs')
    return directory,m,regular,retained


def seal_memory_win16_shell(destination,*,compiler_evidence=None):
    """Bind actual Windows NE images to retained sources; no runtime claim."""
    directory,m,regular,retained=_admit_win16_build(destination)
    names=[*m['source_artifacts'],'source-shell.json']
    names += [name[:-2]+'.OBJ' for name in m['source_artifacts'] if name.endswith('.C')]
    names += ['PROGRAM.EXE','PROBE.EXE','PROGRAM.MAP','PROBE.MAP']
    artifacts={name:hashlib.sha256(regular(name).read_bytes()).hexdigest() for name in names}
    images={name:inspect_windows_ne(regular(name).read_bytes()) for name in ('PROGRAM.EXE','PROBE.EXE')}
    if m['stage']=='compiled':
        if (m.get('artifacts')!=artifacts or m.get('images')!=images or
            compiler_evidence is not None and compiler_evidence!=m.get('compiler')):
            raise ValueError('compiled Win16 receipt is immutable; choose a new build')
        return m
    m.update(stage='compiled',artifacts=artifacts,images=images,
        source_manifest_sha256=hashlib.sha256(retained).hexdigest(),compiler=deepcopy(compiler_evidence),
        artifact_admission='bounded Windows NE executable/segments and hashes; compiler lineage is supplied evidence',
        scope='compiled Windows NE artifacts; original fidelity, native GDI/input and runtime must be qualified separately')
    (directory/'native-shell.json').write_bytes(_json(m));return m


def compile_memory_win16_shell(destination,*,c_compiler=None,linker=None):
    """Compile with an explicitly available Open Watcom SDK; install nothing."""
    import shutil
    import subprocess
    directory,m,regular,retained=_admit_win16_build(destination)
    if m['stage']!='source-only':raise ValueError('compiled Win16 receipt is immutable; choose a new build')
    comp=shutil.which(str(c_compiler or 'wcc'));link=shutil.which(str(linker or 'wlink'))
    if not comp or not link:raise ValueError('Win16 compilation requires the separate Open Watcom wcc/wlink SDK')
    outputs=[n[:-2]+'.OBJ' for n in m['source_artifacts'] if n.endswith('.C')]+['PROGRAM.EXE','PROBE.EXE','PROGRAM.MAP','PROBE.MAP']
    if any(os.path.lexists(directory/n) for n in outputs):
        raise ValueError('owned fresh compiler outputs required; choose a new Win16 build')
    evidence=[]
    for recipe in m['commands']:
        command=[comp if recipe[0]=='wcc' else link,*recipe[1:]]
        run=subprocess.run(command,cwd=directory,capture_output=True,text=True,timeout=180)
        evidence.append({'command':command,'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr})
        if run.returncode:raise ValueError('Win16 compilation failed: '+run.stderr[:3000]+run.stdout[:3000])
    return seal_memory_win16_shell(directory,compiler_evidence=evidence)


def build_memory_win16_shell(project,selections,plan,initial,destination,*,cuts=None,regions=None,c_compiler=None,linker=None):
    emit_memory_win16_shell(project,selections,plan,initial,destination,cuts=cuts,regions=regions)
    return compile_memory_win16_shell(destination,c_compiler=c_compiler,linker=linker)
