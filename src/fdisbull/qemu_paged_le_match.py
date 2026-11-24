"""Paged LE source matching with authentic GDT or LDT descriptor material.

Source windows, fixup masks, budgets, and ambiguity checks reuse the legacy
matcher helpers. This is a capture-only producer, independent of its bindings.
"""

from .qemu_dos_le_match import (
    _require,
    _sha,
    _descriptors,
    _objects,
    _Budget,
    _signature,
    _span,
    MAX_COMPARE,
    MAX_SCAN,
    MAX_SPANS,
)

FORMAT = 'fdisbull-qemu-dos-paged-le-source-match-1'


def match(
    image, cpu, descriptor, read_linear, *, max_compare_bytes=MAX_COMPARE, max_scan_bytes=MAX_SCAN
):
    """Match bounded original-source extents, or None at an unrelated current PC.

    CPU fields are integer CS/IP/base/limit/attributes plus protected mode and
    32-bit width. QEMU's duplicated descriptor-limit nibble in attributes is
    ignored because the full hidden limit is compared separately. The caller
    owns physical translation, stopped-state stability and persistence.
    """
    _require(
        isinstance(cpu, dict)
        and cpu.get('mode') == 'protected'
        and type(cpu.get('bits')) is int
        and cpu['bits'] == 32,
        'LE source matching requires a protected 32-bit stopped CPU',
    )
    for key, maximum in (
        ('cs', 65535),
        ('ip', 2**32 - 1),
        ('cs_base', 2**32 - 1),
        ('cs_limit', 2**32 - 1),
        ('cs_attributes', 2**32 - 1),
    ):
        _require(
            type(cpu.get(key)) is int and 0 <= cpu[key] <= maximum, 'invalid observed CPU ' + key
        )
    _require(cpu['cs'] & ~3, 'LE source matching requires a non-null selector')
    _require(
        image.format == 'LE'
        and image.metadata['le'].get('runtime_source_profile') == 'fdisbull-le-runtime-source-1',
        'LE matching requires explicit runtime-carrier parsing',
    )
    _require(
        isinstance(image.source_bytes, bytes)
        and _sha(image.source_bytes) == image.metadata['source_sha256'],
        'LE retained source identity differs',
    )
    from .qemu_le_translation import decode_descriptor

    _require(
        isinstance(descriptor, dict)
        and descriptor.get('selector') == cpu['cs']
        and descriptor.get('table') == ('ldt' if cpu['cs'] & 4 else 'gdt'),
        'Current descriptor selector or table differs',
    )
    table_base, table_limit = descriptor['table_base'], descriptor['table_limit']
    selector_index = cpu['cs'] & ~7
    _require(
        type(table_base) is int
        and type(table_limit) is int
        and 0 <= table_base < 2**32
        and 0 <= table_limit <= 65535
        and selector_index + 7 <= table_limit
        and table_base + selector_index + 8 <= 2**32
        and descriptor['address'] == table_base + selector_index,
        'Current descriptor table identity differs',
    )
    raw = bytes.fromhex(descriptor['descriptor']['raw'])
    _require(
        decode_descriptor(raw) == descriptor['descriptor'], 'Current descriptor decoding differs'
    )
    decoded = _descriptors(raw)
    current = dict(decoded[0], value=selector_index) if len(decoded) == 1 else None
    _require(
        current is not None and current['bits'] == 32 and not current['attributes'] & 0x200000,
        'Current table code descriptor is absent or not a supported 32-bit executable',
    )
    dpl, rpl = current['attributes'] >> 13 & 3, cpu['cs'] & 3
    _require(
        dpl <= rpl if current['attributes'] & 0x400 else dpl == rpl,
        'Current code selector privilege and table descriptor disagree',
    )
    _require(
        cpu['cs_base'] == current['base']
        and cpu['cs_limit'] == current['limit']
        and cpu['cs_attributes'] & 0xF0FF00 == current['attributes'],
        'observed CS cache and descriptor disagree',
    )
    _require(
        cpu['ip'] + 95 <= current['limit'], 'current 96-byte source window exceeds the CS limit'
    )
    linear = current['base'] + cpu['ip']
    budget = _Budget(read_linear, max_compare_bytes, max_scan_bytes)
    observed = budget.read(linear, 96)
    objects = _objects(image)
    # A logical source window may cross adjacent LE pages. Retain holes, while
    # allowing the shared matcher to treat contiguous file-backed bytes as one.
    for obj in objects:
        merged = []
        for low, high in sorted(obj['backed']):
            if merged and low == merged[-1][1]:
                merged[-1] = (merged[-1][0], high)
            else:
                merged.append((low, high))
        obj['backed'] = merged
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
    stable = meta['entry_object'] == code['index'] and any(
        a <= entry and entry + 96 <= b for a, b in code['backed']
    )
    if stable:
        spans.append(
            _span(
                image,
                code,
                entry,
                budget.read(codebase + entry, 96),
                codebase + entry,
                'entry-code',
                'code',
            )
        )
    else:
        spans.append(discovery)
    proofs = []
    for obj in objects:
        if obj['executable']:
            continue
        sites = {
            f['source_offset']: f
            for f in meta['fixups']
            if f['source_object'] == code['index']
            and f['source_type'] == 'offset32'
            and f['target_object'] == obj['index']
            and f.get('addend') is None
        }
        if len(sites) < 8:
            continue
        bases, proof = set(), []
        for site, fixup in sorted(sites.items())[:8]:
            value = int.from_bytes(budget.read(codebase + site, 4), 'little')
            bases.add(value - fixup['target_offset'])
            proof.append(
                dict(source_offset=site, target_offset=fixup['target_offset'], value=value)
            )
        _require(len(bases) == 1, 'inconsistent LE data relocation sites')
        base = bases.pop()
        matched = False
        for low, high in obj['backed']:
            for off in range(low, max(low, high - 31), 32):
                budget.charge(32)
                candidate = obj['data'][off : off + 32]
                if (
                    len(set(candidate)) < 8
                    or sum(v != 0 for v in candidate) < 16
                    or any(a < off + 32 and b > off for a, b in obj['fixups'])
                ):
                    continue
                actual = budget.read(base + off, 32)
                if actual == candidate:
                    spans.append(
                        _span(
                            image,
                            obj,
                            off,
                            actual,
                            base + off,
                            'initialized-data-' + str(obj['index']),
                            'data',
                        )
                    )
                    matched = True
                    break
            if matched:
                break
        _require(matched, 'no unchanged initialized LE data witness within budget')
        proofs.append(dict(object_index=obj['index'], runtime_base=base, offset32_sites=proof))
    _require(len(spans) <= MAX_SPANS, 'source span budget exceeded')
    return dict(
        format=FORMAT,
        status='bounded-stopped-source-candidate',
        source=dict(
            source_sha256=_sha(image.source_bytes),
            application_source_sha256=meta['application_source_sha256'],
            carrier=meta['carrier'],
            source_view='embedded-le',
            object_address_namespace='preferred LE keys; not ordinary MZ project addresses',
        ),
        identity_evidence=dict(
            kind='passive-source-match',
            lifetime_qualified=False,
            cpu=dict(cpu),
            descriptor_identity=descriptor,
            current_descriptor=current,
            code_object=code['index'],
            runtime_code_base=codebase,
            current_pc_source_match=discovery,
            stable_code_extent=stable,
            object_proofs=proofs,
            excluded_loader_fixups=[
                dict(object_index=o['index'], offset=a, length=b - a)
                for o in objects
                for a, b in o['fixups']
            ],
        ),
        source_spans=spans,
        budget=dict(compared_bytes=budget.compared, scanned_bytes=budget.scanned),
        limitations=[
            'Only compared stopped extents match; unobserved object bytes and execution remain unknown',
            'Excluded offset16 operands retain unresolved loader/selector semantics',
            'No continuing mapping, process/task lifetime, checkpoint binding or active-overlay proof',
        ],
    )
