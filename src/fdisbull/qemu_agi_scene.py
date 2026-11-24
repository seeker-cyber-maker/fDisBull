"""Read-only stopped observations for the native raw AGI pilot.

This adapter does not decode or execute AGI instructions. The native CPU owns
both the current actor snapshot and the bounded observation journal.
"""
from __future__ import annotations

import time
import re


def observe(session, *, timeout_ms=10000):
    """Bracket the native event journal with identical stopped state reads.

    The raw journal is a retained prefix, not proof of complete history. A
    position record witnesses an effective change; an unchanged assignment has
    no position record. Actor positions are current at this stopped snapshot but do
    not establish visibility or a rendered scene.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Invalid AGI scene observation timeout')
    deadline = time.monotonic() + timeout_ms / 1000
    with session._budget(session.vm, deadline):
        session._stopped()
        before = session._state()
        events = session._events()
        source = before.get('source', {}) if isinstance(before, dict) else {}
        projection = (session._json_property('agi-runtime-scene-json')
                      if isinstance(source, dict) and source.get('profile') == 'agi-2917-runtime-1'
                      else None)
        after = session._state()
    if before != after:
        raise ValueError('Stopped AGI state changed during scene observation')
    schemas = {
        'agi-2917-scalar-position-pilot-1': ('fdisbull-agi-native-state-1', 'fdisbull-agi-native-events-1'),
        'agi-2917-runtime-1': ('fdisbull-agi-runtime-state-1', 'fdisbull-agi-runtime-events-1'),
    }
    if (not isinstance(before, dict)
            or not isinstance(events, dict)
            or not isinstance(events.get('events'), list)
            or not isinstance(before.get('source'), dict)
            or before['source'] != events.get('source')
            or schemas.get(before['source'].get('profile')) != (before.get('schema'), events.get('schema'))
            or not isinstance(before.get('guest'), dict)
            or not isinstance(before['guest'].get('actors'), list)
            or not isinstance(before.get('observation'), dict)
            or before['observation'].get('epoch') != events.get('epoch')):
        raise ValueError('Unsupported or inconsistent AGI scene observation')
    source = before['source']
    guest = before['guest']
    observation = before['observation']
    rows = events['events']
    def uint(value):
        return type(value) is int and value >= 0
    def sha(value):
        return type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None
    if (not sha(source.get('sha256')) or not uint(observation.get('epoch'))
            or not uint(events.get('epoch')) or not all(isinstance(row, dict) for row in rows)
            or not all(uint(observation.get(key)) for key in ('mask', 'capacity', 'count', 'eligible', 'dropped'))
            or observation['mask'] > 3 or observation['count'] != len(rows)
            or observation['count'] > observation['capacity']
            or observation['eligible'] != observation['count'] + observation['dropped']
            or not isinstance(observation.get('per_channel'), dict)):
        raise ValueError('Invalid native AGI observation counters or source identity')
    channels = observation['per_channel']
    for name in ('disasm', 'scene'):
        channel = channels.get(name)
        if (not isinstance(channel, dict)
                or not all(uint(channel.get(key)) for key in ('eligible', 'stored', 'dropped'))
                or channel['eligible'] != channel['stored'] + channel['dropped']):
            raise ValueError('Invalid native AGI observation channel counters')
    if any(sum(channels[name][key] for name in ('disasm', 'scene')) != observation[total]
           for key, total in (('stored', 'count'), ('eligible', 'eligible'), ('dropped', 'dropped'))):
        raise ValueError('Inconsistent native AGI observation channel totals')
    identity = session.identity
    if not isinstance(identity, dict):
        raise ValueError('Missing AGI session identity')
    if source['profile'] == 'agi-2917-runtime-1':
        if (source['sha256'] != identity.get('runtime_package_sha256')
                or len(guest['actors']) != 256
                or not sha(source.get('logic_sha256')) or not uint(source.get('logic_id'))
                or source['logic_id'] > 255 or events.get('observation') != observation):
            raise ValueError('Invalid native AGI runtime identity or event counters')
    elif (source['sha256'] != identity.get('source_sha256')
          or source.get('size') != identity.get('source_size')
          or len(guest['actors']) != 16
          or not uint(source.get('size')) or source['size'] < 1):
        raise ValueError('Invalid native AGI raw source size')
    if projection is not None:
        guest = before['guest']
        if (not isinstance(projection, dict)
                or projection.get('schema') != 'fdisbull-agi-runtime-scene-1'
                or projection.get('source') != before['source']
                or type(projection.get('width')) is not int or projection['width'] != 160
                or type(projection.get('height')) is not int or projection['height'] != 168
                or not all(uint(projection.get(key)) for key in ('revision', 'presentation', 'picture_shown'))
                or not all(uint(guest.get(key)) for key in ('scene_revision', 'presentation_revision', 'picture_shown'))
                or projection.get('revision') != guest.get('scene_revision')
                or projection.get('presentation') != guest.get('presentation_revision')
                or projection.get('picture_shown') != guest.get('picture_shown')):
            raise ValueError('Inconsistent native AGI runtime scene projection')
        for name in ('visual', 'priority'):
            plane = projection.get(name)
            if (type(plane) is not str or len(plane) != 160 * 168 * 2
                    or any(c not in '0123456789abcdef' for c in plane)
                    or any(pixel > 15 for pixel in bytes.fromhex(plane))):
                raise ValueError('Invalid native AGI runtime scene plane')
    return {
        'schema': 'fdisbull-qemu-agi-scene-observation-1',
        'evidence': {
            'state': 'current stopped native state',
            'events': 'retained native observations; consult mask and dropped counters',
            'static_predictions': 'not included',
            'projection': 'native stopped scene planes' if projection is not None else 'unavailable for scalar profile',
            'visibility_and_rendering': 'native projection only; original-game equivalence not established',
        },
        'state': before,
        'events': events,
        'projection': projection,
    }
