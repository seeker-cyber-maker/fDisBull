#!/usr/bin/env python3
"""Check patch/result correspondence and a second SCI1 LZW implementation."""
from pathlib import Path
import json, hashlib, struct, time
import compare_game_patches as p
R=p.ROOT

def verify_result(before,recipe,candidate):
    expected,_,_,_=p.apply_patch(before,recipe)
    if candidate!=expected:raise ValueError('candidate does not match the declared patch transform')
    return True

def dictionary_lzw(src,expected):
    # String dictionary with the KwKwK case, independent of the first decoder's
    # forward output-offset table. Width grows at the SCI1 early-change boundary.
    bits=int.from_bytes(src,'big');total=len(src)*8;pos=0
    table={i:bytes([i]) for i in range(256)};nxt=258;w=9;prev=None;out=bytearray()
    while len(out)<expected:
        if pos+w>total:raise ValueError('short bitstream')
        code=(bits>>(total-pos-w))&((1<<w)-1);pos+=w
        if code==257:break
        if code==256:table={i:bytes([i]) for i in range(256)};nxt=258;w=9;prev=None;continue
        if code in table:word=table[code]
        elif code==nxt and prev is not None:word=prev+prev[:1]
        else:raise ValueError('bad code')
        out.extend(word)
        if prev is not None and nxt<4096:
            table[nxt]=prev+word[:1];nxt+=1
            if nxt==(1<<w)-1 and w<12:w+=1
        prev=word
    if len(out)!=expected:raise ValueError('wrong dictionary output size')
    return bytes(out)

def main():
    import argparse
    import bootstrap_intake
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory holding the exact uploaded GOG patch and new SQ1 installer")
    args = parser.parse_args()
    checks=[];sel=json.loads((R/'selectors.json').read_text())
    for recipe in p.recipes(sel):
        raw=(R/f'resources/script.{recipe["script"]:03}').read_bytes();want,base,changed,written=p.apply_patch(raw,recipe)
        verify_result(raw,recipe,want)
        for at,kind in [(0,'outside_write_set'),(changed[0],'inside_write_set')]:
            candidate=bytearray(want);candidate[at]^=1
            try:verify_result(raw,recipe,bytes(candidate))
            except ValueError:checks.append(dict(case=recipe['id'],test='reject_wrong_result_'+kind,passed=True))
            else:raise AssertionError('invalid result accepted')
        if recipe['id']=='id_card_counter':
            text=p.render_c(p.lift(p.decode(want[base:base+25],base)))
            good=text.count('read_selector(')==1 and text.index('read_selector(')<text.index('write_selector(')
            if not good:raise AssertionError('C repeats stateful read after write')
            checks.append(dict(case=recipe['id'],test='C_getter_evaluated_once_before_store',passed=True))
    p.save(R/'results/patch_oracle_extra_controls.json',checks)
    resources=json.loads((R/'resource_manifest.json').read_text());passed=[];start=time.perf_counter()
    for rec in resources:
        v=(R/f'intake/space_quest/app/vga/RESOURCE.{rec["volume"]:03}').read_bytes()
        packed=v[rec['offset']+9:rec['offset']+9+rec['packed_size']]
        b=dictionary_lzw(packed,rec['size']) if rec['method']==2 else packed
        if p.sha(b)!=rec['sha256']:raise AssertionError('independent decoder mismatch')
        passed.append(rec['name'])
    p.save(R/'results/decompressor_comparison.json',dict(resources=len(passed),all_equal=True,wall_ms=(time.perf_counter()-start)*1000,scope='offset-table decoder versus string-dictionary decoder; same documented SCI1 profile, not independent proof of that format'))
    manifest=json.loads((R/'intake/patch/replacement_manifest.json').read_text());cmp=[]
    for rec in manifest:
        b=(R/'intake/patch/payload'/rec['path']).read_bytes();target=(R/'intake/space_quest/app'/rec['path']).read_bytes()
        if p.sha(b)!=rec['sha256'] or b!=target:raise AssertionError('GOG target mismatch')
        cmp.append(dict(path=rec['path'],size=len(b),sha256=p.sha(b),matches_full_installer=True))
    inputs={}
    for label, key in [('patch', 'patch'), ('new_installer', 'space_quest')]:
        f = args.input_dir / bootstrap_intake.INPUTS[key]
        digest = p.sha(f.read_bytes())
        if digest != bootstrap_intake.EXPECTED[key]:
            raise ValueError('Input does not match the original studied artifact: ' + f.name)
        inputs[label] = dict(name=f.name, size=f.stat().st_size, sha256=digest)
    p.save(R/'results/gog_patch_oracle.json',dict(inputs=inputs,target_count=len(cmp),expanded_target_bytes=sum(c['size'] for c in cmp),targets=cmp,
        payload_kind='36 complete zlib replacement payloads, checksum-verified',old_installer_obtained=False,historical_file_status='addition/replacement/unchanged classification unresolved without predecessor bytes',
        wrapper_control_flow='not fully decompiled; manifest and support JSON inspected, not an executed installation',support_actions=json.loads((R/'intake/patch/payload/goggame-1207661413.script').read_text()),native_execution=False))
    print('GOG targets:',len(cmp),'independent SCI decode:',len(passed),'extra controls:',len(checks))
if __name__=='__main__':main()
