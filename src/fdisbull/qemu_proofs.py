"""Host model checks associated with one QEMU debugger run.

The shared proof engine checks caller-supplied finite-width expressions. A run
reference supplies provenance, not a claim that the model describes guest code,
registers, memory, source mappings or a completed guest frame.
"""
import json
import time

from .operation_budget import request_deadline
from .proofs import _json, _validate


def validate_proof_parameters(spec, *, timeout_ms=1000, author='agent', evidence=None,
                              allow_references=False, session=None):
    def reference(value):
        return allow_references and isinstance(value, str) and value.startswith('$')
    _validate(spec, allow_references=allow_references)
    if not reference(timeout_ms) and (type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000):
        raise ValueError('timeout_ms must be an integer in 1..60000')
    if not reference(author) and (not isinstance(author, str) or not 1 <= len(author) <= 256):
        raise ValueError('author must be a nonempty string of at most 256 characters')
    if evidence is not None and not reference(evidence):
        if not isinstance(evidence, list) or len(_json(evidence).encode()) > 65536:
            raise ValueError('evidence must be a JSON list within 64 KiB')
    if session is not None:
        _, run, _ = _identity(session)
        if not reference(evidence) and len(_json([{'run': run}, *(evidence or [])]).encode()) > 65536:
            raise ValueError('evidence with debugger run must be a JSON list within 64 KiB')


def _identity(session):
    project, run, selected = session.project, session.run_id, session.version
    version = project.version(selected['id'])
    metadata = session.metadata
    row = project.db.execute('SELECT version FROM debug_runs WHERE id=?', (run,)).fetchone()
    if (row is None or row['version'] != version['id'] or selected['sha256'] != version['sha256']
            or metadata.get('source_sha256') != project.meta['source_sha256']
            or metadata.get('version_sha256') != version['sha256']):
        raise ValueError('Proof check requires its exact project, source, version and debugger run')
    return project, run, version['id']


class QemuProofMixin:
    def proof_check(self, spec, *, timeout_ms=1000, author='agent', evidence=None):
        # Establish the budget before model validation. Only immutable project
        # data and host deadline fields are inspected; no native lock or control
        # guard is needed for a model whose semantics are independent of the VM.
        deadline = request_deadline(self, timeout_ms)
        vm = getattr(self, 'vm', None)
        limits = [deadline, getattr(self, '_deadline', None),
                  getattr(vm, 'operation_deadline', None),
                  *(getattr(channel, 'operation_deadline', None) for channel in
                    (getattr(vm, 'qmp', None), getattr(vm, 'gdb', None)) if channel is not None)]
        deadline = min(value for value in limits if value is not None)
        validate_proof_parameters(spec, timeout_ms=timeout_ms, author=author, evidence=evidence,
                                  session=self)
        project, run, version = _identity(self)
        # Snapshot caller-owned containers and include the run in the existing
        # evidence limit. The project engine retains its canonical result schema.
        model = json.loads(_json(spec))
        facts = json.loads(_json([{'run': run}, *(evidence or [])]))
        if len(_json(facts).encode()) > 65536:
            raise ValueError('evidence with debugger run must be a JSON list within 64 KiB')

        def remaining():
            value = int((deadline - time.monotonic()) * 1000)
            if value <= 0:
                raise TimeoutError('Proof check host deadline expired before solver admission')
            return min(timeout_ms, value)

        remaining()
        # Pin the initial run/version as host provenance. Full machine restore,
        # selected CPU undo, pending input and native histories are unaffected.
        with project.transaction(True):
            result = project.proof_check(model, version=version, timeout_ms=remaining(),
                                         author=author, evidence=facts)
            from .debugger import stamp
            project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                               (run, stamp(), 'proof-check', json.dumps(
                                   {'id': result['id'], 'status': result['result']['status']})))
        if time.monotonic() >= deadline:
            error = TimeoutError('Proof check exceeded its host deadline')
            error.result = result
            raise error
        return result
