#!/usr/bin/env python3
"""Fixed native endpoint for the existing n8n CI status/tick bridge."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
MODULE_ROOT = HERE / 'fdisbull-ci-production' if (HERE / 'fdisbull-ci-production').is_dir() else HERE
sys.path.insert(0, str(MODULE_ROOT))

CONFIG = Path('/etc/fdisbull-ci-production/config.json')
STATE = Path('/var/lib/fdisbull-ci/control/recovery/production')


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('unsafe installed record')
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise ValueError('installed object required')
    return value


def verify_sources(config, root, owner):
    hashes = config.get('module_sha256')
    if not isinstance(hashes, dict) or not {'production_manifest.py', 'production-ci.py'} <= set(hashes):
        raise ValueError('exact installed source manifest missing')
    for name, expected in hashes.items():
        if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.py', name)
                or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected)):
            raise ValueError('invalid installed source manifest')
        path = root / name
        if (path.is_symlink() or not path.is_file() or path.stat().st_uid != owner
                or path.stat().st_mode & 0o022 or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError('installed source changed')
    spec = importlib.util.spec_from_file_location('installed_ci_manifest', root / 'production_manifest.py')
    manifest = importlib.util.module_from_spec(spec); spec.loader.exec_module(manifest)
    if set(hashes) != set(manifest.MODULES):
        raise ValueError('installed source manifest incomplete')
    if (config.get('entrypoint_sha256') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or config['entrypoint_sha256'] != hashes['production-ci.py']):
        raise ValueError('native entrypoint differs')


def installation_config():
    if os.geteuid() != 0:
        raise ValueError('native endpoint requires its installed service identity')
    if (CONFIG.is_symlink() or not CONFIG.is_file() or CONFIG.stat().st_uid != 0
            or CONFIG.stat().st_mode & 0o077):
        raise ValueError('private installed configuration required')
    config = read_json(CONFIG)
    if config.get('state_dir') != str(STATE):
        raise ValueError('installed state path mismatch')
    verify_sources(config, MODULE_ROOT, 0)
    return config


def runtime_factory(config, root, lease):
    # Status imports no provider implementation and performs no API/model call.
    from production_runtime import Runtime
    return Runtime(config, root, lease)


def service_factory(config):
    # Installation/source verification precedes imports of mutable local code.
    from production_control import ProductionService
    return ProductionService(config, runtime_factory)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Invalid CI command.\n')


def record_failure(error_type):
    if (not STATE.is_dir() or any(p.is_symlink() for p in (STATE, *STATE.parents))
            or STATE.stat().st_uid != os.geteuid() or STATE.stat().st_mode & 0o077):
        return
    path = STATE / ('service-error-' + str(time.time_ns()) + '.json')
    record = {'status': 'attention', 'error_type': error_type, 'observed_epoch': time.time()}
    def exclusive(target, value):
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    exclusive(path, record)
    blocked = STATE / 'blocked.json'
    if not blocked.exists(): exclusive(blocked, {**record, 'receipt_path': str(path)})


def main(argv=None):
    parser = SafeParser(description=__doc__)
    parser.add_argument('operation', choices=('status', 'run'))
    args = parser.parse_args(argv)
    previous_term = signal.signal(signal.SIGTERM, signal.SIG_IGN) if args.operation == 'run' else None
    try:
        config = installation_config()
        service = service_factory(config)
        result = service.status() if args.operation == 'status' else service.run()
        print(json.dumps(result, separators=(',', ':'), allow_nan=False))
        return 0 if args.operation == 'status' or result.get('status') in ('disabled', 'idle', 'complete') else 1
    except BlockingIOError:
        print('{"status":"busy"}')
        return 0
    except Exception as error:
        # Preserve only a safe error category; provider/log/credential text must
        # never enter the web response, journal or notification payload.
        if args.operation == 'run':
            try:
                record_failure(type(error).__name__)
            except Exception:
                pass
        if args.operation == 'status': print('{"schema_version":1,"state":"unknown"}')
        else: print(json.dumps({'status': 'attention', 'error_type': type(error).__name__}, separators=(',', ':')))
        return 1
    finally:
        if previous_term is not None: signal.signal(signal.SIGTERM, previous_term)


if __name__ == '__main__':
    raise SystemExit(main())
