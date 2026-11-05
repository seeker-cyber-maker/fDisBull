"""Generic private save-corpus intake; never executes or edits donor content.

A same-sized file and successful parsing do not qualify original-game compatibility.
Receipt summaries describe supplied evidence; they are not signed attestations.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import zipfile

REJECTED_SUFFIXES = {'.exe','.com','.dll','.bat','.cmd','.sh','.ps1','.py','.js','.vbs'}


def inspect_archive(path: Path, *, expected_paths: set[str], byte_budget: int = 16 * 1024 * 1024) -> dict:
    """Inventory an untrusted ZIP without extraction; the caller supplies a profile."""
    if not expected_paths or any(PurePosixPath(n).is_absolute() or '..' in PurePosixPath(n).parts
                                 or '\\' in n for n in expected_paths):
        raise ValueError('Explicit safe expected paths are required')
    if type(byte_budget) is not int or not 1 <= byte_budget <= 128 * 1024 * 1024:
        raise ValueError('Invalid archive budget')
    files, seen, total = [], set(), 0
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > 1024:
            raise ValueError('Too many archive entries')
        for item in archive.infolist():
            name = item.filename
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe archive name')
            if name.casefold() in seen:
                raise ValueError('Case-colliding or duplicate member')
            seen.add(name.casefold())
            mode = item.external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise ValueError('Symbolic links are not save inputs')
            if item.is_dir():
                continue
            if item.flag_bits & 1 or p.suffix.lower() in REJECTED_SUFFIXES:
                raise ValueError('Encrypted or executable donor content is not accepted')
            total += item.file_size
            if total > byte_budget:
                raise ValueError('Uncompressed byte budget exceeded')
            if name not in expected_paths:
                raise ValueError('Unexpected donor file; revise the explicit input profile first')
            data = archive.read(item)
            if len(data) != item.file_size:
                raise ValueError('Member length mismatch')
            files.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    missing = sorted(expected_paths - {f['path'] for f in files})
    return {'format':'save-seed-intake-1','archive_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'files':files,'missing':missing,'status':'incomplete' if missing else 'candidate',
            'native_compatible':False,'native_executed':False,'files_extracted':False}


def qualification(receipt: dict) -> dict:
    """Summarize explicit gates without accepting 'loads okay' as sufficient."""
    gates = ['edition_identity_checked','bundle_complete','original_loader_completed',
             'state_invariants_checked','required_system_observed','original_tick_observed',
             'save_reload_checked','candidate_preserved']
    missing = [g for g in gates if receipt.get(g) is not True]
    synthetic = receipt.get('origin') == 'diagnostic-generated'
    return {'status':'qualified-for-recorded-slice' if not missing else 'not-qualified',
            'missing_gates':missing,'origin':receipt.get('origin','unknown'),
            'normal_progression_proven':False,
            'requires_intervention_label':synthetic,
            'scope':receipt.get('scope','unknown'),
            'warning':'This checks receipt fields, not authenticity or arbitrary-edition portability.'}
