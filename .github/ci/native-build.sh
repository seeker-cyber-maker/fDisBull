#!/usr/bin/env bash
# All native configure flags and dependency source pins live here and enter the key.
set -euo pipefail
case "$1" in
  dosbox)
    cd .native/dosbox-x
    ./autogen.sh
    ./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent \
      --disable-avcodec --disable-libslirp --disable-libfluidsynth
    make -j2
    mkdir -p ../../.native-cache/dosbox
    cp src/dosbox-x ../../.native-cache/dosbox/dosbox-x
    ;;
  qemu)
    mkdir -p .native/pe .native-cache/qemu/pc-bios
    curl --fail --location --retry 3 https://download.qemu.org/qemu-9.2.4.tar.xz \
      --output .native/pe/qemu-9.2.4.tar.xz
    echo 'f3cc1c4eabfdb288218ac3e33763dbe9e276d8bc890b867a2335d58de2ddd39a  .native/pe/qemu-9.2.4.tar.xz' | sha256sum --check
    tar -xJf .native/pe/qemu-9.2.4.tar.xz -C .native/pe
    qemu_data="$PWD/.native-cache/qemu/pc-bios"
    cd .native/pe/qemu-9.2.4
    mkdir build
    cd build
    ../configure --target-list=x86_64-softmmu --disable-docs --disable-user \
      --disable-gtk --disable-sdl --disable-vnc --disable-curses --disable-werror \
      --datadir="$qemu_data"
    ninja -j2 qemu-system-x86_64
    cp qemu-system-x86_64 ../../../../.native-cache/qemu/
    # Include shipped firmware and any generated option ROMs; dereference build links.
    cp -rL ../pc-bios/. "$qemu_data/"
    cp -rL pc-bios/. "$qemu_data/"
    ;;
  *) exit 2 ;;
esac
