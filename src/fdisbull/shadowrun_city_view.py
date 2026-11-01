"""Private, asset-free city views of one source-bound Shadowrun snapshot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .game_il import canonical
from .shadowrun_city import (captured_entities, project_city, render_city_text,
                             render_region_text, terrain_symbols)
from .shadowrun_play import machine_from_capture
from .shadowrun_replay import _new_private_directory, _read_rom, _source_capture
from .shadowrun_z import ShadowrunRuntime


def render_html(state):
    """Render passive layers; coarse cells never become action destinations."""
    city = project_city(state)
    data = {**city, 'terrain_symbols': list(terrain_symbols(state)),
            'terrain_codes': list(state['terrain'])}
    packed = json.dumps(data, ensure_ascii=True, separators=(',', ':'))
    packed = packed.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    return _HTML.replace('__CITY_DATA__', packed)


def export_city(rom_path, *, snapshot, output):
    runtime = open_runtime(rom_path, snapshot=snapshot)
    state = runtime.snapshot()
    city = project_city(state)
    identity, _, _ = _source_capture(snapshot, state['source_sha256'])
    out = _new_private_directory(output)
    out.mkdir(mode=0o700)
    values = {'city.json': json.dumps({**city, 'terrain_codes': list(state['terrain']),
                                      'terrain_symbols': list(terrain_symbols(state))}, indent=2) + '\n',
              'city.html': render_html(state),
              'city.txt': render_region_text(state) + '\n\n' + render_city_text(state) + '\n'}
    files = {}
    for name, text in values.items():
        raw = text.encode()
        path = out / name
        path.write_bytes(raw)
        path.chmod(0o600)
        files[name] = {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    result = {'format': 'fdisbull-shadowrun-city-export-1',
              'source_sha256': state['source_sha256'], 'capture': identity,
              'program_sha256': hashlib.sha256(canonical(runtime.machine.program)).hexdigest(),
              'scene_id': state['scene_id'], 'grid': [64, 44],
              'captured_entities': len(city['captured_entities']), 'files': files,
              'executed': False, 'observation': 'prepared-state investigator snapshot',
              'visibility': 'unknown', 'walkability': 'unknown',
              'scope': 'passive city and tactical index; no input, teleport or route execution'}
    (out / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def open_runtime(rom_path, *, snapshot):
    rom = _read_rom(rom_path)
    return ShadowrunRuntime(machine_from_capture(rom, snapshot),
                            captured_entities=captured_entities(rom, snapshot))


_HTML = r'''<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'">
<title>Shadowrun city snapshot</title>
<style>
:root{color-scheme:dark;font:16px system-ui;background:#101821;color:#e1ebee}
body{margin:0 auto;max-width:1400px;padding:28px}h1{font-size:30px;margin:0 0 12px}
p{max-width:90ch;color:#bdced4;line-height:1.5}.tools{display:flex;gap:20px;flex-wrap:wrap;align-items:center;margin:20px 0}
button,input{font:inherit}button{background:#244354;color:white;border:1px solid #608499;padding:8px 14px;border-radius:6px}
.map{overflow:auto;border:1px solid #466273;border-radius:8px;max-height:75vh}canvas{display:block;image-rendering:pixelated}
.legend{display:flex;flex-wrap:wrap;gap:20px;margin:14px 0;font-size:14px}.swatch{display:inline-block;width:12px;height:12px;margin-right:5px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:9px;border-bottom:1px solid #304654;text-align:left}
#selection{padding:16px;background:#172a37;margin:18px 0;white-space:pre-wrap;line-height:1.5}small{color:#a4bdc9}
</style>
<h1>Shadowrun · city and tactical index</h1>
<p id="context"></p>
<p>This investigator snapshot keeps the city grid, exact positions and captured actors together.
Terrain colors distinguish source byte categories. Visibility and walkability remain unknown.
Selecting a cell shows its bounds and occupants; it does not choose a movement or teleport destination.</p>
<div class="tools"><label>Zoom <input id="zoom" type="range" min="10" max="40" value="16"></label>
<label><input id="regions" type="checkbox" checked> Region borders</label>
<label><input id="actors" type="checkbox" checked> Captured actors</label>
<button id="focus">Focus runner</button></div>
<div class="legend" id="legend"></div><div class="map" id="map"><canvas id="canvas"></canvas></div>
<div id="selection">Select a cell to inspect its exact interval.</div>
<h2>Actors and observation layers</h2><p>The runner uses the shared model's current position. Other actor positions and health bytes come from the recorded capture; their current positions, AI and line of sight remain unknown. This viewer is a passive snapshot.</p>
<table><thead><tr><th>Stable ID</th><th>Kind</th><th>Exact source pixels</th><th>Observed health byte</th><th>Visibility</th></tr></thead><tbody id="entities"></tbody></table>
<p><small id="identity"></small></p>
<script id="data" type="application/json">__CITY_DATA__</script>
<script>
'use strict';
const city=JSON.parse(document.getElementById('data').textContent),W=64,H=44;
const canvas=document.getElementById('canvas'),ctx=canvas.getContext('2d');
const colors=['#111b24','#345653','#8a6570','#c9a56a','#687cb3'];
const labels=['Outside field bounds','Raw 0','Raw 127','Other low code','High code'];
const text=(id,value)=>document.getElementById(id).textContent=value;
text('context',`Scene ${city.scene_id} · ${W} × ${H} cells · each cell 32 × 32 source pixels · Y increases downward`);
text('identity',`Source ${city.source_sha256} · snapshot revision ${city.revision}`);
for(let i=0;i<labels.length;i++){const item=document.createElement('span'),s=document.createElement('span');s.className='swatch';s.style.background=colors[i];item.append(s,document.createTextNode(labels[i]));document.getElementById('legend').append(item);}
for(const a of city.captured_entities){const tr=document.createElement('tr');for(const value of [a.id,a.kind,`${a.x/16}, ${a.y/16}`,a.hp_byte_4c,'unknown']){const td=document.createElement('td');td.textContent=String(value);tr.append(td);}document.getElementById('entities').append(tr);}
function draw(){const s=Number(document.getElementById('zoom').value);canvas.width=W*s;canvas.height=H*s;
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){ctx.fillStyle=colors[city.terrain_symbols[y*W+x]];ctx.fillRect(x*s,y*s,s,s);}
 ctx.strokeStyle='#ffffff60';ctx.lineWidth=1;if(document.getElementById('regions').checked){for(let x=0;x<=W;x+=8){ctx.beginPath();ctx.moveTo(x*s,0);ctx.lineTo(x*s,H*s);ctx.stroke();}for(let y=0;y<=H;y+=8){ctx.beginPath();ctx.moveTo(0,y*s);ctx.lineTo(W*s,y*s);ctx.stroke();}}
 if(document.getElementById('actors').checked)for(const a of city.captured_entities){ctx.beginPath();ctx.fillStyle='#f4c55a';ctx.arc(a.x/512*s,a.y/512*s,Math.max(3,s*.2),0,Math.PI*2);ctx.fill();}
 ctx.fillStyle='#ff7070';ctx.beginPath();ctx.arc(city.player.x/512*s,city.player.y/512*s,Math.max(4,s*.24),0,Math.PI*2);ctx.fill();
 ctx.strokeStyle='#e3f1ff';ctx.lineWidth=2;ctx.strokeRect(city.camera.x/512*s,city.camera.y/512*s,256/32*s,224/32*s);
}
for(const id of ['zoom','regions','actors'])document.getElementById(id).addEventListener('input',draw);
document.getElementById('focus').addEventListener('click',()=>{const s=Number(document.getElementById('zoom').value),map=document.getElementById('map');map.scrollTo({left:city.player.x/512*s-map.clientWidth/2,top:city.player.y/512*s-map.clientHeight/2,behavior:'smooth'});});
canvas.addEventListener('click',event=>{const r=canvas.getBoundingClientRect(),s=Number(document.getElementById('zoom').value),x=Math.floor((event.clientX-r.left)/s),y=Math.floor((event.clientY-r.top)/s);if(x<0||x>=W||y<0||y>=H)return;
 const actors=city.captured_entities.filter(a=>(a.x>>9)===x&&(a.y>>9)===y).map(a=>a.id);
 text('selection',`Cell (${x}, ${y}) · raw code ${city.terrain_codes[y*W+x]}\nSource-pixel bounds: X [${x*32}, ${(x+1)*32}), Y [${y*32}, ${(y+1)*32})\nFixed-point bounds: X [${x*512}, ${(x+1)*512}), Y [${y*512}, ${(y+1)*512})\nCaptured actors: ${actors.join(', ')||'none recorded in this cell'}\nNo execution coordinate has been selected. Visibility and walkability are unknown.`);
});draw();
</script></html>'''
