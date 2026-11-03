#!/usr/bin/env python3
"""Exercise Genesis VDP presentation writes against a host-side VRAM model.

The renderer source is captured and its MMIO assignments instrumented in a
private build only. This is not a Genesis hardware or native 68000 test.
"""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from check_genesis_game_renderer import HARNESS

PROLOGUE='''\nvoid test_ctrl16(unsigned short);\nvoid test_ctrl32(unsigned int);\nvoid test_data16(unsigned short);\nvoid test_data32(unsigned int);\n'''
TEST=r'''
static u8 vram[65536],expected_vram[65536],cram[128],expected_cram[128];static u16 vdp_address;static u8 vdp_cram,seen_increment;
extern const u8 genesis_chr[8192];
void genesis_renderer_init(void);
static unsigned int rng=0x921ca46du;
static u8 next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return (u8)rng;}
static void put(u8 *mem,u16 at,u16 v){mem[at]=(u8)(v>>8);mem[(u16)(at+1)]=(u8)v;}
void test_ctrl16(u16 v){if(v==0x8f02)seen_increment=1;}
void test_ctrl32(u32 v){vdp_cram=(u8)((v&0xc0000000u)==0xc0000000u);vdp_address=vdp_cram?0:(u16)(((v>>16)&0x3fff)|((v&3)<<14));}
void test_data16(u16 v){if(vdp_cram){put(cram,vdp_address,v);}else{put(vram,vdp_address,v);}vdp_address+=2;}
void test_data32(u32 v){test_data16((u16)(v>>16));test_data16((u16)v);}
void genesis_present(void);
int main(void){
 unsigned n,i,row,col,tile,bit;u16 at,attr;u8 sample,index,count,lo,hi;u32 pixels;
 static const u16 colors[16]={0x0000,0x0a40,0x0620,0x0eee,0x0000,0x0c40,0x0c86,0x0eee,0x0000,0x00ae,0x06ee,0x0eee,0x0000,0x000c,0x066e,0x0eee};
 memset(vram,0x5a,sizeof(vram));memset(expected_vram,0x5a,sizeof(expected_vram));
 for(tile=0;tile<512;tile++)for(row=0;row<8;row++){
  lo=genesis_chr[tile*16+row];hi=genesis_chr[tile*16+row+8];pixels=0;
  for(bit=0;bit<8;bit++)pixels=(pixels<<4)|(((lo>>(7-bit))&1))|(((hi>>(7-bit))&1)<<1);
  at=(u16)(tile*32+row*4);put(expected_vram,at,(u16)(pixels>>16));put(expected_vram,at+2,(u16)pixels);
 }
 for(i=0;i<64;i++)put(expected_cram,(u16)(i*2),((i&15)<4)?colors[(i>>4)*4+(i&3)]:0);
 genesis_renderer_init();
 if(!seen_increment || memcmp(vram,expected_vram,65536) || memcmp(cram,expected_cram,128)){puts("INIT FAIL");return 2;}
 for(n=0;n<1000;n++){
  for(i=0;i<65536;i++)vram[i]=expected_vram[i]=(u8)(i^n);
  for(i=0;i<256;i++){genesis_plane[i]=next();genesis_palettes[i]=next();}
  for(i=0;i<24;i++)genesis_hud[i]=next();
  for(i=0;i<252;i++)genesis_sprites[i]=next();
  count=(u8)(n%64);genesis_sprite_count=count;
  for(row=0;row<16;row++)for(col=0;col<16;col++){
   index=(u8)(row*16+col);sample=(u8)(((row&0xfe)+1)*16+(col&0xfe)+1);
   attr=((u16)(genesis_palettes[sample]&3)<<13)|genesis_plane[index];
   put(expected_vram,(u16)(0xc000+(12+row)*128+(12+col)*2),attr);
  }
  for(col=0;col<24;col++)put(expected_vram,(u16)(0xc000+8*128+(8+col)*2),genesis_hud[col]);
  if(!count)for(i=0;i<8;i++)expected_vram[0xd000+i]=0;
  for(i=0;i<count;i++){
   at=(u16)(i*4);put(expected_vram,0xd000+i*8,(u16)genesis_sprites[at+1]+128);
   put(expected_vram,0xd002+i*8,(i+1<count)?(u16)(i+1):0);
   put(expected_vram,0xd004+i*8,((u16)(genesis_sprites[at+3]&3)<<13)|(u16)(256+genesis_sprites[at+2]));
   put(expected_vram,0xd006+i*8,(u16)genesis_sprites[at]+160);
  }
  genesis_present();
  if(memcmp(vram,expected_vram,65536)){for(i=0;i<65536;i++)if(vram[i]!=expected_vram[i]){printf("FAIL %u address%u actual%u expected%u\n",n,i,vram[i],expected_vram[i]);break;}return 1;}
 }
 puts("PASS 1000");return 0;
}
'''
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--game-api',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve()
 if out.exists() or any((p/'.git').exists() for p in (out,*out.parents)):raise ValueError('choose fresh output outside Git')
 out.mkdir(parents=True);root=Path(__file__).resolve().parents[1];src=root/'src/fdisbull/game_sources/genesis_game_renderer.c';data=src.read_bytes();s=data.decode();counts={}
 for reg,fn in [('VDP_CONTROL16','test_ctrl16'),('VDP_CONTROL32','test_ctrl32'),('VDP_DATA16','test_data16'),('VDP_DATA32','test_data32')]:
  s,n=re.subn(r'\b'+reg+r'\s*=\s*([^;]+);',lambda m:fn+'('+m.group(1)+');',s);counts[reg]=n
 if any(n==0 for n in counts.values()):raise ValueError('missing VDP instrumentation target')
 s=s.replace('#include "game_api.h"','#include "game_api.h"'+PROLOGUE,1)
 header=a.game_api.read_text().replace('typedef unsigned long u32;','typedef unsigned int u32;').replace('typedef signed long i32;','typedef signed int i32;')
 (out/'game_api.h').write_text(header);(out/'instrumented.c').write_text(s);(out/'harness.c').write_text(HARNESS+TEST)
 arrays={'genesis_projection':65536,'genesis_terrain':40320,'genesis_object_projection':65536,'genesis_raft_projection':65536,'genesis_ending_projection':12288,'genesis_ending_ids':48,'genesis_tile_palette':35,'genesis_chr':8192}
 (out/'assets.c').write_text('\n'.join(('const unsigned char genesis_chr[8192]={'+','.join(str((i*37+11)&255) for i in range(8192))+'};') if k=='genesis_chr' else f'const unsigned char {k}[{v}]={{0}};' for k,v in arrays.items()))
 build=subprocess.run(['cc','-std=c99','-O2','-Wno-unknown-pragmas','-I',str(out),'-o',str(out/'check'),str(out/'instrumented.c'),str(out/'harness.c'),str(out/'assets.c')],capture_output=True,text=True,timeout=60);(out/'build.txt').write_text(build.stdout+build.stderr)
 if build.returncode:raise RuntimeError(build.stderr)
 run=subprocess.run([str(out/'check')],capture_output=True,text=True,timeout=60);(out/'run.txt').write_text(run.stdout+run.stderr)
 if run.returncode or run.stdout.strip()!='PASS 1000':raise RuntimeError(run.stdout+run.stderr)
 if src.read_bytes()!=data:raise RuntimeError('renderer changed during check')
 sha=lambda b:hashlib.sha256(b).hexdigest();result={'passed':True,'cases':1000,'renderer_sha256':sha(data),'instrumented_sha256':sha(s.encode()),'harness_sha256':sha((HARNESS+TEST).encode()),'program_sha256':sha((out/'check').read_bytes()),'instrumented_assignments':counts,'coverage':'authored 512-tile 2bpp-to-4bpp conversion, palette and increment setup; all 64 sprite counts, name table terrain/attribute mapping, HUD, sprite links and coordinates; complete 64 KiB VRAM compared','limits':'host MMIO simulation with authored CHR, not native 68000 or Genesis VDP timing/visual output'}
 (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
