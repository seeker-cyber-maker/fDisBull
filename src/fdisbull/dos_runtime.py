"""Prepare the DOSBox/QEMU profile from a trusted Linux base and explicit ELF."""
import argparse
import json
from pathlib import Path

from .wine_runtime import prepare as prepare_base


def resources():
    root=Path(__file__).parent
    return {'init':root/'dos_guest/init.sh','opt/fdisbull/dos_broker.py':root/'dos_guest/broker.py',
            'opt/fdisbull/remote/__init__.py':root/'dos_guest/__init__.py',
            'opt/fdisbull/remote/dosbox_rpc.py':root/'dosbox_rpc.py'}


def prepare(base,output,dosbox):
    path=Path(dosbox).expanduser().resolve(strict=True)
    with path.open('rb') as stream:header=stream.read(20)
    if header[:6]!=b'\x7fELF\x02\x01' or header[18:20]!=b'\x3e\x00':raise ValueError('DOS guest requires a Linux x86-64 ELF DOSBox executable')
    return prepare_base(base,output,resource_files=dict(resources(),**{'opt/fdisbull/dosbox-x':path}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base-initramfs','output','dosbox'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.base_initramfs,args.output,args.dosbox),indent=2))


if __name__=='__main__':main()
