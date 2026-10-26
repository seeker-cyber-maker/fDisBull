"""Prepare the IDA guest controller; vendor server binaries are supplied at launch."""
from pathlib import Path
import argparse
import json

from .wine_runtime import resources as wine_resources, prepare as prepare_wine


def resources():
    root = Path(__file__).parent
    result = wine_resources()
    result.pop('opt/fdisbull/selftest.c') # IDA profile does not offer the Wine self-test RPC.
    result.update({
        'init': root/'ida_guest'/'init.sh',
        'opt/fdisbull/ida_broker.py': root/'ida_guest'/'broker.py',
        'opt/fdisbull/ui.c': root/'ida_guest'/'ui.c',
        'opt/fdisbull/remote/__init__.py': root/'ida_guest'/'__init__.py',
        'opt/fdisbull/remote/ida_wire.py': root/'ida_wire.py',
        'opt/fdisbull/remote/ida_remote.py': root/'ida_remote.py',
        'opt/fdisbull/remote/ida_trace.py': root/'ida_trace.py',
    })
    return result


def prepare(base, output):
    return prepare_wine(base, output, resource_files=resources())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-initramfs', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.base_initramfs, args.output), indent=2))


if __name__ == '__main__':
    main()
