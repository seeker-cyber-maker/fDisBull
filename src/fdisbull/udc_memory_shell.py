"""Build an owned canvas/input shell around exact persisted memory selections."""
from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import tempfile

from .udc_layers import digest
from .udc_memory_layers import resolve, TARGETS

FORMAT = 'fdisbull-memory-browser-1'


def validate_arena(plan,words):
    """Admission of initial/diagnostic state, mirrored at the runtime boundary."""
    for g in plan['guards']:
        if not g['min']<=words[g['index']]<=g['max']:raise ValueError('arena fails state guard')
    for g in plan.get('array_guards',[]):
        length=words[g['length_index']]
        if length>g['capacity']:raise ValueError('array prefix exceeds capacity')
        values=words[g['offset']:g['offset']+length]
        if any(not g['min']<=v<=g['max'] for v in values) or (g['unique'] and len(set(values))!=len(values)):raise ValueError('array values outside domain or duplicate')
        columns=g['adjacent_columns']
        for a,b in zip(values,values[1:]):
            if not (abs(a-b)==columns or abs(a-b)==1 and a//columns==b//columns):raise ValueError('array prefix is not adjacent')
        e=g['exclude'];value=words[e['index']]
        if words[e['when_index']]==e['when_value'] and (not g['min']<=value<=g['max'] or value in values):raise ValueError('excluded value outside domain or overlaps array')
    frame=plan['frame']
    if any(str(v) not in frame['palette'] for v in words[frame['offset']:frame['offset']+frame['width']*frame['height']]):raise ValueError('frame has unknown palette index')
    return True


def validate_plan(plan, program):
    required = {'format', 'title', 'help', 'initialize', 'concurrency', 'bindings', 'inputs', 'outputs', 'commit_ranges',
                'replace_ranges', 'scratch_ranges', 'guards', 'render', 'frame', 'events', 'keymap', 'logic_functions'}
    if type(plan) is not dict or not required<=set(plan) or set(plan)-required-{'array_guards'} or plan['format'] != 'fdisbull-memory-orchestration-1' or plan['concurrency'] != 'ordered-events':
        raise ValueError('invalid memory orchestration plan')
    n = program['memory']['words']
    integer = lambda x: type(x) is int
    def index(i):
        if not integer(i) or not 0 <= i < n: raise ValueError('plan index outside arena')
    def ranges(values):
        if type(values) is not list or not values: raise ValueError('nonempty output ranges required')
        seen = set()
        for item in values:
            if type(item) is not list or len(item) != 2: raise ValueError('invalid output range')
            start, count = item
            if not integer(start) or not integer(count) or count < 1 or start < 0 or start + count > n: raise ValueError('range outside arena')
            selected = set(range(start, start + count))
            if seen & selected: raise ValueError('overlapping output ranges')
            seen |= selected
        return seen
    if type(plan['title']) is not str or not 1 <= len(plan['title']) <= 100: raise ValueError('invalid canvas title')
    if type(plan['help']) is not str or len(plan['help'])>2048 or plan['initialize'] not in program['functions']: raise ValueError('invalid initialization/help')
    if plan['bindings'] != {fn: 'wasm' for fn in program['functions']}: raise ValueError('initial bindings must cover each function')
    if type(plan['inputs']) is not list or len(plan['inputs']) != len(set(plan['inputs'])): raise ValueError('invalid host inputs')
    for i in plan['inputs']: index(i)
    if type(plan['outputs']) is not dict or set(plan['outputs']) != set(program['functions']): raise ValueError('every function needs its output footprint')
    commits = ranges(plan['commit_ranges']); replacement = ranges(plan['replace_ranges']); scratch=ranges(plan['scratch_ranges'])
    if not replacement <= commits or set(plan['inputs']) & (commits|scratch) or commits&scratch: raise ValueError('host inputs and scratch must not be committed')
    for values in plan['outputs'].values():
        if not ranges(values) <= commits|scratch: raise ValueError('function output outside declared footprint')
    if type(plan['guards']) is not list: raise ValueError('invalid state guards')
    for g in plan['guards']:
        if type(g) is not dict or set(g) != {'index', 'min', 'max'}: raise ValueError('invalid state guard')
        index(g['index'])
        if not all(integer(g[k]) for k in ('min', 'max')) or not 0 <= g['min'] <= g['max'] <= 0xffffffff: raise ValueError('invalid guard bounds')
    arrays=plan.get('array_guards',[])
    if type(arrays) is not list or len(arrays)>32:raise ValueError('invalid array guards')
    for g in arrays:
        if type(g) is not dict or set(g)!={'offset','length_index','capacity','min','max','unique','adjacent_columns','exclude'}:raise ValueError('invalid array guard')
        index(g['length_index']);index(g['offset'])
        if not integer(g['capacity']) or not 1<=g['capacity']<=n-g['offset'] or not all(integer(g[k]) for k in ('min','max','adjacent_columns')) or not 0<=g['min']<=g['max']<=0xffffffff or not 1<=g['adjacent_columns']<=1024 or type(g['unique']) is not bool:raise ValueError('invalid array guard domain')
        e=g['exclude']
        if type(e) is not dict or set(e)!={'index','when_index','when_value'}:raise ValueError('invalid array exclusion')
        index(e['index']);index(e['when_index'])
        if not integer(e['when_value']) or not 0<=e['when_value']<=0xffffffff:raise ValueError('invalid exclusion condition')
    render = plan['render']
    if type(render) is not dict or set(render) != {'function', 'when_nonzero'} or render['function'] not in program['functions']: raise ValueError('invalid render binding')
    index(render['when_nonzero'])
    frame = plan['frame']
    if type(frame) is not dict or set(frame) != {'offset', 'width', 'height', 'palette'}: raise ValueError('invalid indexed frame')
    if not integer(frame['width']) or not integer(frame['height']) or not 1 <= frame['width'] <= 1024 or not 1 <= frame['height'] <= 1024: raise ValueError('invalid frame dimensions')
    if not integer(frame['offset']) or not 0<=frame['offset']<n or frame['offset']+frame['width']*frame['height']>n:raise ValueError('frame outside arena')
    pixels = set(range(frame['offset'], frame['offset'] + frame['width'] * frame['height']))
    if not pixels or not pixels <= commits: raise ValueError('frame must be committed arena output')
    palette = frame['palette']
    if type(palette) is not dict or '0' not in palette: raise ValueError('indexed palette required')
    for key, rgb in palette.items():
        if not key.isdigit() or str(int(key)) != key or not 0 <= int(key) <= 255 or type(rgb) is not list or len(rgb) != 3 or any(not integer(v) or not 0 <= v <= 255 for v in rgb): raise ValueError('invalid palette color')
    e = plan['events']
    if type(e) is not dict or set(e) != {'function', 'kind', 'ascii', 'scan', 'x', 'y', 'buttons', 'clock', 'quit_index', 'keyboard_kind', 'pointer_kind', 'clock_kind', 'tick_ms'} or e['function'] not in program['functions']: raise ValueError('invalid host event adapter')
    for key in ('kind', 'ascii', 'scan', 'x', 'y', 'buttons', 'clock'):
        index(e[key])
        if e[key] not in plan['inputs']: raise ValueError('event input is not admitted')
    index(e['quit_index'])
    if any(not integer(e[k]) or not 0 <= e[k] <= 0xffffffff for k in ('keyboard_kind','pointer_kind','clock_kind')) or type(e['tick_ms']) not in (int, float) or not 1 <= e['tick_ms'] <= 1000: raise ValueError('invalid clock/event constants')
    if type(plan['keymap']) is not dict or len(plan['keymap']) > 256: raise ValueError('invalid keyboard map')
    for code, v in plan['keymap'].items():
        if type(code) is not str or len(code) > 64 or type(v) is not dict or set(v) != {'ascii','scan'} or any(not integer(x) or not 0 <= x <= 255 for x in v.values()): raise ValueError('invalid key binding')
    if type(plan['logic_functions']) is not list or not plan['logic_functions'] or not set(plan['logic_functions']) <= set(program['functions']): raise ValueError('invalid logic bindings')
    return deepcopy(plan)


def resolve_memory_shell(project, selections, plan, initial, *, cuts=None, regions=None):
    """Resolve source identities and orchestration independently of a target.

    Stored web selections are source provenance, not native-target receipts.
    Every consumer emits its own explicitly identified realization.
    """
    if type(selections) is not dict or set(selections) != {'wasm', 'webgpu'}: raise ValueError('select both memory providers')
    first = project.udl_selection_info(selections['wasm'], full=True)['document']
    program = first['program']; execution_program = program; resolved_regions = None
    if regions is not None:
        from .udc_memory_regions import prepare_regions
        resolved_regions = prepare_regions(project, program, regions)
        execution_program = resolved_regions['execution_program']
    normalized = validate_plan(plan, execution_program)
    lowered = None
    if cuts is not None:
        from .udc_memory_cuts import lower_memory_cuts
        execution_cuts = cuts
        if resolved_regions is not None:
            if type(cuts) is not dict or set(cuts) != {'format','module_uil_sha256','cuts'} or cuts['format'] != 'fdisbull-memory-cuts-2' or cuts['module_uil_sha256'] != digest(program):
                raise ValueError('named regions require canonical-source cut plan version 2')
            if type(cuts['cuts']) is not list or any(type(cut) is not dict or cut.get('caller') not in program['functions'] for cut in cuts['cuts']):
                raise ValueError('named-region cuts require canonical source callers')
            execution_cuts = {**cuts, 'format':'fdisbull-memory-cuts-1', 'module_uil_sha256':digest(execution_program)}
        lowered = lower_memory_cuts(execution_program, execution_cuts)
    elif resolved_regions is not None:
        raise ValueError('named regions require explicit source cut boundaries')
    if resolved_regions is not None:
        for name,slot in resolved_regions['slots'].items():
            if normalized['outputs'][name] != [[slot['region']['output']['index'],1]]:
                raise ValueError('region plan output must match its one-word contract')
    if type(initial) is not list or len(initial) != program['memory']['words'] or any(type(v) is not int or not 0 <= v <= 0xffffffff for v in initial): raise ValueError('invalid initial word arena')
    validate_arena(normalized,initial)
    endpoints = {}
    for backend, target in zip(('wasm', 'webgpu'), TARGETS):
        endpoints[backend] = {}
        for function in sorted(program['functions']):
            resolved, selected_target, identity = resolve(project, selections[backend], function)
            if resolved != program or selected_target != target:
                raise ValueError('memory sources need identical UIL and declared targets')
            endpoints[backend][function] = identity
    return {'program':deepcopy(program), 'execution_program':deepcopy(execution_program),
        'plan':normalized, 'initial':deepcopy(initial), 'cuts':lowered,
        'regions':resolved_regions, 'source_cut_document':deepcopy(cuts),
        'endpoints':endpoints, 'source_selections':deepcopy(selections)}


def build_memory_shell(project, selections, plan, initial, destination, *, cuts=None, regions=None):
    from .udc_web_memory import build_memory_block
    prepared = resolve_memory_shell(project, selections, plan, initial, cuts=cuts, regions=regions)
    program = prepared['program']; execution_program = prepared['execution_program']
    normalized = prepared['plan']; initial = prepared['initial']
    lowered = prepared['cuts']; resolved_regions = prepared['regions']
    destination = Path(destination).expanduser().absolute()
    if os.path.lexists(destination): raise ValueError('choose a new private memory shell output')
    destination = destination.resolve()
    if any((p / '.git').exists() for p in (destination, *destination.parents)): raise ValueError('memory shell output must be outside Git')
    artifacts = {name: files('fdisbull').joinpath('web_runtime/' + name).read_bytes() for name in ('memory.mjs','memory-shell.mjs','memory-canvas.mjs','memory-index.html')}
    artifacts['index.html'] = artifacts.pop('memory-index.html')
    artifacts['initial.json'] = (json.dumps(initial,separators=(',',':'))+'\n').encode()
    variants = {}; endpoints = prepared['endpoints']; cut_variants = {}; region_variants = {}
    with tempfile.TemporaryDirectory(prefix='fdisbull-memory-shell-') as temp:
        for backend, target in zip(('wasm', 'webgpu'), TARGETS):
            variants[backend] = {}
            for function in sorted(program['functions']):
                directory = 'blocks/' + backend + '/' + function
                output = Path(temp) / backend / function
                output.parent.mkdir(exist_ok=True)
                build = build_memory_block(program, function, target, output, report_steps=lowered is not None)
                variants[backend][function] = {'directory':directory, 'build':build}
                for file in output.iterdir(): artifacts[directory + '/' + file.name] = file.read_bytes()
            if lowered is not None:
                cut_variants[backend] = {}
                for function, cut in lowered['functions'].items():
                    cut_variants[backend][function] = {}
                    for name, phase in cut['phases'].items():
                        directory = 'phases/' + backend + '/' + function + '/' + name
                        output = Path(temp) / 'phases' / backend / function / name
                        output.parent.mkdir(parents=True, exist_ok=True)
                        build = build_memory_block(phase['program'], function, target, output,
                            report_steps=True, capture_locals=[cut['token_local']])
                        cut_variants[backend][function][name] = {'directory':directory, 'build':build}
                        for file in output.iterdir(): artifacts[directory + '/' + file.name] = file.read_bytes()
            if resolved_regions is not None:
                region_variants[backend] = {}
                for function, slot in resolved_regions['slots'].items():
                    region_variants[backend][function] = {}
                    for name, variant in slot['variants'].items():
                        directory = 'regions/' + backend + '/' + function + '/' + name
                        output = Path(temp) / 'regions' / backend / function / name
                        output.parent.mkdir(parents=True, exist_ok=True)
                        build = build_memory_block(variant['program'], function, target, output, report_steps=True)
                        region_variants[backend][function][name] = {'directory':directory, 'build':build}
                        for file in output.iterdir(): artifacts[directory + '/' + file.name] = file.read_bytes()
    manifest = {'format':FORMAT,'module_uil_sha256':digest(program),'program':program,'plan':normalized,
        'plan_sha256':digest(normalized),'variants':variants,'endpoints':endpoints,
        'artifacts':{name:hashlib.sha256(data).hexdigest() for name,data in artifacts.items()},
        'execution':False,'source_to_uil':False,'scope':'owned word arena; ordered input events; staged logic/render; guarded atomic commit'}
    if lowered is not None:
        manifest.update(cuts=lowered, cuts_sha256=digest(lowered), cut_variants=cut_variants)
    if resolved_regions is not None:
        manifest.update(regions=resolved_regions, regions_sha256=digest(resolved_regions),
            execution_program=execution_program, execution_uil_sha256=digest(execution_program),
            source_cut_document=deepcopy(cuts), source_cut_plan_sha256=digest(cuts), region_variants=region_variants)
    destination.mkdir(parents=True,mode=0o700,exist_ok=False)
    for name,data in artifacts.items():
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    (destination/'memory-shell.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
