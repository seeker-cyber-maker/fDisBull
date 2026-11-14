"""Pure, bounded comparisons of already captured native argument samples."""


CLAIM = ('Observed sampled bytes only; pointer roles and meaning are not inferred. '
         'No guest memory is read by this summary.')
MAX_ARGUMENTS = 7
MAX_SAMPLE_BYTES = 256
MAX_RANGES = 4
MAX_PREVIEW_BYTES = 15


def _rows(contract, key):
    rows = contract.get(key, [])
    if not isinstance(rows, list) or len(rows) > MAX_ARGUMENTS:
        raise ValueError(f'{key} must contain at most {MAX_ARGUMENTS} arguments')
    indexed = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f'{key} arguments must be objects')
        name = row.get('register')
        if not isinstance(name, str) or not 1 <= len(name) <= 16:
            raise ValueError('argument register must be a short nonempty string')
        name = name.upper()
        if name in indexed:
            raise ValueError(f'duplicate argument register: {name}')
        indexed[name] = row
    return indexed


def _sample(row):
    if row is None:
        return None, 'missing_argument'
    if 'pointer_read_error' in row:
        return None, 'pointer_read_error'
    sample = row.get('pointer_hypothesis')
    if sample is None:
        return None, 'missing_pointer_sample'
    if not isinstance(sample, dict):
        return None, 'invalid_pointer_sample'
    address, size, value = sample.get('address'), sample.get('bytes'), sample.get('hex')
    if (type(address) is not int or not 0 <= address <= 0xFFFFFFFF
            or type(size) is not int or not 1 <= size <= MAX_SAMPLE_BYTES
            or address + size > 0x100000000 or not isinstance(value, str)
            or len(value) != size * 2):
        return None, 'invalid_pointer_sample'
    try:
        raw = bytes.fromhex(value)
    except ValueError:
        return None, 'invalid_pointer_sample'
    if len(raw) != size:
        return None, 'invalid_pointer_sample'
    return (address, raw), None


def _compare(name, before_row, after_row):
    before, before_error = _sample(before_row)
    after, after_error = _sample(after_row)
    result = {'registers': [name], 'status': 'unobserved',
              'bytes_compared': 0, 'bytes_changed': 0}
    if before_error or after_error:
        result['unobserved'] = {key: reason for key, reason in
                                (('before', before_error), ('after', after_error)) if reason}
        return result, None
    before_address, old = before
    after_address, new = after
    result.update(before_bytes=len(old), after_bytes=len(new))
    if before_address != after_address:
        result.update(status='not_comparable', reason='pointer_address_mismatch',
                      before_address=before_address, after_address=after_address)
        return result, None
    size = min(len(old), len(new))
    ranges = []
    offset = 0
    changed = 0
    while offset < size:
        if old[offset] == new[offset]:
            offset += 1
            continue
        start = offset
        while offset < size and old[offset] != new[offset]:
            offset += 1
        changed += offset - start
        ranges.append((start, offset))
    preview = []
    for start, end in ranges[:MAX_RANGES]:
        stop = min(end, start + MAX_PREVIEW_BYTES)
        preview.append({'offset': start, 'length': end - start,
                        'before_hex': old[start:stop].hex(), 'after_hex': new[start:stop].hex(),
                        'omitted_bytes': end - stop})
    result.update(address=before_address, bytes_compared=size, bytes_changed=changed,
                  status='changed' if changed else ('unchanged' if len(old) == len(new) else 'partial'),
                  comparison_complete=len(old) == len(new),
                  before_uncompared_bytes=len(old) - size, after_uncompared_bytes=len(new) - size,
                  changed_ranges=preview, changed_range_count=len(ranges),
                  omitted_ranges=max(0, len(ranges) - MAX_RANGES),
                  omitted_changed_bytes=changed - sum(min(end - start, MAX_PREVIEW_BYTES)
                                                     for start, end in ranges[:MAX_RANGES]))
    if size >= 4 and old[:4] != new[:4]:
        result['first_u32_le'] = {'before': int.from_bytes(old[:4], 'little'),
                                  'after': int.from_bytes(new[:4], 'little')}
        result['first_i32_le'] = {'before': int.from_bytes(old[:4], 'little', signed=True),
                                  'after': int.from_bytes(new[:4], 'little', signed=True)}
    return result, (before_address, old, new)


def summarize_argument_changes(contract):
    """Compare matching registers and pointer addresses without reading the guest.

    Counts cover the common sampled prefix only. Identical captured pointer
    pairs share one comparison with all register aliases retained. A changed
    integer candidate describes bytes, not an inferred argument type or role.
    Input is bounded to the capture contract's seven registers and 256 bytes
    per sample; malformed samples are unobserved rather than unchanged.
    """
    if not isinstance(contract, dict):
        raise ValueError('contract must be an object')
    before, after = _rows(contract, 'arguments'), _rows(contract, 'post_arguments')
    comparisons, aliases = [], {}
    for name in dict.fromkeys((*before, *after)):
        comparison, identity = _compare(name, before.get(name), after.get(name))
        if identity is not None and identity in aliases:
            aliases[identity]['registers'].append(name)
        else:
            comparisons.append(comparison)
            if identity is not None:
                aliases[identity] = comparison
    return {'claim': CLAIM, 'comparisons': comparisons,
            'bytes_compared': sum(row['bytes_compared'] for row in comparisons),
            'bytes_changed': sum(row['bytes_changed'] for row in comparisons)}
