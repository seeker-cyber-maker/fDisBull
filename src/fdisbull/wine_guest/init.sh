#!/bin/sh
# Offline disposable Linux runtime. The second UART is the private RPC channel.
set -eu
export PATH=/opt/wine-stable/bin:/usr/sbin:/usr/bin:/sbin:/bin
# The existing Wine64 runtime remains valid; Wine 11 new WoW64 adds PE32.
export WINEDLLOVERRIDES=mscoree,mshtml=
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts /dev/shm /proc /sys /work /tmp
mount -t devpts devpts /dev/pts
mount -t tmpfs -o mode=1777,size=256M tmpfs /dev/shm
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs -o mode=1777,size=2G tmpfs /work
mount -t tmpfs -o mode=1777,size=1G tmpfs /tmp
python3 - <<'PY'
import fcntl,socket,struct
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
    request=fcntl.ioctl(sock,0x8913,struct.pack('16s24x',b'lo'))
    flags=struct.unpack_from('H',request,16)[0]
    fcntl.ioctl(sock,0x8914,struct.pack('16sH22x',b'lo',flags|1))
PY
chown ubuntu:ubuntu /dev/ttyS1
chmod 600 /dev/ttyS1
x86_64-w64-mingw32-gcc -O2 -Wall -Wextra -o /opt/fdisbull/agent.exe /opt/fdisbull/agent.c -luser32 -lgdi32 -lcrypt32
x86_64-w64-mingw32-gcc -O0 -Wall -Wextra -o /opt/fdisbull/selftest.exe /opt/fdisbull/selftest.c -mwindows -luser32 -lgdi32
pe32_cc=$(command -v i686-w64-mingw32-gcc || true)
if [ -z "$pe32_cc" ] && [ -x /usr/bin/i686-w64-mingw32-gcc-13-win32 ]; then pe32_cc=/usr/bin/i686-w64-mingw32-gcc-13-win32; fi
if [ -n "$pe32_cc" ] && [ -f /opt/fdisbull/selftest32.c ]; then
    "$pe32_cc" -O0 -Wall -Wextra -o /opt/fdisbull/selftest32.exe /opt/fdisbull/selftest32.c -mwindows -luser32 -lgdi32
fi
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp > /work/xvfb.log 2>&1 &
wine_major=$(wine --version | sed -n 's/^wine-\([0-9][0-9]*\).*/\1/p')
case "$wine_major" in ''|*[!0-9]*) wine_arch=win64 ;; *)
    if [ "$wine_major" -ge 11 ]; then wine_arch=wow64; else wine_arch=win64; fi ;;
esac
runuser -u ubuntu -- env DISPLAY=:99 WINEPREFIX=/work/prefix WINEARCH="$wine_arch" WINEDEBUG=-all \
  XDG_RUNTIME_DIR=/work/runtime XDG_CACHE_HOME=/work/cache python3 /opt/fdisbull/broker.py
sync
python3 - <<'PY'
import ctypes
ctypes.CDLL(None).reboot(0x4321fedc)
PY
