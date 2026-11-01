"""Agent-facing common UIL operations, separate from legacy profile commands."""
from .common_uil import (load_json, digest, validate_program, validate_presentation,
                         validate_orchestration, validate_realization, fold_function, expand_fold)
from .uil_runtime import execute_program
from .uil_store import validate_package


def _document(value):
    return load_json(value) if isinstance(value,str) else value


def invoke_common(method, params):
    p = dict(params)
    if method in ('uil-store','uil-info','uil-list'):
        from .project import Project
        path = p.pop('project')
        with Project(path) as project:
            if method == 'uil-info':
                revision = p.pop('revision'); full = p.pop('full',False)
                if p: raise ValueError('unknown uil-info parameter')
                return project.uil_package_info(revision,full=full)
            if method == 'uil-list':
                limit = p.pop('limit',100); offset = p.pop('offset',0)
                if p: raise ValueError('unknown uil-list parameter')
                return project.uil_packages(limit=limit,offset=offset)
            name = p.pop('name'); package = _document(p.pop('package'))
            version = p.pop('version',None); parent = p.pop('parent',None); author = p.pop('author','agent')
            if p: raise ValueError('unknown uil-store parameter')
            return project.store_uil_package(name,package,version=version,parent=parent,author=author)
    if method == 'uil-catalog':
        from .uil_catalog import build_catalog
        blocks = _document(p.pop('blocks'))
        if p: raise ValueError('unknown uil-catalog parameter')
        return build_catalog(blocks)
    if method in ('uil-fold','uil-expand'):
        program = _document(p.pop('program'))
        if method == 'uil-fold':
            function = p.pop('function'); semantic = p.pop('semantic_id')
            if p: raise ValueError('unknown uil-fold parameter')
            return fold_function(program,function,semantic)
        recovery = _document(p.pop('recovery'))
        if p: raise ValueError('unknown uil-expand parameter')
        return {'program':expand_fold(program,recovery)}
    if method == 'uil-check' and 'package' in p:
        package = _document(p.pop('package'))
        if p: raise ValueError('unknown uil-check parameter')
        validate_package(package)
        return {'status':'valid','package_sha256':digest(package),'runtime_execution':False}
    program = _document(p.pop('program'))
    if method == 'uil-check' and type(program) is dict and program.get('format') == 'fdisbull-common-uil-package-1':
        if p: raise ValueError('unknown uil-check parameter')
        validate_package(program)
        return {'status':'valid','package_sha256':digest(program),'runtime_execution':False}
    validate_program(program)
    presentation = _document(p.pop('presentation')) if 'presentation' in p else None
    catalog = _document(p.pop('catalog')) if 'catalog' in p else None
    orchestration = _document(p.pop('orchestration')) if 'orchestration' in p else None
    if method == 'uil-check':
        if p: raise ValueError('unknown uil-check parameter')
        if presentation is not None: validate_presentation(program,presentation)
        if catalog is not None or orchestration is not None:
            if catalog is None or orchestration is None: raise ValueError('catalog and orchestration are required together')
            if presentation is None: validate_orchestration(program,catalog,orchestration)
            else: validate_realization(program,presentation,catalog,orchestration)
        return {'status':'valid','program_sha256':digest(program),'runtime_execution':False}
    if presentation is None: raise ValueError('presentation bindings are required')
    if method == 'uil-run':
        inputs = _document(p.pop('inputs')) if 'inputs' in p else None
        max_steps = p.pop('max_steps',4000000)
        if p: raise ValueError('unknown uil-run parameter')
        return execute_program(program,presentation,orchestration,catalog,inputs,max_steps)
    if method == 'uil-compile':
        from .uil_codegen import compile_program
        output = p.pop('output'); target = p.pop('target','python')
        if p: raise ValueError('unknown uil-compile parameter')
        if catalog is None or orchestration is None: raise ValueError('compilation needs a catalog and orchestration')
        return compile_program(program,presentation,catalog,orchestration,output,target=target)
    raise ValueError('unknown common UIL method')
