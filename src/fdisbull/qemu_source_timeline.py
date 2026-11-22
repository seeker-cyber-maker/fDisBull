"""Historical source-raster identity and stopped timeline admission."""
from copy import deepcopy

from .qemu_dos_history import _hex_digest, _json, _sha
from .qemu_frame_contract import FRAME_SOURCE
from .qemu_instrumented_checkpoint import COMMANDS


SOURCE_RASTER = 'source-raster'
SOURCE_UNIT = 'accepted source raster followed by an owned safe CPU stop'


def source_timeline_capable(session):
    return bool(session.capabilities.get('frame_step')
        and session.capabilities.get('rewind')
        and COMMANDS | {'query-qmp-schema'} <= session.vm.qmp_commands)


def require_source_checkpoint_schema(vm):
    schema = vm.qmp.call('query-qmp-schema', max_reply_bytes=4 * 1024**2)
    if isinstance(schema, list) and all(isinstance(entry, dict) for entry in schema):
        entries = {entry.get('name'): entry for entry in schema}
        command = entries.get('x-fdisbull-instrumented-checkpoint-import', {})
        result = entries.get(command.get('ret-type'), {})
        if result.get('meta-type') == 'object' and {
                'video-frame-token', 'video-frame-generation'} <= {
                member.get('name') for member in result.get('members', [])
                if isinstance(member, dict)}:
            return
    raise ValueError('Source raster timeline requires native format-3 checkpoints')


def source_raster_record(info):
    """Bind the stopped phase and row observations independently of live IDs."""
    if not isinstance(info, dict) or info.get('state') != 'observing' or not info.get('frame'):
        raise ValueError('Source raster timeline requires an observing stream with a retained raster')
    logical = deepcopy(info)
    stream, epoch = logical.pop('token'), logical.pop('epoch')
    frame = logical['frame']
    del frame['epoch']
    return dict(source=FRAME_SOURCE, stream=stream, epoch=epoch,
                frame_id=frame['frame-id'], width=frame['width'], height=frame['height'],
                pixel_sha256=frame['pixel-sha256'], logical_sha256=_sha(_json(logical)))


def validate_source_raster(record):
    if (not isinstance(record, dict) or record.get('source') != FRAME_SOURCE
            or not isinstance(record.get('stream'), str) or not 1 <= len(record['stream']) <= 128
            or any(type(record.get(k)) is not int or not 1 <= record[k] < 1 << 64
                   for k in ('epoch', 'frame_id'))
            or type(record.get('width')) is not int or record['width'] != 320
            or type(record.get('height')) is not int or record['height'] != 200
            or not _hex_digest(record.get('pixel_sha256'))
            or not _hex_digest(record.get('logical_sha256'))):
        raise ValueError('Invalid stored source raster identity')
