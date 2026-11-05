"""Extract semantic campaign descriptors from the caller's exact private MAIN.

The output contains names, progression links and source identities, not executable
bytes, original images, descriptions or a runnable game representation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from campaign import MAIN_SHA256


def extract(path: Path) -> dict:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != MAIN_SHA256:
        raise ValueError('Unqualified original executable')
    from fdisbull.le import load_le
    image = load_le(data)
    def read(address, length):
        for r in image.regions:
            if r.start <= address and address + length <= r.start + len(r.data):
                return bytes(r.data[address-r.start:address-r.start+length])
        raise ValueError('Out-of-range source span')
    def name(table, index):
        pointer = struct.unpack('<I',read(table + 12*index,4))[0]
        value = read(pointer,80).split(b'\0',1)[0]
        if not value or any(c < 32 or c > 126 for c in value):
            raise ValueError('Unqualified English label')
        return value.decode('ascii')
    territories = []
    for i in range(50):
        r = read(0x5b060+19*i,19)
        # The original availability consumer reads +9..+16 and +17.
        targets = [v-1 for v in r[9:17] if v]
        if any(not 0<=v<50 for v in targets):
            raise ValueError('Invalid progression link')
        territories.append({'id':i,'label':name(0x541a4,r[18]),
                            'mission_number':r[17], 'outgoing':targets,
                            'map_rectangle_raw':list(struct.unpack_from('<4H',r)),
                            'rectangle_semantics':'source metadata; original display transform not recovered'})
    projects = {'weapon':[{'id':i,'label':name(0x54b10,i) if i < 17 else f'unidentified record {i}'} for i in range(20)],
                'mod':[{'id':i,'label':name(0x54a38,i)} for i in range(18)]}
    spans = [(0x28610,0x286d2),(0x28d60,0x28e90),(0x35e20,0x36182),
             (0x36190,0x36332),(0x38350,0x38420),(0x38420,0x38540)]
    return {'format':'syndicate-campaign-catalog-1','source_sha256':MAIN_SHA256,
            'qualification':'source-derived; admission additionally tested in an isolated original-CPU profile',
            'language_index':0,'territories':territories,'projects':projects,
            'source_windows':[{'preferred_start':hex(a),'length':b-a,
                               'sha256':hashlib.sha256(read(a,b-a)).hexdigest()} for a,b in spans]}


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('main',type=Path);ap.add_argument('output',type=Path)
    args=ap.parse_args()
    catalog=extract(args.main)
    with args.output.open('x') as out:json.dump(catalog,out,indent=2);out.write('\n')
