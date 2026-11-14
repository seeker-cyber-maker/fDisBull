"""Authored Z test inputs and process probe, included in source distributions.

The demonstration is synthetic. This helper contains no original game assets.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import subprocess
import threading

_SCENE = {'format': 'fdisbull-il-scene-1',
 'programs': {'take-key': {'format': 'fdisbull-il-1',
                           'role': 'uil',
                           'variables': {'$key': {'type': 'bool', 'initial': False},
                                         '$unlocked': {'type': 'bool', 'initial': False},
                                         '$room': {'type': 'u8', 'initial': 0},
                                         '$moves': {'type': 'u16', 'initial': 0}},
                           'resources': {'message': {'kind': 'text',
                                                     'text': 'You take the brass key.'}},
                           'body': [{'id': 'guard',
                                     'op': 'require',
                                     'condition': {'op': 'eq',
                                                   'left': {'var': '$key'},
                                                   'right': False}},
                                    {'id': 'set-key', 'op': 'set', 'var': '$key', 'value': True},
                                    {'id': 'message', 'op': 'text', 'resource': 'message'}]},
              'unlock-gate': {'format': 'fdisbull-il-1',
                              'role': 'uil',
                              'variables': {'$key': {'type': 'bool', 'initial': False},
                                            '$unlocked': {'type': 'bool', 'initial': False},
                                            '$room': {'type': 'u8', 'initial': 0},
                                            '$moves': {'type': 'u16', 'initial': 0}},
                              'resources': {'message': {'kind': 'text',
                                                        'text': 'You unlock the gate.'}},
                              'body': [{'id': 'guard',
                                        'op': 'require',
                                        'condition': {'op': 'eq',
                                                      'left': {'var': '$key'},
                                                      'right': True}},
                                       {'id': 'set-unlocked',
                                        'op': 'set',
                                        'var': '$unlocked',
                                        'value': True},
                                       {'id': 'message', 'op': 'text', 'resource': 'message'}]},
              'north': {'format': 'fdisbull-il-1',
                        'role': 'uil',
                        'variables': {'$key': {'type': 'bool', 'initial': False},
                                      '$unlocked': {'type': 'bool', 'initial': False},
                                      '$room': {'type': 'u8', 'initial': 0},
                                      '$moves': {'type': 'u16', 'initial': 0}},
                        'resources': {'message': {'kind': 'text',
                                                  'text': 'You pass through the gate into the '
                                                          'garden.'}},
                        'body': [{'id': 'guard',
                                  'op': 'require',
                                  'condition': {'op': 'eq',
                                                'left': {'var': '$unlocked'},
                                                'right': True}},
                                 {'id': 'set-room', 'op': 'set', 'var': '$room', 'value': 1},
                                 {'id': 'move', 'op': 'add', 'var': '$moves', 'value': 1},
                                 {'id': 'message', 'op': 'text', 'resource': 'message'}]},
              'south': {'format': 'fdisbull-il-1',
                        'role': 'uil',
                        'variables': {'$key': {'type': 'bool', 'initial': False},
                                      '$unlocked': {'type': 'bool', 'initial': False},
                                      '$room': {'type': 'u8', 'initial': 0},
                                      '$moves': {'type': 'u16', 'initial': 0}},
                        'resources': {'message': {'kind': 'text',
                                                  'text': 'You return to the courtyard.'}},
                        'body': [{'id': 'set-room', 'op': 'set', 'var': '$room', 'value': 0},
                                 {'id': 'move', 'op': 'add', 'var': '$moves', 'value': 1},
                                 {'id': 'message', 'op': 'text', 'resource': 'message'}]}},
 'contexts': [{'id': 'courtyard',
               'title': 'Courtyard',
               'description': 'An iron gate stands in the north wall.',
               'when': {'op': 'eq', 'left': {'var': '$room'}, 'right': 0}},
              {'id': 'garden',
               'title': 'Garden',
               'description': 'You stand among quiet flower beds. The courtyard is south.',
               'when': {'op': 'eq', 'left': {'var': '$room'}, 'right': 1}}],
 'objects': [{'id': 'key',
              'context': 'courtyard',
              'label': 'brass key',
              'aliases': ['key'],
              'description': 'A small brass key.',
              'bindings': [{'verb': 'take', 'program': 'take-key'}],
              'visible_when': {'op': 'eq', 'left': {'var': '$key'}, 'right': False},
              'inventory_when': {'op': 'eq', 'left': {'var': '$key'}, 'right': True}},
             {'id': 'gate',
              'context': 'courtyard',
              'label': 'gate',
              'aliases': ['north', 'n'],
              'description': 'An iron gate in the north wall.',
              'bindings': [{'verb': 'use', 'item': 'key', 'program': 'unlock-gate'},
                           {'verb': 'go', 'program': 'north'}]},
             {'id': 'south',
              'context': 'garden',
              'label': 'south',
              'aliases': ['courtyard', 's'],
              'description': 'The way back to the courtyard.',
              'bindings': [{'verb': 'go', 'program': 'south'}]}],
 'partial': False}


def scene_definition():
    return deepcopy(_SCENE)


def write_scene(path):
    path=Path(path)
    path.write_text(json.dumps(scene_definition()))
    return path


def quiet_player(python, output, name, *, player_path=None):
    password_file = output / (name + '.password')
    password_file.write_text('0' * 64 + '\n')
    password_file.chmod(0o600)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(3)
    finish = threading.Event()
    def peer():
        try:
            with listener.accept()[0] as connection:
                connection.settimeout(2)
                connection.recv(4096)
                finish.wait(3)
        except OSError:
            pass
    thread = threading.Thread(target=peer, daemon=True); thread.start()
    argv = [python, '-m', 'fdisbull_player', '--connect', '127.0.0.1:' + str(listener.getsockname()[1]),
            '--connect-password-file', str(password_file)]
    if player_path is None:
        argv.insert(1, '-I')
        environment = None
    else:
        environment = dict(os.environ, PYTHONPATH=str(player_path))
        argv += ['--backend-timeout', '0.2']
    try:
        with (output / (name + '.stdout')).open('wb') as stdout, (output / (name + '.stderr')).open('wb') as stderr:
            try:
                result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                        timeout=1.5, env=environment)
                return {'outer_timeout': False, 'exit_code': result.returncode}
            except subprocess.TimeoutExpired:
                return {'outer_timeout': True, 'exit_code': None}
    finally:
        finish.set(); listener.close(); thread.join(timeout=1)
        password_file.unlink(missing_ok=True)
