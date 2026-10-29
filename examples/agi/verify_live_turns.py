"""Check automatic turn saves across fresh host and independent player processes.

Use play-private.json from verify_progressive_text.py and an installed player
interpreter. Checkpoints and game files remain in the private host project.
The external story agent here is a scripted protocol fixture, not an LLM.
"""
import argparse
import json
import os
from pathlib import Path
import selectors
import shlex
import subprocess
import time


def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = {'format': 'fdisbull-live-turn-verification-1', 'sessions': [],
              'claim': 'Fresh-process native resume and scripted story protocol; not autonomous puzzle completion.'}

    def session(commands=None, story=False):
        index = len(report['sessions'])
        with (root / f'host-{index}.stderr').open('w') as errors:
            host = subprocess.Popen([str(args.core_python), '-m', 'fdisbull', 'text-host',
                                     str(args.configuration.resolve())],
                                    stdout=subprocess.PIPE, stderr=errors, text=True)
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(host.stdout, selectors.EVENT_READ)
                    if not selector.select(45):
                        raise TimeoutError('Host did not provide an endpoint')
                line = host.stdout.readline(1024 * 1024)
                endpoint = json.loads(line)['text_player_endpoint']
                client = [str(args.player_python), '-I', '-m', 'fdisbull_player', '--connect',
                          f"{endpoint['host']}:{endpoint['port']}", '--live']
                if story:
                    transcript = root / 'story.json'
                    client += ['--agent-command', shlex.join([str(args.player_python), '-I', str(root / 'agent.py')]),
                               '--max-turns', '2', '--wall-seconds', '30', '--transcript', str(transcript)]
                    data = ''
                else:
                    data = json.dumps({'commands': commands}) + '\n'
                result = subprocess.run(client, input=data, capture_output=True, text=True, timeout=60,
                                        cwd=root, env={k:v for k,v in os.environ.items() if k != 'PYTHONPATH'})
                if result.returncode:
                    raise RuntimeError('Player failed: ' + result.stderr + result.stdout)
                host_output, _ = host.communicate(timeout=15)
                if host.returncode:
                    raise RuntimeError('Host failed: ' + host_output)
                receipt = json.loads(transcript.read_text()) if story else json.loads(result.stdout)
                (root / f'player-{index}.txt').write_text(result.stdout)
                report['sessions'].append({'new_host_process': True, 'new_player_process': True,
                                           'receipt': receipt})
                checkpoint = receipt['turns'][-1]['checkpoint'] if story else receipt['checkpoint']
                if checkpoint.get('status') != 'saved' or checkpoint.get('complete') is not True:
                    raise RuntimeError('Turn checkpoint incomplete')
                return receipt
            finally:
                if host.poll() is None:
                    host.terminate()
                    try:
                        host.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        host.kill(); host.wait()
                host.stdout.close()

    # One model turn has two assisted actions. Neither command requests a save.
    first = session(['teleport east marker', 'go east exit', 'look'])
    if first['restore']['status'] != 'missing' or not all(
            item['outcome'].startswith('Success') for item in first['outcomes'][:2]):
        raise RuntimeError('Expected a new private slot and successful assisted route')
    second = session(['look', 'inventory'])
    if second['restore']['status'] != 'restored' or 'neighboring room' not in second['outcomes'][0]['outcome']:
        raise RuntimeError('Fresh process did not resume in the observed neighboring room')
    if second['restore']['checkpoint'] != first['checkpoint']['checkpoint']:
        raise RuntimeError('Fresh process restored a different checkpoint')
    (root / 'agent.py').write_text(
        'import json, sys\nfor line in sys.stdin:\n'
        ' r=json.loads(line)\n'
        ' print(json.dumps({"commands":["look"],"narration":'
        '"I choose to look around the neighboring room before taking another step.",'
        '"done":True}),flush=True)\n')
    story = session(story=True)
    if story['status'] != 'agent_done' or story['restore']['status'] != 'restored':
        raise RuntimeError('Scripted story protocol did not finish after resuming')
    report['complete'] = True
    report['finished_at_unix'] = time.time()
    (root / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'complete': True, 'fresh_host_client_pairs': len(report['sessions']),
                      'automatic_checkpoints': 3, 'scripted_story_protocol': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configuration', type=Path, required=True)
    parser.add_argument('--core-python', type=Path, required=True)
    parser.add_argument('--player-python', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args())
