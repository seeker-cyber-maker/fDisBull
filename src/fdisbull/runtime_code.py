"""Explicit temporal interpretations of qualified runtime byte observations."""
from copy import deepcopy
import hashlib
import json

from .model import Region

RUNTIME_DDL = '''
CREATE TABLE IF NOT EXISTS runtime_versions(
 version INTEGER PRIMARY KEY REFERENCES versions(id),
 artifact TEXT NOT NULL REFERENCES debug_artifacts(id),
 document TEXT NOT NULL, sha256 TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS runtime_capture_once ON runtime_versions(artifact)
 WHERE json_extract(document,'$.kind')='runtime-capture';
'''


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def qualify_capture(session, observed):
    from .project import now
    registers = session.registers()
    dos = session.project.meta['format'] == 'MZ'
    identity = {'run': session.run_id, 'source_version': session.version['id'],
                'source_version_sha256': session.version['sha256'],
                'source_sha256': session.project.meta['source_sha256'],
                'arch': session.project.arch, 'bits': session.project.bits,
                'cpu_mode': registers['cpu_mode'], 'captured_at': now(),
                'project_base': hex(session.static_base), 'runtime_base': hex(session.runtime_base),
                'delta': session.delta, 'backend': session.metadata.get('backend', 'dosbox'),
                'backend_sha256': session.metadata.get('emulator_sha256'),
                'runtime_inputs': {k: v['sha256'] for k, v in session.metadata.get('runtime_inputs', {}).items()}}
    if dos:
        runtime = int(observed['runtime_address'], 16)
        cs = int(observed['runtime_cs'], 16)
        if not 0 <= runtime - cs * 16 <= 0xffff:
            cs = runtime >> 4
        identity.update(runtime_cs=cs, project_cs=cs-session.runtime_load+session.dos['load_segment'])
    identity['layer_hashes']={i:session.project.debug_layer_info(i)['sha256'] for i in observed['active_layers']}
    return {**observed, 'format': 'fdisbull-runtime-code-1', 'identity': identity,
            'capture_registers': registers, 'execution_proven': False}


class RuntimeCodeMixin:
    def _runtime_record(self, version):
        row = self.db.execute('SELECT * FROM runtime_versions WHERE version=?', (version,)).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row['document'].encode()).hexdigest() != row['sha256']:
            raise ValueError('Temporal interpretation provenance hash mismatch')
        return json.loads(row['document'])

    def runtime_version_info(self, version=None):
        v = self.version(version)['id']
        record = self._runtime_record(v)
        return {'version': v, 'temporal': record is not None, **(record or {})}

    def _runtime_store(self, version, record):
        text = packed(record)
        self.db.execute('INSERT INTO runtime_versions VALUES (?,?,?,?)',
                        (version, record['artifact'], text, hashlib.sha256(text.encode()).hexdigest()))

    def _runtime_fork(self, parent, regions, label, origin, record):
        from .project import key, now
        cur = self.db.execute('INSERT INTO versions(parent,label,origin,sha256,created) VALUES (?,?,?,?,?)',
                              (parent, label, origin, self.digest(regions), now()))
        v = cur.lastrowid
        for r in regions:
            self.db.execute('INSERT INTO regions VALUES (?,?,?,?,?,?)',
                            (v, r.name, key(r.start), r.data, r.executable, r.writable))
        self.db.execute('INSERT INTO annotations SELECT ?,context,address,kind,text,author,created,? FROM annotations WHERE version=?', (v, parent, parent))
        self.db.execute("INSERT INTO functions SELECT ?,context,address,name,source,status FROM functions WHERE version=? AND source!='direct call'", (v, parent))
        self.db.execute('INSERT INTO definitions SELECT ?,context,address,representation,size,author FROM definitions WHERE version=?', (v, parent))
        document = self._document(parent)
        document['runtime_interpretation'] = {'artifact': record['artifact'], 'kind': record['kind'],
                                               'disk_image_reconstructed': False}
        document.setdefault('warnings', []).append('Temporal mapped-byte interpretation; unobserved bytes inherit the parent. No reconstructed disk image.')
        self.db.execute('INSERT INTO binary_info VALUES (?,?,NULL)', (v, packed(document)))
        self._index_symbols(v, document)
        self._copy_interpretations(parent, v)
        self._runtime_store(v, record)
        self._reset_analysis(v)
        return v

    def _runtime_patch(self, parent, address, replacement, label, origin):
        record = deepcopy(self._runtime_record(parent))
        regions = self.regions(parent)
        match = next((r for r in regions if r.start <= address and address+len(replacement) <= r.start+len(r.data)), None)
        if match is None:
            raise ValueError('patch must fit entirely inside one mapped region')
        changed = [Region(r.name, r.start, r.data[:address-r.start]+replacement+r.data[address-r.start+len(replacement):]
                          if r is match else r.data, r.executable, r.writable) for r in regions]
        record.update(kind='authored-edit', parent=parent)
        record['edits'] = record.get('edits', []) + [{'address': address, 'size': len(replacement),
                                                     'sha256': hashlib.sha256(replacement).hexdigest(), 'origin': origin}]
        v = self._runtime_fork(parent, changed, label, origin, record)
        return {'version': v, 'parent': parent, 'address': hex(address), 'bytes': replacement.hex(),
                'sha256': self.version(v)['sha256'], 'temporal': self.runtime_version_info(v),
                'analysis': 'fresh work queue; raw runtime capture and earlier interpretations preserved'}

    def _runtime_normalize(self, version, address, raw, delta):
        """Normalize only complete, unmodified loader fixups; never guess pointer roles."""
        if not delta:
            return raw, []
        fixups = []
        if self.meta['format'] == 'MZ':
            fixups = [(r['linear_address'], 2, delta//16) for r in self._document(version)['dos']['relocations']]
        elif self.meta['format'] == 'PE':
            import lief
            source = self.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (version,)).fetchone()[0]
            if source is None:
                raise ValueError('Capture source has no original relocation evidence')
            binary = lief.PE.parse(list(bytes(source)))
            for block in binary.relocations:
                for item in block.entries:
                    if int(item.type) == 0:
                        continue
                    if int(item.type) != 10:
                        raise ValueError('Unsupported PE relocation type in runtime interpretation')
                    fixups.append((self.meta['loader_metadata']['imagebase']+block.virtual_address+item.position, 8, delta))
        result = bytearray(raw); normalized = []; touched = set()
        regions = self.regions(version)
        for site, width, adjustment in fixups:
            if not site < address+len(raw) or not address < site+width:
                continue
            if site < address or site+width > address+len(raw):
                raise ValueError('Runtime capture cuts through a loader relocation; capture the complete fixup')
            positions = set(range(site, site+width))
            if touched & positions:
                raise ValueError('Overlapping loader relocations cannot be normalized safely')
            touched.update(positions)
            region = next(r for r in regions if r.start <= site and site+width <= r.start+len(r.data))
            parent = region.data[site-region.start:site-region.start+width]
            expected = ((int.from_bytes(parent, 'little')+adjustment) % (1 << (8*width))).to_bytes(width, 'little')
            offset = site-address
            if raw[offset:offset+width] != expected:
                raise ValueError('Modified runtime relocation has no verified static counterpart')
            result[offset:offset+width] = parent
            normalized.append({'address': hex(site), 'width': width, 'runtime_hex': expected.hex(), 'project_hex': parent.hex()})
        return bytes(result), normalized

    def debug_promote_code(self, artifact, *, label='runtime interpretation', max_instructions=128, defer=False):
        from .project import integer
        budget = integer(max_instructions, 'max_instructions', 1, 1000000)
        if type(defer) is not bool or not isinstance(label, str) or not label.strip() or len(label) > 256:
            raise ValueError('Promotion requires a boolean defer and a 1..256 character label')
        row = self.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?', (artifact,)).fetchone()
        if row is None or row['kind'] != 'code-snapshot':
            raise ValueError('Promotion requires a runtime code snapshot')
        data = bytes(row['data'])
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Runtime code snapshot hash mismatch')
        observation = json.loads(data)
        if observation.get('format') != 'fdisbull-runtime-code-1':
            raise ValueError('Legacy code capture lacks qualified mapping identity; capture again before promotion')
        identity = observation['identity']; parent = self.version(row['version'])
        if (identity['source_version'] != parent['id'] or identity['source_version_sha256'] != parent['sha256']
                or identity['source_sha256'] != self.meta['source_sha256'] or identity['run'] != row['run']
                or identity['arch'] != self.arch or identity['bits'] != self.bits):
            raise ValueError('Runtime capture source identity mismatch')
        if self.meta['format'] not in ('MZ', 'PE') or identity['cpu_mode'] != ('real' if self.meta['format'] == 'MZ' else 'long64'):
            raise ValueError('Runtime promotion supports real-mode MZ and x86-64 PE code')
        expected_base = self._document(parent['id'])['dos']['image_base'] if self.meta['format'] == 'MZ' else self.meta['loader_metadata']['imagebase']
        if isinstance(expected_base,str):expected_base=int(expected_base,0)
        if self.arch != 'x86' or int(identity['project_base'], 16) != expected_base or type(identity['delta']) is not int:
            raise ValueError('Runtime capture architecture or base mapping mismatch')
        if observation['view'] == 'execute' and not observation.get('overlay_valid', True):
            raise ValueError('Stale execution overlay cannot be promoted')
        if observation['view'] not in ('ram','execute') or set(identity['layer_hashes']) != set(observation['active_layers']):
            raise ValueError('Runtime capture byte view or layer identity mismatch')
        for identifier,digest in identity['layer_hashes'].items():
            layer=self.debug_layer_info(identifier)
            if layer['version'] != parent['id'] or layer['sha256'] != digest:
                raise ValueError('Runtime capture layer definition mismatch')
        address = int(observation['project_address'], 16); runtime = int(observation['runtime_address'], 16)
        delta = identity['delta']; raw = bytes.fromhex(observation['hex'])
        if (runtime-address != delta or int(identity['runtime_base'], 16)-int(identity['project_base'], 16) != delta
                or not 1 <= len(raw) <= 65536 or hashlib.sha256(raw).hexdigest() != observation['sha256']):
            raise ValueError('Runtime capture mapping or byte identity mismatch')
        regions = self.regions(parent['id'])
        match = next((r for r in regions if r.start <= address and address+len(raw) <= r.start+len(r.data)), None)
        if match is None or not match.executable:
            raise ValueError('Runtime code capture must fit an executable project region')
        cs = identity.get('project_cs')
        if self.meta['format'] == 'MZ':
            if delta % 16:
                raise ValueError('DOS relocation delta must preserve paragraph alignment')
            self._dos_parse_address(address, cs)
            if identity['runtime_cs']*16+address-cs*16 != runtime:
                raise ValueError('Runtime capture CS mapping mismatch')
        normalized, corrections = self._runtime_normalize(parent['id'], address, raw, delta)
        with self.transaction(True):
            existing = self.db.execute("SELECT version FROM runtime_versions WHERE artifact=? AND json_extract(document,'$.kind')='runtime-capture'", (artifact,)).fetchone()
            if existing:
                v = existing[0]
            else:
                record = {'kind': 'runtime-capture', 'artifact': artifact, 'artifact_sha256': row['sha256'],
                          'run': row['run'], 'parent': parent['id'], 'source_version': parent['id'],
                          'source_version_sha256': parent['sha256'], 'identity': identity, 'view': observation['view'],
                          'address': address, 'size': len(raw), 'project_cs': cs,
                          'active_layers': observation['active_layers'], 'generation': observation['generation'],
                          'raw_sha256': hashlib.sha256(raw).hexdigest(), 'normalized_sha256': hashlib.sha256(normalized).hexdigest(),
                          'relocations': corrections, 'edits': [], 'execution_proven': False,
                          'scope': 'Captured span normalized into project space; all other bytes inherited and unobserved'}
                changed = [Region(r.name, r.start, r.data[:address-r.start]+normalized+r.data[address-r.start+len(normalized):]
                                  if r is match else r.data, r.executable, r.writable) for r in regions]
                v = self._runtime_fork(parent['id'], changed, label, 'runtime-capture '+artifact, record)
            analysis = self.analysis_status(v) if defer else self.analyze(version=v, start=address, cs=cs, max_instructions=budget)
        return {'version': v, 'parent': parent['id'], 'artifact': artifact, 'sha256': self.version(v)['sha256'],
                'analysis': analysis, 'temporal': self.runtime_version_info(v)}

    def _runtime_byte_provenance(self, record, address, size=1):
        overlaps = address < record['address']+record['size'] and record['address'] < address+size
        full = record['address'] <= address and address+size <= record['address']+record['size']
        edited = any(address < e['address']+e['size'] and e['address'] < address+size for e in record['edits'])
        return {'kind': 'authored-edit' if edited else 'runtime-capture' if full else 'mixed' if overlaps else 'inherited-unobserved',
                'artifact': record['artifact'], 'view': record['view'], 'fully_observed': full and not edited,
                'execution_proven': False}

    def debug_trace_view(self, artifact, *, version):
        """Read-only byte/context comparison; never assign a trace to a whole version."""
        from iced_x86 import Decoder
        row=self.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(artifact,)).fetchone()
        if row is None or row['kind']!='trace':raise ValueError('Expected a stored instruction trace')
        data=bytes(row['data'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('Stored trace hash mismatch')
        document=json.loads(data);target=self.version(version)['id'];record=self._runtime_record(target)
        if record is None or record['source_version']!=row['version']:raise ValueError('Trace and temporal interpretation require the same source version')
        if 'observation_contract' not in document:raise ValueError('Trace lacks qualified observation semantics; capture a new trace')
        regions=self.regions(target);events=[];dos=self.meta['format']=='MZ'
        for index,event in enumerate(document['events']):
            item={'index':index,'identity':event.get('identity'),'observation':event.get('observation'),
                  'bytes_match':None,'analysis_match':False}
            address=event.get('project_address');raw=event.get('execution_bytes',event.get('bytes'))
            if address is None or not raw:
                item['reason']='No mapped project instruction bytes';events.append(item);continue
            a=int(address,16);context=event['identity']['context'];cs=None
            if dos:
                if not context or not context.startswith('real:'):
                    item['reason']='Unknown segmented context';events.append(item);continue
                cs=int(context.split(':')[1],16);pc=a-cs*16
                runtime=int(event['address']['segment'],16)*16+int(event['address']['offset'],16)
            else:pc=a;runtime=int(event['address'],16)
            instruction=Decoder(16 if dos else 64,bytes.fromhex(raw),ip=pc).decode()
            if instruction.is_invalid:
                item['reason']='Invalid observed instruction';events.append(item);continue
            observed=bytes.fromhex(raw)[:instruction.len]
            try:normalized,_=self._runtime_normalize(row['version'],a,observed,runtime-a)
            except ValueError as error:
                item['reason']=str(error);events.append(item);continue
            region=next((r for r in regions if r.start<=a and a+len(normalized)<=r.start+len(r.data)),None)
            item['bytes_match']=region is not None and region.data[a-region.start:a-region.start+len(normalized)]==normalized
            stored=self.disassembly(a,cs=cs,version=target,lines=1)['instructions']
            item['analysis_match']=bool(item['bytes_match'] and stored and int(stored[0]['address'],16)==a and stored[0]['bytes']==normalized.hex())
            item['byte_provenance']=self._runtime_byte_provenance(record,a,len(normalized))
            events.append(item)
        return {'artifact':artifact,'artifact_sha256':row['sha256'],'version':target,'events':events,
                'scope':'Per-instruction byte/context comparison only; completion remains native; no claim the entire temporal version executed'}

    def _runtime_snapshot(self, snapshot, *, nodes='instructions'):
        record = self._runtime_record(snapshot['version'])
        if record is not None:
            snapshot['temporal'] = record
            for row in snapshot.get(nodes, []):
                row['byte_provenance'] = self._runtime_byte_provenance(record, int(row['address'], 16), row['size'])
        return snapshot
