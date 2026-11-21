"""Persistent learned controls through real sockets, projects and native frames."""

import base64
from copy import deepcopy
from io import BytesIO
import importlib.util
import os
from pathlib import Path
import threading
import time

import pytest

from dotbox.backend import FDisBullBackend
from dotbox.client import Client
from dotbox.service import PlayService


def test_controls_learned_during_human_play_survive_service_restart(tmp_path):
    executable = os.environ.get('DOTBOX_DOSBOX_EXECUTABLE')
    if not executable:
        pytest.skip('DOTBOX_DOSBOX_EXECUTABLE required for persistent-control native acceptance')
    Image = pytest.importorskip('PIL.Image')
    fixture_path = Path(__file__).resolve().parents[1] / 'examples/input_playground.py'
    spec = importlib.util.spec_from_file_location('dotbox_harness_fixture', fixture_path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    game_dir = tmp_path / 'game'
    game_dir.mkdir()
    program = game_dir / 'PLAY.COM'
    program.write_bytes(fixture.program())
    config = {'project': tmp_path / 'play.fdb', 'program': program,
              'game_dir': game_dir, 'executable': executable, 'image': 'com'}
    descriptor = tmp_path / 'session/session.json'
    processes, failures = [], []

    def start():
        ready = threading.Event()

        def factory():
            backend = FDisBullBackend(config)
            processes.append(backend._session.rpc.process)
            return backend

        service = PlayService(factory, descriptor.parent, manual_control=True)

        def serve():
            try:
                service.run(on_ready=lambda _: ready.set())
            except BaseException as error:
                failures.append(error)
                ready.set()

        worker = threading.Thread(target=serve)
        worker.start()
        assert ready.wait(10) and not failures, failures
        return service, worker, Client(descriptor)

    def request(client, op, params=None, lease=None):
        reply = client.request(op, params, lease=lease)
        assert reply['ok'], reply
        return reply

    def square(client, x):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            reply = client.request('frame')
            if reply['ok']:
                frame = reply['result']
                image = Image.open(BytesIO(base64.b64decode(frame['png_base64']))).convert('RGB')
                points = [(i, j) for j in range(image.height) for i in range(image.width)
                          if image.getpixel((i, j))[1] > 200
                          and image.getpixel((i, j))[0] < 120 and image.getpixel((i, j))[2] < 120]
                if points and (min(i for i, _ in points), min(j for _, j in points)) == (x, 100):
                    return reply['session']
            time.sleep(0.02)
        raise AssertionError('Named control did not produce the expected fresh visible position')

    profile = {'format': 'fdisbull-macro-set-1', 'name': 'dotbox.playground',
               'macros': {'move_right': {'authority': 'player-input', 'steps': [
                   {'op': 'keyboard.press', 'key': 'right', 'hold_ms': 40, 'gap_ms': 40}]}}}
    service, worker, client = start()
    try:
        initial = request(client, 'status')['result']
        agent = request(client, 'control', {'owner': 'agent', 'resume': True}, initial)['session']
        square(client, 160)
        human = request(client, 'control', {'owner': 'human'}, agent)['session']
        saved = request(client, 'harness-save', {'definition': profile}, human)
        revision = saved['result']['revision']
        assert saved['session']['owner'] == 'human' and saved['session']['state'] == 'running'
        assert saved['session']['run_id'] == initial['run_id']
        rejected = client.request('act', {'revision': revision, 'name': 'move_right'}, lease=human)
        assert rejected['error']['code'] == 'human_has_control'
        square(client, 160)
        agent = request(client, 'control', {'owner': 'agent'}, human)['session']
        used = request(client, 'act', {'revision': revision, 'name': 'move_right'}, agent)
        assert used['result']['transition_verified'] is False
        square(client, 168)  # Independently establish the queued action's actual effect.
        other = Client(descriptor)
        assert request(other, 'harness-info', {'revision': revision})['result']['revision'] == revision
        extended = deepcopy(profile)
        extended['macros']['move_left'] = {'steps': [{'op': 'keyboard.press', 'key': 'left'}]}
        newer = request(other, 'harness-save', {'definition': extended, 'parent': revision}, agent)['result']['revision']
        assert newer != revision
        request(client, 'act', {'revision': newer, 'name': 'move_left'}, agent)
        last = square(client, 160)
        assert request(client, 'harness-info', {'revision': revision})['result']['definition'] == profile
        request(client, 'close', lease=last)
    finally:
        service.request_stop()
        worker.join(10)
    assert not worker.is_alive() and not failures and not descriptor.exists()
    assert all(p.poll() is not None for p in processes)

    # Game state restarts; learned controls persist in the existing project.
    service, worker, client = start()
    try:
        restarted = request(client, 'status')['result']
        assert restarted['instance_id'] != agent['instance_id']
        stale = client.request('act', {'revision': newer, 'name': 'move_left'}, lease=agent)
        assert stale['error']['code'] == 'stale_instance'
        rows = request(client, 'harness-list')['result']['revisions']
        assert {row['revision'] for row in rows} == {revision, newer}
        agent = request(client, 'control', {'owner': 'agent', 'resume': True}, restarted)['session']
        square(client, 160)
        request(client, 'act', {'revision': newer, 'name': 'move_left'}, agent)
        last = square(client, 152)
        request(client, 'close', lease=last)
    finally:
        service.request_stop()
        worker.join(10)
    assert not worker.is_alive() and not failures and not descriptor.exists()
    assert len(processes) == 2 and all(p.poll() is not None for p in processes)
