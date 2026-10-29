"""Native acceptance for pinned spatial evidence and fair-play checkpoints."""
import base64
import hashlib
import os
from pathlib import Path

import pytest
from PIL import Image

from fdisbull.project import Project


@pytest.fixture
def native_backend(request):
    configured = os.environ.get('FDISBULL_DOSBOX')
    if not configured:
        if request.config.getoption('--require-native', default=False):
            pytest.fail('Native spatial acceptance requires FDISBULL_DOSBOX')
        pytest.skip('Set FDISBULL_DOSBOX for native spatial acceptance')
    backend = Path(configured).expanduser().resolve(strict=True)
    if not backend.is_file() or not os.access(backend, os.X_OK):
        pytest.fail('FDISBULL_DOSBOX must name an executable native backend')
    return str(backend)


def _pixel(rgb):
    return {'pixels': {'samples': [{'x': 0, 'y': 0, 'rgb': list(rgb)}]}}


def _program():
    # COM fixture: enter mode 13h, write room id 1 at DS:0200, paint a
    # 64x64 red patch in VGA memory, then spin. All behavior is guest code.
    return bytes.fromhex('b81300cd108cc88ed8c606000201b800a08ec031ffb00cba4000b94000f3aa81c700014a75f4ebfe')


def test_native_pinned_spatial_evidence_and_fair_play_checkpoint(tmp_path, native_backend):
    binary = tmp_path / 'SPATIAL.COM'
    binary.write_bytes(_program())
    database = tmp_path / 'spatial.fdb'
    with Project.create(database, binary, image='com') as project:
        project.analyze(max_instructions=64)
        with project.debugger(native_backend, tmp_path) as session:
            session.run(guest_ms=100, timeout_ms=5000, fast_forward=True)
            initial = session.frame_probe([[0, 0], [100, 100]])
            red, black = [sample['rgb'] for sample in initial['samples']]
            assert red != black

            image = session.screenshot('spatial-reference.png')
            definition = {
                'format': 'fdisbull-scene-1', 'width': image['metadata']['width'],
                'height': image['metadata']['height'], 'mode_id': image['metadata']['mode_id'],
                'reference': image['artifact'],
                'context': {'state': 'fixture room initialized', 'triggers': ['guest program wrote room id and VGA patch']},
                'match': _pixel(red),
                'content': {'requested': {'constant': True}, 'displayed': _pixel(red), 'ready': {'constant': True}},
                'objects': [{
                    'name': 'red-patch', 'context': {'state': 'fixture obstacle', 'triggers': ['COM fixture paints VGA pixels 0..4095']},
                    'original_area': {'rect': [0, 0, 64, 64]}, 'area': {'rect': [0, 0, 64, 64]},
                    'point': [10, 10], 'visible': _pixel(red), 'ready': {'constant': True},
                    'enabled': {'constant': True}, 'action': {'kind': 'click'},
                    'outcome': {'constant': True}, 'guest_ms': 100, 'timeout_ms': 1000,
                }],
            }
            scene = project.debug_save_scene('spatial-native', definition)
            assert session.scene(scene['id']).check()['status'] == 'matched'

            digest = project.version()['sha256']
            room_map = {
                'format': 'fdisbull-spatial-map-1',
                'source': {'sha256': digest, 'context': scene['id'], 'room': '1', 'resource': 'self-authored-mode13-fixture'},
                'space': {'name': 'mode13-fixture', 'width': 320, 'height': 200, 'unit': 'game'},
                'actor': {'width': 1, 'height': 1, 'anchor': [0, 0]},
                'known': {'rect': [0, 0, 320, 200]}, 'safe': {'rect': [0, 0, 320, 200]},
                'layers': [{'id': 'red-patch', 'kind': 'obstacle', 'area': {'rect': [0, 0, 64, 64]}}],
                'evidence': {'native_fixture': {'description': 'Guest-authored pixels and pinned native scene; no game assets.'}},
            }
            revision = project.debug_save_spatial_map('native-room', room_map)
            runtime_room = session.runtime_base + 0x100
            binding = session.bind_runtime_memory('room', runtime_room, length=1, expected_hex='01',
                provenance={'source': 'self-authored COM room byte at DS:0200'})
            observation = {'room': {'runtime_memory': {'binding': binding['id'], 'offset': 0, 'type': 'u8'}}}
            navigation = session.spatial_navigation(revision['id'], observations=observation)
            blocked = navigation.navigation_check([10, 10])
            assert blocked['classification'] == 'blocked', blocked
            assert navigation.navigation_check([100, 100])['classification'] == 'clear'

            policy = session.spatial_policy('physical', fair_play=True)
            assert policy['fair_play'] is True and policy['spatial_mode'] == 'physical'
            with pytest.raises(ValueError, match='Fair play'):
                session.spatial_policy('assisted', fair_play=False)

            before_registers = session.registers()
            checkpoint = session.save_state('spatial-native-before.sav')
            before_room = session.runtime_memory(binding['id'], length=1)['hex']
            assert before_room == '01'

            # Change the observed room identity through a hash-guarded write,
            # then confirm the same-room map becomes unknown until restore.
            address = {'space': 'linear', 'offset': f'0x{runtime_room:08X}'}
            live = session.call('memory.read', {'address': address, 'length': 1})
            room_byte = base64.b64decode(live['data_base64'], validate=True)
            assert room_byte == b'\x01'
            session.call('memory.write', {
                'address': address, 'expected_sha256': hashlib.sha256(room_byte).hexdigest(),
                'data_base64': base64.b64encode(b'\x02').decode('ascii'),
            })
            session.run(guest_ms=100, timeout_ms=5000, fast_forward=True)
            assert navigation.navigation_check([100, 100])['classification'] == 'unknown'

            session.load_state(checkpoint['artifact'])
            with pytest.raises(ValueError, match='invalidated'):
                session.runtime_memory(binding['id'], length=1)
            assert session.spatial_policy()['fair_play'] is True
            restored_registers = session.registers()
            for key in ('cs', 'ip', 'flags', 'segments'):
                assert restored_registers[key] == before_registers[key]
            session.run(guest_ms=100, timeout_ms=5000, fast_forward=True)
            rebound = session.bind_runtime_memory('room-after-restore', runtime_room, length=1, expected_hex='01',
                provenance={'source': 'new binding after native save-state restore'})
            assert session.runtime_memory(rebound['id'], length=1)['hex'] == '01'
            assert session.scene(scene['id']).check()['status'] == 'matched'

            export = tmp_path / 'headless-spatial-reference.png'
            project.debug_export(image['artifact'], export)
            with Image.open(export) as rendered:
                assert rendered.size == (320, 200)
                rendered.verify()
