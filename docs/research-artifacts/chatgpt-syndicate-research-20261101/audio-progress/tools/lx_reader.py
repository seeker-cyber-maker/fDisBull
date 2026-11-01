"""Pinned one-object LX research reader, not general LX support."""
import struct
def lx(raw,base=None):
 h=struct.unpack_from('<I',raw,0x3c)[0];u=lambda o:struct.unpack_from('<I',raw,h+o)[0]
 assert raw[h:h+4]==b'LX\0\0' and u(68)==1 and u(40)==4096
 size,pref,flags,mapstart,pages,_=struct.unpack_from('<6I',raw,h+u(64));assert mapstart==1 and pages==u(20) and size<1048576
 if base is None:base=pref
 image=bytearray(size)
 for p in range(pages):
  off,n,fl=struct.unpack_from('<IHH',raw,h+u(72)+p*8);assert fl==0 and 0<n<=4096
  start=u(128)+(off<<u(44));assert start+n<=len(raw);count=min(n,size-p*4096);image[p*4096:p*4096+count]=raw[start:start+count]
 offsets=struct.unpack_from('<'+'I'*(pages+1),raw,h+u(104));assert offsets[0]==0 and list(offsets)==sorted(offsets)
 fixbase=h+u(108);fixes=[];writes={}
 for p in range(pages):
  pos=fixbase+offsets[p];end=fixbase+offsets[p+1];assert end<=len(raw)
  while pos<end:
   sf,tf,local=struct.unpack_from('<BBh',raw,pos);pos+=4;assert sf==7 and tf&~0x50==0
   ordsize=2 if tf&0x40 else 1;ordinal=int.from_bytes(raw[pos:pos+ordsize],'little');pos+=ordsize
   offsize=4 if tf&0x10 else 2;target=int.from_bytes(raw[pos:pos+offsize],'little');pos+=offsize
   assert pos<=end and ordinal==1 and 0<=target<=size and -3<=local<4096
   loc=p*4096+local;assert 0<=loc<=size-4
   if loc in writes:assert writes[loc]==base+target
   writes[loc]=base+target;fixes.append({'source':loc,'target_offset':target})
 for loc,val in writes.items():struct.pack_into('<I',image,loc,val)
 table=struct.unpack_from('<I',image)[0]-base;assert 0<=table<len(image)-8
 entries={};q=table
 while True:
  key,ptr=struct.unpack_from('<II',image,q);q+=8
  if key==0xffffffff:break
  assert len(entries)<256 and base<=ptr<base+size;entries[key]=ptr-base
 return image,entries,fixes
