#!/usr/bin/env bash
set -euo pipefail
[[ "${FDISBULL_EXECUTION_ORIGIN:-}" = local-linux || "${FDISBULL_EXECUTION_ORIGIN:-}" = boat-linux ]]
python -c 'import platform,sys; assert sys.version_info[:3] == (3,13,5) and platform.machine() == "x86_64" and sys.platform == "linux"'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends binutils xz-utils libglib2.0-0 libpixman-1-0 libsdl2-2.0-0 libsdl2-net-2.0-0 libncurses6 libncursesw6 libgl1 libpng16-16 zlib1g libfreetype6
mkdir -p .native/chat/wheels .native/chat/output native-evidence/chat
shopt -s nullglob
core=(dist/fdisbull-*.whl)
player=(dist/fdisbull_player-*.whl)
[ "${#core[@]}" = 1 ] && [ "${#player[@]}" = 1 ]
python -m pip download --only-binary=:all: --dest .native/chat/wheels "${core[0]}[proof,udc,managed,source,console]" "${player[0]}"
python -m pip install --no-index --find-links .native/chat/wheels --force-reinstall "${core[0]}[proof,udc,managed,source,console]" "${player[0]}"
python scripts/ci/prepare-chat-inputs.py
python scripts/prepare_chat_offline_inventory.py --config .native/chat/config.json --stage .native/chat/stage
python scripts/build_chat_offline_kit.py --inventory .native/chat/stage/inventory.json --output .native/chat/output/fdisbull-chat-offline.zip
python - <<'PY'
import hashlib, json, os
from pathlib import Path
p=Path('.native/chat/output/fdisbull-chat-offline.zip')
with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
Path('native-evidence/chat/assembly.json').write_text(json.dumps({'schema':'fdisbull-chat-assembly-v1','status':'not-qualified-by-builder','source_commit':os.environ['CI_COMMIT_SHA'],'local_run_id':os.environ['FDISBULL_LOCAL_RUN_ID'],'archive':{'sha256':digest,'size':p.stat().st_size}},indent=2)+'\n')
PY
