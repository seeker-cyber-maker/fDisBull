#!/usr/bin/env python3
"""Compare all 16-bit word hypotheses at one fixed address mapping, not semantics."""
import argparse
import hashlib
import itertools
import json

from fdisbull.rom_asm import BACKENDS, disassemble_rom
from fdisbull.rom_asm_ghidra import GhidraDecodeSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghidra-home', required=True)
    parser.add_argument('--saturn-root', required=True)
    args = parser.parse_args()
    data = b''.join(word.to_bytes(2, 'big') for word in range(65536))
    facts = {name: {} for name in BACKENDS}
    identities = {}
    with GhidraDecodeSession(ghidra_home=args.ghidra_home, timeout=180) as session:
        for offset in (0, 65536):
            for backend in BACKENDS:
                report = disassemble_rom(data, base_address=0x06000000, offset=offset,
                    length=65536, max_instructions=32768, backend=backend, mode='word-scan',
                    ghidra_home=args.ghidra_home, saturn_recomp_root=args.saturn_root,
                    ghidra_session=session if backend == 'ghidra' else None, timeout=180)
                assert report['attempted_words'] == 32768
                identities[backend] = report['engine_identity']
                facts[backend].update({row['file_offset'] // 2: row['normalized'] for row in report['instructions']})
    comparisons = []
    for left, right in itertools.combinations(BACKENDS, 2):
        a, b = facts[left], facts[right]
        validity = sorted(set(a) ^ set(b))
        text = sorted(word for word in set(a) & set(b) if a[word] != b[word])
        comparisons.append({'left': left, 'right': right,
            'both_decoded': len(set(a) & set(b)), 'both_unknown': 65536 - len(set(a) | set(b)),
            'validity_differences': len(validity), 'normalized_text_differences': len(text),
            'first_differences': [{'authored_word_hex': f'{word:04x}', 'left': a.get(word), 'right': b.get(word)}
                                  for word in (validity + text)[:20]]})
    print(json.dumps({'schema': 'fdisbull-sh2-word-census-1', 'words': 65536,
        'authored_input_sha256': hashlib.sha256(data).hexdigest(), 'base_address': 0x06000000,
        'decoded_counts': {name: len(items) for name, items in facts.items()},
        'engine_identities': identities, 'comparisons': comparisons,
        'scope': 'Exhaustive aligned 16-bit word hypotheses at the declared PC mapping, default SH-2 context. Agreement does not prove instruction execution, target semantics or all contexts.'}, indent=2))


if __name__ == '__main__':
    main()
