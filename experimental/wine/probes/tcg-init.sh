#!/bin/sh
# PID 1 in an offline, disposable x86-64 Linux VM. No host folders or ports.
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts /dev/shm /proc /sys /work /tmp
mount -t devpts devpts /dev/pts
mount -t tmpfs -o mode=1777,size=256M tmpfs /dev/shm
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs -o mode=1777,size=2G tmpfs /work
mount -t tmpfs -o mode=1777,size=1G tmpfs /tmp
# Bring up only the guest loopback interface; QEMU has no network device.
python3 - <<'PY'
import fcntl,socket,struct
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    request=fcntl.ioctl(sock,0x8913,struct.pack('16s24x',b'lo'))
    flags=struct.unpack_from('H',request,16)[0]
    fcntl.ioctl(sock,0x8914,struct.pack('16sH22x',b'lo',flags|1))
PY
printf '\nFDISBULL_TCG_STARTED\n'
uname -a
cp /opt/probes/controller64.exe /opt/probes/controller64-original.exe
x86_64-w64-mingw32-gcc -O2 -Wall -o /opt/probes/controller64.exe /opt/probes/controller64.c
set +e
runuser -u ubuntu -- /bin/sh /opt/probes/probe.sh > /work/probe-summary.log 2>&1
probe_status=$?
set -e
cat /work/probe-summary.log
printf '{"probe_exit":%s}\n' "$probe_status" > /work/evidence/tcg-init-result.json
# Also replay the exact controller that failed under Rosetta.
set +e
runuser -u ubuntu -- env WINEPREFIX=/work/wine-prefix WINEARCH=win64 WINEDEBUG=-all \
  XDG_RUNTIME_DIR=/work/runtime XDG_CACHE_HOME=/work/cache \
  xvfb-run -a timeout 45 wine /opt/probes/controller64-original.exe \
  'Z:\opt\probes\target64.exe' "$(cat /work/counter-rva.txt)" \
  > /work/evidence/wine-original-controller.jsonl 2> /work/evidence/wine-original-controller.stderr
original_status=$?
set -e
printf '%s\n' "$original_status" > /work/evidence/wine-original-controller.exit
sha256sum /opt/probes/controller64-original.exe /opt/probes/controller64.c \
  /opt/probes/probe.sh /init > /work/evidence/tcg-inputs.sha256
printf '\nFDISBULL_TCG_NATIVE_RESULT\n'
tail -4 /work/evidence/dosbox-tests.log
cat /work/evidence/wine-original-controller.jsonl
# Return only reports. Native states, prefixes and project databases stay in RAM.
tar -C /work/evidence -czf /work/evidence.tgz .
printf '\nFDISBULL_TCG_EVIDENCE_BEGIN\n'
base64 -w0 /work/evidence.tgz
printf '\nFDISBULL_TCG_EVIDENCE_END\n'
sync
python3 - <<'PY'
import ctypes
libc=ctypes.CDLL(None,use_errno=True)
if libc.reboot(0x4321fedc)!=0:
    raise OSError(ctypes.get_errno(),'Guest poweroff failed')
PY
