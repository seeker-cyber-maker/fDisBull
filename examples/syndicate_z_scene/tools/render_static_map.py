"""Render the semantic survey as a precise SVG; no game artwork is used."""
import json,html
from pathlib import Path
import sys
p=Path(sys.argv[1]);m=json.loads((p/'map-model.json').read_text());scene=m['scene'];L=next(x for x in m['layers'] if x['z']==2)
x0,y0,x1,y1=40,20,100,60;scale=17;left=65;top=140;width=1450;height=960
parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
'<rect width="100%" height="100%" fill="#101820"/>',
'<g font-family="DejaVu Sans, sans-serif" fill="#e8eff4">',
'<text x="48" y="45" font-size="27" font-weight="bold">Syndicate · Mission 1 spatial survey</text>',
'<text x="48" y="78" font-size="17">Original-game snapshot | world coordinates | ground layer z=2</text>',
'<text x="48" y="108" font-size="14" fill="#becdd7">Conditional surfaces and routes. Doors, collision footprints and walking are not yet qualified.</text>']
for y in range(y0,y1):
 for x in range(x0,x1):
  color='#23303a'
  if L['candidate'][y][x]:color='#8b754c' if L['support'][y][x] in [6,7,8,9,11,14,15] else '#46674f'
  parts.append(f'<rect x="{left+(x-x0)*scale}" y="{top+(y-y0)*scale}" width="{scale-.4}" height="{scale-.4}" fill="{color}"/>')
for x in range(40,101,5):parts.append(f'<text x="{left+(x-x0)*scale}" y="{top-14}" font-size="12" text-anchor="middle">{x}</text>')
for y in range(20,61,5):parts.append(f'<text x="{left-12}" y="{top+(y-y0)*scale+5}" font-size="12" text-anchor="end">{y}</text>')
def xy(p):return left+(p[0]-x0)*scale,top+(p[1]-y0)*scale
path=m['candidate_routes']['civilian']['path'];pts=' '.join(f'{xy([q[0]+.5,q[1]+.5])[0]},{xy([q[0]+.5,q[1]+.5])[1]}' for q in path)
parts.append(f'<polyline points="{pts}" stroke="#f5d16b" fill="none" stroke-width="2.5" stroke-dasharray="5 4"/>')
for w in m['waypoints']:
 if w['position'][2]!=2:continue
 x,y=xy(w['position']);parts.append(f'<circle cx="{x}" cy="{y}" r="6" fill="none" stroke="#a8dfe9" stroke-width="2"/>')
symbols={'agent':'A','civilian':'C','police':'P','guard':'G','vehicle':'V','door':'D'}
for e in scene['entities']:
 mark='★' if e['mission_critical'] else symbols.get(e['category']);x,y,z=e['position']
 if not mark or int(z)!=2:continue
 xx,yy=xy([x,y]);color='#f2b45f' if e['mission_critical'] else '#7adbe7' if e['category']=='agent' else '#f19a97' if e['category']=='guard' else '#f0eff0'
 parts.append(f'<circle cx="{xx}" cy="{yy}" r="8" fill="#101820"/><text x="{xx}" y="{yy+5}" font-size="16" font-weight="bold" text-anchor="middle" fill="{color}">{mark}</text>')
text=[('Snapshot census',22),('Team agents: 4',16),('Civilians: 2',16),('Police: 0 registered',16),('Guards: 4',16),('Cars: 1',16),('Doors: 4',16),('',14),('★ Mission civilian #8',18),('(64.250, 30.750, z=2)',15),('Objective type: 2',15),('',14),('Car #0',18),('(60.531, 35.719, z=2)',15),('Boarding/gate: unknown',15),('',14),('A  Team agent',16),('C  Other civilian',16),('G  Guard',16),('V  Vehicle',16),('D  Door / portal candidate',16),('○  Diagnostic waypoint',16),('',14),('Dashed target route:',16),('38 candidate grid steps',16),('passes door #3',16),('not a verified walk',16)]
y=top+15
for t,size in text:
 parts.append(f'<text x="1120" y="{y}" font-size="{size}">{html.escape(t)}</text>');y+=25
parts += ['<text x="48" y="865" font-size="16">The same x/y can describe different floors. The interactive HTML includes z=1..11 and a full-map view.</text>',
'<text x="48" y="895" font-size="15" fill="#becdd7">Green/brown: conditional flat support; dark: excluded or unresolved. Actor counts are not line-of-sight or alive-count proofs.</text>',
'<text x="48" y="922" font-size="15" fill="#becdd7">Teleports were checked in the original DOSBox world. Placement is not evidence that a route, staircase or gate can be crossed.</text>','</g></svg>']
(p/'mission-map.svg').write_text('\n'.join(parts))
