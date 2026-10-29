"""Synthetic protocol peer; does not represent a Z-machine implementation."""
import hashlib
import json
import os
import sys
import time
story = sys.argv[1]
identity = {'python': os.path.realpath(sys.executable), 'story_sha256': hashlib.sha256(open(story, 'rb').read()).hexdigest(), 'python_sha256': hashlib.sha256(open(sys.executable, 'rb').read()).hexdigest(), 'jericho_version': '3.3.1', 'jericho_sha256': 'b'*64, 'jericho_module_sha256': 'c'*64, 'native_sha256': 'd'*64}
def send(x): print(json.dumps(x), flush=True)
send({'complete': True, 'outcome': 'ready', 'identity': identity, 'observation': 'initial', 'layout': {'ram': 8, 'stack': 8, 'story': os.path.getsize(story)}, 'protected_paths': [os.path.realpath(__file__)]})
for line in sys.stdin:
    req = json.loads(line)
    if req['op'] == 'command':
        if req['text'] == 'cwd':
            with open('relative-save', 'w') as saved: saved.write('fixture')
            send({'complete': True, 'outcome': 'ok', 'observation': os.getcwd(), 'done': False, 'mode': 'unknown'}); continue
        if req['text'] == 'hang': time.sleep(10)
        if req['text'] == 'oversize': print('x' * 8000001, flush=True); continue
        if req['text'] == 'malformed': print('not-json', flush=True); continue
        if req['text'] == 'bad': send({'complete': False, 'outcome': 'error'}); continue
        send({'complete': True, 'outcome': 'ok', 'observation': req['text'], 'done': False, 'mode': 'unknown'})
    elif req['op'] == 'state': send({'complete': True, 'outcome': 'ok', 'state': ['AAAAAAAAAAA=', 'AAAAAAAAAAA=', 1, 1, 2, 1, 1, [1, 1, 1], '']})
    elif req['op'] == 'restore': send({'complete': True, 'outcome': 'ok'})
