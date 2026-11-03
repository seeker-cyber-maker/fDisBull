"""Identify a local run explicitly; never manufacture provider identifiers."""
import os
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
    if origin == 'local-linux':
        return {'execution_origin': origin,
                'local_run_id': canonical_uuid(os.environ.get('FDISBULL_LOCAL_RUN_ID')),
                'local_job_id': canonical_uuid(os.environ.get('FDISBULL_LOCAL_JOB_ID')),
                'job_name': os.environ['CI_JOB_NAME']}
    if origin != 'gitlab':
        raise ValueError('Unknown execution origin')
    return {'pipeline_id': os.environ['CI_PIPELINE_ID'],
            'job_id': os.environ['CI_JOB_ID'], 'job_name': os.environ['CI_JOB_NAME']}
