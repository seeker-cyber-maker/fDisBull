# SPDX-License-Identifier: GPL-2.0-or-later
# Reference-guided adaptation of FreeSynd dernc.cpp, including work credited to
# Stuart Binge (2005), Joost Peters (2005), Trent Waddington (2006).
# Full license: ../LICENSE-GPL-2.0.txt. No game data is distributed.
"""Bounded RNC1 decoder, reference-guided by FreeSynd dernc.cpp (GPL-2.0-or-later).
Reference: winterheart/freesynd b8c05e606d75fcd320ce02b584f4cc427799b110.
This is not claimed as independent original-binary recovery.
"""
import struct
CRC=[]
for i in range(256):
 v=i
 for _ in range(8):v=(v>>1)^ (0xa001 if v&1 else 0)
 CRC.append(v)
def crc16(data):
 c=0
 for b in data:c=(c>>8)^CRC[(c^b)&255]
 return c

def unpack(raw,max_output=16*1024*1024):
 if len(raw)<18 or raw[:4]!=b'RNC\x01':raise ValueError('not RNC1')
 outlen,packed,oc,pc,leeway,chunks=struct.unpack('>IIHHBB',raw[4:18])
 if not (0<outlen<=max_output) or packed!=len(raw)-18:raise ValueError('length/domain')
 data=raw[18:]
 if crc16(data)!=pc:raise ValueError('packed CRC')
 ptr=0;bits=int.from_bytes(data[:2],'little');count=16;out=bytearray();blocks=0
 def word(p):
  if p>len(data)+2:raise ValueError('bitstream beyond lookahead')
  return int.from_bytes(data[p:p+2],'little')
 def read(n):
  nonlocal ptr,bits,count
  v=bits&((1<<n)-1);bits>>=n;count-=n
  if count<16:
   ptr+=2;bits|=word(ptr)<<count;count+=16
  return v
 def table():
  n=read(5);lengths=[read(4) for _ in range(n)];code=0;t=[]
  for length in range(1,max(lengths,default=0)+1):
   for sym,ln in enumerate(lengths):
    if ln==length:
     rev=int(f'{code:0{length}b}'[::-1],2);t.append((length,rev,sym));code+=1
   code<<=1
  return t
 def value(t):
  for ln,code,sym in t:
   if bits&((1<<ln)-1)==code:
    read(ln)
    return sym if sym<2 else (1<<(sym-1))|read(sym-1)
  raise ValueError('no Huffman code')
 read(2)
 while len(out)<outlen:
  blocks+=1
  if blocks>255:raise ValueError('block limit')
  lit,dist,length=table(),table(),table();runs=read(16)
  if runs==0:raise ValueError('zero runs')
  for i in range(runs):
   n=value(lit)
   if (n and ptr+n>len(data)) or len(out)+n>outlen:raise ValueError('literal bound')
   if n:
    out.extend(data[ptr:ptr+n]);ptr+=n
    count-=16;bits&=(1<<count)-1;bits|=word(ptr)<<count;count+=16
   if i+1==runs:break
   off=value(dist)+1;n=value(length)+2
   if off>len(out) or len(out)+n>outlen:raise ValueError('backref bound')
   for _ in range(n):out.append(out[-off])
 if len(out)!=outlen or crc16(out)!=oc:raise ValueError('output length/CRC')
 return bytes(out),{'unpacked':outlen,'packed':packed,'packed_crc':pc,'unpacked_crc':oc,'blocks':blocks,'header_blocks':chunks,'leeway':leeway,'crc_verified':True}
