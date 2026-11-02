"""Explicit pure word-update regions over a preserved canonical memory UIL.

This deliberately small profile supports one store expression per region.  The
source update and each realization therefore charge exactly one UIL statement.
An intentional behavior variant is an authored policy choice, never an exact
source-equivalence claim. Existing exact-memory contracts are not widened.
"""
from copy import deepcopy

from .udc_layers import _json, digest
from .udc_web_memory import NAME, OPS, TARGETS, validate_memory_uil

FORMAT = 'fdisbull-memory-regions-1'
RESOLUTION = 'fdisbull-memory-region-resolution-1'
ASSURANCES = {'exact-source-region', 'intentional-behavior-variant'}


def _fields(value, required, optional=()):
    if type(value) is not dict or not set(required) <= set(value) or set(value)-set(required)-set(optional):
        raise ValueError('invalid memory-region fields')


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _name(value):
    if type(value) is not str or not NAME.fullmatch(value):
        raise ValueError('invalid memory-region name')


def _label(value):
    if type(value) is not str or not 1 <= len(value) <= 100:
        raise ValueError('invalid memory-region label')


def _plain(value):
    if type(value) is dict:
        return {key:_plain(item) for key,item in value.items() if key not in {'id','evidence'}}
    if type(value) is list:
        return [_plain(item) for item in value]
    return value


def _nodes(body):
    for node in body:
        yield node
        if node['op'] == 'if':
            yield from _nodes(node['then']);yield from _nodes(node['else'])
        elif node['op'] == 'while':
            yield from _nodes(node['body'])


def _expression(value, reads):
    if _integer(value, 0, 0xffffffff):
        return
    if type(value) is not dict:
        raise ValueError('memory-region expression requires unsigned words')
    if set(value) == {'load'}:
        if not _integer(value['load'],0,0xffffffff) or value['load'] not in reads:
            raise ValueError('memory-region load exceeds declared reads')
    elif set(value) == {'op','left','right'} and value['op'] in OPS:
        _expression(value['left'],reads);_expression(value['right'],reads)
    else:
        raise ValueError('memory-region expressions cannot depend on locals or dynamic addresses')


def _store(node, region):
    if node['op'] != 'store' or type(node['index']) is not int or node['index'] != region['output']['index']:
        raise ValueError('memory-region must store its one declared output')
    _expression(node['value'],set(region['reads']))


def _source(program, region):
    _fields(region,('name','source','reads','output'))
    _name(region['name'])
    if region['name'] in program['functions']:
        raise ValueError('memory-region name collides with canonical function')
    source=region['source'];_fields(source,('function','entry','count'))
    if (type(source['function']) is not str or source['function'] not in program['functions'] or
            type(source['entry']) is not str or not source['entry'] or type(source['count']) is not int or source['count'] != 1):
        raise ValueError('memory-region source must name exactly one statement')
    reads=region['reads'];words=program['memory']['words']
    if (type(reads) is not list or len(reads) > 64 or
            any(not _integer(index,0,words-1) for index in reads) or len(set(reads)) != len(reads)):
        raise ValueError('invalid memory-region read footprint')
    output=region['output'];_fields(output,('index','min','max'))
    if (not _integer(output['index'],0,words-1) or not _integer(output['min'],0,0xffffffff) or
            not _integer(output['max'],output['min'],0xffffffff)):
        raise ValueError('invalid memory-region output domain')
    matches=[node for node in _nodes(program['functions'][source['function']]['body']) if node.get('id') == source['entry']]
    if len(matches) != 1:
        raise ValueError('unknown or ambiguous memory-region source statement')
    _store(matches[0],region)
    return matches[0]


def validate_contract(document):
    _json(document)
    _fields(document,('format','name','inputs','outputs','behavior'),('author','effects','evidence'))
    if document['format'] != 'fdisbull-block-contract-1':
        raise ValueError('invalid memory-region contract format')
    behavior=document['behavior'];_fields(behavior,('kind','program','region'))
    if behavior['kind'] != 'memory-region':
        raise ValueError('explicit memory-region behavior required')
    program=validate_memory_uil(behavior['program'])
    if program['role'] != 'uil':
        raise ValueError('memory-region requires canonical UIL')
    _source(program,behavior['region'])
    arena={'arena':{'type':'u32-array','words':program['memory']['words']}}
    if document['inputs'] != arena or document['outputs'] != arena or document.get('effects',[]) != []:
        raise ValueError('memory-region requires one pure owned arena')
    return deepcopy(document)


def register_contract(project, document, *, author=None):
    validate_contract(document)
    return project.store_contract(document,author=author)


def validate_layer(project, document):
    _json(document)
    _fields(document,('format','name','contract','implementation','assurance'),('author','snippet','evidence'))
    if (document['format'] != 'fdisbull-udl-layer-1' or type(document['assurance']) is not str or
            document['assurance'] not in ASSURANCES):
        raise ValueError('memory-region layer needs an explicit assurance')
    contract=validate_contract(project.contract_info(document['contract'],full=True)['document'])
    behavior=contract['behavior'];source_program=behavior['program'];region=behavior['region']
    implementation=document['implementation'];_fields(implementation,('backend','target','program','function'))
    if (implementation['backend'] != 'memory-region' or implementation['target'] not in TARGETS or
            implementation['function'] != region['name']):
        raise ValueError('invalid memory-region implementation target')
    program=validate_memory_uil(implementation['program'])
    function=region['name']
    if (program['role'] != 'uil' or program['memory'] != source_program['memory'] or program['variables'] != {} or
            set(program['functions']) != {function} or program['functions'][function]['max_steps'] != 1 or
            len(program['functions'][function]['body']) != 1):
        raise ValueError('memory-region implementation requires one one-step function')
    body=program['functions'][function]['body'];_store(body[0],region)
    exact=_plain(body[0]) == _plain(_source(source_program,region))
    if exact != (document['assurance'] == 'exact-source-region'):
        raise ValueError('memory-region assurance differs from selected expression')
    if document.get('snippet') is not None:
        project.snippet_info(document['snippet'])
    return contract


def register_layer(project, document, *, author=None):
    validate_layer(project,document)
    return project.store_udl_layer(document,author=author)


def select_layers(project, name, bindings, *, program, target, author='agent'):
    canonical=validate_memory_uil(program)
    if canonical['role'] != 'uil' or target not in TARGETS or type(bindings) is not dict or not 1 <= len(bindings) <= 16:
        raise ValueError('invalid memory-region selection')
    for region_name,ident in bindings.items():
        _name(region_name)
        layer=project.udl_layer_info(ident,full=True)['document']
        contract=validate_layer(project,layer)
        if (contract['behavior']['program'] != canonical or contract['behavior']['region']['name'] != region_name or
                layer['implementation']['target'] != target):
            raise ValueError('memory-region selection endpoint differs')
    return project.store_udl_selection({'format':'fdisbull-udl-selection-1','name':name,
        'bindings':deepcopy(bindings),'program':canonical,'target':target,'author':author},author=author)


def resolve(project, selection, region_name):
    selected=project.udl_selection_info(selection,full=True);document=selected['document']
    _fields(document,('format','name','bindings','program','target'),('author',))
    if (document['format'] != 'fdisbull-udl-selection-1' or document['target'] not in TARGETS or
            type(document['bindings']) is not dict or not 1 <= len(document['bindings']) <= 16 or
            type(region_name) is not str or region_name not in document['bindings']):
        raise ValueError('unknown memory-region selection')
    canonical=validate_memory_uil(document['program'])
    if canonical['role'] != 'uil':raise ValueError('memory-region selection requires UIL')
    selected_layer=None;selected_contract=None
    # Revalidate the full selection, including endpoints not requested now.
    for name,ident in document['bindings'].items():
        _name(name)
        layer=project.udl_layer_info(ident,full=True)
        contract=project.contract_info(layer['document']['contract'],full=True)
        validate_layer(project,layer['document'])
        if (contract['document']['behavior']['program'] != canonical or
                contract['document']['behavior']['region']['name'] != name or
                layer['document']['implementation']['target'] != document['target']):
            raise ValueError('persisted memory-region endpoint mismatch')
        if name == region_name:selected_layer,selected_contract=layer,contract
    implementation=selected_layer['document']['implementation']
    identities={'selection':selected['id'],'selection_sha256':selected['sha256'],
        'layer':selected_layer['id'],'layer_sha256':selected_layer['sha256'],
        'contract':selected_contract['id'],'contract_sha256':selected_contract['sha256'],
        'module_uil_sha256':digest(canonical),'implementation_uil_sha256':digest(implementation['program']),
        'assurance':selected_layer['document']['assurance'],'region':deepcopy(selected_contract['document']['behavior']['region'])}
    return deepcopy(implementation['program']),document['target'],identities


def prepare_regions(project, program, document):
    canonical=validate_memory_uil(program);_json(document)
    _fields(document,('format','module_uil_sha256','allow_behavior_variants','slots'))
    if (canonical['role'] != 'uil' or document['format'] != FORMAT or document['module_uil_sha256'] != digest(canonical) or
            type(document['allow_behavior_variants']) is not bool or type(document['slots']) is not dict or
            not 1 <= len(document['slots']) <= 16 or len(canonical['functions'])+len(document['slots']) > 32):
        raise ValueError('invalid memory-region plan')
    execution=deepcopy(canonical);slots={}
    for name,slot in document['slots'].items():
        _name(name);_fields(slot,('label','default','variants'));_label(slot['label'])
        if name in canonical['functions'] or type(slot['variants']) is not dict or not 1 <= len(slot['variants']) <= 16:
            raise ValueError('invalid memory-region slot')
        if type(slot['default']) is not str or slot['default'] not in slot['variants']:
            raise ValueError('memory-region default variant missing')
        variants={};descriptor=None
        for variant_name,variant in slot['variants'].items():
            _name(variant_name);_fields(variant,('label','selections'));_label(variant['label'])
            if type(variant['selections']) is not dict or set(variant['selections']) != {'wasm','webgpu'}:
                raise ValueError('select both region target profiles')
            identities={};implementation=None;assurance=None
            for backend,target in zip(('wasm','webgpu'),TARGETS):
                resolved,selected_target,identity=resolve(project,variant['selections'][backend],name)
                if selected_target != target or identity['module_uil_sha256'] != digest(canonical):
                    raise ValueError('memory-region plan source or target mismatch')
                if descriptor is not None and identity['region'] != descriptor:
                    raise ValueError('memory-region variants must share the exact source descriptor')
                descriptor=identity['region']
                if implementation is not None and (resolved != implementation or identity['assurance'] != assurance):
                    raise ValueError('memory-region target realizations must share program and assurance')
                implementation=resolved;assurance=identity['assurance'];identities[backend]=identity
            if assurance != 'exact-source-region' and not document['allow_behavior_variants']:
                raise ValueError('intentional memory-region variants require explicit opt-in')
            variants[variant_name]={'label':variant['label'],'assurance':assurance,'program':implementation,
                'function':name,'identities':identities}
        if variants[slot['default']]['assurance'] != 'exact-source-region':
            raise ValueError('memory-region default must preserve exact source')
        execution['functions'][name]={'max_steps':1,'body':[_plain(_source(canonical,descriptor))]}
        slots[name]={'label':slot['label'],'default':slot['default'],'region':descriptor,'variants':variants}
    execution=validate_memory_uil(execution)
    return deepcopy({'format':RESOLUTION,'document':document,'region_plan_sha256':digest(document),
        'module_uil_sha256':digest(canonical),'execution_program':execution,
        'execution_uil_sha256':digest(execution),'slots':slots})
