"""Prepare an exact-owned GAMEFM.DLL for bounded private callback experiments.

This is not a security sandbox. It is pinned to one game driver and refuses
other bytes. Outputs include original game code and must remain private.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess
from lx_reader import lx
EXPECTED='520db726d034394e7ea7f62b9bfa90767898990836522fc09f89931f2c388a7e'
C_SOURCE=r'''
#define _GNU_SOURCE
#include <sys/mman.h>
#include <sys/ptrace.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
int main(int argc, char **argv) {
    if (argc != 2) return 110;
    int fd = open(argv[1], O_RDWR);
    if (fd < 0) return 111;
    uint32_t maps[][3] = {{0x10000,0x4000,7}, {0x1000000,0x100000,3},
                         {0x2000000,0x10000,3}};
    for (unsigned i = 0; i < sizeof(maps)/sizeof(maps[0]); ++i) {
        if (mmap((void *)(uintptr_t)maps[i][0], maps[i][1], maps[i][2],
                 MAP_SHARED|MAP_FIXED, fd, maps[i][0]) == MAP_FAILED) return 112;
    }
    if (ptrace(PTRACE_TRACEME, 0, 0, 0) < 0) return 113;
    __asm__("int3");
    return 0;
}
'''
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('original',type=Path);p.add_argument('destination',type=Path)
    p.add_argument('--cc',default='cc');a=p.parse_args()
    raw=a.original.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:raise ValueError('Wrong original GAMEFM identity')
    dst=a.destination.expanduser().absolute()
    if dst.exists() or any(q.is_symlink() or (q/'.git').exists() for q in (dst,*dst.parents)):
        raise ValueError('Use a new private directory outside Git and symlink ancestry')
    cc=shutil.which(a.cc)
    if not cc:raise ValueError('A local C compiler is required; no download is attempted')
    image,entries,fixups=lx(raw)
    dst.mkdir(mode=0o700,parents=True);(dst/'evidence').mkdir(mode=0o700)
    (dst/'region-10000.bin').write_bytes(image)
    manifest={'original_sha256':EXPECTED,'regions':{'0x10000':{'size':len(image),'sha256':hashlib.sha256(image).hexdigest()}},'service_entries':len(entries),'fixup_records':len(fixups),'profile':'Single original FM callback, synthetic data, Linux x86-32 compatibility; no DOS/devices.'}
    (dst/'region-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (dst/'loader.c').write_text(C_SOURCE)
    done=subprocess.run([cc,'-O2','-Wall','-Wextra',str(dst/'loader.c'),'-o',str(dst/'slice_loader64')],capture_output=True,text=True,timeout=30)
    (dst/'compiler.json').write_text(json.dumps({'returncode':done.returncode,'stdout':done.stdout,'stderr':done.stderr},indent=2))
    done.check_returncode()
    print(json.dumps({'private_directory':str(dst),'source_sha256':EXPECTED,'mapped_sha256':manifest['regions']['0x10000']['sha256'],'target_executed':False}))
if __name__=='__main__':main()
