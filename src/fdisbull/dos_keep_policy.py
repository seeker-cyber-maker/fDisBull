"""Opt-in host publication journal for witnessed DOS-created workspace files.

The journal lives in project artifacts, independently of the guest rewind cursor.
A pending reservation is never retried automatically.
"""
import hashlib
import json
import os
from pathlib import Path

from .dos_file_layers import WorkspaceStore
from .qemu_workspace import _dos_path

FORMAT = 'fdisbull-dos-keep-policy-1'
PROVENANCE = 'fdisbull-dos-guest-create-1'
CONFIG_KIND = 'workspace-keep-policy'
EVENT_KIND = 'workspace-keep-policy-event'
PROVENANCE_KIND = 'workspace-guest-create-provenance'


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _directory(path):
    path = Path(path)
    if not path.is_absolute() or any(part in ('.', '..') for part in path.parts):
        raise ValueError('Keep directory must be an absolute existing directory')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        st = os.fstat(fd)
        return dict(path=str(path), device=st.st_dev, inode=st.st_ino)
    finally:
        os.close(fd)


class KeepPolicyStore:
    def __init__(self, session):
        self.session = session
        self.db = session.project.db
        self.version = session.version['id']
        self.workspace = WorkspaceStore(session)

    def _put(self, kind, doc):
        data = _encode(doc)
        return self.session._artifact('keep-policy.json', kind, data,
                                      dict(format=FORMAT, policy=doc.get('policy')))

    def _read(self, identifier, kind):
        row = self.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?', (identifier,)).fetchone()
        if row is None or row['kind'] != kind or row['version'] != self.version:
            raise ValueError('Missing or wrong-version keep artifact')
        raw = bytes(row['data'])
        if _sha(raw) != row['sha256']:
            raise ValueError('Keep artifact hash mismatch')
        try:
            doc = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError('Invalid keep artifact JSON') from error
        if not isinstance(doc, dict):
            raise ValueError('Invalid keep artifact document')
        return row, doc

    def _events(self, policy):
        rows = self.db.execute('SELECT a.id FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.kind=? AND r.version=? ORDER BY a.rowid', (EVENT_KIND, self.version)).fetchall()
        events = []
        for row in rows:
            _, event = self._read(row['id'], EVENT_KIND)
            if event.get('format') != FORMAT:
                raise ValueError('Invalid keep journal event')
            if event.get('policy') == policy:
                events.append(event)
        if len(events) > 1024:
            raise ValueError('Keep journal exceeds bounded event count')
        return events

    def create(self, path, directory, observer_token, base_generation):
        if self.db.in_transaction:
            raise ValueError('Keep policy requires no caller transaction')
        path = _dos_path(path)
        if not isinstance(observer_token, str) or not observer_token:
            raise ValueError('Observer token is required')
        base = self.workspace.load(base_generation)
        if path in base['manifest']['protected_dos_paths']:
            raise ValueError('Keep path is protected')
        root = _directory(directory)
        manifest = dict(format=FORMAT, path=path, directory=root, observer_token=observer_token,
                        base_generation=base_generation, source_sha256=self.session.metadata['source_sha256'],
                        version=self.version, enabled=True)
        with self.session.project.transaction(True):
            ref = self._put(CONFIG_KIND, manifest)
        return dict(**ref, manifest=manifest)

    def load(self, policy_id):
        row, doc = self._read(policy_id, CONFIG_KIND)
        if doc.get('format') != FORMAT or doc.get('version') != self.version or doc.get('source_sha256') != self.session.metadata.get('source_sha256'):
            raise ValueError('Keep policy source or format differs')
        return dict(artifact=policy_id, sha256=row['sha256'], manifest=doc)

    def _check_root(self, config):
        expected = config['directory']
        if _directory(expected['path']) != expected:
            raise ValueError('Keep directory identity changed')

    def status(self, policy_id):
        config = self.load(policy_id)['manifest']
        events = self._events(policy_id)
        enabled = config['enabled']
        for event in events:
            if event.get('action') == 'enabled':
                enabled = event['enabled']
        reservations = [e for e in events if e.get('action') == 'reserve']
        completions = [e for e in events if e.get('action') == 'complete']
        return dict(policy=policy_id, enabled=enabled, reservations=len(reservations),
                    completed=len(completions), pending=len(reservations)-len(completions), events=events)

    def set_enabled(self, policy_id, enabled):
        if type(enabled) is not bool:
            raise ValueError('Enabled must be a boolean')
        if self.db.in_transaction:
            raise ValueError('Keep policy requires no caller transaction')
        with self.session.project.transaction(True):
            state = self.status(policy_id)
            if len(state['events']) + state['pending'] + 1 > 1024:
                raise ValueError('Keep journal exceeds bounded event count')
            self._put(EVENT_KIND, dict(format=FORMAT, policy=policy_id, action='enabled', enabled=enabled))
        return self.status(policy_id)

    def apply(self, policy_id, generation, provenance_receipt):
        if self.db.in_transaction:
            raise ValueError('Keep policy requires no caller transaction')
        if not isinstance(provenance_receipt, dict):
            raise ValueError('A stored provenance reference is required')
        row, proof = self._read(provenance_receipt.get('artifact'), PROVENANCE_KIND)
        if provenance_receipt.get('sha256') != row['sha256'] or proof.get('format') not in (PROVENANCE, 'fdisbull-dos-save-operations-1'):
            raise ValueError('Invalid provenance reference')
        # Deferred import avoids the policy/provenance module dependency cycle.
        from .qemu_dos_provenance import validate_proof_document, _stored_proof
        if proof.get('format') == 'fdisbull-dos-save-operations-1':
            proof, _ = _stored_proof(self.session, provenance_receipt)
        else:
            validate_proof_document(proof)
        config = self.load(policy_id)['manifest']
        for key, expected in (('path', config['path']), ('source_sha256', config['source_sha256']),
                              ('version', self.version), ('base_generation', config['base_generation']),
                              ('generation', generation), ('observer_token', config['observer_token'])):
            if proof.get(key) != expected:
                raise ValueError('Provenance does not match keep policy')
        loaded = self.workspace.load(generation)
        if loaded['manifest']['base'] != config['base_generation']:
            raise ValueError('Generation does not descend from policy base')
        entry = next((x for x in loaded['entries'] if x['dos_path'] == config['path']), None)
        if (not entry or entry['type'] != 'file' or config['path'] in loaded['manifest']['protected_dos_paths']
                or entry['path'].casefold() in loaded['manifest']['protected_paths']
                or proof.get('payload_sha256') != entry['sha256'] or proof.get('size') != entry['size']):
            raise ValueError('Provenance does not match eligible workspace bytes')
        digest = entry['sha256']
        with self.session.project.transaction(True):
            status = self.status(policy_id)
            if not status['enabled']:
                raise ValueError('Keep policy is disabled')
            self._check_root(config)
            reservations = [e for e in status['events'] if e.get('action') == 'reserve']
            matching = next((e for e in reservations if e['payload_sha256'] == digest), None)
            if matching:
                completions = [e for e in status['events'] if e.get('action') == 'complete' and e.get('sequence') == matching['sequence']]
                if not completions:
                    return dict(outcome='needs-reconciliation', policy=policy_id, reservation=matching)
                destination = Path(config['directory']['path']) / matching['filename']
                parent = os.open(config['directory']['path'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    import stat
                    parent_stat = os.fstat(parent)
                    if (parent_stat.st_dev, parent_stat.st_ino) != (config['directory']['device'], config['directory']['inode']):
                        raise ValueError('Keep directory identity changed')
                    fd = os.open(matching['filename'], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                    try:
                        st = os.fstat(fd)
                        if not stat.S_ISREG(st.st_mode): raise ValueError('Kept output is not a regular file')
                        data = bytearray()
                        while True:
                            part = os.read(fd, 65536)
                            if not part: break
                            data.extend(part)
                            if len(data) > entry['size']: raise ValueError('Kept output size differs')
                    finally:
                        os.close(fd)
                finally:
                    os.close(parent)
                if len(data) != entry['size'] or _sha(data) != digest:
                    raise ValueError('Kept output bytes differ')
                return dict(outcome='already-kept', policy=policy_id, destination=str(destination), sha256=digest)
            if len(reservations) >= 128:
                raise ValueError('Keep policy version bound reached')
            if len(status['events']) + status['pending'] + 2 > 1024:
                raise ValueError('Keep journal has no room for a reservation and completion')
            sequence = max((e['sequence'] for e in reservations), default=0) + 1
            reservation = dict(format=FORMAT, policy=policy_id, action='reserve', sequence=sequence,
                               filename=f'{sequence:08d}.SAV', payload_sha256=digest,
                               generation=generation, provenance=provenance_receipt['artifact'])
            self._put(EVENT_KIND, reservation)
        destination = Path(config['directory']['path']) / reservation['filename']
        exported = None
        try:
            exported = self.workspace.export_file(generation, config['path'], destination,
                expected_parent_identity={k:config['directory'][k] for k in ('device','inode')})
            with self.session.project.transaction(True):
                self._put(EVENT_KIND, dict(format=FORMAT, policy=policy_id, action='complete',
                                          sequence=sequence, export=exported))
        except BaseException as error:
            error.result = dict(policy=policy_id, reservation=reservation,
                                export=exported if exported is not None else getattr(error, 'result', None),
                                outcome='needs-reconciliation')
            raise
        return dict(outcome='kept', policy=policy_id, reservation=reservation, export=exported)
