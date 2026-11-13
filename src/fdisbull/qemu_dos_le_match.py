"""Bounded stopped LE source matching; no process lifetime or execution proof.

Adapted from reviewed runtime_source_matching.py (SHA-256
57496323922bc0f7e16b569dae04481b053a6a5019f03385450e603ec5042fee).
The caller supplies a stopped CPU/GDT and a physically verified linear reader.
No registry, guest control, active overlay or ordinary MZ address map is used.
"""
from __future__ import annotations

import hashlib
import re
from bisect import bisect_right

MAX_COMPARE = 512 * 1024
MAX_SCAN = 16 * 1024 * 1024
MAX_SPANS = 512
FORMAT = 'fdisbull-qemu-dos-le-source-match-1'


class SourceMatchError(ValueError):
    """Unsupported, changed, ambiguous or over-budget stopped evidence."""


def _require(value, message):
    if not value:
        raise SourceMatchError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _ranges(offsets):
    result = []
    for value in sorted(set(offsets)):
        if result and result[-1][0] + result[-1][1] == value:
            result[-1][1] += 1
        else:
            result.append([value, 1])
    return result


class _Budget:
    def __init__(self, reader, compare, scan):
        for value, maximum in ((compare, MAX_COMPARE), (scan, MAX_SCAN)):
            _require(type(value) is int and 1 <= value <= maximum, 'invalid source matching budget')
        self.reader, self.compare, self.scan = reader, compare, scan
        self.compared = self.scanned = 0

    def charge(self, count):
        self.scanned += count
        _require(self.scanned <= self.scan, 'source scan budget exceeded; no partial match published')

    def read(self, address, length):
        _require(type(address) is int and type(length) is int and 0 <= address < 2**32 and
                 0 < length <= MAX_COMPARE and address + length <= 2**32, 'invalid runtime extent')
        self.compared += length
        _require(self.compared <= self.compare, 'runtime comparison budget exceeded; no partial match published')
        result = self.reader(address, length)
        _require(isinstance(result, bytes) and len(result) == length, 'short or invalid runtime memory read')
        return result


def _descriptors(raw):
    result = []
    for offset in range(0, len(raw) - 7, 8):
        row = raw[offset:offset + 8]
        if row[5] & 0x98 != 0x98:
            continue
        address = int.from_bytes(row[2:4], 'little') | row[4] << 16 | row[7] << 24
        bound = int.from_bytes(row[:2], 'little') | (row[6] & 15) << 16
        if row[6] & 128:
            bound = (bound << 12) | 4095
        result.append(dict(value=offset, base=address, limit=bound,
                           bits=32 if row[6] & 64 else 16, raw_hex=row.hex(),
                           attributes=(row[5] << 8) | ((row[6] & 0xf0) << 16)))
    return result


def _objects(image):
    meta = image.metadata['le']
    result = []
    for obj in meta['objects']:
        region = next(r for r in image.regions if r.start == obj['virtual_address'])
        result.append(dict(id='le:' + str(obj['index']), index=obj['index'], start=region.start,
                           data=region.data, bits=obj['bits'], executable=region.executable,
                           backed=[(p['object_offset'], p['object_offset'] + p['file_size'])
                                   for p in meta['pages'] if p['object'] == obj['index'] and p['file_size']],
                           fixups=[(f['source_offset'], f['source_offset'] + f['width'])
                                   for f in meta['fixups'] if f['source_object'] == obj['index']]))
    return result


def masked_window_offsets(data, observed, fixups, budget, *, backed=None):
    """Find every eligible masked window, refusing a second source placement.

    A two-byte encoding separates literal bytes from loader-fixup wildcards.
    The fixed-width lookahead scans overlapping windows in C; anchors cannot
    hide a competing placement. Only aligned encoded positions, admitted
    source-backed extents and windows with comparable bytes can qualify.
    """
    size = len(observed)
    if size < 16 or len(data) < size or backed is not None and not backed:
        return set()
    # Charge before allocating the doubled source and applying wildcard masks.
    budget.charge(len(data) * 4)
    encoded = bytearray(len(data) * 2)
    encoded[1::2] = data
    intervals = []
    for low, high in sorted(fixups):
        low, high = max(0, low), min(len(data), high)
        if low >= high:
            continue
        encoded[low * 2:high * 2] = b'\x01\x00' * (high - low)
        if intervals and low <= intervals[-1][1]:
            intervals[-1][1] = max(high, intervals[-1][1])
        else:
            intervals.append([low, high])
    starts = [low for low, _ in intervals]
    pattern = b'(?=' + b''.join(b'(?:\x00' + re.escape(bytes([value])) + b'|\x01\x00)'
                               for value in observed) + b')'
    candidates = set()
    for found in re.finditer(pattern, encoded):
        if found.start() & 1:
            continue
        offset = found.start() // 2
        if backed is not None and not any(a <= offset and offset + size <= b for a, b in backed):
            continue
        interval = bisect_right(starts, offset) - 1
        if interval >= 0 and offset + size <= intervals[interval][1]:
            continue  # Entirely masked bytes cannot qualify a source extent.
        candidates.add(offset)
        _require(len(candidates) <= 1, 'ambiguous source placement within one object')
    return candidates


def _signature(data, observed, fixups, budget, backed):
    candidates = masked_window_offsets(data, observed, fixups, budget, backed=backed)
    return next(iter(candidates)) if candidates else None


def _span(image, obj, off, actual, address, name, kind):
    size = len(actual)
    expected = obj['data'][off:off + size]
    exclusions = [(max(off, a) - off, min(off + size, b) - max(off, a))
                  for a, b in obj['fixups'] if a < off + size and b > off]
    excluded = {i for a, n in exclusions for i in range(a, a + n)}
    comparable = [i for i in range(size) if i not in excluded]
    _require(comparable and all(expected[i] == actual[i] for i in comparable), 'changed source bytes in qualified span')
    fragments = []
    for mapping in image.metadata['file_mappings']:
        left = max(obj['start'] + off, mapping['virtual_address'])
        right = min(obj['start'] + off + size, mapping['virtual_address'] + mapping['file_size'])
        if left < right:
            fragments.append(dict(span_offset=left - obj['start'] - off,
                                  file_offset=mapping['file_offset'] + left - mapping['virtual_address'],
                                  length=right - left))
    _require(sum(f['length'] for f in fragments) == size, 'LE source fragment coverage incomplete')
    return dict(name=name, kind=kind, address=address, length=size,
                source_view='embedded-le', object_id=obj['id'], object_index=obj['index'], object_offset=off,
                preferred_address=obj['start'] + off, file_fragments=fragments,
                expected_sha256=_sha(expected), observed_sha256=_sha(actual),
                compared_bytes=len(comparable), fixups=[dict(offset=a, length=n) for a, n in exclusions],
                comparable_sha256=_sha(bytes(expected[i] for i in comparable)))


def match(image, cpu, gdt_bytes, read_linear, *, max_compare_bytes=MAX_COMPARE, max_scan_bytes=MAX_SCAN):
    """Match bounded original-source extents, or None at an unrelated current PC.

    CPU fields are integer CS/IP/base/limit/attributes plus protected mode and
    32-bit width. QEMU's duplicated descriptor-limit nibble in attributes is
    ignored because the full hidden limit is compared separately. The caller
    owns physical translation, stopped-state stability and persistence.
    """
    _require(isinstance(cpu, dict) and cpu.get('mode') == 'protected' and type(cpu.get('bits')) is int and cpu['bits'] == 32,
             'LE source matching requires a protected 32-bit stopped CPU')
    for key, maximum in (('cs', 65535), ('ip', 2**32 - 1), ('cs_base', 2**32 - 1),
                         ('cs_limit', 2**32 - 1), ('cs_attributes', 2**32 - 1)):
        _require(type(cpu.get(key)) is int and 0 <= cpu[key] <= maximum, 'invalid observed CPU ' + key)
    _require(not cpu['cs'] & 4 and cpu['cs'] & ~7, 'LE source matching requires a non-null GDT selector; LDT is unsupported')
    _require(isinstance(gdt_bytes, bytes) and 8 <= len(gdt_bytes) <= 65536,
             'GDT exceeds bounded descriptor budget or is unavailable')
    _require(image.format == 'LE' and image.metadata['le'].get('runtime_source_profile') == 'fdisbull-le-runtime-source-1',
             'LE matching requires explicit runtime-carrier parsing')
    _require(isinstance(image.source_bytes, bytes) and _sha(image.source_bytes) == image.metadata['source_sha256'],
             'LE retained source identity differs')
    descriptors = _descriptors(gdt_bytes)
    current = next((d for d in descriptors if d['value'] == cpu['cs'] & ~7), None)
    _require(current is not None and current['bits'] == 32 and not current['attributes'] & 0x200000,
             'Current GDT code descriptor is absent or not a supported 32-bit executable')
    dpl, rpl = current['attributes'] >> 13 & 3, cpu['cs'] & 3
    _require(dpl <= rpl if current['attributes'] & 0x400 else dpl == rpl,
             'Current code selector privilege and GDT descriptor disagree')
    _require(cpu['cs_base'] == current['base'] and cpu['cs_limit'] == current['limit'] and
             cpu['cs_attributes'] & 0xf0ff00 == current['attributes'], 'observed CS cache and GDT disagree')
    _require(cpu['ip'] + 95 <= current['limit'], 'current 96-byte source window exceeds the CS limit')
    linear = current['base'] + cpu['ip']
    budget = _Budget(read_linear, max_compare_bytes, max_scan_bytes)
    observed = budget.read(linear, 96)
    objects = _objects(image)
    choices = []
    for obj in objects:
        if obj['bits'] != 32 or not obj['executable']:
            continue
        offset = _signature(obj['data'], observed, obj['fixups'], budget, obj['backed'])
        if offset is not None:
            choices.append((obj, offset, linear - offset))
    _require(len(choices) <= 1, 'ambiguous protected source placement')
    if not choices:
        return None
    code, offset, codebase = choices[0]
    _require(codebase >= 0, 'LE code placement has a negative base')
    discovery = _span(image, code, offset, observed, linear, 'current-code', 'code')
    spans = []
    meta = image.metadata['le']
    entry = meta['entry_offset']
    stable = meta['entry_object'] == code['index'] and any(a <= entry and entry + 96 <= b for a, b in code['backed'])
    if stable:
        spans.append(_span(image, code, entry, budget.read(codebase + entry, 96), codebase + entry, 'entry-code', 'code'))
    else:
        spans.append(discovery)
    proofs = []
    for obj in objects:
        if obj['executable']:
            continue
        sites = {f['source_offset']: f for f in meta['fixups'] if f['source_object'] == code['index'] and
                 f['source_type'] == 'offset32' and f['target_object'] == obj['index'] and f.get('addend') is None}
        if len(sites) < 8:
            continue
        bases, proof = set(), []
        for site, fixup in sorted(sites.items())[:8]:
            value = int.from_bytes(budget.read(codebase + site, 4), 'little')
            bases.add(value - fixup['target_offset'])
            proof.append(dict(source_offset=site, target_offset=fixup['target_offset'], value=value))
        _require(len(bases) == 1, 'inconsistent LE data relocation sites')
        base = bases.pop()
        matched = False
        for low, high in obj['backed']:
            for off in range(low, max(low, high - 31), 32):
                budget.charge(32)
                candidate = obj['data'][off:off + 32]
                if len(set(candidate)) < 8 or sum(v != 0 for v in candidate) < 16 or any(a < off + 32 and b > off for a, b in obj['fixups']):
                    continue
                actual = budget.read(base + off, 32)
                if actual == candidate:
                    spans.append(_span(image, obj, off, actual, base + off, 'initialized-data-' + str(obj['index']), 'data'))
                    matched = True
                    break
            if matched:
                break
        _require(matched, 'no unchanged initialized LE data witness within budget')
        proofs.append(dict(object_index=obj['index'], runtime_base=base, offset32_sites=proof))
    for obj in objects:
        if obj['bits'] != 16 or not obj['executable']:
            continue
        size = min(len(obj['data']), 256)
        if not any(a == 0 and b >= size for a, b in obj['backed']):
            continue
        excluded = {i for a, b in obj['fixups'] for i in range(a, b)}
        matches = []
        for descriptor in descriptors:
            if descriptor['bits'] != 16 or descriptor['limit'] + 1 < size or descriptor['attributes'] & 0x200000:
                continue
            actual = budget.read(descriptor['base'], size)
            if all(actual[i] == obj['data'][i] for i in range(size) if i not in excluded):
                matches.append((descriptor, actual))
        _require(len(matches) <= 1, 'ambiguous 16-bit LE descriptor/source match')
        if matches:
            descriptor, actual = matches[0]
            spans.append(_span(image, obj, 0, actual, descriptor['base'], 'bridge-' + str(obj['index']), 'code'))
            proofs.append(dict(object_index=obj['index'], descriptor=descriptor,
                               execution_observed=False, symbolic_operands_qualified=False))
    _require(len(spans) <= MAX_SPANS, 'source span budget exceeded')
    return dict(format=FORMAT, status='bounded-stopped-source-candidate',
                source=dict(source_sha256=_sha(image.source_bytes),
                            application_source_sha256=meta['application_source_sha256'], carrier=meta['carrier'],
                            source_view='embedded-le', object_address_namespace='preferred LE keys; not ordinary MZ project addresses'),
                identity_evidence=dict(kind='passive-source-match', lifetime_qualified=False, cpu=dict(cpu),
                                       gdt_sha256=_sha(gdt_bytes), current_descriptor=current,
                                       code_object=code['index'], runtime_code_base=codebase,
                                       current_pc_source_match=discovery, stable_code_extent=stable, object_proofs=proofs,
                                       excluded_loader_fixups=[dict(object_index=o['index'], offset=a, length=b-a)
                                                              for o in objects for a, b in o['fixups']]),
                source_spans=spans, budget=dict(compared_bytes=budget.compared, scanned_bytes=budget.scanned),
                limitations=['Only compared stopped extents match; unobserved object bytes and execution remain unknown',
                             'Excluded offset16 operands retain unresolved loader/selector semantics',
                             'No continuing mapping, process/task lifetime, checkpoint binding or active-overlay proof'])
