"""Native Win32/X11 realizations of the source-bound bounded-memory profile.

Source emission, compiler execution, artifact sealing and execution qualification
are distinct gates. The binary study protocol observes owned state and native
surfaces, never the desktop. No original game is bundled.
"""
from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

from .udc_layers import digest
from .udc_memory_macos import HEADER, _json, _runtime
from .udc_memory_shell import resolve_memory_shell

TARGETS = {
    'windows-x64': {'target':'windows-x64-memory-1','profile':'windows-x64-memory-win32-1',
        'adapter':'memory-win32.c','compiler':'x86_64-w64-mingw32-gcc',
        'library':'memory-runtime.dll','application':'program.exe','probe':'probe.exe'},
    'linux-x64': {'target':'linux-x64-memory-1','profile':'linux-x64-memory-x11-1',
        'adapter':'memory-x11.c','compiler':'gcc',
        'library':'memory-runtime.so','application':'program','probe':'probe'},
}
FORMAT='fdisbull-memory-desktop-shell-1'


def _owner(target):
    if target=='windows-x64':
        return ['#include <windows.h>',
            'static DWORD fdb_owner_id; __attribute__((constructor)) static void fdb_capture_owner(void) { fdb_owner_id=GetCurrentThreadId(); }',
            'static int fdb_owner_thread(void) { return GetCurrentThreadId()==fdb_owner_id; }']
    return ['#include <pthread.h>',
        'static pthread_t fdb_owner_id; __attribute__((constructor)) static void fdb_capture_owner(void) { fdb_owner_id=pthread_self(); }',
        'static int fdb_owner_thread(void) { return pthread_equal(pthread_self(),fdb_owner_id); }']


def _controls(prepared):
    result=[]
    for name,slot in sorted((prepared['regions']['slots'] if prepared['regions'] else {}).items()):
        order=sorted(slot['variants'])
        result.append({'name':name,'label':slot['label'],'default_index':order.index(slot['default']),
            'variants':[{'name':key,'label':slot['variants'][key]['label']} for key in order]})
    return result


def _host_config(prepared,controls,functions,config_sha):
    plan=prepared['plan'];frame=plan['frame'];events=plan['events']
    def text(value):
        if '\x00' in value:raise ValueError('native text cannot contain NUL')
        return '"'+''.join(chr(b) if 32<=b<127 and b not in (34,92) else '\\'+format(b,'03o') for b in value.encode('utf-8'))+'"'
    lines=['/* Generated from the validated source plan. */']
    keys=sorted(plan['keymap'])
    lines.append('static const FdbHostKey fdb_keys[] = {'+','.join(
        '{'+text(key)+','+str(plan['keymap'][key]['ascii'])+'u,'+str(plan['keymap'][key]['scan'])+'u}' for key in keys)+'};')
    lines.append('static const FdbHostColor fdb_colors[] = {'+','.join(
        '{'+str(int(key))+'u,'+','.join(map(str,value))+'}' for key,value in sorted(frame['palette'].items(),key=lambda pair:int(pair[0])))+'};')
    for index,control in enumerate(controls):
        for field in ('name','label'):
            lines.append('static const char *const fdb_region_'+str(index)+'_'+field+'s[] = {'+
                ','.join(text(v[field]) for v in control['variants'])+'};')
    lines.append('static const FdbHostRegion fdb_regions[] = {'+(','.join(
        '{'+text(c['name'])+','+text(c['label'])+','+str(len(c['variants']))+'u,'+str(c['default_index'])+'u,fdb_region_'+str(i)+'_names,fdb_region_'+str(i)+'_labels}'
        for i,c in enumerate(controls)) or '{0}')+'};')
    lines.append('static const char *const fdb_function_names[] = {'+','.join(text(n) for n in functions)+'};')
    fields={'words':prepared['program']['memory']['words'],'width':frame['width'],'height':frame['height'],
        'frame_offset':frame['offset'],'tick_ms':events['tick_ms'],
        **{k:events[k] for k in ('kind','ascii','scan','x','y','buttons','clock','quit_index','keyboard_kind','pointer_kind','clock_kind')},
        'key_count':len(keys),'color_count':len(frame['palette']),'region_count':len(controls),'function_count':len(functions)}
    lines.append('static const FdbHostConfig fdb_config = {'+','.join('.'+k+'='+str(v)+('' if k=='tick_ms' else 'u') for k,v in fields.items())+
        ',.keys=fdb_keys,.colors=fdb_colors,.regions=fdb_regions,.function_names=fdb_function_names,'+
        '.title='+text(plan['title'])+',.help='+text(plan['help'])+',.config_sha256='+text(config_sha)+'};')
    return '\n'.join(lines)+'\n'


PROBE=r'''#include "memory-desktop.h"
#include <stdio.h>
#include <string.h>
static int command(void *context,const FdbHostCommand *c,const uint32_t *payload) {
    FdbHost *h=(FdbHost*)context;(void)payload;
    switch(c->kind) {
    case FDB_CMD_KEY:return fdb_host_key(h,c->a,c->b,(int)c->c,c->clock);
    case FDB_CMD_POINTER:return fdb_host_pointer(h,c->a,c->b,(int32_t)c->c,(int32_t)c->d,c->clock);
    case FDB_CMD_CLOCK:return fdb_host_tick(h,c->clock);
    case FDB_CMD_SELECT:return fdb_host_select(h,c->a,c->b);
    case FDB_CMD_RESIZE:return fdb_host_resize(h,(int)c->a,(int)c->b);
    case FDB_CMD_FOCUS:return fdb_host_focus(h,(int)c->a,c->clock);
    default:return 1;
    }
}
static int capture(void *context,uint8_t *out,uint32_t w,uint32_t h) {
    return fdb_host_render((FdbHost*)context,out,w,h);
}
int main(int argc,char **argv) {
    if(argc!=4 || strcmp(argv[1],"--adapter-test"))return 2;
    FdbHost h;if(fdb_host_open(&h,0))return 3;
    FdbHostPlatform p={command,capture};
    int result=fdb_host_study(&h,argv[2],argv[3],&p,&h);
    fdb_host_destroy(&h);return result;
}
'''


def _commands(target):
    spec=TARGETS[target]
    cc=spec['compiler'];common=[cc,'-std=c11','-O1','-Wall','-Wextra']
    commands=[[*common,*(['-fPIC'] if target=='linux-x64' else []),'-c','memory-runtime.c','-o','memory-runtime.o']]
    if target=='linux-x64':
        commands.extend([[cc,'-shared','memory-runtime.o','-pthread','-o',spec['library']],
            [*common,'memory-desktop-probe.c','memory-desktop.c','memory-runtime.o','-pthread','-o',spec['probe']],
            [*common,spec['adapter'],'memory-desktop.c','memory-runtime.o','-lX11','-pthread','-o',spec['application']]])
    else:
        commands.extend([[cc,'-shared','memory-runtime.o','-static-libgcc','-Wl,--no-insert-timestamp','-Wl,--export-all-symbols','-o',spec['library']],
            [*common,'memory-desktop-probe.c','memory-desktop.c','memory-runtime.o','-static-libgcc','-Wl,--no-insert-timestamp','-o',spec['probe']],
            [*common,spec['adapter'],'memory-desktop.c','memory-runtime.o','-static-libgcc','-Wl,--no-insert-timestamp','-mwindows','-lgdi32','-luser32','-o',spec['application']]])
    return commands


def emit_memory_desktop_shell(project,selections,plan,initial,destination,*,target,cuts=None,regions=None):
    if type(target) is not str or target not in TARGETS:raise ValueError('choose windows-x64 or linux-x64')
    prepared=resolve_memory_shell(project,selections,plan,initial,cuts=cuts,regions=regions)
    if prepared['program']['memory']['words']>4_194_304:raise ValueError('desktop arena budget exceeded')
    event_indices=[prepared['plan']['events'][k] for k in ('kind','ascii','scan','x','y','buttons','clock')]
    if len(set(event_indices))!=7:raise ValueError('desktop event fields must use distinct input words')
    destination=Path(destination).expanduser().absolute()
    if os.path.lexists(destination):raise ValueError('choose a new private desktop output')
    destination=destination.resolve()
    if any((p/'.git').exists() for p in (destination,*destination.parents)):
        raise ValueError('desktop output must remain outside Git')
    spec=TARGETS[target];controls=_controls(prepared)
    config={'plan':prepared['plan'],'region_controls':controls,'module_uil_sha256':digest(prepared['program'])}
    config_bytes=_json(config);config_sha=hashlib.sha256(config_bytes).hexdigest()
    source,realizations,functions=_runtime(prepared,controls,config_sha,target=spec['target'],owner_prelude=_owner(target))
    payloads={'memory-runtime.h':HEADER.encode(),'memory-runtime.c':source.encode(),
        'config.json':config_bytes,'initial.json':_json(initial),
        'memory-host-config.h':_host_config(prepared,controls,functions,config_sha).encode(),
        'memory-desktop-probe.c':PROBE.encode()}
    for name in ('memory-desktop.h','memory-desktop.c',spec['adapter']):
        payloads[name]=files('fdisbull').joinpath('native_runtime/'+name).read_bytes()
    commands=_commands(target)
    manifest={'format':FORMAT,'stage':'source-only','target':spec['target'],'platform':target,'profile':spec['profile'],
        'architecture':'x86-64','program':prepared['program'],'execution_program':prepared['execution_program'],
        'module_uil_sha256':digest(prepared['program']),
        'module_udl_sha256':digest({**prepared['program'],'role':'udl'}),'execution_uil_sha256':digest(prepared['execution_program']),
        'plan':prepared['plan'],'plan_sha256':digest(prepared['plan']),'source_selections':prepared['source_selections'],
        'source_endpoints':prepared['endpoints'],'cuts':prepared['cuts'],'regions':prepared['regions'],
        'realizations':realizations,'runtime':{'function_order':functions,'region_controls':controls,'key_order':sorted(plan['keymap']),
            'config_sha256':config_sha,'ownership':'module-load thread; synchronous guarded transactions; owned host snapshots',
            'study_protocol':'fdisbull-native-desktop-study-1'},
        'library':spec['library'],'application':spec['application'],'probe':spec['probe'],'commands':commands,
        'source_artifacts':{n:hashlib.sha256(b).hexdigest() for n,b in payloads.items()},
        'native_execution':False,'source_to_uil':False,'scope':'source emission only; compilation and native input/view execution are separate gates'}
    destination.mkdir(parents=True,mode=0o700)
    for name,data in payloads.items():(destination/name).write_bytes(data)
    (destination/'native-shell.json').write_bytes(_json(manifest))
    (destination/'source-shell.json').write_bytes(_json(manifest))
    return manifest


def _admit_build(destination):
    destination=Path(destination).expanduser().resolve()
    if any((p/'.git').exists() for p in (destination,*destination.parents)):
        raise ValueError('desktop build must remain outside Git')
    manifest_path=destination/'native-shell.json'
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_nlink!=1:
        raise ValueError('desktop manifest must be an owned regular file')
    manifest=json.loads(manifest_path.read_text())
    platform=manifest.get('platform')
    if manifest.get('format')!=FORMAT or type(platform) is not str or platform not in TARGETS:
        raise ValueError('invalid desktop build')
    spec=TARGETS[platform]
    if any(manifest.get(k)!=spec[k] for k in ('target','profile','application','library','probe')):
        raise ValueError('desktop artifact paths/profile differ')
    if manifest.get('commands')!=_commands(platform):raise ValueError('desktop compiler recipe differs')
    expected={'memory-runtime.h','memory-runtime.c','config.json','initial.json',
        'memory-host-config.h','memory-desktop-probe.c','memory-desktop.h','memory-desktop.c',spec['adapter']}
    if set(manifest.get('source_artifacts',{}))!=expected:raise ValueError('desktop source set differs')
    for name,sha in manifest['source_artifacts'].items():
        path=destination/name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise ValueError('desktop source artifact changed')
    if (digest(manifest['program'])!=manifest['module_uil_sha256'] or
        digest({**manifest['program'],'role':'udl'})!=manifest['module_udl_sha256'] or
        digest(manifest['execution_program'])!=manifest['execution_uil_sha256'] or
        digest(manifest['plan'])!=manifest['plan_sha256'] or
        manifest['runtime']['function_order']!=sorted(manifest['execution_program']['functions'])):
        raise ValueError('desktop source identity differs')
    if hashlib.sha256((destination/'config.json').read_bytes()).hexdigest()!=manifest['runtime']['config_sha256']:
        raise ValueError('desktop config identity differs')
    for name in ('memory-runtime.o',spec['library'],spec['application'],spec['probe']):
        artifact=destination/name
        if artifact.is_symlink() or (artifact.exists() and (not artifact.is_file() or artifact.stat().st_nlink!=1)):
            raise ValueError('desktop artifact must be an owned regular file')
    if 'source_manifest_sha256' in manifest:
        retained=destination/'source-shell.json'
        if retained.is_symlink() or not retained.is_file() or hashlib.sha256(retained.read_bytes()).hexdigest()!=manifest['source_manifest_sha256']:
            raise ValueError('retained desktop source manifest changed')
    return destination,manifest


def seal_memory_desktop_shell(destination,*,compiler_evidence=None):
    destination,manifest=_admit_build(destination)
    source_receipt=destination/'source-shell.json'
    if manifest.get('stage')=='source-only':
        source_bytes=(destination/'native-shell.json').read_bytes()
        if source_receipt.exists():
            if source_receipt.is_symlink() or source_receipt.read_bytes()!=source_bytes:
                raise ValueError('retained desktop source manifest differs')
        else:
            with source_receipt.open('xb') as stream:stream.write(source_bytes)
    import lief
    for name in (manifest['library'],manifest['application'],manifest['probe']):
        path=destination/name
        if manifest['platform']=='windows-x64':
            image=lief.PE.parse(str(path))
            if image is None or image.header.machine!=lief.PE.Header.MACHINE_TYPES.AMD64:
                raise ValueError('desktop output is not AMD64 PE')
            is_dll=bool(int(image.header.characteristics)&0x2000)
            if is_dll!=(name==manifest['library']):raise ValueError('desktop PE DLL/executable kind differs')
            if name==manifest['application'] and int(image.optional_header.subsystem)!=2:
                raise ValueError('desktop Win32 application must use the GUI subsystem')
            if name==manifest['probe'] and int(image.optional_header.subsystem)!=3:
                raise ValueError('desktop Win32 probe must use the console subsystem')
        else:
            image=lief.ELF.parse(str(path))
            if image is None or image.header.machine_type!=lief.ELF.ARCH.X86_64:
                raise ValueError('desktop output is not x86-64 ELF')
            file_type=int(image.header.file_type)
            interpreted=any(int(segment.type)==3 for segment in image.segments)
            if name==manifest['library']:
                if file_type!=3 or interpreted:raise ValueError('desktop ELF library kind differs')
            elif file_type not in (2,3) or not interpreted or not image.entrypoint:
                raise ValueError('desktop ELF program is not an admitted executable')
    artifacts={n:hashlib.sha256((destination/n).read_bytes()).hexdigest()
        for n in [*manifest['source_artifacts'],'memory-runtime.o',manifest['library'],manifest['application'],manifest['probe']]}
    if manifest.get('stage')=='compiled':
        previous={k:v for k,v in manifest['artifacts'].items() if k!='source-shell.json'}
        if artifacts!=previous or (compiler_evidence is not None and compiler_evidence!=manifest.get('compiler')):
            raise ValueError('compiled desktop receipt is immutable; choose a new build')
        return manifest
    artifacts['source-shell.json']=hashlib.sha256(source_receipt.read_bytes()).hexdigest()
    manifest.update(stage='compiled',artifacts=artifacts,
        source_manifest_sha256=artifacts['source-shell.json'],
        compiler=deepcopy(compiler_evidence if compiler_evidence is not None else manifest.get('compiler')),
        artifact_admission='format, architecture and hashes; compiler lineage is supplied evidence',
        scope='compiled native artifacts; original fidelity and native graphics/input require separate execution qualification')
    (destination/'native-shell.json').write_bytes(_json(manifest));return manifest


def compile_memory_desktop_shell(destination,*,c_compiler=None):
    destination,manifest=_admit_build(destination)
    if manifest.get('stage')!='source-only':raise ValueError('compiled desktop receipt is immutable; choose a new build')
    compiler=c_compiler or shutil.which(TARGETS[manifest['platform']]['compiler'])
    if not compiler:raise ValueError('native compiler unavailable; source-only recipe remains unqualified')
    compiler=Path(compiler).resolve();version=subprocess.run([str(compiler),'--version'],capture_output=True,text=True,timeout=10,check=True).stdout.splitlines()[0]
    commands=[]
    for recipe in manifest['commands']:
        command=[str(compiler),*recipe[1:]];commands.append(command)
        run=subprocess.run(command,cwd=destination,capture_output=True,text=True,timeout=180)
        if run.returncode:raise ValueError('desktop compilation failed: '+run.stderr[:3000])
    return seal_memory_desktop_shell(destination,compiler_evidence={'version':version,'commands':commands})


def build_memory_desktop_shell(project,selections,plan,initial,destination,*,target,cuts=None,regions=None,c_compiler=None):
    emit_memory_desktop_shell(project,selections,plan,initial,destination,target=target,cuts=cuts,regions=regions)
    return compile_memory_desktop_shell(destination,c_compiler=c_compiler)


def encode_study(manifest, commands, *, clock=0, x=0, y=0, buttons=0):
    """Encode explicit numeric native commands; IDs remain companion metadata."""
    if type(commands) is not list or len(commands)>4096:raise ValueError('invalid desktop command count')
    frame=manifest['plan']['frame'];words=manifest['program']['memory']['words']
    if any(type(v) is not int for v in (clock,x,y,buttons)) or not 0<=clock<=65535 or not 0<=x<frame['width'] or not 0<=y<frame['height'] or not 0<=buttons<=7:
        raise ValueError('invalid initial desktop services')
    data=bytearray(b'FDBEVT1\0'+struct.pack('<6I',words,len(commands),clock,x,y,buttons))
    names=('kind','a','b','c','d','e','clock','flags')
    for command in commands:
        if type(command) is not dict or 'kind' not in command or set(command)-set(names)-{'payload','id'}:
            raise ValueError('invalid desktop command')
        fields=[]
        for name in names:
            value=command.get(name,0)
            if type(value) is not int or not (-2147483648 if name in ('c','d') else 0)<=value<=0xffffffff:
                raise ValueError('invalid desktop command field')
            fields.append(value&0xffffffff)
        payload=command.get('payload',[])
        if type(payload) is not list or len(payload)>words*2 or any(type(v) is not int or not 0<=v<=0xffffffff for v in payload):
            raise ValueError('invalid desktop command payload')
        if fields[0]>10 or fields[6]>65535 or fields[7]&~7:raise ValueError('invalid desktop command kind/flags/clock')
        data.extend(struct.pack('<9I',*fields,len(payload)))
        if payload:data.extend(struct.pack('<'+str(len(payload))+'I',*payload))
    return bytes(data)


def decode_study(manifest, data):
    """Reject incomplete/trailing frames; keep large arenas as owned u32 arrays."""
    from array import array
    import sys
    if type(data) is not bytes or len(data)<24 or data[:8]!=b'FDBOUT1\0':raise ValueError('invalid desktop result magic')
    view=memoryview(data);at=8
    def take(n):
        nonlocal at
        if n<0 or at+n>len(view):raise ValueError('incomplete desktop result')
        result=view[at:at+n];at+=n;return result
    def u32():return struct.unpack('<I',take(4))[0]
    n,count,regions,functions=(u32() for _ in range(4))
    controls=manifest['runtime']['region_controls'];order=manifest['runtime']['function_order']
    if n!=manifest['program']['memory']['words'] or count>4096 or regions!=len(controls) or functions!=len(order):raise ValueError('desktop result shape differs')
    sizes=[u32() for _ in range(regions)]
    if sizes!=[len(c['variants']) for c in controls]:raise ValueError('desktop region shape differs')
    rows=[];frame=manifest['plan']['frame']
    for index in range(count):
        fields=struct.unpack('<12I',take(48));kind,accepted,committed,closed,low,high,x,y,buttons,width,height,flags=fields
        if (kind>10 or max(accepted,committed,closed)>1 or buttons>7 or
            x>=frame['width'] or y>=frame['height'] or
            not 1<=width<=4096 or not 1<=height<=4096 or flags&~7 or (committed and not accepted)):
            raise ValueError('invalid desktop observation fields')
        selected=[struct.unpack('<i',take(4))[0] for _ in range(regions)]
        if any(v!=-1 if closed else not 0<=v<sizes[i] for i,v in enumerate(selected)):raise ValueError('invalid desktop selection')
        counts={name:struct.unpack('<Q',take(8))[0] for name in order}
        region_counts={control['name']:{variant['name']:struct.unpack('<Q',take(8))[0]
            for variant in control['variants']} for control in controls}
        words=array('I');words.frombytes(take(n*4))
        if words.itemsize!=4:raise ValueError('host u32 carrier differs')
        if sys.byteorder!='little':words.byteswap()
        row={'index':index,'kind':kind,'accepted':bool(accepted),'committed':bool(committed),
            'closed':bool(closed),'revision':low|(high<<32),'mouse_x':x,'mouse_y':y,'buttons':buttons,
            'width':width,'height':height,'flags':flags,'selected':selected,'words':words,
            'invocation_counts':counts,'region_counts':region_counts}
        if flags&1:row['frame_rgba']=bytes(take(frame['width']*frame['height']*4))
        if flags&2:row['view_rgba']=bytes(take(width*height*4))
        rows.append(row)
    if at!=len(data):raise ValueError('trailing desktop observation bytes')
    return rows
