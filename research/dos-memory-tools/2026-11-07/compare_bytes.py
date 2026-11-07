"""Bounded research comparator. Exact byte evidence; no semantic equivalence claim.

Unchanged spans are literal-checked. Unique 64-byte anchors and a monotone
chain preserve obvious insert/delete shifts. Short gaps use ordered matching;
large unmatched gaps remain opaque replacements. This is not a minimum edit
distance or a shipped fDisBull method, and never executes the input programs.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from difflib import SequenceMatcher
from hashlib import sha256
import json
from pathlib import Path
import random
import time

MAX_BYTES = 1024 * 1024
ANCHOR = 64
STRIDE = 16
MAX_GAP = 4096
MAX_GAP_PRODUCT = 4 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(data):
    return dict(size=len(data), sha256=sha256(data).hexdigest())


def positional_ranges(left, right):
    """Exact fixed-offset changes, including explicit end-of-file extents."""
    spans = []
    start = None
    for offset in range(max(len(left), len(right))):
        equal = offset < min(len(left), len(right)) and left[offset] == right[offset]
        if not equal and start is None:
            start = offset
        if equal and start is not None:
            spans.append((start, offset))
            start = None
    if start is not None:
        spans.append((start, max(len(left), len(right))))
    return [dict(start=a, end=b, length=b-a) for a, b in spans]


def _prefix_suffix(a, b):
    prefix = 0
    while prefix < min(len(a), len(b)) and a[prefix] == b[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(a), len(b)) - prefix and a[-suffix-1] == b[-suffix-1]:
        suffix += 1
    return prefix, suffix


def _anchor_chain(a, b, prefix, suffix):
    ahi, bhi = len(a)-suffix, len(b)-suffix
    if min(ahi-prefix, bhi-prefix) < ANCHOR:
        return []
    # Duplicate exact windows are not trusted as unambiguous anchors.
    right = {}
    for j in range(prefix, bhi-ANCHOR+1):
        key = b[j:j+ANCHOR]
        right[key] = j if key not in right else -1
    left = {}
    for i in range(prefix, ahi-ANCHOR+1, STRIDE):
        key = a[i:i+ANCHOR]
        left[key] = i if key not in left else -1
    candidates = sorted((i, right[key]) for key, i in left.items()
                        if i >= 0 and right.get(key, -1) >= 0)
    if not candidates:
        return []
    # Longest increasing chain of matching positions; ambiguous/reordered
    # content can remain an unmatched replacement rather than a guessed move.
    tails, indices, prev = [], [], [-1] * len(candidates)
    for k, (_, j) in enumerate(candidates):
        slot = bisect_left(tails, j)
        if slot:
            prev[k] = indices[slot-1]
        if slot == len(tails):
            tails.append(j)
            indices.append(k)
        else:
            tails[slot], indices[slot] = j, k
    k = indices[-1]
    chain = []
    while k >= 0:
        chain.append((*candidates[k], ANCHOR))
        k = prev[k]
    chain.reverse()
    merged = []
    for x, y, size in chain:
        if merged:
            px, py, pn = merged[-1]
            if x-y == px-py and x <= px+pn:
                merged[-1] = (px, py, max(pn, x+size-px))
                continue
            if x < px+pn or y < py+pn:
                continue
        merged.append((x, y, size))
    return merged


def alignment(a, b):
    if max(len(a), len(b)) > MAX_BYTES:
        raise ValueError('research byte budget exceeded')
    prefix, suffix = _prefix_suffix(a, b)
    anchors = _anchor_chain(a, b, prefix, suffix)
    if prefix:
        anchors.insert(0, (0, 0, prefix))
    if suffix:
        anchors.append((len(a)-suffix, len(b)-suffix, suffix))
    grown = []
    for index, (x, y, size) in enumerate(anchors):
        lowa, lowb = (grown[-1][0]+grown[-1][2], grown[-1][1]+grown[-1][2]) if grown else (0, 0)
        higha, highb = anchors[index+1][:2] if index+1 < len(anchors) else (len(a), len(b))
        while x > lowa and y > lowb and a[x-1] == b[y-1]:
            x, y, size = x-1, y-1, size+1
        while x+size < higha and y+size < highb and a[x+size] == b[y+size]:
            size += 1
        require(a[x:x+size] == b[y:y+size], 'Anchor content mismatch')
        grown.append((x, y, size))
    ops = []

    def gap(x0, x1, y0, y1):
        if x0 == x1 and y0 == y1:
            return
        if x0 == x1:
            ops.append(('insert', x0, x1, y0, y1))
        elif y0 == y1:
            ops.append(('delete', x0, x1, y0, y1))
        elif max(x1-x0, y1-y0) <= MAX_GAP and (x1-x0)*(y1-y0) <= MAX_GAP_PRODUCT:
            for tag, l0, l1, r0, r1 in SequenceMatcher(None, a[x0:x1], b[y0:y1], autojunk=False).get_opcodes():
                ops.append((tag, x0+l0, x0+l1, y0+r0, y0+r1))
        else:
            ops.append(('replace_opaque', x0, x1, y0, y1))

    pa = pb = 0
    for x, y, size in grown:
        gap(pa, x, pb, y)
        ops.append(('equal', x, x+size, y, y+size))
        pa, pb = x+size, y+size
    gap(pa, len(a), pb, len(b))
    merged = []
    for tag, a0, a1, b0, b1 in ops:
        if merged and merged[-1][0] == tag and merged[-1][2] == a0 and merged[-1][4] == b0:
            old = merged[-1]
            merged[-1] = tag, old[1], a1, old[3], b1
        else:
            merged.append((tag, a0, a1, b0, b1))
    pa = pb = 0
    forward, reverse = [], []
    for tag, a0, a1, b0, b1 in merged:
        require((a0, b0) == (pa, pb), 'Alignment coverage gap')
        require(a0 <= a1 <= len(a) and b0 <= b1 <= len(b), 'Alignment extent out of bounds')
        if tag == 'equal':
            require(a[a0:a1] == b[b0:b1], 'Equal span content mismatch')
        forward.append(a[a0:a1] if tag == 'equal' else b[b0:b1])
        reverse.append(b[b0:b1] if tag == 'equal' else a[a0:a1])
        pa, pb = a1, b1
    require((pa, pb) == (len(a), len(b)), 'Alignment does not cover both inputs')
    require(b''.join(forward) == b and b''.join(reverse) == a,
            'Bidirectional reconstruction mismatch')
    return merged


def compare(left, right):
    if max(len(left), len(right)) > MAX_BYTES:
        raise ValueError('research byte budget exceeded')
    started = time.monotonic()
    ranges = positional_ranges(left, right)
    ops = alignment(left, right)
    histogram = Counter()
    counts = Counter()
    documents = []
    for tag, a0, a1, b0, b1 in ops:
        record = dict(operation=tag, before_start=a0, before_end=a1, after_start=b0, after_end=b1,
                      before_size=a1-a0, after_size=b1-b0)
        if tag == 'equal':
            histogram[b0-a0] += a1-a0
            counts['equal_bytes'] += a1-a0
            if a0 != b0:
                counts['shifted_equal_bytes'] += a1-a0
            record['sha256'] = sha256(left[a0:a1]).hexdigest()
        else:
            counts[tag+'_operations'] += 1
            counts[tag+'_before_bytes'] += a1-a0
            counts[tag+'_after_bytes'] += b1-b0
            record['before_sha256'] = sha256(left[a0:a1]).hexdigest()
            record['after_sha256'] = sha256(right[b0:b1]).hexdigest()
        documents.append(record)
    return dict(before=identity(left), after=identity(right), identical=left == right,
                size_delta=len(right)-len(left),
                fixed_offset_difference_count=sum(x['length'] for x in ranges),
                fixed_offset_difference_ranges=ranges,
                exact_alignment=dict(algorithm='unique-64-byte-anchors-plus-bounded-ordered-gap-matching-v1',
                    minimal_edit_claim=False, semantic_equivalence=False, entire_inputs_covered=True,
                    literal_equal_spans_verified=True, both_directions_reconstruct=True,
                    counts=dict(counts), equality_displacements={str(k): v for k, v in sorted(histogram.items())},
                    operations=documents), seconds=time.monotonic()-started)


def controls():
    data = random.Random(4117).randbytes(5000)
    pairs = [
        ('identical', data, data),
        ('insert', data, data[:513]+b'inserted-control'+data[513:]),
        ('delete', data, data[:513]+data[528:]),
        ('replacement', data, data[:513]+b'changed-control!'+data[529:]),
        ('separated_insert_and_delete', data, data[:513]+b'INSERT!'+data[513:3200]+data[3202:]),
        ('repeated_bytes', b'\0'*5000, b'\0'*2000+b'\xff'+b'\0'*3000),
        ('empty_to_bytes', b'', data),
        ('bytes_to_empty', data, b''),
    ]
    result = []
    for name, left, right in pairs:
        compared = compare(left, right)
        if name == 'identical':
            require(compared['fixed_offset_difference_count'] == 0, 'Identity control differs')
            require(compared['exact_alignment']['counts']['equal_bytes'] == len(data),
                    'Identity control loses equal bytes')
        if name in ('insert', 'delete', 'repeated_bytes'):
            require(compared['exact_alignment']['counts']['equal_bytes'] == min(len(left), len(right)),
                    'Shift control loses equal bytes')
            require(compared['exact_alignment']['counts']['shifted_equal_bytes'] > 0,
                    'Shift control did not identify displaced equal content')
        result.append(dict(name=name, passed=True, counts=compared['exact_alignment']['counts']))
    return result



def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', nargs='?', type=Path)
    parser.add_argument('after', nargs='?', type=Path)
    parser.add_argument('--controls', action='store_true', help='Run eight authored verifier controls')
    parser.add_argument('--output', type=Path, help='New report file; existing files are never overwritten')
    args = parser.parse_args()
    if (args.before is None) != (args.after is None):
        parser.error('Supply both input files')
    if args.before is None and not args.controls:
        parser.error('Supply two input files or --controls')
    result = dict(schema='bounded-byte-comparison-1',
                  qualification='Standalone research verifier; not a shipped fDisBull method or semantic equivalence proof',
                  limits=dict(max_bytes=MAX_BYTES, anchor=ANCHOR, stride=STRIDE,
                              max_gap=MAX_GAP, max_gap_product=MAX_GAP_PRODUCT))
    if args.controls:
        result['controls'] = controls()
    if args.before is not None:
        data = []
        for path in (args.before, args.after):
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                parser.error('Input must be a regular file no larger than 1 MiB: ' + str(path))
            with path.open('rb') as stream:
                value = stream.read(MAX_BYTES + 1)
            if len(value) > MAX_BYTES:
                parser.error('Input grew beyond the 1 MiB budget: ' + str(path))
            data.append(value)
        result['comparison'] = compare(*data)
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(encoded)
        print(json.dumps({'output': str(args.output),
                          'controls_passed': len(result.get('controls', [])),
                          'fixed_offset_difference_count': result.get('comparison', {}).get('fixed_offset_difference_count')}))
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
