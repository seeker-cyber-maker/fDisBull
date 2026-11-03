from pathlib import Path
import re
src=Path('../source/attt.asm').read_text()
lines=src.splitlines()
out=['; Mechanical TASM-to-NASM COM adaptation. See README.','bits 16','org 100h','jmp start']
vars={}
for line in lines:
 m=re.match(r'^(\w+)\s+d([bw])\s+(.+)$',line,re.I)
 if m: vars[m[1]]=m[2].lower()
for line in lines:
 s=line.strip()
 if re.match(r'^(assume |program segment|\.386|dstack segment|db\s+4\s+dup|dstack ends|program ends|end start)',s,re.I): continue
 m=re.match(r'^(\w+)\s+proc\s*$',s,re.I)
 if m: out.append(m[1]+':'); continue
 if re.match(r'^\w+\s+endp\s*$',s,re.I): continue
 if re.match(r'^\w+\s+d[bw]\s+',s,re.I): out.append(line); continue
 for var,sz in vars.items():
  line=re.sub(r'\b'+var+r'\b', '['+var+']',line)
 # NASM needs explicit size when memory operand is followed by immediate
 for var,sz in vars.items():
  line=re.sub(r'(?i)(\b(?:mov|cmp|inc|dec)\s+)\['+var+r'\](?=\s*(?:,\s*(?:\d|\x27)|$))',r'\1'+('byte' if sz=='b' else 'word')+' ['+var+']',line)
 out.append(line)
Path('attt-nasm.asm').write_text('\n'.join(out)+'\n')
