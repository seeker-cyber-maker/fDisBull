"""Original-backed, bounded KQ1 AGI host trials.

The model never dispatches an arbitrary callback. This adapter advances the
already admitted original invocation, consumes real handler returns, and
compares a declared state projection. It is not a game scheduler or renderer.
"""
from copy import deepcopy
from hashlib import sha256
import re

from .agi_dos import AGIDOSMonitor
from .agi_effects import CONTRACT, object_state, validate_context
from .agi_lift import lift_logic
from .agi_picture import extract_v2_resource
from .agi_resources import bind_native_view, capture_view, logic_messages
from .interaction_il import execute_il

_SCALAR=re.compile(r'^\$agi_([vf])(0|[1-9][0-9]{0,2})$')
_FLAGS=('drawn','ignore_blocks','fixed_priority','ignore_horizon','update','cycling',
        'animated','motion_bit','on_water','ignore_objects','update_pos','on_land',
        'dont_update','fixed_loop','didnt_move','adjust_ego')
_CYCLES=('normal','end','reverse_loop','reverse')
_MOTIONS=('normal','wander','follow')


def capture_state(monitor,names,raw=None):
    """Read explicit AGI scalar names, including high-bit-first packed flags."""
    raw=monitor.snapshot() if raw is None else raw
    data=bytes.fromhex(raw['data_0009_013f_hex']);state={}
    if len(data)!=0x137:raise ValueError('incomplete native AGI scalar capture')
    for name in names:
        match=_SCALAR.fullmatch(name) if isinstance(name,str) else None
        if not match or int(match[2])>255:raise ValueError('invalid native AGI scalar name')
        index=int(match[2])
        state[name]=data[index] if match[1]=='v' else bool(data[0x100+(index>>3)]&(0x80>>(index&7)))
    return state


class AGIDOSHostAdapter:
    """One original DOS invocation, bound to an immutable lifted leaf routine.

    Construct at the initial evaluator fetch. A failed/unknown attempt requires
    external reconciliation or an explicit checkpoint restoration and new
    adapter. Calling run again only reads the retained result; it never retries.
    Source resources, contexts, screenshots and model checkpoints stay private.
    """
    def __init__(self,monitor,projection,*,viewdir,volume_dir,dialogue_key=None):
        if dialogue_key is not None and dialogue_key not in ('enter','escape'):
            raise ValueError('dialogue_key must be enter, escape or None')
        if not isinstance(monitor,AGIDOSMonitor) or not monitor.prefetch:
            raise ValueError('an original DOS initial-fetch monitor is required')
        if projection.get('calls') or projection.get('opaque_operations'):
            raise ValueError('host adapter requires a fully modeled leaf routine')
        self.monitor=monitor;self.session=monitor.session
        self.viewdir,self.volume_dir=viewdir,volume_dir
        self.dialogue_key=dialogue_key
        self.projection=deepcopy(projection);self.document=projection['uil']
        self._payloads={};self._views={};self._report=None
        self._view_bindings={};self.native_view_captures={}
        raw=monitor.snapshot();self.initial=capture_state(monitor,self.document['variables'],raw)
        rebuilt=lift_logic(monitor.resource,initial_state=self.initial,control_flow='compact',
                           effect_profile='agi-2.917')
        if rebuilt!=projection:raise ValueError('projection does not match original source and captured initial state')
        self.context=self._context(raw)
        self._initial_raw=raw

    def _read(self,offset,size):
        if not 0<=offset<=65535 or not 0<=size<=65536-offset:raise ValueError('native data reference outside segment')
        return self.monitor._read(self.monitor.ds*16+offset,size)

    def _view(self,number):
        if number not in self._views:
            item=capture_view(self.viewdir,self.volume_dir,number,profile='2.917')
            payload=extract_v2_resource(self.viewdir,self.volume_dir,number)['payload']
            if sha256(payload).hexdigest()!=item['metadata']['sha256']:raise ValueError('view source changed during capture')
            self._views[number]=item['metadata'];self._payloads[number]=payload
        return deepcopy(self._views[number])

    def _loaded(self):
        pointer=int.from_bytes(self._read(0xff2,2),'little');seen=set();views={}
        while pointer:
            if pointer in seen or len(seen)>=256:raise ValueError('invalid loaded-view chain')
            seen.add(pointer);node=self._read(pointer,5);n=node[2];data=int.from_bytes(node[3:5],'little')
            if n in views or not data:raise ValueError('ambiguous loaded view')
            self._view(n)
            native=self._read(data,len(self._payloads[n]))
            binding=bind_native_view(self._payloads[n],native)
            key=(n,binding['source_sha256'],binding['runtime_sha256'])
            if key not in self._view_bindings:
                if len(self._view_bindings)>=1024:raise ValueError('native VIEW version budget exhausted')
                self._view_bindings[key]={'view':n,**binding}
                self.native_view_captures[binding['runtime_sha256']]=native
            views[n]=data;pointer=int.from_bytes(node[:2],'little')
        return views

    def _object(self,raw):
        b=bytes.fromhex(raw)
        def word(pos):return int.from_bytes(b[pos:pos+2],'little')
        def signed(pos):return int.from_bytes(b[pos:pos+2],'little',signed=True)
        if b[0x22]>=len(_MOTIONS) or b[0x23]>=len(_CYCLES):raise ValueError('unsupported native motion/cycle')
        previous=word(0x12)
        dimensions=self._read(previous,2) if previous else bytes(2)
        # view_replaced has no qualified original storage. The two dimensions
        # with a null previous-cel pointer are explicit model conventions.
        # They are excluded from native equality below, never native facts.
        return object_state(x=signed(3),y=signed(5),prev_x=signed(0x16),prev_y=signed(0x18),
            width=word(0x1a),height=word(0x1c),prev_width=dimensions[0],prev_height=dimensions[1],
            view=b[7],loop=b[0xa],cel=b[0xe],loop_count=b[0xb],cel_count=b[0xf],
            direction=b[0x21],step_size=b[0x1e],motion=_MOTIONS[b[0x22]],cycle=_CYCLES[b[0x23]],
            follow_step=b[0x27],follow_flag=f'$agi_f{b[0x28]}',follow_count=b[0x29],view_replaced=False,
            flags=[name for bit,name in enumerate(_FLAGS) if word(0x25)&(1<<bit)])

    def _context(self,raw):
        def coherent():
            status=self.session.call('session.status')
            if status.get('state')!='stopped' or any(raw['status'].get(k)!=status.get(k) for k in ('state_revision','frame_id','mode_id')):
                raise ValueError('native context changed during capture')
        coherent()
        loaded=self._loaded();views={str(n):self._view(n) for n in loaded}
        for item in self.projection['effect_operations']:
            block=next(b for c in self.document['continuations'].values() for b in c['body'] if b['id']==item['block_id'])
            for key in ('object','first','second'):
                if key in block['args'] and block['args'][key] not in (0,13):raise ValueError('unqualified native object')
            if 'view' in block['args']:
                n=block['args']['view'];views[str(n)]=self._view(n)
        data=bytes.fromhex(raw['data_0009_013f_hex'])
        word=lambda address:int.from_bytes(data[address-9:address-7],'little')
        if word(0x139) not in (0,1):raise ValueError('invalid native player-control state')
        objects={str(n):self._object(raw[f'object_{n}_hex']) for n in (0,13)}
        cels=set()
        for n,base in loaded.items():
            payload=self._payloads[n]
            for loop in range(payload[2]):
                start=int.from_bytes(payload[5+2*loop:7+2*loop],'little')
                for cel in range(payload[start]):
                    cels.add(base+start+int.from_bytes(payload[start+1+2*cel:start+3+2*cel],'little'))
        for n,obj in objects.items():
            record=bytes.fromhex(raw[f'object_{n}_hex'])
            w=lambda pos:int.from_bytes(record[pos:pos+2],'little')
            if w(0x12) and w(0x12) not in cels:raise ValueError('previous cel pointer is not a bound native resource')
            if not w(8):
                if w(0xc) or w(0x10) or obj['width'] or obj['height'] or 'drawn' in obj['flags']:
                    raise ValueError('native object lacks its view/cel binding')
                continue
            number=obj['view']
            if loaded.get(number)!=w(8):raise ValueError('native object view pointer differs from bound resource')
            payload=self._payloads[number]
            if obj['loop']>=payload[2]:raise ValueError('native object loop is outside bound view')
            loop=int.from_bytes(payload[5+2*obj['loop']:7+2*obj['loop']],'little')
            if obj['cel']>=payload[loop]:raise ValueError('native object cel is outside bound loop')
            cel=loop+int.from_bytes(payload[loop+1+2*obj['cel']:loop+3+2*obj['cel']],'little')
            if (w(0xc),w(0x10),obj['loop_count'],obj['cel_count'],obj['width'],obj['height'])!=(
                loaded[number]+loop,loaded[number]+cel,payload[2],payload[loop],payload[cel],payload[cel+1]):
                raise ValueError('native object cel pointer or geometry differs from bound resource')
        coherent();self.monitor._check_code()
        return validate_context(dict(contract=CONTRACT,horizon=word(0x12d),player_control=bool(word(0x139)),
            objects=objects,views=views,loaded_views=sorted(loaded),messages=logic_messages(self.monitor.resource)))

    @staticmethod
    def _differences(model,state,context,raw):
        differences=[];excluded=[]
        if model['state'].keys()!=state.keys():
            differences.append({'field':'state.keys','expected':sorted(model['state']),'actual':sorted(state)})
        for field in ('objects','views','messages'):
            if model['effect_context'][field].keys()!=context[field].keys():
                differences.append({'field':field+'.keys','expected':sorted(model['effect_context'][field]),'actual':sorted(context[field])})
        for field in ('views','messages'):
            if model['effect_context'][field]!=context[field]:
                differences.append({'field':field,'reason':'bound capture differs'})
        for key in model['state']:
            if model['state'][key]!=state.get(key):differences.append({'field':key,'expected':model['state'][key],'actual':state.get(key)})
        expected=model['effect_context']
        for field in ('horizon','player_control','loaded_views'):
            a,b=expected[field],context[field]
            if (sorted(a) if field=='loaded_views' else a)!=(sorted(b) if field=='loaded_views' else b):
                differences.append({'field':field,'expected':a,'actual':b})
        for n,obj in expected['objects'].items():
            if n not in context['objects']:continue
            native=context['objects'][n];record=bytes.fromhex(raw[f'object_{n}_hex'])
            for field,value in obj.items():
                path=f'objects.{n}.{field}'
                if field=='view_replaced' or field in ('prev_width','prev_height') and not int.from_bytes(record[0x12:0x14],'little') or field.startswith('follow_') and obj['motion']!='follow':
                    excluded.append(path);continue
                actual=native[field]
                if (sorted(value) if field=='flags' else value)!=(sorted(actual) if field=='flags' else actual):
                    differences.append({'field':path,'expected':value,'actual':actual})
        return differences,excluded

    def readback(self):
        return deepcopy(self._report)

    def run(self):
        if self._report is not None:return self.readback()
        report=self._report=dict(format='fdisbull-agi-original-host-trial-1',status='incomplete',complete=False,
            qualification='selected_original_invocation_projection',identity=deepcopy(self.monitor.identity),
            native_execution=False,attempts=[],host_completions=[],source_offsets=[],differences=[],excluded_fields=[])
        try:
            current=self.monitor.snapshot()
            if capture_state(self.monitor,self.initial,current)!=self.initial or self._context(current)!=self.context:
                raise ValueError('native initial state changed after adapter capture')
            model=execute_il(self.document,self.initial,effect_context=self.context)
            report['model']=model
            cursor=0
            def advance(expected,dialogue_key=None):
                nonlocal cursor
                raw=self.monitor.snapshot();offset,_=self.monitor._location(raw['registers'])
                if offset!=expected:raise ValueError('original source path differs from model')
                report['attempts'].append({'offset':offset,'status':'attempted'})
                report['native_execution_attempted']=True
                if not report['native_execution']:report['native_execution']=None
                result=self.monitor.step(dialogue_key=dialogue_key)
                report['attempts'][-1]=result
                if result.get('stop'):report['native_execution']=True
                if result['status'] not in ('completed','returned'):raise ValueError('original operation did not reach its qualified boundary')
                report['native_execution']=True;report['source_offsets'].append(offset);cursor+=1
                return result
            while model['status']!='refused':
                expected=[self.projection['block_sources'][item['continuation']]['offset'] for item in model['control_trace']]
                if model['status']=='pending_host':
                    request=model.get('host_request')
                    if request is None:raise ValueError('unsupported non-AGI host plan')
                    site=next(item for item in self.projection['effect_operations'] if item['block_id']==request['block_id'])
                    while cursor<len(expected)-1:advance(expected[cursor])
                    if expected[-1]!=site['offset']:raise ValueError('host request source occurrence mismatch')
                    kind=request['operation']
                    key=self.dialogue_key if kind=='print' and not request['details']['output_mode'] and not request['details']['window_timer'] else None
                    result=advance(site['offset'],key);raw=result['raw_after'];context=self._context(raw)
                    if kind=='draw':
                        obj=context['objects'][str(request['details']['object'])];answer={k:obj[k] for k in ('x','y')}
                    elif kind=='erase':answer={}
                    elif kind=='print':answer={'shown' if request['details']['output_mode'] else 'dismissed':True}
                    else:raise ValueError('unknown host operation')
                    # A returned original handler is evidence; screenshots are
                    # retained artifacts, not assumed text/pixel recognition.
                    completion=dict(request_id=request['request_id'],status='completed',result=answer)
                    receipt=dict(completion,source_offset=site['offset'],operation=kind,frame_status='pending',
                        basis='observed original handler return',visual_verified=False,identity=deepcopy(self.monitor.identity))
                    if 'dialogue' in result:receipt['dialogue']=deepcopy(result['dialogue'])
                    report['host_completions'].append(receipt)
                    try:
                        receipt['frame']=self.session.screenshot(f'agi-host-{len(report["host_completions"])-1}.png',hooks=False)
                        receipt['frame_status']='captured'
                    except Exception as exc:
                        receipt.update(frame_status='failed',frame_error=str(exc))
                        raise
                    model=execute_il(self.document,checkpoint=model['checkpoint'],host_result=completion)
                    report['model']=model
                    continue
                if model['status']!='complete':raise ValueError('incomplete model execution')
                final=None
                while cursor<len(expected):final=advance(expected[cursor])
                if final is None or final['status']!='returned':raise ValueError('original logic return was not observed')
                raw=final['raw_after'];state=capture_state(self.monitor,self.initial,raw);context=self._context(raw)
                differences,excluded=self._differences(model,state,context,raw)
                report.update(status='difference' if differences else 'verified',complete=not differences,
                    differences=differences,excluded_fields=excluded,observed_state=state,
                    observed_effect_context=context,return_boundary='original evaluator returned to its caller')
                break
            else:raise ValueError('model refused: '+model.get('error','unknown'))
        except Exception as exc:
            report.update(status='incomplete',error=str(exc),recovery_required=bool(report['attempts']))
        finally:
            report['view_bindings']=deepcopy(list(self._view_bindings.values()))
            if report['status']!='verified' and report['attempts']:report['recovery_required']=True
        return self.readback()
