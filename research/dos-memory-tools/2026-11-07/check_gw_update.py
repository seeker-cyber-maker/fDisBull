"""Check the observed Game Wizard 3.0a update recipe without executing it.

This is a source-pinned research witness, not a general patch-file parser.
Original and output files stay in caller-owned private directories. JSON
contains identities, offsets, counts and verdicts, never original payloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PATCH_SHA256 = '0c8263fe20a3b545ceb65a864c6691591ca7ed1720f517d5b2db35f36c3f23cf'
PATCH_SIZE = 121912
KEEP_PREFIX = 25207
PATCH_SPLIT = 81336
MAX_INPUT_BYTES = 2 * 1024 * 1024


def read(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError('Expected a regular input of at most two MiB')
    data = path.read_bytes()
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError('Input grew beyond the declared limit')
    return data


def identity(data):
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def reconstruct(before_install, patch):
    if len(patch) != PATCH_SIZE or identity(patch)['sha256'] != PATCH_SHA256:
        raise ValueError('This witness requires the exact inspected official UPD payload')
    if len(before_install) < KEEP_PREFIX:
        raise ValueError('Predecessor lacks the prefix retained by this observed recipe')
    return {'INSTALL.PRO': before_install[:KEEP_PREFIX] + patch[:PATCH_SPLIT],
            'GW': patch[PATCH_SPLIT:]}


def compare(expected, actual):
    ranges = []
    for offset in range(max(len(expected), len(actual))):
        different = offset >= min(len(expected), len(actual)) or expected[offset] != actual[offset]
        if different:
            if ranges and ranges[-1][1] == offset:
                ranges[-1][1] += 1
            else:
                ranges.append([offset, offset+1])
    return {'equal': expected == actual, 'expected': identity(expected),
            'actual': identity(actual), 'fixed_offset_ranges': ranges,
            'fixed_offset_difference_count_including_eof': sum(b-a for a,b in ranges)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True, help='Private predecessor installation directory')
    parser.add_argument('--patch', type=Path, required=True, help='Exact GWPRO30A.UPD')
    parser.add_argument('--observed-output', type=Path, required=True, help='Private output of the vendor updater')
    parser.add_argument('--candidate-after', type=Path, required=True, help='Independent preserved 3.0a directory')
    parser.add_argument('--output', type=Path, help='New JSON report; never overwritten')
    args = parser.parse_args()
    patch = read(args.patch)
    old = read(args.before/'INSTALL.PRO')
    predicted = reconstruct(old, patch)
    result = {'schema': 'gamewizard-offline-update-witness-1',
              'scope': 'Exact observed payload recipe; native execution, unknown predecessors and inner code semantics are separate',
              'patch': identity(patch), 'before_install': identity(old),
              'retained_prefix': [0, KEEP_PREFIX],
              'payload_slices': {'INSTALL.PRO': [0, PATCH_SPLIT], 'GW': [PATCH_SPLIT, len(patch)]},
              'unaccounted_payload_bytes': 0, 'files': {}}
    for name, data in predicted.items():
        observed = read(args.observed_output/name)
        candidate = read(args.candidate_after/name)
        comparison = compare(data, candidate)
        inherited = name == 'INSTALL.PRO' and all(
            i < len(old) and data[i] == old[i]
            for start, end in comparison['fixed_offset_ranges'] for i in range(start,end)
            if i < len(data)
        ) and len(data) == len(candidate)
        result['files'][name] = {'reconstruction_vs_native_output': compare(data, observed),
                                 'reconstruction_vs_independent_after': comparison,
                                 'all_candidate_differences_inherited_from_before': inherited if name == 'INSTALL.PRO' and not comparison['equal'] else None}
    result['native_output_reconstructed_exactly'] = all(x['reconstruction_vs_native_output']['equal'] for x in result['files'].values())
    result['independent_after_matches_completely'] = all(x['reconstruction_vs_independent_after']['equal'] for x in result['files'].values())
    encoded = json.dumps(result, indent=2)+'\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(encoded)
    print(encoded, end='')
    return 0 if result['native_output_reconstructed_exactly'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
