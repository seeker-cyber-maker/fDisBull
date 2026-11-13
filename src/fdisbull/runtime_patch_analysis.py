"""Bind temporal byte interpretations to unchanged captured-region evidence."""
import hashlib
import json

from .pe_path_transfer import _qualified_trace
from .pe_region_equivalence import compare_pe_regions


def _artifact(project, identifier, kind):
    row = project.db.execute(
        'SELECT a.*,r.version AS source_version FROM debug_artifacts a '
        'JOIN debug_runs r ON r.id=a.run WHERE a.id=?', (identifier,)).fetchone()
    if row is None or row['kind'] != kind:
        raise ValueError('Expected stored ' + kind + ' artifact')
    raw = bytes(row['data'])
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError('Stored ' + ('trace' if kind == 'trace' else 'capture') + ' hash mismatch')
    return row, json.loads(raw)


def _bound_trace(project, version, artifact):
    selected = project.version(version)
    record = project._runtime_record(selected['id'])
    if record is None or record['kind'] != 'runtime-capture':
        raise ValueError('Comparison requires an unmodified runtime capture interpretation')
    capture_row, capture = _artifact(project, record['artifact'], 'code-snapshot')
    if (capture_row['sha256'] != record['artifact_sha256']
            or capture_row['run'] != record['run']
            or capture_row['source_version'] != record['source_version']
            or capture.get('identity') != record['identity']
            or project.digest(project.regions(selected['id'])) != selected['sha256']):
        raise ValueError('Temporal capture or mapped-byte identity mismatch')
    row, trace = _artifact(project, artifact, 'trace')
    bits = _qualified_trace(trace)
    source = project.version(record['source_version'])
    if (bits != project.bits or trace.get('complete') is not True
            or row['run'] != record['run'] or row['source_version'] != source['id']
            or ('run' in trace and trace['run'] != row['run'])
            or trace['version'] != source['id']
            or trace['mapping']['source_sha256'] != project.meta['source_sha256']
            or trace['mapping']['version_sha256'] != source['sha256']
            or record['source_version_sha256'] != source['sha256']):
        raise ValueError('Complete trace and capture must share their owning source and run')
    identity = record['identity']
    if identity.get('backend') != 'wine-qemu' or identity.get('cpu_mode') != 'long64':
        raise ValueError('Runtime patch analysis requires a qualified Wine/QEMU capture')
    if any(int(event['address'], 16) - int(event['project_address'], 16) != identity['delta']
           for event in trace['events']):
        raise ValueError('Trace runtime sites differ from the capture mapping')
    for key, captured in (('static_image_base', 'project_base'), ('runtime_image_base', 'runtime_base')):
        if key in trace['mapping'] and int(trace['mapping'][key], 16) != int(identity[captured], 16):
            raise ValueError('Trace image bases differ from the capture mapping')
    view = project.debug_trace_view(artifact, version=selected['id'])
    if any(not item.get('byte_provenance', {}).get('fully_observed') for item in view['events']):
        raise ValueError('Compared region and exit boundary must be fully observed in the capture')
    if any(item['bytes_match'] is not True or item['analysis_match'] is not True
           for item in view['events']):
        raise ValueError('Trace instruction bytes and analysis must match the observed capture')
    return trace, {
        'version': selected['id'], 'version_sha256': selected['sha256'],
        'source_version': source['id'], 'source_version_sha256': source['sha256'],
        'source_sha256': project.meta['source_sha256'], 'run': row['run'],
        'capture': record['artifact'], 'capture_sha256': capture_row['sha256'],
        'trace': artifact, 'trace_sha256': row['sha256'], 'view': record['view'],
        'capture_address': hex(record['address']), 'capture_size': record['size'],
        'execution_proven': False, 'trace_view': view,
    }


def compare_runtime_code(project, baseline_version, layer_version, baseline_trace, layer_trace, *,
                         contract, correspondence=None, baseline_memory=None, layer_memory=None,
                         timeout_ms=1000):
    """Compare evidenced PE64 regions from two preserved runtime interpretations.

    Native source versions and events are never relabeled as temporal versions.
    A matching capture only qualifies its observed span, including the regional
    exit boundary. The existing solver still checks the actual transitions.
    """
    if project.meta['format'] != 'PE' or project.arch != 'x86' or project.bits != 64:
        raise ValueError('Runtime regional patch analysis currently requires an x86-64 PE project')
    baseline, a = _bound_trace(project, baseline_version, baseline_trace)
    layer, b = _bound_trace(project, layer_version, layer_trace)
    if a['source_version'] != b['source_version']:
        raise ValueError('Runtime interpretations must derive from the same immutable source version')
    regional = compare_pe_regions(baseline, layer, contract=contract,
        same_source=correspondence is None, correspondence=correspondence,
        baseline_memory=baseline_memory, layer_memory=layer_memory, timeout_ms=timeout_ms)
    return {'format': 'fdisbull-runtime-patch-analysis-1', 'baseline': a, 'layer': b,
            'regional': regional, 'semantic_equivalence': None,
            'scope': 'Compared captured PE64 paths and explicit live-state/RAM contract; '
                     'temporal IDs identify byte interpretations, not whole executed versions. '
                     'Uncaptured code, other paths, external effects and timing remain unknown'}


def compare_runtime_functions(project, baseline_version, layer_version, baseline_paths, layer_paths, *,
                              contract, timeout_ms=5000):
    """Bind one observed code epoch per family, then prove coverage and effects."""
    from .pe_function_recovery import compare_pe_functions
    from .pe_region_equivalence import _contract
    if project.meta['format'] != 'PE' or project.arch != 'x86' or project.bits != 64:
        raise ValueError('Runtime function recovery currently requires an x86-64 PE project')
    _, addresses, _ = _contract(contract, 64)
    documents, receipts = [], []
    for version, paths in ((baseline_version, baseline_paths), (layer_version, layer_paths)):
        if not isinstance(paths, list) or not 1 <= len(paths) <= 8:
            raise ValueError('Function recovery requires 1..8 stored paths per code epoch')
        group, references = [], []
        for path in paths:
            if not isinstance(path, dict) or set(path) != {'trace', 'memory'}:
                raise ValueError('Stored function paths require trace artifact and memory evidence')
            trace, receipt = _bound_trace(project, version, path['trace'])
            record = project._runtime_record(receipt['version'])
            start = record['address'] + record['identity']['delta']
            if any(start <= address < start + record['size'] for address in addresses):
                raise ValueError('Declared function memory overlaps its observed code epoch')
            group.append({'trace': trace, 'memory': path['memory']})
            references.append(receipt)
        documents.append(group)
        receipts.append({'version': references[0]['version'],
                         'version_sha256': references[0]['version_sha256'], 'paths': references,
                         'execution_proven': False})
    if receipts[0]['paths'][0]['source_version'] != receipts[1]['paths'][0]['source_version']:
        raise ValueError('Function epochs must derive from the same immutable source version')
    function = compare_pe_functions(*documents, contract=contract, timeout_ms=timeout_ms)
    return {'format': 'fdisbull-runtime-function-analysis-1',
            'baseline': receipts[0], 'layer': receipts[1], 'function': function,
            'semantic_equivalence': None,
            'scope': 'Whole-function recovery per stable captured epoch under an explicit call frame and private RAM; '
                     'native source identities and earlier evidence remain unchanged'}
