"""Pure identity and instruction checks for revalidated owned LE stop sequences.

The recipe retains an immutable admission, not an OS/task lifetime certificate.
Each qualified boundary rechecks its descriptor, code anchor and pointer sites.
"""
from copy import deepcopy
import hashlib
import json

from iced_x86 import Decoder

from .qemu_dos_le_match import _descriptors

CAPTURE_FORMAT = 'fdisbull-qemu-dos-le-capture-1'
SOURCE_SCOPE = 'owned-revalidated-LE-stop-sequence'
BINDING_FORMAT = 'fdisbull-qemu-dos-le-binding-1'
_ADMISSION = 'fdisbull-qemu-dos-le-admission-1'
_MATCH = 'fdisbull-qemu-dos-le-source-match-1'


def _require(value, message):
    if not value:
        raise ValueError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _raw(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError('LE binding requires canonical JSON values') from error


def _uint(value, maximum=2**32 - 1):
    return type(value) is int and 0 <= value <= maximum


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _text(value):
    return isinstance(value, str) and 1 <= len(value) <= 256 and all(32 <= ord(c) < 127 for c in value)


def _image(image):
    _require(image.format == 'LE' and isinstance(image.source_bytes, bytes), 'LE binding requires a retained runtime LE image')
    meta = image.metadata['le']
    _require(meta.get('runtime_source_profile') == 'fdisbull-le-runtime-source-1' and
             _digest(image.metadata.get('source_sha256')) and _sha(image.source_bytes) == image.metadata['source_sha256'],
             'LE binding source/profile identity differs')
    origin = meta['carrier']['application_offset']
    _require(_uint(origin) and origin < len(image.source_bytes) and
             _sha(image.source_bytes[origin:]) == meta['application_source_sha256'], 'LE application identity differs')
    objects = {obj['index']: obj for obj in meta['objects']}
    regions = {obj['index']: next(r for r in image.regions if r.start == obj['virtual_address']) for obj in objects.values()}
    return meta, objects, regions


def _span(image, span, objects, regions):
    index, offset, size = span['object_index'], span['object_offset'], span['length']
    _require(type(index) is int and index in objects and _uint(offset) and _uint(size) and size > 0 and
             span['object_id'] == 'le:' + str(index) and span.get('source_view') == 'embedded-le', 'Invalid LE admission source span')
    source = regions[index].data[offset:offset + size]
    _require(len(source) == size and _sha(source) == span['expected_sha256'] and _digest(span['observed_sha256']),
             'LE admission source span hash differs')
    expected = [(max(offset, f['source_offset']) - offset,
                 min(offset + size, f['source_offset'] + f['width']) - max(offset, f['source_offset']))
                for f in image.metadata['le']['fixups'] if f['source_object'] == index and
                f['source_offset'] < offset + size and f['source_offset'] + f['width'] > offset]
    _require(span['fixups'] == [dict(offset=a, length=n) for a, n in expected], 'LE admission fixup exclusions differ')
    excluded = {i for a, n in expected for i in range(a, a + n)}
    comparable = bytes(b for i, b in enumerate(source) if i not in excluded)
    _require(comparable and span['compared_bytes'] == len(comparable) and
             span['comparable_sha256'] == _sha(comparable), 'LE admission comparable source bytes differ')
    _require(span['preferred_address'] == objects[index]['virtual_address'] + offset, 'LE preferred source location differs')
    return index, offset, size


def _make_recipe(image, admission, binding_id):
    meta, objects, regions = _image(image)
    _require(_text(binding_id) and isinstance(admission, dict) and len(_raw(admission)) <= 4 * 1024**2,
             'Invalid LE binding identity/admission size')
    _require(admission.get('format') == _ADMISSION and admission.get('backend') == 'qemu-dos' and
             admission.get('status') == 'admitted' and admission.get('source_view') == 'embedded-le' and
             admission.get('lifetime_qualified') is False and admission.get('live_mapping_installed') is False,
             'LE binding requires bounded stopped source admission')
    _require(_text(admission.get('run')) and _text(admission.get('capture_epoch')) and
             type(admission.get('version')) is int and admission['version'] > 0 and _digest(admission.get('version_sha256')),
             'LE admission run/version identity differs')
    _require(admission.get('source_sha256') == image.metadata['source_sha256'], 'LE admission source identity differs')
    observed = admission['observation']
    _require(observed['format'] == _MATCH and observed['source']['source_sha256'] == admission['source_sha256'] and
             observed['source']['application_source_sha256'] == meta['application_source_sha256'] and
             observed['source']['carrier'] == meta['carrier'], 'LE admission view identity differs')
    evidence = observed['identity_evidence']
    _require(evidence['lifetime_qualified'] is False and evidence['cpu'] == admission['observed_cpu'] and
             evidence['gdt_sha256'] == admission['gdt']['sha256'] and _digest(evidence['gdt_sha256']),
             'LE admission CPU/GDT identity differs')
    cpu = admission['observed_cpu']; table = admission['gdt']
    _require(isinstance(cpu, dict) and cpu.get('mode') == 'protected' and type(cpu.get('bits')) is int and cpu['bits'] == 32 and
             all(_uint(cpu.get(k), 65535 if k == 'cs' else 2**32-1)
                 for k in ('cs', 'ip', 'cs_base', 'cs_limit', 'cs_attributes')) and
             cpu['cs'] & ~7 and not cpu['cs'] & 4 and cpu['ip'] + 95 <= cpu['cs_limit'], 'Malformed LE admission CPU context')
    _require(_uint(table['base']) and _uint(table['limit'], 65535) and
             table['base'] + table['limit'] + 1 <= 2**32 and (cpu['cs'] & ~7) + 8 <= table['limit'] + 1,
             'Malformed LE admission descriptor-table extent')
    descriptor = evidence['current_descriptor']
    raw_descriptor = bytes.fromhex(descriptor['raw_hex'])
    decoded = _descriptors(raw_descriptor)
    _require(len(raw_descriptor) == 8 and len(decoded) == 1, 'Malformed LE admission descriptor')
    expected_descriptor = dict(decoded[0], value=cpu['cs'] & ~7)
    _require(_raw(descriptor) == _raw(expected_descriptor) and descriptor['bits'] == 32 and
             not descriptor['attributes'] & 0x200000 and descriptor['base'] == cpu['cs_base'] and
             descriptor['limit'] == cpu['cs_limit'] and descriptor['attributes'] == cpu['cs_attributes'] & 0xf0ff00,
             'LE admission CS cache and descriptor differ')
    index = evidence['code_object']
    _require(type(index) is int and index in objects and objects[index]['bits'] == 32 and objects[index]['executable'],
             'LE admission code object differs')
    placements = {index: dict(object_index=index, runtime_base=evidence['runtime_code_base'], bits=32)}
    for proof in evidence['object_proofs']:
        target = proof['object_index']
        _require(type(target) is int and target in objects and target not in placements, 'LE admission has ambiguous object placement')
        obj = objects[target]
        if 'runtime_base' in proof:
            _require(not obj['executable'] and len(proof['offset32_sites']) == 8, 'LE data placement requires eight pointer witnesses')
            sites = {f['source_offset']: f for f in meta['fixups'] if f['source_object'] == index and
                     f['source_type'] == 'offset32' and f['target_object'] == target and f.get('addend') is None}
            _require([p['source_offset'] for p in proof['offset32_sites']] == sorted(sites)[:8], 'LE pointer witness sites differ')
            base = proof['runtime_base']
            for witness in proof['offset32_sites']:
                fixup = sites[witness['source_offset']]
                _require(_uint(base) and witness['target_offset'] == fixup['target_offset'] and
                         _uint(witness['value']) and witness['value'] == base + fixup['target_offset'], 'LE data pointer witness differs')
        else:
            _require(obj['bits'] == 16 and obj['executable'] and proof['execution_observed'] is False and
                     proof['symbolic_operands_qualified'] is False, 'LE bridge placement qualification differs')
            base = proof['descriptor']['base']
        placements[target] = dict(object_index=target, runtime_base=base, bits=obj['bits'])
    ordered = sorted(placements.values(), key=lambda p: p['object_index'])
    intervals = []
    for placement in ordered:
        index = placement['object_index']; base = placement['runtime_base']
        _require(_uint(base) and base + objects[index]['virtual_size'] <= 2**32, 'LE runtime object placement exceeds its address domain')
        intervals.append((base, base + objects[index]['virtual_size']))
    intervals.sort()
    _require(not any(a[1] > b[0] for a, b in zip(intervals, intervals[1:])), 'LE runtime object placements overlap')
    spans = observed['source_spans']
    _require(isinstance(spans, list) and 1 <= len(spans) <= 512, 'LE admission source spans unavailable')
    for span in spans:
        index, offset, _ = _span(image, span, objects, regions)
        _require(index in placements and span['address'] == placements[index]['runtime_base'] + offset,
                 'LE source span runtime placement differs')
    index, offset, size = _span(image, evidence['current_pc_source_match'], objects, regions)
    _require(index == evidence['code_object'] and size == 96 and
             evidence['current_pc_source_match']['address'] == evidence['runtime_code_base'] + offset == cpu['cs_base'] + cpu['ip'],
             'LE current-code placement differs')
    anchor_name = 'entry-code' if evidence['stable_code_extent'] else 'current-code'
    anchors = [s for s in spans if s['name'] == anchor_name and s['object_index'] == index]
    _require(len(anchors) == 1 and anchors[0]['length'] == 96, 'LE code anchor is unavailable or ambiguous')
    return dict(format=BINDING_FORMAT, binding_id=binding_id, run=admission['run'], capture_epoch=admission['capture_epoch'],
                source_sha256=admission['source_sha256'], version=admission['version'], version_sha256=admission['version_sha256'],
                source_view='embedded-le', application_source_sha256=meta['application_source_sha256'],
                initial_admission=deepcopy(admission), placements=ordered)


def make_recipe(image, admission_document, *, binding_id):
    """Derive placements exclusively from the immutable admission's proofs."""
    try:
        return _make_recipe(image, admission_document, binding_id)
    except (KeyError, TypeError, AttributeError, StopIteration) as error:
        raise ValueError('Malformed LE source binding admission') from error


def validate_recipe(image, recipe):
    """Reproduce the complete recipe rather than trusting caller placements."""
    _require(isinstance(recipe, dict), 'Invalid LE source binding recipe')
    try:
        expected = make_recipe(image, recipe['initial_admission'], binding_id=recipe['binding_id'])
        _require(_raw(recipe) == _raw(expected), 'LE source binding recipe differs from its source admission')
    except (KeyError, TypeError) as error:
        raise ValueError('Malformed LE source binding recipe') from error
    return expected


def qualify_instruction(image, recipe, cpu, gdt_bytes, read_linear):
    """Qualify one exact stopped instruction; no placement signature rescans."""
    recipe = validate_recipe(image, recipe)
    meta, objects, regions = _image(image)
    admission = recipe['initial_admission']; evidence = admission['observation']['identity_evidence']
    seed = admission['observed_cpu']
    _require(isinstance(cpu, dict) and cpu.get('mode') == 'protected' and type(cpu.get('bits')) is int and cpu['bits'] == 32 and
             all(_uint(cpu.get(k)) for k in ('cs', 'ip', 'cs_base', 'cs_limit', 'cs_attributes')),
             'Invalid live protected LE CPU context')
    for field in ('mode', 'bits', 'cs', 'cs_base', 'cs_limit'):
        _require(cpu[field] == seed[field], 'LE binding CPU/descriptor identity changed: ' + field)
    _require(cpu['cs_attributes'] & 0xf0ff00 == seed['cs_attributes'] & 0xf0ff00,
             'LE binding CS attributes changed')
    _require(isinstance(gdt_bytes, bytes) and len(gdt_bytes) == admission['gdt']['limit'] + 1 and
             _sha(gdt_bytes) == admission['gdt']['sha256'], 'LE binding GDT identity changed')
    for field, saved in (('gdtr_base', 'base'), ('gdtr_limit', 'limit')):
        if field in cpu:
            _require(cpu[field] == admission['gdt'][saved], 'LE binding descriptor-table location changed')
    current = next((d for d in _descriptors(gdt_bytes) if d['value'] == cpu['cs'] & ~7), None)
    _require(not cpu['cs'] & 4 and current is not None and current['bits'] == 32 and
             current['base'] == cpu['cs_base'] and current['limit'] == cpu['cs_limit'] and
             current['attributes'] == cpu['cs_attributes'] & 0xf0ff00, 'LE binding current descriptor differs')
    context = dict(binding_id=recipe['binding_id'], run=recipe['run'], capture_epoch=recipe['capture_epoch'],
                   source_view='embedded-le', code_bits=32, cpu_mode='protected',
                   source_sha256=recipe['source_sha256'], version=recipe['version'], version_sha256=recipe['version_sha256'],
                   gdt_sha256=admission['gdt']['sha256'], cs=cpu['cs'], cs_base=cpu['cs_base'],
                   cs_limit=cpu['cs_limit'], cs_attributes=cpu['cs_attributes'] & 0xf0ff00)
    def boundary(reason, *, size=0, raw=b'', source=None, location=None):
        qualified = reason == 'qualified'
        result = dict(qualified=qualified, reason=reason, instruction_size=size,
                      execution_bytes=raw.hex(), source_instruction_sha256=_sha(source) if qualified else None,
                      source_location=location if qualified else None,
                      context=('embedded-le:' + recipe['application_source_sha256'] + ':le:' + str(location['object_index']) + ':32')
                              if qualified else None,
                      binding_context=deepcopy(context))
        if not qualified and location is not None:
            result['candidate_location'] = deepcopy(location)
        return result
    def read(address, length):
        _require(_uint(address) and 0 < length <= 96 and address + length <= 2**32, 'Invalid LE witness read extent')
        value = read_linear(address, length)
        _require(isinstance(value, bytes) and len(value) == length, 'LE witness read is short or invalid')
        return value
    linear = cpu['cs_base'] + cpu['ip']
    _require(linear < 2**32 and cpu['ip'] <= cpu['cs_limit'], 'LE instruction fetch exceeds its CPU segment')
    selected = [(p, linear - p['runtime_base']) for p in recipe['placements'] if p['bits'] == 32 and
                objects[p['object_index']]['executable'] and
                p['runtime_base'] <= linear < p['runtime_base'] + objects[p['object_index']]['virtual_size']]
    if not selected:
        return boundary('unrelated-source')
    _require(len(selected) == 1, 'Ambiguous live LE code placement')
    placement, offset = selected[0]; index = placement['object_index']; obj = objects[index]
    location = dict(source_view='embedded-le', application_source_sha256=recipe['application_source_sha256'],
                    object_id='le:' + str(index), object_index=index, object_offset=offset,
                    preferred_address=obj['virtual_address'] + offset)
    context.update(object_index=index, runtime_base=placement['runtime_base'])
    anchor_name = 'entry-code' if evidence['stable_code_extent'] else 'current-code'
    anchor = next(s for s in admission['observation']['source_spans'] if s['name'] == anchor_name and s['object_index'] == index)
    if _sha(read(anchor['address'], anchor['length'])) != anchor['observed_sha256']:
        return boundary('code-anchor-changed', location=location)
    for proof in evidence['object_proofs']:
        for witness in proof.get('offset32_sites', []):
            actual = int.from_bytes(read(evidence['runtime_code_base'] + witness['source_offset'], 4), 'little')
            if actual != witness['value']:
                return boundary('runtime-placement-witness-changed', location=location)
    backed = [(p['object_offset'], p['object_offset'] + p['file_size']) for p in meta['pages']
              if p['object'] == index and p['file_size']]
    backed_end = next((b for a, b in backed if a <= offset < b), None)
    if backed_end is None:
        return boundary('unbacked-or-straddling-source', location=location)
    for a, b in sorted(backed):
        if a == backed_end:
            backed_end = b
    available = min(15, cpu['cs_limit'] - cpu['ip'] + 1, obj['virtual_size'] - offset, backed_end - offset)
    raw = read(linear, available)
    instruction = Decoder(32, raw, ip=cpu['ip']).decode()
    if instruction.is_invalid or not 1 <= instruction.len <= available:
        return boundary('undecodable-source', raw=raw, location=location)
    size = instruction.len; raw = raw[:size]; source = regions[index].data[offset:offset + size]
    source_instruction = Decoder(32, regions[index].data[offset:offset + available],
                                 ip=obj['virtual_address'] + offset).decode()
    if source_instruction.is_invalid or source_instruction.len != size:
        return boundary('source-instruction-shape-changed', size=size, raw=raw, location=location)
    expected = bytearray(source)
    placements = {p['object_index']: p for p in recipe['placements']}
    for fixup in meta['fixups']:
        low, high = fixup['source_offset'], fixup['source_offset'] + fixup['width']
        if fixup['source_object'] != index or low >= offset + size or high <= offset:
            continue
        if low < offset or high > offset + size:
            return boundary('straddling-relocation', size=size, raw=raw, source=source, location=location)
        if fixup['source_type'] != 'offset32' or fixup['width'] != 4 or fixup.get('addend') is not None:
            return boundary('symbolic-or-unsupported-relocation', size=size, raw=raw, source=source, location=location)
        target = placements.get(fixup['target_object'])
        if target is None:
            return boundary('unproved-relocation-target', size=size, raw=raw, source=source, location=location)
        value = target['runtime_base'] + fixup['target_offset']
        _require(_uint(value), 'LE relocated operand exceeds its address domain')
        expected[low-offset:high-offset] = value.to_bytes(4, 'little')
    if raw != bytes(expected):
        return boundary('changed-source-instruction', size=size, raw=raw, source=source, location=location)
    return boundary('qualified', size=size, raw=raw, source=source, location=location)
