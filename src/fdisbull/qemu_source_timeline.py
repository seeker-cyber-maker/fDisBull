"""Historical source-raster identity and stopped timeline admission."""
from copy import deepcopy

from .qemu_dos_history import _hex_digest, _json, _sha
from .qemu_frame_contract import FRAME_SOURCE
from .qemu_instrumented_checkpoint import COMMANDS
from .qemu_video_checkpoint import (VGA480_LAYOUTS, VGA480_MODELS, VBE101_ORIGIN_FIELD,
                                    valid_vbe101_origin, vbe101_flip_scanout, video_frame_size)


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
    raise ValueError('Source raster timeline requires native format-3 or later checkpoints')


def source_raster_record(info):
    """Bind the stopped phase and row observations independently of live IDs."""
    if not isinstance(info, dict) or info.get('state') != 'observing' or not info.get('frame'):
        raise ValueError('Source raster timeline requires an observing stream with a retained raster')
    logical = deepcopy(info)
    stream, epoch = logical.pop('token'), logical.pop('epoch')
    frame = logical['frame']
    del frame['epoch']
    model = info.get('model')
    layout = (dict(frame_profile=model, scanout_layout=frame['scanout-layout'])
              if model in VGA480_MODELS else {})
    if VBE101_ORIGIN_FIELD in frame:
        layout['vbe101_origin_bytes'] = frame[VBE101_ORIGIN_FIELD]
    return dict(**layout, source=FRAME_SOURCE, stream=stream, epoch=epoch,
                frame_id=frame['frame-id'], width=frame['width'], height=frame['height'],
                pixel_sha256=frame['pixel-sha256'], logical_sha256=_sha(_json(logical)))


def validate_source_raster(record):
    if not isinstance(record, dict):
        raise ValueError('Invalid stored source raster identity')
    profile = record.get('frame_profile')
    width, height = video_frame_size(profile)
    flip = vbe101_flip_scanout(profile, record.get('scanout_layout'))
    if (record.get('source') != FRAME_SOURCE
            or not isinstance(record.get('stream'), str) or not 1 <= len(record['stream']) <= 128
            or any(type(record.get(k)) is not int or not 1 <= record[k] < 1 << 64
                   for k in ('epoch', 'frame_id'))
            or type(record.get('width')) is not int or record['width'] != width
            or type(record.get('height')) is not int or record['height'] != height
            or ('scanout_layout' in record) != (profile in VGA480_MODELS)
            or profile in VGA480_MODELS and record.get('scanout_layout') not in VGA480_LAYOUTS
            or ('vbe101_origin_bytes' in record) != flip
            or flip and not valid_vbe101_origin(record.get('vbe101_origin_bytes'))
            or not _hex_digest(record.get('pixel_sha256'))
            or not _hex_digest(record.get('logical_sha256'))):
        raise ValueError('Invalid stored source raster identity')
