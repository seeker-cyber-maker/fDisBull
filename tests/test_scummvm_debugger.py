"""Protocol and project-contract tests; real AGI runtime is verified separately."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import io
import json
import textwrap
import time

import pytest
from PIL import Image

from fdisbull.project import Project
from fdisbull.scummvm_debugger import ScummVMAGISession


def bridge(tmp_path):
    script = tmp_path / 'bridge.py'
    script.write_text(textwrap.dedent('''\
        #!/usr/bin/env python3
        import base64, json, os, pathlib, socket, sys
        savepath = pathlib.Path(next(a.split('=',1)[1] for a in sys.argv if a.startswith('--savepath=')))
        sock = socket.socket(fileno=int(os.environ['FDISBULL_SCUMMVM_FD']))
        stream = sock.makefile('rwb', buffering=0)
        vars = [0] * 256
        flags = [False] * 256
        objects = [{'id': 0, 'name': 'key', 'location': 0}]
        logic_original = bytearray.fromhex('0300000102')
        logic_current = bytearray(logic_original)
        logic_generation = 0
        guest_ms = 0
        offset = 0
        pending = 0
        while True:
            line = stream.readline()
            if not line:
                break
            request = json.loads(line)
            op = request['op']
            response = {'id': request['id'], 'ok': True}
            if op == 'hello':
                response.update(engine='agi', version='2.8.1-test',
                                capabilities=['state','frame','step','save','input.status'],
                                virtual_clock=True)
            elif op == 'state.get':
                response['state'] = dict(room=1, logic=0, offset=offset, vars=vars,
                    flags=flags, objects=objects, screen_objects=[], guest_ms=guest_ms,
                    at_cycle=True, frame_revision=0, instructions=offset,
                    logic_patches=[{'logic':0,'generation':logic_generation}] if logic_generation else [])
            elif op == 'state.set':
                kind, index, value = request['kind'], request['index'], request['value']
                if kind == 'var': vars[index] = value
                elif kind == 'flag': flags[index] = value
                else: objects[index]['location'] = value
                response['value'] = value
            elif op == 'frame.get':
                response.update(width=2, height=2, format='rgb24', revision=0,
                                guest_ms=guest_ms, data_base64=base64.b64encode(
                                bytes([1,2,3,4,5,6,7,8,9,10,11,12])).decode())
            elif op == 'input':
                pending += 1
                response['queued'] = 1
            elif op == 'input.status':
                response.update(pending=pending,guest_ms=guest_ms,
                    queue_tail_guest_ms=guest_ms,next_due_guest_ms=guest_ms if pending else None,
                    held_keycodes=[],leases=[])
            elif op in ('run', 'run_until_cycle'):
                guest_ms += request.get('max_guest_ms', 1)
                offset += 1
                pending = 0
                response['stop'] = dict(reason='cycle' if op == 'run_until_cycle' else
                                        'host_timeout' if request['max_instructions'] == 7 else
                                        'guest_budget' if 'max_guest_ms' in request else 'budget',
                                        logic=0, offset=offset, instructions=1, guest_ms=guest_ms)
            elif op == 'step':
                offset += 1
                pending = 0
                response['stop'] = dict(reason='host_timeout' if request.get('max_ms',30000) < 1000 else 'step',
                                        logic=0, offset=offset, instructions=1,
                                        guest_ms=guest_ms)
            elif op == 'logic.read':
                start, length = request['offset'], request['length']
                response.update(logic=0,offset=start,length=length,size=len(logic_original),
                    generation=logic_generation,scope='loaded_logic_memory',
                    original_hex=logic_original[start:start+length].hex(),
                    current_hex=logic_current[start:start+length].hex(),
                    original_fnv1a64=format(sum(logic_original),'016x'),
                    current_fnv1a64=format(sum(logic_current),'016x'),
                    native_save_persists_patch=False)
            elif op == 'logic.restore':
                if request['expected_fnv1a64'] != format(sum(logic_current),'016x'):
                    response = dict(id=request['id'],ok=False,error='expected_mismatch',message='stale hash')
                else:
                    logic_current[:] = logic_original
                    logic_generation += 1
                    response.update(restored=True,generation=logic_generation)
            elif op == 'logic.patch':
                start = request['offset']
                expected = bytes.fromhex(request['expected_hex'])
                replacement = bytes.fromhex(request['data_hex'])
                if logic_current[start:start+len(expected)] != expected:
                    response = dict(id=request['id'],ok=False,error='expected_mismatch',message='stale bytes')
                else:
                    logic_current[start:start+len(expected)] = replacement
                    logic_generation += 1
                    response.update(logic=0,offset=start,length=len(expected),size=len(logic_original),
                        generation=logic_generation,scope='loaded_logic_memory',
                        before_hex=expected.hex(),after_hex=replacement.hex())
            elif op == 'save':
                slot = request['slot']
                (savepath / ('slot-%03d.sav' % slot)).write_text(json.dumps(
                    {'vars':vars, 'flags':flags, 'objects':objects, 'guest_ms':guest_ms, 'offset':offset}))
                response['slot'] = slot
            elif op == 'load':
                data = json.loads((savepath / ('slot-%03d.sav' % request['slot'])).read_text())
                vars, flags, objects = data['vars'], data['flags'], data['objects']
                guest_ms, offset = data['guest_ms'], data['offset']
                response['slot'] = request['slot']
            elif op == 'quit':
                stream.write((json.dumps(response)+'\\n').encode())
                break
            stream.write((json.dumps(response)+'\\n').encode())
    '''))
    script.chmod(0o700)
    return script


def fixture(tmp_path):
    game = tmp_path / 'game'
    game.mkdir()
    (game / 'AGI').write_bytes(b'AGI SOURCE IDENTITY')
    payload = b'\x03\x00\x00\x01\x02'
    (game / 'LOGDIR').write_bytes(b'\x00\x00\x00')
    (game / 'VOL.0').write_bytes(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)
    project = Project.create(tmp_path / 'game.fdb', game / 'AGI', arch='x86', bits=16, base=0)
    return project, game


def test_agi_session_persists_source_bound_vm_evidence_and_real_png(tmp_path):
    executable = bridge(tmp_path)
    project, game = fixture(tmp_path)
    with project:
        with ScummVMAGISession(project, executable, game, game_id='agi:kq1') as session:
            state = session.engine_state()
            assert state['room'] == 1 and state['position']['logic'] == 0 and state['position']['offset'] == 0
            assert state['resource_manifest_sha256'] == session.manifest_sha256
            first = session.frame_probe([[0,0],[1,1]])
            assert first['samples'][0]['rgb'] == [1,2,3]
            assert session.frame_probe([])['frame_id'] == first['frame_id']
            image = session.screenshot()
            assert image['metadata']['backend'] == 'scummvm-agi'
            output = tmp_path / 'frame.png'
            project.debug_export(image['artifact'], output)
            with Image.open(output) as png:
                assert png.size == (2,2) and png.getpixel((1,1)) == (10,11,12)
            written = session.write_engine_state('var', 3, 16, expected=0)
            assert written['after'] == 16
            assert session.frame_probe([])['frame_id'] != first['frame_id']
            assert session.run(guest_ms=100)['outcome'] == 'guest_time'
            assert session.engine_state()['guest_ms'] == 100
            assert session.step()['steps'][0]['completed_opcode_count'] == 1
            point = session.breakpoint({'logic':0,'offset':2})
            watch = session.watchpoint('var',3)
            session.delete_breakpoint(point['breakpoint_id'])
            session.delete_watchpoint(watch['watchpoint_id'])
            assert session.code({'logic':0,'offset':3},length=2)['hex'] == '0102'
            original = session.resource(0,2,1)
            assert original['current_hex'] == '00' and original['disk_source']['bytes_verified']
            altered = session.patch_resource(0,2,'00','ff')
            assert altered['resource_layers_sha256'] != '0' * 64
            assert session.frame_probe([])['resource_layers_sha256'] == altered['resource_layers_sha256']
            with pytest.raises(ValueError, match='active loaded-logic patches'):
                session.save_state()
            restored = session.restore_resource(0)
            assert restored['resource_layers_sha256'] == '0' * 64
            saved = session.save_state()
            assert saved['metadata']['format'] == 'scummvm-agi-native-slot-v1'
            assert saved['metadata']['exact_vm_checkpoint'] is False
            session.write_engine_state('var',3,17)
            assert session.load_state(saved['artifact'])['engine_state']['vars'][3] == 16
            assert session.keyboard_type('look\n')['consumed'] is False
            with pytest.raises(ValueError, match='empty input queue'):
                session.save_state('pending.sav')
            with pytest.raises(ValueError, match='empty input queue'):
                session.load_state(saved['artifact'])
            assert session.engine_state()['vars'][3] == 16
            assert session.keyboard_state()['keyboard']['pending_events'] == 1
            assert session.click(1,1)['queued'] == 3
            route = session.script({'format':'fdisbull-script-1','backend':'scummvm-agi',
                'steps':[{'op':'engine-state','as':'initial'},
                         {'op':'engine-resource','logic':0,'offset':2,'length':1},
                         {'op':'engine-cycle','max_instructions':100,'timeout_ms':1000},
                         {'op':'engine-set','kind':'var','index':2,'value':7}]},timeout_ms=5000)
            assert route['ok'] and route['completed_steps'] == 4
            assert session.trace(count=2)['metadata']['complete']
        assert project.debug_state_info(saved['artifact'])['sha256'] == saved['sha256']
        assert project.debug_runs()['runs'][0]['metadata']['replacement_engine'] is True
    with Project(tmp_path / 'game.fdb') as reopened:
        assert reopened.debug_state_info(saved['artifact'])['metadata']['resource_manifest_sha256'] == image['metadata']['resource_manifest_sha256']


def test_agi_session_refuses_patched_version_and_changed_resource(tmp_path):
    executable = bridge(tmp_path)
    project, game = fixture(tmp_path)
    with project:
        project.patch(0, '58', label='child')
        with pytest.raises(ValueError, match='original project version'):
            ScummVMAGISession(project, executable, game, game_id='kq1', version=2)
        with ScummVMAGISession(project, executable, game, game_id='kq1', version=1) as session:
            game.joinpath('VOL.0').write_bytes(game.joinpath('VOL.0').read_bytes() + b'changed')
            with pytest.raises(ValueError, match='manifest changed'):
                session.save_state()
            with pytest.raises(ValueError, match='resources changed'):
                session.frame_probe([])
            assert session.closed


def test_agi_session_does_not_expose_native_cpu_or_unverified_guest_time(tmp_path):
    executable = bridge(tmp_path)
    project, game = fixture(tmp_path)
    with project, ScummVMAGISession(project, executable, game, game_id='kq1') as session:
        with pytest.raises(ValueError, match='x86 registers'):
            session.registers()
        with pytest.raises(ValueError, match='DOS memory'):
            session.memory(0)
        with pytest.raises(ValueError, match='AGI breakpoint'):
            session.breakpoint(0)
        session.rpc.capabilities['virtual_time'] = False
        with pytest.raises(ValueError, match='virtual guest-time'):
            session.run(guest_ms=10)
        stopped = session.run(max_instructions=7)
        assert stopped['outcome'] == 'timeout' and stopped['native_stop']['reason'] == 'host_timeout'
        stepped = session.step(timeout_ms=200)
        assert stepped['completed'] is False
        assert stepped['steps'][0]['completed_opcode_count'] == 1
        assert stepped['steps'][0]['stop']['reason'] == 'host_timeout'


def test_agi_hook_capability_is_declared_in_metadata_and_every_status(tmp_path):
    project,game=fixture(tmp_path)
    with project,ScummVMAGISession(project,bridge(tmp_path),game,game_id='kq1') as session:
        assert type(session).native_hooks_available is False
        assert session.metadata['native_hooks_available'] is False
        assert session.status()['native_hooks_available'] is False
        session._run_active=True
        try:
            assert session.status()['native_hooks_available'] is False
        finally:
            session._run_active=False
        session._guest_exited=True
        try:
            assert session.status()['native_hooks_available'] is False
        finally:
            session._guest_exited=False


def test_agi_explicit_hook_stop_refuses_without_running_guest(tmp_path):
    project,game=fixture(tmp_path)
    with project,ScummVMAGISession(project,bridge(tmp_path),game,game_id='kq1') as session:
        before=session.engine_state()['instructions']
        with pytest.raises(ValueError,match='hooks are unavailable'):
            session.run(stop_on_hook=True)
        assert session.engine_state()['instructions']==before


def test_agi_duplicate_controls_share_one_native_registration_identity(tmp_path):
    project,game=fixture(tmp_path)
    with project,ScummVMAGISession(project,bridge(tmp_path),game,game_id='kq1') as session:
        address={'logic':0,'offset':2}
        first=session.breakpoint(address)
        second=session.breakpoint(dict(address),view='execute')
        assert first['breakpoint_id']==second['breakpoint_id']
        assert len(session._breakpoints)==1
        session.delete_breakpoint(second['breakpoint_id'])
        with pytest.raises(ValueError,match='Unknown'):
            session.delete_breakpoint(first['breakpoint_id'])
        first_watch=session.watchpoint('var',3,access='rw')
        second_watch=session.watchpoint('var',3,access='rw')
        assert first_watch['watchpoint_id']==second_watch['watchpoint_id']
        distinct=[session.watchpoint('flag',3,access='rw'),session.watchpoint('var',3,access='r')]
        assert len({first_watch['watchpoint_id'],*(item['watchpoint_id'] for item in distinct)})==3
        session.delete_watchpoint(first_watch['watchpoint_id'])
        with pytest.raises(ValueError,match='Unknown'):
            session.delete_watchpoint(second_watch['watchpoint_id'])
        assert len(session._watches)==2


@pytest.mark.skipif(not (os.environ.get('FDISBULL_SCUMMVM_NATIVE') and
                         os.environ.get('FDISBULL_AGI_KQ1_DIR')),
                    reason='set explicit patched backend and private KQ1 directory for native qualification')
def test_native_scummvm_kq1_initial_pause_step_and_frame(tmp_path):
    game = Path(os.environ['FDISBULL_AGI_KQ1_DIR'])
    executable = Path(os.environ['FDISBULL_SCUMMVM_NATIVE'])
    original = hashlib.sha256((game / 'AGI').read_bytes()).hexdigest()
    project = Project.create(tmp_path / 'native-kq1.fdb', game / 'AGI',
                             arch='x86', bits=16, base=0)
    with project:
        with project.debugger(executable, game, backend='scummvm-agi', game_id='kq1') as session:
            state = session.engine_state()
            assert state['position']['logic'] == 0 and state['position']['offset'] == 2
            assert len(state['vars']) == len(state['flags']) == 256
            frame = session.frame_probe([[0,0]])
            assert frame['width'] == 320 and frame['height'] == 200
            artifact = session.screenshot('native-kq1.png')
            assert artifact['metadata']['frame_commit_revision'] >= 1
            frame_rgb = frame['samples'][0]['rgb']
            scene = project.debug_save_scene('native-agi-screen', {
                'format':'fdisbull-scene-1','width':320,'height':200,
                'mode_id':artifact['metadata']['mode_id'],'reference':artifact['artifact'],
                'context':{'state':'observed AGI screen','triggers':['native KQ1 pause']},
                'match':{'pixels':{'samples':[{'x':0,'y':0,'rgb':frame_rgb}]}},
                'objects':[{'name':'observed.screen.region',
                            'context':{'state':'screen sample','triggers':['native RGB frame']},
                            'area':{'rect':[1,1,16,16]},'point':[8,8],
                            'visible':{'constant':True},'ready':{'constant':True},
                            'enabled':{'constant':True},'action':{'kind':'click'},
                            'outcome':{'constant':False}}]})
            assert session.scene_check(scene['id'])['status'] == 'matched'
            original_logic = session.resource(0,2,1)
            assert original_logic['disk_source']['bytes_verified']
            with pytest.raises(ValueError, match='expected_hex'):
                session.patch_resource(0,2,'ff' if original_logic['current_hex'] != 'ff' else '00','aa')
            assert session.resource(0,2,1)['current_hex'] == original_logic['current_hex']
            alternative = 'ff' if original_logic['current_hex'] != 'ff' else '00'
            patched = session.patch_resource(0,2,original_logic['current_hex'],alternative)
            assert patched['resource_layers_sha256'] != '0' * 64
            assert session.frame_probe([])['resource_layers_sha256'] == patched['resource_layers_sha256']
            assert session.scene_check(scene['id'])['status'] == 'unavailable'
            session.restore_resource(0)
            assert session.frame_probe([])['resource_layers_sha256'] == '0' * 64
            assert session.scene_check(scene['id'])['status'] == 'matched'
            first = session.step()
            assert first['steps'][0]['completed_opcode_count'] == 1
            assert first['steps'][0]['before_position_instruction_completed'] is None
            after = session.engine_state()
            assert after['position']['offset'] != 2
            assert after['state_revision'] > state['state_revision']
            trace = session.trace(count=4)
            report = json.loads(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                (trace['artifact'],)).fetchone()[0])
            assert report['complete'] and report['events'][0]['original_source']['scope'] == 'validated AGI v2 original disk resource'
        with Image.open(io.BytesIO(project.db.execute(
                'SELECT data FROM debug_artifacts WHERE id=?',
                (artifact['artifact'],)).fetchone()[0])) as image:
            image.verify()
    assert hashlib.sha256((game / 'AGI').read_bytes()).hexdigest() == original
    with Project(tmp_path / 'native-kq1.fdb') as reopened:
        overlay = reopened.debug_scene_overlay(scene['id'], artifact=artifact['artifact'],
                                               name='native-agi-overlay.png')
        reopened.debug_export(overlay['artifact'], tmp_path / 'native-agi-overlay.png')
        with Image.open(tmp_path / 'native-agi-overlay.png') as image:
            assert image.size == (320,200)
            image.verify()


@pytest.mark.skipif(not (os.environ.get('FDISBULL_SCUMMVM_NATIVE') and
                         os.environ.get('FDISBULL_AGI_KQ1_DIR')),
                    reason='set explicit patched backend and private KQ1 directory for native qualification')
def test_native_scummvm_breakpoint_watchpoint_and_cycle_save_restore(tmp_path):
    game = Path(os.environ['FDISBULL_AGI_KQ1_DIR'])
    executable = Path(os.environ['FDISBULL_SCUMMVM_NATIVE'])
    project = Project.create(tmp_path / 'native-control.fdb', game / 'AGI',
                             arch='x86', bits=16, base=0)
    with project:
        with project.debugger(executable, game, backend='scummvm-agi', game_id='kq1') as session:
            bp = session.breakpoint({'logic':0,'offset':11})
            stopped = session.run(max_instructions=1000,timeout_ms=5000)
            assert stopped['outcome'] == 'breakpoint'
            assert stopped['native_stop']['logic'] == 0 and stopped['native_stop']['offset'] == 11
            session.delete_breakpoint(bp['breakpoint_id'])
            watch = session.watchpoint('var',0,access='r')
            observed = session.run(max_instructions=50000,timeout_ms=5000)
            assert observed['outcome'] == 'watchpoint'
            assert observed['native_stop']['watch']['kind'] == 'var'
            assert observed['native_stop']['watch']['index'] == 0
            session.delete_watchpoint(watch['watchpoint_id'])
            cycle = session.run_until_cycle(max_instructions=100000,timeout_ms=5000)
            assert cycle['outcome'] == 'cycle' and session.engine_state()['at_cycle'] is True
            saved = session.save_state('cycle.sav')
            saved_var = session.engine_state()['vars'][3]
            changed_var = (saved_var + 1) % 256
            session.write_engine_state('var',3,changed_var,expected=saved_var)
            queued = session.keyboard_type('a')
            assert queued['queued'] == 2
            with pytest.raises(ValueError, match='empty input queue'):
                session.save_state('pending.sav')
            with pytest.raises(ValueError, match='empty input queue'):
                session.load_state(saved['artifact'])
            assert session.engine_state()['vars'][3] == changed_var
            assert session.keyboard_state()['keyboard']['pending_events'] == 2
        with project.debugger(executable, game, backend='scummvm-agi', game_id='kq1') as reopened:
            assert reopened.run_until_cycle(max_instructions=100000,timeout_ms=5000)['outcome'] == 'cycle'
            loaded = reopened.load_state(saved['artifact'])
            assert loaded['engine_state']['vars'][3] == saved_var
            assert loaded['exact_vm_checkpoint'] is False
        assert project.debug_state_info(saved['artifact'])['metadata']['resource_manifest_sha256']


@pytest.mark.skipif(not (os.environ.get('FDISBULL_SCUMMVM_NATIVE') and
                         os.environ.get('FDISBULL_AGI_PQ1_DIR')),
                    reason='set explicit patched backend and private PQ1 directory for native qualification')
def test_native_scummvm_pq1_separate_manifest_and_frame(tmp_path):
    game = Path(os.environ['FDISBULL_AGI_PQ1_DIR'])
    project = Project.create(tmp_path / 'native-pq1.fdb', game / 'AGI',
                             arch='x86', bits=16, base=0)
    with project, project.debugger(os.environ['FDISBULL_SCUMMVM_NATIVE'], game,
                                   backend='scummvm-agi', game_id='pq1') as session:
        state = session.engine_state()
        frame = session.frame_probe([[0,0]])
        assert state['backend'] == 'scummvm-agi' and frame['width'] == 320
        assert frame['resource_manifest_sha256'] == session.manifest_sha256
        assert session.step()['steps'][0]['completed_opcode_count'] == 1


@pytest.mark.skipif(not (os.environ.get('FDISBULL_SCUMMVM_NATIVE') and
                         os.environ.get('FDISBULL_AGI_KQ1_DIR')),
                    reason='set explicit patched backend and private KQ1 directory for native qualification')
def test_native_scummvm_virtual_input_queue_and_owned_key_lease(tmp_path):
    game = Path(os.environ['FDISBULL_AGI_KQ1_DIR'])
    project = Project.create(tmp_path / 'native-input.fdb', game / 'AGI',
                             arch='x86', bits=16, base=0)
    with project, project.debugger(os.environ['FDISBULL_SCUMMVM_NATIVE'], game,
                                   backend='scummvm-agi', game_id='kq1') as session:
        typed = session.keyboard_type('a\tB',hold_ms=40,gap_ms=40)
        assert typed['timing_applied'] is True and typed['queued'] == 6
        assert session.keyboard_state()['keyboard']['pending_events'] == 6
        session.run(guest_ms=90,max_instructions=100000,timeout_ms=5000)
        pending = session.keyboard_state()['keyboard']['pending_events']
        assert 0 < pending < 6
        down = session.keyboard_key_down('left')
        assert down['lease'] in [entry['lease'] for entry in session.keyboard_state()['keyboard']['leases']]
        up = session.keyboard_key_up(down['lease'])
        assert up['release_delivered'] is False
        session.run(guest_ms=500,max_instructions=100000,timeout_ms=5000)
        after = session.keyboard_state()['keyboard']
        assert after['pending_events'] == 0 and after['leases'] == []
        clicked = session.click(0,0,hold_ms=80)
        assert clicked['queued'] == 2 and clicked['timing_applied'] is True


@pytest.mark.skipif(not (os.environ.get('FDISBULL_SCUMMVM_NATIVE') and
                         os.environ.get('FDISBULL_AGI_KQ1_DIR')),
                    reason='set explicit patched backend and private KQ1 directory for native qualification')
def test_native_scummvm_concurrent_pause_confirms_stop_and_resume(tmp_path):
    game = Path(os.environ['FDISBULL_AGI_KQ1_DIR'])
    project = Project.create(tmp_path / 'native-pause.fdb', game / 'AGI',
                             arch='x86', bits=16, base=0)
    with project, project.debugger(os.environ['FDISBULL_SCUMMVM_NATIVE'], game,
                                   backend='scummvm-agi', game_id='kq1') as session:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(session.run,max_instructions=1000000,timeout_ms=10000)
            deadline = time.monotonic() + 3
            with session._run_condition:
                while not session._run_sent and not future.done() and time.monotonic() < deadline:
                    session._run_condition.wait(deadline - time.monotonic())
                assert session._run_sent and session._run_active
            assert session.status()['state'] == 'running'
            with pytest.raises(ValueError, match='Another AGI execution is active'):
                session.run(max_instructions=1, timeout_ms=1)
            with pytest.raises(ValueError, match='execution is active'):
                session.write_engine_state('var',3,1)
            paused = session.pause(timeout_ms=3000)
            assert paused['acknowledged'] and paused['confirmed_stopped']
            assert paused['stop']['reason'] == 'pause'
            assert future.result(timeout=5)['outcome'] == 'pause'
        operations = [row[0] for row in project.db.execute(
            'SELECT operation FROM debug_events WHERE run=? ORDER BY rowid', (session.run_id,))]
        assert 'run' in operations and 'pause' in operations
        assert session.status()['state'] == 'stopped'
        resumed = session.resume(guest_ms=20,max_instructions=1000000,timeout_ms=5000)
        assert resumed['outcome'] == 'guest_time'
