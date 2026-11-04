"""Identify a local run explicitly; never manufacture provider identifiers."""
import os
import json
import re
import uuid


def canonical_uuid(value):
    if not isinstance(value, str):
        raise ValueError('Missing local UUID')
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError('Invalid local UUID') from exc
    if str(parsed) != value:
        raise ValueError('Local UUID must be canonical')
    return value


def execution_identity():
    origin = os.environ.get('FDISBULL_EXECUTION_ORIGIN', 'gitlab')
    if origin in ('local-linux', 'boat-linux'):
        result = {'execution_origin': origin,
                'local_run_id': canonical_uuid(os.environ.get('FDISBULL_LOCAL_RUN_ID')),
                'local_job_id': canonical_uuid(os.environ.get('FDISBULL_LOCAL_JOB_ID')),
                'job_name': os.environ['CI_JOB_NAME']}
        if origin == 'boat-linux':
            sandbox = os.environ.get('FDISBULL_BOAT_SANDBOX_ID', '')
            if not re.fullmatch(r'bx_[A-Za-z0-9_-]+', sandbox):
                raise ValueError('Invalid Boat sandbox identity')
            try:
                proof = json.loads(os.environ['FDISBULL_BOAT_WORKER_RECEIPT'])
            except (KeyError, ValueError) as exc:
                raise ValueError('Invalid Boat worker receipt identity') from exc
            validate_boat_receipt_identity(proof)
            result.update(boat_sandbox_id=sandbox, boat_worker_receipt=proof)
        return result
    if origin != 'gitlab':
        raise ValueError('Unknown execution origin')
    return {'pipeline_id': os.environ['CI_PIPELINE_ID'],
            'job_id': os.environ['CI_JOB_ID'], 'job_name': os.environ['CI_JOB_NAME']}


def validate_boat_receipt_identity(proof):
    if (not isinstance(proof, dict) or set(proof) != {'path', 'sha256', 'size'}
        or proof.get('path') != 'artifacts/receipts/boat-worker.json'
        or not isinstance(proof.get('sha256'), str)
        or not re.fullmatch(r'[0-9a-f]{64}', proof['sha256'])
        or type(proof.get('size')) is not int or proof['size'] <= 0):
        raise ValueError('Invalid Boat worker receipt identity')
    return proof
