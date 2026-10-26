"""Reproduce the bundled fixup-free DOS runtime catalog from licensed inputs."""
import argparse
import hashlib
import json
from pathlib import Path

from fdisbull.omf_catalog import omf_signatures

COMMIT='2d04cacc5322951f187bb17e017c12920ac8ebe2'
LIBRARIES={
    'SLIBCE.LIB': ('d077b91d63d051d3333ca53f81cb15b0597cfdb6ec8a7fadc60f76ab6883e24f','x86_16_cdecl_near'),
    'MLIBCE.LIB': ('fd7775a15c5b94361dc59ad93f1d79f2eedb0a90cefc4c47c3483dc4eddbcad6','x86_16_cdecl_far'),
    'LLIBCE.LIB': ('5a1b1f376b59a029fd60dcdb3bcb1f1f350786e1442b09529590aac0c81f156f','x86_16_cdecl_far'),
}


def build(directory):
    signatures=[];inputs=[]
    for name,(digest,abi) in LIBRARIES.items():
        data=(Path(directory)/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Input hash differs: '+name)
        source=f'https://github.com/microsoft/MS-DOS/blob/{COMMIT}/v4.0/src/TOOLS/BLD/LIB/{name}'
        catalog=omf_signatures(data,source=source,abi=abi)
        signatures.extend(catalog['signatures'])
        inputs.append(dict(source=source,sha256=digest,extraction=catalog['extraction']))
    return dict(format='fdisbull-signatures-1',name='Microsoft DOS C runtime subset',
        license='MIT; Copyright (c) Microsoft Corporation. See MICROSOFT-DOS-LICENSE.txt',
        source_commit=COMMIT,inputs=inputs,signatures=signatures,
        limitations='Byte identities only; not compiler identification or memory-effect contracts. Unresolved fixups and non-contiguous/incomplete routines are excluded.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('library_directory');parser.add_argument('output')
    args=parser.parse_args()
    Path(args.output).write_text(json.dumps(build(args.library_directory),indent=2,sort_keys=True)+'\n')
