"""Run one finite offline Wine/DOSBox qualification and collect only reports."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile


REPORTS={
    'linux.txt','wine-version.txt','package-versions.txt','SHA256SUMS',
    'wine-probe.jsonl','wine-probe.stderr','dosbox-tests.xml','dosbox-tests.log',
    'exit-codes.json','tcg-init-result.json','wine-original-controller.jsonl',
    'wine-original-controller.stderr','wine-original-controller.exit','tcg-inputs.sha256',
}


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel',required=True,type=Path)
    parser.add_argument('--initramfs',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--timeout',type=int,default=600)
    args=parser.parse_args()
    if not 1<=args.timeout<=1800:raise SystemExit('Timeout must be 1..1800 seconds')
    binary=shutil.which('qemu-system-x86_64')
    if not binary:raise SystemExit('qemu-system-x86_64 is required')
    kernel=args.kernel.resolve(strict=True);initramfs=args.initramfs.resolve(strict=True)
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    command=[binary,'-accel','tcg,thread=multi','-machine','q35','-cpu','max',
             '-smp','2','-m','8G','-nic','none','-display','none','-monitor','none',
             '-no-reboot','-serial','file:'+str(output/'serial.log'),
             '-kernel',str(kernel),'-initrd',str(initramfs),
             '-append','console=ttyS0,115200 earlycon=uart8250,io,0x3f8,115200 rdinit=/init loglevel=7 panic=1 random.trust_cpu=on']
    timed_out=False
    with (output/'qemu.stdout').open('wb') as stdout,(output/'qemu.stderr').open('wb') as stderr:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
        try:code=process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;process.terminate()
            try:code=process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();code=process.wait()
        except BaseException:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            raise
    receipt={'command':command,'timeout_seconds':args.timeout,'timed_out':timed_out,
             'qemu_exit':code,'kernel_sha256':digest(kernel),'initramfs_sha256':digest(initramfs),
             'qemu_version':subprocess.check_output([binary,'--version'],text=True).splitlines()[0]}
    (output/'vm-result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    serial=output/'serial.log'
    if not serial.exists() or serial.stat().st_size>8*1024**2:
        raise SystemExit('Missing or oversized guest transcript')
    transcript=serial.read_bytes().replace(b'\r\n',b'\n')
    start=b'FDISBULL_TCG_EVIDENCE_BEGIN\n';end=b'\nFDISBULL_TCG_EVIDENCE_END'
    if transcript.count(start)!=1 or transcript.count(end)!=1:
        raise SystemExit('Guest did not return the bounded evidence frame; see serial.log')
    encoded=transcript.split(start,1)[1].split(end,1)[0]
    payload=base64.b64decode(encoded,validate=True)
    if len(payload)>2*1024**2:raise SystemExit('Oversized guest evidence')
    evidence=output/'evidence';evidence.mkdir()
    seen=set();total=0
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        for member in archive:
            name=member.name.removeprefix('./')
            if member.isdir() and name in ('','.'):continue
            total+=member.size
            if not member.isfile() or name not in REPORTS or name in seen or member.size>1024**2 or total>4*1024**2:
                raise SystemExit('Unexpected guest report: '+name)
            seen.add(name)
            (evidence/name).write_bytes(archive.extractfile(member).read())
    exits=json.loads((evidence/'exit-codes.json').read_text())
    print(json.dumps({'vm':receipt,'checks':exits},indent=2))
    if timed_out or code!=0 or any(exits.values()):raise SystemExit(1)


if __name__=='__main__':main()
