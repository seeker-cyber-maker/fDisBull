"""Source-bound profile for the authored Win16 fixture; no native claims."""
from hashlib import sha256
from pathlib import Path

from fdisbull.udc_memory_win16_shell import inspect_windows_ne

SOURCE = Path(__file__).with_name('offline_win16_oracle.c')
STATE = bytes.fromhex('4644425731075354415445')
CHECKPOINT = bytes.fromhex('b85713b86824b89a36')


def win16_recipe():
    """Commands to run separately with an explicitly supplied Open Watcom SDK."""
    return [
        ['wcc', '-bt=windows', '-ml', '-zW', '-od', '-w3',
         '-i=/opt/watcom/h', '-i=/opt/watcom/h/win',
         '-fo=ORACLE.OBJ', 'ORACLE.C'],
        ['wlink', 'system', 'windows', 'option', 'quiet', 'option', 'map=ORACLE.MAP',
         'option', 'stack=16384', 'option', 'heapsize=8192', 'name', 'ORACLE.EXE',
         'file', 'ORACLE.OBJ'],
    ]


def win16_profile(data):
    """Locate unique fixture markers in the bound entry code and automatic DS.

    The source and executable hashes are identities, not compiler provenance or
    proof of execution. A compiler output with another layout fails closed.
    """
    ne = inspect_windows_ne(data)
    def locate(marker, segment):
        start = segment['file_offset']
        payload = data[start:start + segment['file_bytes']]
        offset = payload.find(marker)
        if offset < 0 or payload.find(marker, offset + 1) >= 0 or data.count(marker) != 1:
            raise ValueError('fixture marker must occur exactly once in the declared segment')
        return offset
    code = ne['segments'][ne['entry']['segment'] - 1]
    ds = ne['segments'][ne['automatic_data_segment'] - 1]
    checkpoint = locate(CHECKPOINT, code)
    state = locate(STATE, ds)
    return {
        'format': 'fdisbull-authored-win16-oracle-1',
        'source_sha256': sha256(SOURCE.read_bytes()).hexdigest(),
        'executable_sha256': sha256(data).hexdigest(),
        'entry': 'ne:%d:%#x' % (ne['entry']['segment'], ne['entry']['offset']),
        'checkpoint': 'ne:%d:%#x' % (code['index'], checkpoint),
        'checkpoint_hex': CHECKPOINT.hex(),
        'counter': 'ne:%d:%#x' % (ds['index'], state + 5),
        'counter_initial_hex': '07',
        'frame': {'width': 320, 'height': 200, 'sample': [40, 56],
                  'initial_rgb': [224, 160, 32], 'after_right_rgb': [32, 192, 96]},
        'scope': 'static fixture profile only; compile provenance and native execution unverified',
    }
