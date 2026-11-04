#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$CI_PROJECT_DIR/.native/tmp"
mkdir -p .native/offline/packages .native/offline/wheels .native/offline/lib "$NATIVE_EVIDENCE/offline"
shopt -s nullglob
core_wheels=(dist/fdisbull-*.whl)
player_wheels=(dist/fdisbull_player-*.whl)
[[ ${#core_wheels[@]} -eq 1 && ${#player_wheels[@]} -eq 1 ]]
cp "${core_wheels[0]}" .native/offline/packages/
cp "${core_wheels[0]}" "${player_wheels[0]}" .native/offline/wheels/
kit_wheel=".native/offline/packages/$(basename "${core_wheels[0]}")"
python -m pip download --only-binary=:all: --dest .native/offline/wheels "$kit_wheel[proof]"
kit_sdl=$(ldd "$FDISBULL_DOSBOX" | awk '/libSDL2_net/{print $3; exit}')
test -f "$kit_sdl"
cp -L "$kit_sdl" .native/offline/lib/libSDL2_net-2.0.so.0
python scripts/build_dosbox_source_companion.py \
  --source "$FDISBULL_DOSBOX_SOURCE" \
  --manifest experimental/dosbox-x/layers/source-manifest.json \
  --source-commit "$CI_COMMIT_SHA" --output .native/offline/source-companion.tar \
  > "$NATIVE_EVIDENCE/offline"/source-companion.json
python scripts/build_offline_kit.py --wheelhouse .native/offline/wheels \
  --backend "$FDISBULL_DOSBOX" --sdl-lib .native/offline/lib/libSDL2_net-2.0.so.0 \
  --dosbox-license "$FDISBULL_DOSBOX_SOURCE/COPYING" \
  --sdl-license /usr/share/doc/libsdl2-net-2.0-0/copyright \
  --source-companion .native/offline/source-companion.tar --source-commit "$CI_COMMIT_SHA" \
  --backend-receipt "$NATIVE_EVIDENCE/backend-identity.json" \
  --patch-manifest experimental/dosbox-x/layers/source-manifest.json --output .native/offline/output
mkdir .native/offline/unpacked
kit_version=$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
tar -xzf ".native/offline/output/fdisbull-${kit_version}-linux-x86_64-offline.tar.gz" -C .native/offline/unpacked
kit_root="$CI_PROJECT_DIR/.native/offline/unpacked/fdisbull-${kit_version}-linux-x86_64-offline"
python - "$kit_root/manifest.json" "${core_wheels[0]}" "${player_wheels[0]}" <<'PYCODE'
import hashlib, json, os, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
if manifest['source_commit'] != os.environ['CI_COMMIT_SHA']:
    raise SystemExit('offline kit source commit mismatch')
for name, path in zip(('fdisbull', 'fdisbull-player'), map(Path, sys.argv[2:])):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest['wheels'][name]['sha256'] != digest:
        raise SystemExit(f'offline kit wheel mismatch: {name}')
print('Offline kit source commit and ordinary wheel hashes verified')
PYCODE
kit_install_parent=$(mktemp -d "$CI_BUILDS_DIR/fdisbull-offline-installed.XXXXXX")
kit_install="$kit_install_parent/venv"
"$kit_root/install.sh" "$kit_install" \
  2>&1 | tee "$NATIVE_EVIDENCE/offline"/install.log
"$kit_install/bin/python" -I scripts/verify_offline_kit.py \
  --kit "$kit_root" --output "$NATIVE_EVIDENCE/offline"/acceptance.json
python scripts/check_agent_skill.py --python "$kit_install/bin/python" \
  --output "$kit_install_parent/agent-skill.json"
cp "$kit_install_parent/agent-skill.json" "$NATIVE_EVIDENCE/offline"/agent-skill.json
python scripts/check_agent_skill.py --python "$kit_install/bin/python" --skill write-gamefaqs-guide \
  --output "$kit_install_parent/guide-skill.json"
cp "$kit_install_parent/guide-skill.json" "$NATIVE_EVIDENCE/offline"/guide-skill.json
sha256sum .native/offline/output/* > "$NATIVE_EVIDENCE/offline"/SHA256SUMS
