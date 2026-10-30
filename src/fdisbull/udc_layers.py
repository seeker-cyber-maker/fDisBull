"""Reusable, persisted block contracts and explicit implementation selection.

Selection pins implementations, not semantic changes. Exact UIL contracts are
checked on each execution; policy contracts explicitly admit implementation
variation. No declaration in a database is silently promoted to a proof.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from .interaction_il import execute_il, validate_il, _typed

_TYPES={'bool'}|{f'{s}{n}' for s in 'ui' for n in (8,16,32,64)}
_NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


class LayerQualificationError(ValueError):
    def __init__(self,message,receipt):
        super().__init__(message);self.receipt=receipt


def _json(document):
    try:raw=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    except (TypeError,ValueError,RecursionError) as exc:raise ValueError('layer documents must be finite JSON') from exc
    if len(raw)>4*1024*1024:raise ValueError('layer document exceeds4MiB')
    return raw


def digest(document):return hashlib.sha256(_json(document)).hexdigest()


def _ports(ports,label):
    if type(ports) is not dict or len(ports)>256 or any(not isinstance(k,str) or not _NAME.fullmatch(k) or v not in _TYPES for k,v in ports.items()):
        raise ValueError(f'invalid {label} typed ports')


def validate_contract(document):
    _json(document)
    if type(document) is not dict or document.get('format')!='fdisbull-block-contract-1':raise ValueError('invalid block contract')
    if set(document)-{'format','name','author','inputs','outputs','behavior','domain','effects','evidence'}:raise ValueError('unknown contract fields')
    _ports(document.get('inputs'),'input');_ports(document.get('outputs'),'output')
    behavior=document.get('behavior')
    if type(behavior) is not dict or behavior.get('kind') not in ('uil','bounded','service'):raise ValueError('unsupported contract behavior')
    if behavior['kind']=='uil':
        if set(behavior)-{'kind','program','inputs','outputs'}:raise ValueError('unknown UIL behavior fields')
        _validate_program_ports(behavior,document)
    elif behavior['kind']=='bounded':
        if set(behavior)-{'kind','bounds','policy'} or type(behavior.get('bounds')) is not dict or set(behavior['bounds'])!=set(document['outputs']):raise ValueError('bounded policy needs every output bound')
        for name,bound in behavior['bounds'].items():_bound(bound,document['outputs'][name])
    else:
        if set(behavior)-{'kind','service','profile'} or not isinstance(behavior.get('service'),str) or not behavior['service']:raise ValueError('invalid logical service contract')
    domain=document.get('domain',{})
    if type(domain) is not dict or set(domain)-set(document['inputs']):raise ValueError('invalid input domain')
    for name,bound in domain.items():_bound(bound,document['inputs'][name])
    return deepcopy(document)


def _bound(bound,typ):
    if type(bound) is not dict or set(bound)!={'min','max'} or not _typed(bound['min'],typ) or not _typed(bound['max'],typ) or bound['min']>bound['max']:
        raise ValueError('invalid typed range bound')


def _validate_program_ports(descriptor,contract):
    program=descriptor.get('program');validate_il(program)
    for side in ('inputs','outputs'):
        mapping=descriptor.get(side,{p:'$'+p for p in contract[side]})
        if type(mapping) is not dict or set(mapping)!=set(contract[side]):raise ValueError('UIL port bindings must be complete')
        for port,var in mapping.items():
            if not isinstance(var,str) or var not in program['variables'] or program['variables'][var]['type']!=contract[side][port]:raise ValueError('UIL port type/binding mismatch')
        if side=='inputs' and len(set(mapping.values()))!=len(mapping):raise ValueError('UIL input bindings require distinct variables')
    return program


def register_contract(project,document,*,author=None):
    validate_contract(document)
    return project.store_contract(document,author=author)


def _contract(project,ident):
    document=project.contract_info(ident,full=True)['document'];validate_contract(document);return document


def _native_code(project,layer):
    implementation=layer['implementation']
    if 'code_hex' in implementation:
        if layer.get('snippet') is not None:raise ValueError('native layer cannot override retained snippet bytes')
        try:code=bytes.fromhex(implementation['code_hex'])
        except (TypeError,ValueError) as exc:raise ValueError('invalid native code bytes') from exc
    else:
        if not layer.get('snippet'):raise ValueError('native layer requires explicit code or a retained snippet')
        snippet=project.snippet_info(layer['snippet'],include_bytes=True)['document']
        if len(snippet['spans'])!=1:raise ValueError('native block requires one contiguous retained span')
        code=bytes.fromhex(snippet['spans'][0]['bytes_hex'])
    if not 1<=len(code)<=65536:raise ValueError('native block code exceeds its budget')
    return code


def _validate_layer(project,document):
    _json(document)
    if type(document) is not dict or document.get('format')!='fdisbull-udl-layer-1':raise ValueError('invalid UDL layer')
    if set(document)-{'format','name','author','contract','snippet','implementation','adapter','assurance','evidence','domain'}:raise ValueError('unknown layer fields')
    contract=_contract(project,document.get('contract'))
    impl=document.get('implementation')
    if type(impl) is not dict:raise ValueError('layer needs an implementation')
    backend=impl.get('backend')
    if backend in ('uil','c-uil'):
        if set(impl)-{'backend','program','inputs','outputs','return','notification_binding'}:raise ValueError('unknown UIL implementation fields')
        _validate_program_ports(impl,contract)
    elif backend=='x86-16':
        if set(impl)-{'backend','code_hex','origin'}:raise ValueError('unknown native16 implementation fields')
        _native_code(project,document)
        if type(document.get('adapter')) is not dict:raise ValueError('native16 layer requires an explicit adapter')
    elif backend in ('message-box-a','debug-string-a'):
        if contract['behavior']['kind']!='service':raise ValueError('service implementation needs a service contract')
        if set(impl)-{'backend','title','messages','default','style'}:raise ValueError('unknown notification implementation fields')
    else:raise ValueError('unsupported layer backend')
    domain=document.get('domain',{})
    if type(domain) is not dict or set(domain)-set(contract['inputs']):raise ValueError('invalid layer input domain')
    for port,bound in domain.items():_bound(bound,contract['inputs'][port])
    return contract


def register_layer(project,document,*,author=None):
    _validate_layer(project,document)
    return project.store_udl_layer(document,author=author)


def select_layers(project,name,bindings,*,program=None,target=None,author='agent'):
    if type(bindings) is not dict or not bindings:raise ValueError('selection requires exact logical bindings')
    for ident in bindings.values():_validate_layer(project,project.udl_layer_info(ident,full=True)['document'])
    document={'format':'fdisbull-udl-selection-1','name':name,'bindings':deepcopy(bindings),'author':author}
    if program is not None:
        if program.get('format')=='fdisbull-module-uil-1':
            from .udc_blueprint import validate_module_uil
            validate_module_uil(project,program)
        else:validate_il(program)
        document['program']=deepcopy(program)
    if target is not None:document['target']=target
    return project.store_udl_selection(document,author=author)


def _inputs(contract,inputs,extra_domain=None):
    if type(inputs) is not dict or set(inputs)!=set(contract['inputs']):raise ValueError('contract inputs must match typed ports exactly')
    if any(not _typed(inputs[p],typ) for p,typ in contract['inputs'].items()):raise ValueError('contract input value/type mismatch')
    for domain in (contract.get('domain',{}),extra_domain or {}):
        for port,bound in domain.items():
            if not bound['min']<=inputs[port]<=bound['max']:raise ValueError('input is outside admitted domain')


def _execute_uil(descriptor,contract,inputs):
    program=_validate_program_ports(descriptor,contract)
    state={k:v['initial'] for k,v in program['variables'].items()}
    for port,var in descriptor.get('inputs',{p:'$'+p for p in contract['inputs']}).items():state[var]=inputs[port]
    result=execute_il(program,state=state,max_steps=4096)
    if result['status']!='complete':raise ValueError('UIL module refused or requires unsupported host effects: '+result.get('error',result['status']))
    outputs={port:result['state'][var] for port,var in descriptor.get('outputs',{p:'$'+p for p in contract['outputs']}).items()}
    return {'outputs':outputs,'events':result['events'],'execution':'shared-il','steps':len(result['visited'])}


def run_layer(project,layer,inputs,*,caller_registers=None,max_steps=10000):
    item=project.udl_layer_info(layer,full=True);document=item['document'];contract=_validate_layer(project,document)
    _inputs(contract,inputs,document.get('domain'))
    impl=document['implementation']
    if impl['backend']=='uil':observed=_execute_uil(impl,contract,inputs)
    elif impl['backend']=='x86-16':
        from .udc_native16 import execute_native16
        observed=execute_native16(_native_code(project,document),impl,document['adapter'],inputs,contract['inputs'],contract['outputs'],max_steps=max_steps,caller_registers=caller_registers)
    else:raise ValueError('compiled C and notification providers execute only in an explicit native shell, not a CPU/model call')
    if set(observed['outputs'])!=set(contract['outputs']) or any(not _typed(observed['outputs'][p],typ) for p,typ in contract['outputs'].items()):raise ValueError('implementation output violates typed contract')
    behavior=contract['behavior'];expected=None
    if behavior['kind']=='uil':
        expected=_execute_uil(behavior,contract,inputs)
        match=observed['outputs']==expected['outputs'] and observed['events']==expected['events']
        comparison='matched_reference_uil'
    elif behavior['kind']=='bounded':
        match=all(b['min']<=observed['outputs'][p]<=b['max'] for p,b in behavior['bounds'].items()) and not observed['events']
        comparison='satisfies_declared_bounded_policy'
    else:raise ValueError('a service contract cannot be executed as a pure module')
    receipt={**observed,'layer':layer,'contract':document['contract'],'inputs':deepcopy(inputs),'comparison':comparison if match else 'counterexample','expected':expected,
             'qualification_scope':'this explicit invocation only; stored assurance is a declaration, not a proof'}
    if not match:raise LayerQualificationError('selected layer violates the fixed contract',receipt)
    return receipt


def run_selection(project,selection,binding,inputs,**options):
    selected=project.udl_selection_info(selection,full=True)['document']
    if binding not in selected['bindings']:raise ValueError('logical binding is absent from selection')
    result=run_layer(project,selected['bindings'][binding],inputs,**options)
    return {**result,'selection':selection,'binding':binding}


def build_selection_shell(project,selection,plan,destination,*,target="windows-x64",service_adapters=None,capture_state=False,c_compiler=None):
    """Build qualified canonical-port functions and admitted notifications.

    Noncanonical port maps and nonempty domains require adapters/admission
    guards outside this first target profile and refuse before emission.
    Callee locals are activation-private; only declared outputs are committed.
    The selected capsule binds immutable database identities and model receipts,
    without claiming native execution or whole-plan/source correspondence.
    """
    import os
    from pathlib import Path
    from .udc_shell import build_windows_shell, _remove_owned_output
    from .udc_qualify import qualify_uil
    if target not in ("windows-x64","linux-x64"):raise ValueError("unsupported native shell target")
    if target=="windows-x64" and (service_adapters is not None or capture_state):raise ValueError("Linux shell adapters/observation cannot be ignored by a Windows target")
    plan=deepcopy(plan)
    selected_info=project.udl_selection_info(selection,full=True)
    selected=selected_info['document'];modules={};proofs={};layers={};contracts={};adapters={}
    for binding,ident in selected['bindings'].items():
        layer_info=project.udl_layer_info(ident,full=True)
        layer=layer_info['document'];contract=_validate_layer(project,layer)
        contract_info=project.contract_info(layer['contract'],full=True)
        if contract.get('domain') or layer.get('domain'):
            raise ValueError('native shell cannot ignore nonempty contract/layer domains; compiled admission guards are unsupported')
        if contract.get('effects'):
            raise ValueError('additional declared contract effects need an explicit native profile')
        impl=deepcopy(layer['implementation'])
        if impl['backend']=='x86-16':raise ValueError('native PE64 output cannot silently embed an emulated16-bit backing')
        if impl['backend'] in ('uil','c-uil'):
            for descriptor in (contract['behavior'],impl):
                for side in ('inputs','outputs'):
                    canonical={name:'$'+name for name in contract[side]}
                    if descriptor.get(side,canonical)!=canonical:
                        raise ValueError('native shell requires canonical port mappings; noncanonical adapters are unsupported')
            output_variables={'$'+name for name in contract['outputs']}
            if impl.get('return') is not None and impl['return'] not in output_variables:
                raise ValueError('native shell return must be a declared output, not an unqualified local')
            if len(output_variables)!=1 and impl.get('return') is not None:
                raise ValueError('native scalar return mapping requires exactly one declared output')
            proof=qualify_uil(contract,{**impl,'backend':'uil'})
            if proof['status']!='equivalent_under_contract':raise LayerQualificationError('native shell backing lacks contract qualification',proof)
            proofs[binding]=proof
            impl.pop('inputs',None);impl.pop('outputs',None)
            # Bind the scalar ABI from the contract, so omitting optional
            # implementation metadata cannot change a caller-visible return.
            if len(output_variables)==1:impl['return']=next(iter(output_variables))
            impl['state_adapter']={'inputs':['$'+name for name in sorted(contract['inputs'])],
                                   'outputs':['$'+name for name in sorted(contract['outputs'])]}
            adapters[binding]=deepcopy(impl['state_adapter'])
        else:
            behavior=contract['behavior']
            if behavior.get('profile'):raise ValueError('native notification profile obligations are unsupported')
            if (behavior.get('kind')!='service' or behavior.get('service') not in ('ui.notify','notification','notify')
                    or contract['outputs'] or len(contract['inputs'])>1
                    or any(typ!='u16' for typ in contract['inputs'].values())):
                raise ValueError('native service profile admits notifications only: no outputs, at most one u16 input')
            proofs[binding]={'status':'declared_notification_provider','backend':impl['backend'],
                             'contract':contract_info['id'],'contract_sha256':contract_info['sha256'],
                             'proof_scope':'explicit notification realization; no automatic service equivalence or native-execution claim'}
        layers[binding]={'id':layer_info['id'],'sha256':layer_info['sha256'],'document':layer}
        contracts[contract_info['id']]={'id':contract_info['id'],'sha256':contract_info['sha256'],'document':contract}
        modules[binding]=impl
    capsule={'format':'fdisbull-selected-shell-capsule-1','complete':True,
             'selection':selected_info['id'],'selection_sha256':selected_info['sha256'],
             'selection_document':selected,'layer_ids':deepcopy(selected['bindings']),
             'layers':layers,'contracts':contracts,'qualification':proofs,'state_adapters':adapters,
             'plan_sha256':digest(plan),'native_build_capsule_sha256':'0'*64,
             'scope':'qualified supplied UIL models and declared notifications; authored orchestration; source recovery/native execution remain separate'}
    # Validate all retained registry/qualification content before emitting any
    # native artifact. The only later substitution is another 64-byte digest.
    _json(capsule)
    if target=='linux-x64':
        from .udc_linux import build_linux_shell
        result=build_linux_shell(plan,modules,destination,service_adapters=service_adapters,capture_state=capture_state,c_compiler=c_compiler)
    else:result=build_windows_shell(plan,modules,destination,c_compiler=c_compiler)
    directory=Path(result['directory']);owned=directory.stat();path=directory/'selection-capsule.json'
    owned_files={}
    for name in (result['output']['path'],'capsule.json'):
        stat=(directory/name).lstat();owned_files[name]=(stat.st_dev,stat.st_ino)
    try:
        capsule['native_build_capsule_sha256']=hashlib.sha256(Path(result['capsule']).read_bytes()).hexdigest()
        encoded=_json(capsule)+b'\n'
        with path.open('xb') as stream:
            stat=os.fstat(stream.fileno());owned_files[path.name]=(stat.st_dev,stat.st_ino)
            stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        os.chmod(path,0o600)
        if path.read_bytes()!=encoded:raise ValueError('selected capsule readback mismatch')
    except BaseException:
        _remove_owned_output(directory,(owned.st_dev,owned.st_ino),owned_files)
        raise
    result['selection']=selected_info['id'];result['selection_sha256']=selected_info['sha256']
    result['layer_ids']=deepcopy(selected['bindings'])
    result['contract_ids']={binding:entry['document']['contract'] for binding,entry in layers.items()}
    result['native_build_qualification']=deepcopy(result['qualification'])
    result['selection_capsule']=str(path);result['selection_capsule_sha256']=hashlib.sha256(encoded).hexdigest()
    result['qualification']=proofs
    return result


def compile_splice_selection(project,selection,recipe,destination,output_name='PROGRAM.COM'):
    """Place reusable native modules through an explicit hash-bound COM recipe.

    Module math contains no target-file offsets. Placement, seed loads/stores
    and continuations are separate target orchestration data.
    """
    from .udc_splice import emit_splice, build_splice, _filename
    _json(recipe)
    if type(recipe) is not dict or recipe.get('format')!='fdisbull-udc-splice-selection-1':raise ValueError('invalid selected-splice recipe')
    if set(recipe)-{'format','source_snippet','placements','data_bindings','qualification_inputs'}:raise ValueError('unknown selected-splice recipe fields')
    source=project.snippet_info(recipe['source_snippet'],include_bytes=True)['document'];parts=source['spans']
    if len(parts)!=1 or parts[0]['space']!='file' or parts[0]['offset']!=0:raise ValueError('splice source must capture one complete retained file')
    original=bytes.fromhex(parts[0]['bytes_hex'])
    if hashlib.sha256(original).hexdigest()!=parts[0]['file_sha256']:raise ValueError('splice source is not its complete retained file')
    if len(original)>65280:raise ValueError('COM source exceeds16-bit capacity')
    selected=project.udl_selection_info(selection,full=True)['document'];patches=[];appended=[];offset=len(original);modules=[]
    placements=recipe.get('placements',[])
    if type(placements) is not list or len(placements)>256:raise ValueError('invalid placement inventory')
    for place in placements:
        if type(place) is not dict or set(place)!={'binding','offset','size','expected_sha256','prologue_hex','epilogue_hex','continuation'}:raise ValueError('invalid module placement')
        binding=place['binding']
        if binding not in selected['bindings']:raise ValueError('placement has no selected module')
        layer_id=selected['bindings'][binding];layer=project.udl_layer_info(layer_id,full=True)['document'];_validate_layer(project,layer)
        if layer['implementation']['backend']!='x86-16':raise ValueError('COM placement requires an x86-16 implementation')
        start,size,continuation=place['offset'],place['size'],place['continuation']
        if any(type(v) is not int for v in (start,size,continuation)) or not 0<=start<=len(original)-size or size<3 or not 0<=continuation<=len(original):raise ValueError('invalid COM placement range')
        code=_native_code(project,layer)
        if layer.get('adapter',{}).get('relocations'):raise ValueError('COM placement cannot silently reuse CPU-provider segment relocations')
        try:prefix,suffix=(bytes.fromhex(place[k]) for k in ('prologue_hex','epilogue_hex'))
        except (TypeError,ValueError) as exc:raise ValueError('invalid placement adapter bytes') from exc
        jump=lambda target,following:b'\xe9'+((target-following)&65535).to_bytes(2,'little')
        payload=prefix+code+suffix
        payload+=jump(continuation,offset+len(payload)+3)
        replacement=jump(offset,start+3)+b'\x90'*(size-3)
        patches.append({'offset':start,'expected_sha256':place['expected_sha256'],'replace_hex':replacement.hex()})
        appended.append({'bytes_hex':payload.hex(),'sha256':hashlib.sha256(payload).hexdigest()})
        modules.append({'binding':binding,'layer':layer_id,'module_sha256':hashlib.sha256(code).hexdigest(),'append_offset':offset,'adapter_prefix_sha256':hashlib.sha256(prefix).hexdigest(),'adapter_suffix_sha256':hashlib.sha256(suffix).hexdigest()})
        offset+=len(payload)
    program=selected.get('program')
    if program is None:raise ValueError('selected splice requires its fixed UIL program')
    if program.get('format')=='fdisbull-module-uil-1':
        from .udc_blueprint import validate_module_uil
        validate_module_uil(project,program)
    else:validate_il(program)
    nodes={};invoked={}
    def visit(body):
        for node in body:
            nodes[node['id']]=node
            if node['op']=='invoke':
                previous=invoked.setdefault(node['binding'],node['contract'])
                if previous!=node['contract']:raise ValueError('one logical binding cannot invoke different contract revisions')
            if node['op']=='if':visit(node['then']);visit(node['else'])
    visit(program['body'])
    for binding,contract_id in invoked.items():
        if binding not in selected['bindings'] or project.udl_layer_info(selected['bindings'][binding],full=True)['document']['contract']!=contract_id:
            raise ValueError('fixed UIL invocation has no selected compatible contract')
    for module in modules:
        doc=project.udl_layer_info(module['layer'],full=True)['document']
        if invoked.get(module['binding'])!=doc['contract']:raise ValueError('module placement is not bound by the fixed UIL')
    if type(recipe.get('data_bindings',[])) is not list or len(recipe.get('data_bindings',[]))>256:raise ValueError('invalid data binding inventory')
    for item in recipe.get('data_bindings',[]):
        if type(item) is not dict or set(item)!={'block','encoding','offsets','expected_sha256'}:raise ValueError('invalid UIL data binding')
        node=nodes.get(item['block'])
        if node is None:raise ValueError('data binding refers to an unknown UIL block')
        if item['encoding']=='ascii-text' and node['op']=='text':
            try:data=program['resources'][node['resource']]['text'].encode('ascii')
            except (KeyError,UnicodeError) as exc:raise ValueError('text binding requires an ASCII UIL resource') from exc
        elif item['encoding']=='u8-constant' and node['op']=='set' and type(node.get('value')) is int and 0<=node['value']<=255:
            data=bytes([node['value']])
        else:raise ValueError('unsupported UIL data binding encoding/node')
        if type(item['offsets']) is not list or type(item['expected_sha256']) is not list or len(data)!=len(item['offsets']) or len(data)!=len(item['expected_sha256']):raise ValueError('UIL data does not fit its declared placement')
        patches.extend({'offset':offset,'expected_sha256':expected,'replace_hex':bytes([value]).hex()} for offset,expected,value in zip(item['offsets'],item['expected_sha256'],data))
    if not patches:raise ValueError('selected splice contains no declared changes')
    checks=[]
    if type(recipe.get('qualification_inputs',[])) is not list or len(recipe.get('qualification_inputs',[]))>256:raise ValueError('too many qualification inputs')
    for item in recipe.get('qualification_inputs',[]):
        if type(item) is not dict or set(item)!={'binding','inputs'}:raise ValueError('invalid qualification input')
        checks.append(run_selection(project,selection,item['binding'],item['inputs']))
    manifest={'format':'fdisbull-udc-splice-1','source_sha256':hashlib.sha256(original).hexdigest(),'patches':patches,'appended':appended,'max_output_bytes':65280}
    _filename(output_name)
    if output_name.lower()=='selection-capsule.json':raise ValueError('output name conflicts with the selection capsule')
    output,preflight=build_splice(original,manifest)
    capsule={'format':'fdisbull-selected-splice-capsule-1','selection':selection,'selection_document':selected,'uil_sha256':digest(program),'source_snippet':recipe['source_snippet'],'recipe':deepcopy(recipe),'modules':modules,'qualification_invocations':checks,'manifest':manifest,'output':{'name':output_name,'size':len(output),'sha256':preflight['output_sha256']},'qualification_scope':'explicit invocations only; source callsite/data mapping remains an authored orchestration assertion'}
    payload=_json(capsule)+b'\n'
    result=emit_splice(original,manifest,destination,output_name=output_name)
    from pathlib import Path
    target=Path(result['output']);owned=target.stat();capsule_path=target/'selection-capsule.json'
    identities={}
    for name in (output_name,'splice-receipt.json'):
        path=target/name;stat=path.stat();identities[path]=(stat.st_dev,stat.st_ino)
    try:
        with capsule_path.open('xb') as stream:
            stat=stream.fileno()
            import os
            identity=os.fstat(stat);identities[capsule_path]=(identity.st_dev,identity.st_ino)
            stream.write(payload);stream.flush();os.fsync(stat)
        if capsule_path.read_bytes()!=payload:raise ValueError('selection capsule readback differs')
    except BaseException:
        for path,identity in identities.items():
            try:
                current=path.lstat()
                if (current.st_dev,current.st_ino)==identity:path.unlink()
            except FileNotFoundError:pass
        try:
            current=target.lstat()
            if (current.st_dev,current.st_ino)==(owned.st_dev,owned.st_ino):target.rmdir()
        except OSError:pass
        raise
    return {**result,'selection':selection,'modules':modules,'selection_capsule':str(capsule_path),'selection_capsule_sha256':hashlib.sha256(capsule_path.read_bytes()).hexdigest()}
