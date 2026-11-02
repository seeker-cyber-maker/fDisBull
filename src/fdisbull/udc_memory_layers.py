"""Persist bounded-memory contracts in the existing immutable snippet database.

This profile has its own validators. Scalar contract execution is unchanged and
continues to refuse this explicitly different behavior kind.
"""
from copy import deepcopy
from pathlib import Path
import re

from .udc_layers import digest, _json

TARGETS = ('wasm32-memory-1', 'webgpu-wgsl-memory-1')


def validate_contract(document):
    from .udc_web_memory import validate_memory_uil
    _json(document)
    allowed = {'format', 'name', 'author', 'inputs', 'outputs', 'behavior', 'effects', 'evidence'}
    if type(document) is not dict or set(document) - allowed or document.get('format') != 'fdisbull-block-contract-1':
        raise ValueError('invalid bounded-memory contract')
    b = document.get('behavior')
    if type(b) is not dict or set(b) != {'kind', 'program', 'function'} or b['kind'] != 'memory-uil':
        raise ValueError('explicit memory-UIL behavior required')
    validate_memory_uil(b['program'])
    if b['program']['role'] != 'uil' or b['function'] not in b['program']['functions']:
        raise ValueError('unknown memory-UIL function or role')
    arena = {'arena': {'type': 'u32-array', 'words': b['program']['memory']['words']}}
    if document.get('inputs') != arena or document.get('outputs') != arena or document.get('effects', []) != []:
        raise ValueError('one owned pure word arena required')
    return deepcopy(document)


def register_contract(project, document, *, author=None):
    validate_contract(document)
    return project.store_contract(document, author=author)


def validate_layer(project, document):
    _json(document)
    if type(document) is not dict or document.get('format') != 'fdisbull-udl-layer-1' or set(document) - {
        'format', 'name', 'author', 'contract', 'snippet', 'implementation', 'assurance', 'evidence'
    }:
        raise ValueError('invalid bounded-memory UDL layer')
    contract = validate_contract(project.contract_info(document.get('contract'), full=True)['document'])
    i = document.get('implementation')
    if type(i) is not dict or set(i) != {'backend', 'target', 'program', 'function'} or i['backend'] != 'memory-uil' or i['target'] not in TARGETS:
        raise ValueError('explicit bounded-memory target required')
    if i['program'] != contract['behavior']['program'] or i['function'] != contract['behavior']['function']:
        raise ValueError('memory backing differs from its exact behavior contract')
    if document.get('snippet') is not None:project.snippet_info(document['snippet'])
    return contract


def register_layer(project, document, *, author=None):
    validate_layer(project,document)
    # The store separately verifies any retained snippet and contract reference.
    return project.store_udl_layer(document, author=author)


def select_layers(project, name, bindings, *, program, target, author='agent'):
    from .udc_web_memory import validate_memory_uil
    validate_memory_uil(program)
    if program['role'] != 'uil' or target not in TARGETS or type(bindings) is not dict or not bindings:
        raise ValueError('invalid memory selection')
    if set(bindings) != set(program['functions']):
        raise ValueError('select every named memory function exactly once')
    for function, ident in bindings.items():
        layer = project.udl_layer_info(ident, full=True)['document']
        # Pure validation, without creating another record.
        contract = validate_layer(project,layer)
        impl = layer['implementation']
        if impl != {'backend': 'memory-uil', 'target': target, 'program': program, 'function': function} or contract['behavior'] != {
            'kind': 'memory-uil', 'program': program, 'function': function
        }:
            raise ValueError('memory selection endpoint differs')
    return project.store_udl_selection({'format': 'fdisbull-udl-selection-1', 'name': name,
        'bindings': deepcopy(bindings), 'program': deepcopy(program), 'target': target, 'author': author}, author=author)


def resolve(project, selection, function):
    selected = project.udl_selection_info(selection, full=True)
    doc = selected['document']
    if set(doc)-{'format','name','author','bindings','program','target'} or doc.get('target') not in TARGETS or function not in doc.get('bindings', {}):
        raise ValueError('unknown memory selection function')
    from .udc_web_memory import validate_memory_uil
    validate_memory_uil(doc.get('program'))
    if doc['program']['role']!='uil' or set(doc['bindings'])!=set(doc['program']['functions']):raise ValueError('invalid persisted memory bindings')
    layer = project.udl_layer_info(doc['bindings'][function], full=True)
    contract = project.contract_info(layer['document']['contract'], full=True)
    validate_layer(project,layer['document'])
    impl = layer['document']['implementation']
    if impl != {'backend': 'memory-uil', 'target': doc['target'], 'program': doc['program'], 'function': function} or contract['document']['behavior'] != {
        'kind': 'memory-uil', 'program': doc['program'], 'function': function
    }:
        raise ValueError('persisted memory endpoint mismatch')
    return doc['program'], doc['target'], {'selection': selected['id'], 'selection_sha256': selected['sha256'],
        'layer': layer['id'], 'layer_sha256': layer['sha256'], 'contract': contract['id'], 'contract_sha256': contract['sha256'],
        'module_uil_sha256': digest(doc['program']), 'assurance': 'exact selected model identity; original/target execution is separate'}


def run_selection(project, selection, function, words):
    from .udc_web_memory import execute_memory_uil
    program, _, identities = resolve(project, selection, function)
    return {**execute_memory_uil(program, function, words), **identities}


def build_selection(project, selection, function, destination):
    from .udc_web_memory import build_memory_block
    program, target, identities = resolve(project, selection, function)
    result = build_memory_block(program, function, target, destination)
    # Keep builder's exact manifest authoritative; selection bindings accompany
    # it rather than rewriting its artifact or execution identities.
    return {'build': result, **identities, 'execution': False}
