#!/bin/sh
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
chown ubuntu:ubuntu /dev/ttyS1 /work
chmod 600 /dev/ttyS1
runuser -u ubuntu -- env SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  XDG_RUNTIME_DIR=/work/runtime XDG_CACHE_HOME=/work/cache python3 /opt/fdisbull/dos_broker.py
sync
python3 - <<'PY'
import ctypes
ctypes.CDLL(None).reboot(0x4321fedc)
PY
