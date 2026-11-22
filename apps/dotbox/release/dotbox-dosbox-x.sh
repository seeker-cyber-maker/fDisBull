#!/bin/sh
prefix_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 1
exec "$prefix_dir/native/lib/ld-linux-x86-64.so.2" \
  --library-path "$prefix_dir/native/lib" \
  "$prefix_dir/native/bin/dosbox-x" "$@"
