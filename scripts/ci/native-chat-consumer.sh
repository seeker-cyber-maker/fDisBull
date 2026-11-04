#!/usr/bin/env bash
# Fresh consumer control only: the runner mounts no source or backend directory.
set -Eeuo pipefail
archive=$1
results=$2
kit=/fdisbull-chat-offline
mkdir -p "$results/exported/native-evidence/chat" /consumer /consumer-results
python -I - "$results/runtime.json" <<'PY'
import json, platform, sys
from pathlib import Path
observed = {'python': platform.python_version(), 'machine': platform.machine(), 'system': sys.platform}
Path(sys.argv[1]).write_text(json.dumps(observed) + '\n')
if observed != {'python':'3.13.5','machine':'x86_64','system':'linux'}:
    raise RuntimeError('Wrong consumer control runtime')
PY

finish() {
  code=$?
  trap - EXIT
  set +e
  if [[ ! -f /consumer-results/tests.xml ]]; then
    python -I - "$code" <<'PY'
import sys, xml.etree.ElementTree as ET
from pathlib import Path
suite=ET.Element('testsuite',name='chat-offline-consumer',tests='1',failures='1',errors='0',skipped='0')
case=ET.SubElement(suite,'testcase',name='consumer-bootstrap')
ET.SubElement(case,'failure',message='Verifier did not complete').text='Bootstrap exit code: '+sys.argv[1]
ET.ElementTree(suite).write('/consumer-results/tests.xml',encoding='utf-8',xml_declaration=True)
Path('/consumer-results/bootstrap-failure.json').write_text('{"status":"failed","scope":"consumer bootstrap; native checks incomplete"}\n')
PY
    if [[ $code == 0 ]]; then code=1; fi
  fi
  cp -a /consumer-results/. "$results/exported/native-evidence/chat/"
  exit "$code"
}
trap finish EXIT

python -I - "$archive" "$kit" <<'PY'
import hashlib, os, stat, sys, zipfile
from pathlib import Path, PurePosixPath
archive, root = map(Path,sys.argv[1:])
with archive.open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest() != os.environ['FDISBULL_CHAT_ARCHIVE_SHA256']:
        raise RuntimeError('Consumer ZIP differs from producer')
if archive.stat().st_size > 500_000_000:
    raise RuntimeError('Consumer archive exceeds attachment budget')
root.mkdir()
seen=set(); total=0
with zipfile.ZipFile(archive) as zipped:
    for item in zipped.infolist():
        parts=item.filename.split('/'); path=PurePosixPath(item.filename)
        if item.is_dir(): parts=parts[:-1]
        if (not parts or parts[0] != root.name or path.is_absolute() or '\\' in item.filename
                or any(p in ('','.','..') for p in parts) or item.filename in seen):
            raise RuntimeError('Unsafe or duplicate consumer ZIP member')
        seen.add(item.filename)
        mode=item.external_attr >> 16
        if stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):
            raise RuntimeError('Consumer ZIP contains a link or special file')
        total += item.file_size
        if total > 2*1024**3:
            raise RuntimeError('Consumer extraction exceeds bounded workspace')
        target=root.joinpath(*parts[1:])
        if item.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with zipped.open(item) as source, target.open('xb') as output:
            while block := source.read(1024**2): output.write(block)
        target.chmod(mode & 0o777 if mode else 0o644)
PY

# A self-bind leaves no writable extraction alias. The new network namespace
# has only loopback; the verifier independently observes that condition.
mount --bind "$kit" "$kit"
mount -o remount,bind,ro "$kit"
chmod 0777 /consumer /consumer-results
unshare --net -- "$kit/bin/python" "$kit/tools/verify.py" \
  --kit "$kit" --workspace /consumer --archive "$archive" \
  --output /consumer-results/acceptance.json --junitxml /consumer-results/tests.xml
