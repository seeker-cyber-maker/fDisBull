"""Bounded v0.22 probes; large responses stay in private files, never the chat.

These probes examine output amplification and a silent TCP peer. They cannot
establish why a conversation service fails to retrieve a chat.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import threading


def quiet_player(python, output, name, *, player_path=None):
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
    argv = [python, '-m', 'fdisbull_player', '--connect', '127.0.0.1:' + str(listener.getsockname()[1])]
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True, help='explicit installed fDisBull v0.22 Python')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or any((p / '.git').exists() for p in (output, *output.parents)):
        parser.error('output must be new and outside Git')
    output.mkdir(parents=True)
    identity = subprocess.run([args.python, '-I', '-c',
        'import fdisbull, fdisbull.interaction_il as il, json; print(json.dumps({"version": fdisbull.__version__, "module": il.__file__}))'],
        capture_output=True, text=True, timeout=5, check=True)
    source = {'format': 'fdisbull-il-1', 'role': 'uil', 'variables': {},
              'resources': {'message': {'kind': 'text', 'text': 'x' * 32768}},
              'body': [{'id': str(i), 'op': 'text', 'resource': 'message'} for i in range(400)]}
    path = output / 'repeated-text.json'; path.write_text(json.dumps(source))
    with (output / 'il-run.stdout.json').open('wb') as stdout, (output / 'il-run.stderr').open('wb') as stderr:
        result = subprocess.run([args.python, '-I', '-m', 'fdisbull', 'il-run', str(path)],
                                stdout=stdout, stderr=stderr, timeout=10)
    receipt = {'scope': 'bounded release probes, not a chat-crash diagnosis',
               'release': json.loads(identity.stdout),
               'amplification': {'input_bytes': path.stat().st_size,
                                 'output_bytes': (output / 'il-run.stdout.json').stat().st_size,
                                 'exit_code': result.returncode},
               'installed_silent_tcp': quiet_player(args.python, output, 'installed'),
               'candidate_silent_tcp': quiet_player(args.python, output, 'candidate',
                    player_path=Path(__file__).resolve().parents[2] / 'player')}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
