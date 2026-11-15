"""Independent trees and exact reduction replay are qualification boundaries."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

NODE = shutil.which('node')
SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/bla_current_module_prepare.cjs'
pytestmark = pytest.mark.skipif(NODE is None, reason='Node required for static preparation')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def invoke(config, method='prepare'):
    driver = "const fs=require('fs');const m=require(process.argv[1]);m[process.argv[2]](JSON.parse(fs.readFileSync(0,'utf8'))).then(x=>console.log(JSON.stringify({ok:true,result:x}))).catch(e=>console.log(JSON.stringify({ok:false,error:e.message})));"
    result = subprocess.run([NODE, '--max-old-space-size=256', '-e', driver, str(SCRIPT), method],
                            input=json.dumps(config), text=True, capture_output=True, timeout=20,
                            env={'PATH': str(Path(NODE).parent)})
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def authored(tmp_path):
    lasik = tmp_path / 'authored-static-transformer'
    (lasik / 'dist/engine').mkdir(parents=True)
    (lasik / 'dist/js').mkdir()
    (lasik / 'dist/formats').mkdir()
    (lasik / 'package.json').write_text(json.dumps({'name': 'authored-transformer', 'version': '0', 'type': 'module'}))
    (lasik / 'dist/engine/run.js').write_text('''
import fs from 'node:fs';import path from 'node:path';
export function run(root,mode,opts){const files=[];function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory()){walk(p);continue;}const rel=path.relative(root,p),out=path.join(opts.outDir,rel);fs.mkdirSync(path.dirname(out),{recursive:true});const raw=fs.readFileSync(p);fs.writeFileSync(out,raw,{flag:'wx'});files.push({file:rel,format:'authored',bytesBefore:raw.length,bytesAfter:raw.length,healed:false,warnings:[],findings:[]});}}walk(root);return {files};}
''')
    (lasik / 'dist/js/heal.js').write_text('export function healJs(code){return {code,changed:false};}')
    (lasik / 'dist/js/html.js').write_text('export function healHtml(code){return {code,changed:false};}')
    (lasik / 'dist/formats/wasm.js').write_text('export function healWasm(output){return {output,changed:false};}')
    marker = tmp_path / 'target-was-executed'
    source = 'require("fs").writeFileSync(' + json.dumps(str(marker)) + ',"bad");'
    editions = []
    for version in ('v6', 'v7'):
        root = tmp_path / version
        root.mkdir()
        payloads = ({'vault.cjs': source.encode(), 'panel.html': b'<script>throw 7;</script>',
                     'core.wasm.gz': gzip.compress(b'\0asm\1\0\0\0', mtime=0)} if version == 'v6' else
                    {'cli/meridian.cjs': source.encode(), 'core/license.cjs': b'module.exports={};',
                     'data/catalog.json': b'{"authored":true}'})
        pins = []
        for name, raw in sorted(payloads.items()):
            file = root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
            pins.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
        editions.append({'edition': version, 'sourceRoot': str(root), 'pins': pins})
    config = {'sourceCommit': '1' * 40, 'lasikRoot': str(lasik),
              'outputRoot': str(tmp_path / 'prepared'), 'editions': editions}
    return config, marker


def verification(config):
    return {k: v for k, v in {**config, 'manifestPath': str(Path(config['outputRoot']) / 'preparation.json')}.items()
            if k != 'outputRoot'}


def rewrite_manifest(config, edit):
    file = Path(config['outputRoot']) / 'preparation.json'
    manifest = json.loads(file.read_text())
    edit(manifest)
    manifest.pop('manifest_sha256')
    manifest['manifest_sha256'] = sha(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')).encode())
    file.write_text(json.dumps(manifest))


def test_prepare_and_replay_are_static_and_preserve_independent_originals(authored):
    config, marker = authored
    result = invoke(config)
    assert result['ok'], result
    assert not marker.exists()
    checked = invoke(verification(config), 'verifyPrepared')
    assert checked['ok'], checked
    assert checked['result']['verification']['exact_reduction_replayed'] is True
    assert checked['result']['verification']['independent_roots_and_inodes'] is True
    assert not marker.exists()
    assert (Path(config['outputRoot']) / 'v6/original/core.wasm').read_bytes() == b'\0asm\1\0\0\0'


def test_existing_destination_is_preserved(authored):
    config, _ = authored
    root = Path(config['outputRoot'])
    root.mkdir()
    (root / 'retain').write_text('authored prior evidence')
    assert invoke(config)['ok'] is False
    assert (root / 'retain').read_text() == 'authored prior evidence'


def test_json_key_order_does_not_change_source_identity(authored):
    config, _ = authored
    reordered = json.loads(json.dumps(config, sort_keys=True))
    assert invoke(reordered)['ok']
    assert invoke(verification(reordered), 'verifyPrepared')['ok']


def test_changed_source_is_rejected_before_copying(authored):
    config, _ = authored
    (Path(config['editions'][0]['sourceRoot']) / 'vault.cjs').write_text('changed')
    result = invoke(config)
    assert result['ok'] is False
    assert result['error'] == 'Source pins changed before preparation'


def test_declared_candidate_hash_cannot_replace_exact_transform_replay(authored):
    config, _ = authored
    assert invoke(config)['ok']
    file = Path(config['outputRoot']) / 'v7/reduced/core/license.cjs'
    file.write_text('changed candidate source')
    def edit(manifest):
        pin = next(x for x in manifest['editions'][1]['reduced']['pins'] if x['path'] == 'core/license.cjs')
        pin.update(bytes=file.stat().st_size, sha256=sha(file.read_bytes()))
    rewrite_manifest(config, edit)
    result = invoke(verification(config), 'verifyPrepared')
    assert result == {'ok': False, 'error': 'LASIK reduction replay differs'}


@pytest.mark.parametrize('defect', ['manifest_digest', 'distribution', 'extra_file', 'shared_inode'])
def test_changed_manifest_toolchain_or_tree_is_rejected(authored, defect):
    config, _ = authored
    assert invoke(config)['ok']
    root = Path(config['outputRoot'])
    if defect == 'manifest_digest':
        file = root / 'preparation.json'
        data = json.loads(file.read_text()); data['source_commit'] = '2' * 40
        file.write_text(json.dumps(data))
    elif defect == 'distribution':
        (Path(config['lasikRoot']) / 'dist/js/heal.js').write_text('export const changed=1;')
    elif defect == 'extra_file':
        (root / 'v7/reduced/unlisted').write_text('unlisted')
    else:
        file = root / 'v7/reduced/core/license.cjs'
        file.unlink()
        file.hardlink_to(root / 'v7/original/core/license.cjs')
    result = invoke(verification(config), 'verifyPrepared')
    assert result['ok'] is False
