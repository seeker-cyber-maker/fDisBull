"""Private JSONL bridge to an explicitly selected Jericho interpreter."""
import base64
import hashlib
import importlib.metadata
import json
import os
import sys

protocol = os.fdopen(os.dup(1), 'w', buffering=1)
os.dup2(2, 1)

def digest(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def encode_state(state):
    ram, stack, pc, sp, fp, frames, opcode, rng, narrative = state
    return [base64.b64encode(ram.tobytes()).decode(), base64.b64encode(stack.tobytes()).decode(), int(pc), int(sp), int(fp), int(frames), int(opcode), [int(x) for x in rng], base64.b64encode(narrative).decode()]

def decode_state(value, current, story_size):
    import numpy as np
    if not isinstance(value, list) or len(value) != 9:
        raise ValueError('invalid state shape')
    arrays = []
    for item, existing in zip(value[:2], current[:2]):
        if not isinstance(item, str) or len(item) > 4000000:
            raise ValueError('invalid state array')
        raw = base64.b64decode(item, validate=True)
        if len(raw) != len(existing):
            raise ValueError('state array length mismatch')
        arrays.append(np.frombuffer(raw, dtype=np.uint8).copy())
    nums = value[2:7]
    rng = value[7]
    if any(type(n) is not int or not -(2**31) <= n < 2**31 for n in nums):
        raise ValueError('invalid state integer')
    pc, sp, fp, frames, opcode = nums
    stack_words = len(arrays[1]) // 2
    if not (0 <= pc < story_size and 0 <= sp <= stack_words and 0 <= fp <= stack_words and 0 <= frames <= stack_words and 0 <= opcode <= 255):
        raise ValueError('invalid native state pointers')
    if not isinstance(rng, list) or len(rng) != 3 or any(type(n) is not int or not -(2**63) <= n < 2**63 for n in rng):
        raise ValueError('invalid RNG')
    if any(not -(2**31) <= n < 2**31 for n in rng[1:]):
        raise ValueError('invalid RNG range')
    if not isinstance(value[8], str) or len(value[8]) > 1000000:
        raise ValueError('invalid narrative')
    narrative = base64.b64decode(value[8], validate=True)
    if b'\x00' in narrative:
        raise ValueError('invalid narrative bytes')
    return (*arrays, *nums, tuple(rng), narrative)

def main():
    import jericho
    import jericho.jericho as module
    story, seed, expected_hash = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    with open(story, 'rb') as source:
        story_bytes = source.read(16_000_001)
    if len(story_bytes) > 16_000_000 or hashlib.sha256(story_bytes).hexdigest() != expected_hash:
        raise ValueError('story changed before worker startup')
    workdir = sys.argv[4]
    if os.path.realpath(workdir) != os.path.realpath(os.getcwd()):
        raise ValueError('invalid worker directory')
    private_story = os.path.join(workdir, os.path.basename(story))
    with open(private_story, 'wb') as output:
        output.write(story_bytes)
    version = importlib.metadata.version('jericho')
    if version != '3.3.1':
        raise ValueError('Jericho 3.3.1 required')
    identity = {'python': os.path.realpath(sys.executable), 'python_sha256': digest(sys.executable), 'jericho_version': version, 'jericho_sha256': digest(jericho.__file__), 'jericho_module_sha256': digest(module.__file__), 'native_sha256': digest(module.FROTZ_LIB_PATH), 'story_sha256': expected_hash}
    env = jericho.FrotzEnv(private_story, seed=seed)
    obs, info = env.reset()
    def send(obj):
        protocol.write(json.dumps(obj, separators=(',', ':')) + '\n')
    initial = env.get_state()
    send({'complete': True, 'outcome': 'ready', 'identity': identity, 'observation': obs, 'info': info, 'layout': {'ram': len(initial[0]), 'stack': len(initial[1]), 'story': len(story_bytes)}, 'protected_paths': [os.path.realpath(os.path.join(root, name)) for root, dirs, names in os.walk(os.path.dirname(jericho.__file__)) for name in names if os.path.isfile(os.path.join(root, name))]})
    for line in sys.stdin:
        try:
            req = json.loads(line)
            op = req['op']
            if op == 'command':
                obs, reward, done, info = env.step(req['text'])
                response = {'observation': obs, 'reward': reward, 'done': bool(done), 'info': info, 'mode': 'unknown'}
            elif op == 'state':
                response = {'state': encode_state(env.get_state())}
            elif op == 'restore':
                state = decode_state(req['state'], env.get_state(), len(story_bytes))
                env.set_state(state)
                response = {}
            else:
                raise ValueError('unknown operation')
            send({'complete': True, 'outcome': 'ok', **response})
        except Exception as exc:
            send({'complete': False, 'outcome': 'error', 'error': str(exc)})
    env.close()

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        protocol.write(json.dumps({'complete': False, 'outcome': 'error', 'error': str(exc)}) + '\n')
