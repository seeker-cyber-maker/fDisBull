"""Explicit Cortex-M flash/vector loading and version-bound static evidence."""
import hashlib
import json
import struct

from .model import Image, Region, Seed

DDL = '''
CREATE TABLE IF NOT EXISTS thumb_literals(version INTEGER NOT NULL, source TEXT NOT NULL,
 address TEXT NOT NULL, size INTEGER NOT NULL, PRIMARY KEY(version,source,address));
CREATE TABLE IF NOT EXISTS thumb_predicates(version INTEGER NOT NULL, address TEXT NOT NULL,
 origin TEXT NOT NULL, PRIMARY KEY(version,address,origin));
'''


def vectors(data, base, count):
    if type(count) is not int or not 16 <= count <= 256 or len(data) < count * 4:
        raise ValueError('Cortex-M requires 16..256 declared vector words within the image')
    words = struct.unpack_from('<'+'I'*count, data)
    sp = words[0]
    if sp & 3 or not 0x20000000 < sp <= 0x40000000:
        raise ValueError('Cortex-M initial SP must be word-aligned in the SRAM address range (or its top)')
    entries = []
    for index, raw in enumerate(words[1:], 1):
        address = raw & ~1
        reserved = index in (7, 8, 9, 10, 13)
        valid = not reserved and bool(raw & 1) and base + count*4 <= address < base + len(data)
        entries.append(dict(index=index, raw=raw, thumb=bool(raw & 1), address=address,
                            valid=valid, reason='reserved vector' if reserved else 'mapped Thumb target' if valid else 'zero, untagged or outside flash code'))
    if not entries[0]['valid']:
        raise ValueError('Cortex-M reset vector must be a tagged Thumb target within mapped flash code')
    return dict(initial_sp=sp, vector_count=count, vectors=entries, vector_layout='armv7-m',
                entry=entries[0]['address'], base=base,
                memory_model='Only supplied flash bytes are mapped. SRAM, EEPROM, aliases and MMIO bytes are unavailable.',
                assumptions=['Caller-declared flash base and vector count.',
                             'Armv7-M exception-vector layout; Armv8-M Security/SecureFault layouts are not interpreted.',
                             'SP is a range-validated initial value; device SRAM size is not inferred.'])


def load(data, filename, base, count, entry=None):
    if base & 127 or base + len(data) > 1 << 32:
        raise ValueError('Cortex-M vector base must be 128-byte aligned and image must fit in 32 bits')
    info = vectors(data, base, count)
    alignment = max(128, 1 << (count*4-1).bit_length())
    if base % alignment or base + len(data) > 1 << 32:
        raise ValueError('Cortex-M vector base must be table-aligned (at least 128 bytes) and image must fit in 32 bits')
    if entry is not None and entry != info['entry']:
        raise ValueError('Cortex-M entry is derived from the reset vector; omit entry override')
    split = count*4
    if split == len(data):
        raise ValueError('Cortex-M image requires code bytes after its declared vector table')
    regions = [Region('vectors', base, data[:split], False), Region('flash', base+split, data[split:], True)]
    seeds = [Seed(v['address'], 'Reset_Handler' if v['index']==1 else f'vector_{v["index"]}',
                  'Cortex-M reset vector' if v['index']==1 else 'Cortex-M interrupt vector')
             for v in info['vectors'] if v['valid']]
    return Image('raw', 'thumb', 32, info['entry'], regions, seeds,
                 dict(mapping='caller-declared Cortex-M flash', filename=filename,
                      source_sha256=hashlib.sha256(data).hexdigest(), cortex_m=info,
                      file_mappings=[dict(virtual_address=base, file_offset=0, file_size=len(data))]), source_bytes=data)


class CortexMMixin:
    def _thumb_reset(self, version):
        """Rebuild vectors from this byte version, including patched vectors."""
        from .project import key
        for table in ('thumb_literals', 'thumb_predicates'):
            self.db.execute(f'DELETE FROM {table} WHERE version=?', (version,))
        info = self.meta['loader_metadata'].get('cortex_m')
        if not info:
            return False
        regions = self.regions(version)
        data = b''.join(r.data for r in regions)
        document = self._document(version)
        self.db.execute("DELETE FROM functions WHERE version=? AND source LIKE 'Cortex-M % vector'", (version,))
        try:
            current = vectors(data, info['base'], info['vector_count'])
        except ValueError as error:
            document['cortex_m'] = dict(base=info['base'], entry=None, error=str(error))
            self.db.execute('UPDATE binary_info SET document=? WHERE version=?',(json.dumps(document),version))
            self.db.execute("INSERT OR REPLACE INTO work VALUES (?,?,?,?,?,?)",
                            (version,self.context,key(info['base']),'Cortex-M vectors','invalid',str(error)))
            return True
        document['cortex_m'] = current
        self.db.execute('UPDATE binary_info SET document=? WHERE version=?',(json.dumps(document),version))
        for item in current['vectors']:
            if not item['valid']:
                continue
            reset = item['index']==1
            self.db.execute('INSERT OR IGNORE INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',
                            (version,self.context,key(item['address']),'Reset_Handler' if reset else f'vector_{item["index"]}',
                             'Cortex-M reset vector' if reset else 'Cortex-M interrupt vector'))
            if reset:
                self._queue_code(version,item['address'],'Cortex-M reset vector')
            self._add_xref(version,info['base']+item['index']*4,item['address'],'vector',
                           json.dumps(dict(raw=item['raw'],thumb=item['thumb'],index=item['index'],source='version flash bytes')))
        return True

    def _entry_address(self, version):
        info = self._document(version).get('cortex_m') if self.arch=='thumb' else None
        return info.get('entry') if info else self.meta['entry']

    def _thumb_predicate(self, version, address):
        origins = [f'0x{int(row[0],16):x}' for row in self.db.execute(
            'SELECT origin FROM thumb_predicates WHERE version=? AND address=? ORDER BY origin',
            (version,f'{address:016x}'))]
        return dict(origins=origins,qualification='lexical IT coverage; live condition unknown') if origins else None

    def _thumb_prepare(self, version, address, ins, regions):
        from .project import key
        from .thumb import decode_thumb
        for literal in ins.get('literals', []):
            self.db.execute('INSERT OR IGNORE INTO thumb_literals VALUES (?,?,?,?)',
                            (version,key(address),key(literal['address']),literal['size']))
            if any(int(row[0],16)+row[1]>literal['address'] for row in self.db.execute(
                    'SELECT address,size FROM instructions WHERE version=? AND context=? AND address<?',
                    (version,self.context,key(literal['address']+literal['size'])))):
                ins = dict(ins, issue='Thumb literal overlaps stored code; competing interpretations retained')
        following = address + ins['size']
        for _ in range(ins.get('it_slots', 0)):
            self.db.execute('INSERT OR IGNORE INTO thumb_predicates VALUES (?,?,?)',
                            (version,key(following),key(address)))
            region = next((r for r in regions if r.start<=following<r.start+len(r.data)),None)
            child = decode_thumb(region.data[following-region.start:following-region.start+4],following) if region else None
            if not child:
                break
            row = self.db.execute('SELECT flow,size FROM instructions WHERE version=? AND context=? AND address=?',
                                  (version,self.context,key(following))).fetchone()
            if row and row['flow'] in ('jump','return','indirect_jump','stop'):
                self.db.execute("UPDATE instructions SET flow='conditional' WHERE version=? AND context=? AND address=?",
                                (version,self.context,key(following)))
                next_address = following+row['size']
                if region and next_address < region.start+len(region.data):
                    self._queue_code(version,next_address,'Thumb IT conditional continuation')
                    self._add_xref(version,following,next_address,'fallthrough','lexical IT predicate; execution is conditional')
            following += child['size']
        predicate = self.db.execute('SELECT 1 FROM thumb_predicates WHERE version=? AND address=?',(version,key(address))).fetchone()
        if predicate and ins['flow'] in ('jump','return','indirect_jump','stop'):
            ins = dict(ins, flow='conditional')
        return ins

    def _thumb_blocked(self, version, address, size):
        # Literal bytes are not silently linear-swept as instructions. A caller
        # can explicitly represent an overlapping code interpretation.
        return any(address<int(r[0],16)+r[1] and address+size>int(r[0],16)
                   for r in self.db.execute('SELECT address,size FROM thumb_literals WHERE version=?',(version,)))
