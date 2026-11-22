#!/bin/sh
prefix_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 1
export DOTBOX_DOSBOX_EXECUTABLE="$prefix_dir/bin/dotbox-dosbox-x"
exec "$prefix_dir/venv/bin/python" -I -m dotbox "$@"
