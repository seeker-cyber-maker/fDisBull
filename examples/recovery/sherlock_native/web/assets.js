/* Authored browser adapters for the already recovered SHI and puzzle-table
 * contracts. Files are supplied by the player and stay in this browser. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SherlockAssets = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const PALETTE = [[0,0,0],[85,85,85],[170,85,0],[255,0,0],
    [255,170,0],[255,255,0],[0,255,0],[0,255,170],
    [0,170,255],[0,0,255],[170,0,170],[170,85,255],
    [255,0,170],[255,170,170],[170,170,170],[255,255,255]];
  const HEADER = [4,0,1,0,32,0,32,0];
  function bytes(input) {
    if (input instanceof Uint8Array) return input;
    if (input instanceof ArrayBuffer) return new Uint8Array(input);
    throw new TypeError('Expected an ArrayBuffer or Uint8Array.');
  }
  function decodeSHI(input) {
    const b = bytes(input);
    if (b.length !== 23920) throw new Error('SHI must contain exactly 46 images (23,920 bytes).');
    const pixels = new Uint8Array(46 * 1024);
    for (let image=0; image<46; image++) {
      const base=image*520;
      for (let n=0;n<8;n++) if(b[base+n]!==HEADER[n])
        throw new Error('Unsupported SHI header in image '+image+'.');
      for(let y=0;y<32;y++) for(let x=0;x<32;x++) {
        let value=0;
        for(let plane=0;plane<4;plane++)
          value|=((b[base+8+y*16+plane*4+(x>>3)]>>(7-(x&7)))&1)<<plane;
        pixels[image*1024+y*32+x]=value;
      }
    }
    return {pixels, width:32, height:32, count:46, palette:PALETTE.map(x=>x.slice())};
  }
  function encodeSHI(input) {
    const p = input && input.pixels ? input.pixels : input;
    if (!p || p.length!==46*1024) throw new Error('Expected all 46 SHI images.');
    for(const value of p) if(!Number.isInteger(value)||value<0||value>15)
      throw new Error('SHI pixels must be palette indices 0 through 15.');
    const b=new Uint8Array(23920);
    for(let image=0;image<46;image++) {
      const base=image*520; b.set(HEADER,base);
      for(let y=0;y<32;y++) for(let x=0;x<32;x++) for(let plane=0;plane<4;plane++)
        b[base+8+y*16+plane*4+(x>>3)]|=((p[image*1024+y*32+x]>>plane)&1)<<(7-(x&7));
    }
    return b;
  }
  function loadOriginalTable(input) {
    const source=bytes(input);
    const start=16+65537*4;
    if(source.length<start||source.length>32*1024*1024)
      throw new Error('The numbered-puzzle table has an invalid size.');
    // Own the admitted bytes. Mutating the caller's input cannot change a table
    // after its index has been validated.
    const b=new Uint8Array(source), d=new DataView(b.buffer);
    const magic=[83,72,82,76,49,53,48,0];
    if(magic.some((v,i)=>b[i]!==v)||d.getUint32(8,true)!==1||d.getUint32(12,true)!==65536)
      throw new Error('Expected the Sherlock 1.50 table, format 1.');
    let previous=0;
    for(let i=0;i<=65536;i++) {
      const offset=d.getUint32(16+i*4,true);
      if((i===0&&offset!==0)||offset<previous||offset>b.length-start||
         (i===65536&&offset!==b.length-start)) throw new Error('Invalid puzzle-table index.');
      previous=offset;
    }
    return Object.freeze({count:65536, format:1, size:b.length, getPuzzle(number) {
      if(!Number.isInteger(number)||number<0||number>65535) throw new Error('Original number must be 0 through 65535.');
      let p=start+d.getUint32(16+number*4,true);
      const end=start+d.getUint32(20+number*4,true);
      if(end-p<38) throw new Error('Incomplete puzzle record.');
      const answer=Array.from({length:6},()=>Array(6));
      for(let row=0;row<6;row++) {
        let seen=0;
        for(let col=0;col<6;col++) {
          const item=b[p++];
          if(item>=6||(seen&(1<<item))) throw new Error('Invalid stored puzzle permutation.');
          answer[row][col]=item;seen|=1<<item;
        }
      }
      const given=Array.from({length:6},()=>Array(6).fill(-1));
      let count=b[p++];
      if(count>36||end-p<count*2+1) throw new Error('Invalid given-square record.');
      for(let i=0;i<count;i++) {
        const cell=b[p++],item=b[p++],r=Math.floor(cell/6),c=cell%6;
        if(cell>=36||item>=6||given[r][c]!==-1||answer[r][c]!==item)
          throw new Error('Invalid given square.');
        given[r][c]=item;
      }
      count=b[p++];
      if(count>39||end-p!==count*5) throw new Error('Invalid clue record.');
      const clues=[], original_slot=[];let previousSlot=35;
      for(let i=0;i<count;i++) {
        const type=b[p++],a=b[p++],bb=b[p++],c=b[p++],slot=b[p++];
        if(type>7||a>=36||(type!==7&&bb>=36)||((type===5||type===6)&&c>=36)||
          (c>=36&&c!==255)||slot<36||slot>=75||slot<=previousSlot)
          throw new Error('Invalid clue object or display slot.');
        clues.push({type,a,b:bb,c});original_slot.push(slot);previousSlot=slot;
      }
      // The hidden table answer is deliberately discarded at this boundary.
      return {number,given,clues,clue_count:count,original_slot,
        source:{kind:'original',edition:'Sherlock 1.50 UK',table_format:1,number}};
    }});
  }
  /* JSON.parse alone discards duplicate keys. This small, bounded parser keeps
   * the CLI's unambiguous integer/duplicate-key boundary for imported evidence. */
  function parseJSON(text) {
    if(typeof text!=='string'||text.length>1024*1024) throw new Error('JSON input is limited to 1 MiB.');
    let i=0,nodes=0;
    function bad(message){throw new Error(message+' at character '+i+'.');}
    function ws(){while(i<text.length&&/[\x20\t\r\n]/.test(text[i]))i++;}
    function string() {
      const start=i++;
      while(i<text.length){
        if(text[i]==='"'){
          i++;let value;try{value=JSON.parse(text.slice(start,i));}catch(_){bad('Invalid JSON string');}
          if(value.includes('\u0000'))bad('NUL is not permitted in JSON strings');
          return value;
        }
        if(text[i]==='\\'){i+=2;continue;}
        if(text.charCodeAt(i)<32)bad('Unescaped control character');
        i++;
      }
      bad('Unterminated string');
    }
    function value(depth){
      if(depth>64||++nodes>30000)bad('JSON structure is too large');
      ws();const ch=text[i];
      if(ch==='"')return string();
      if(ch==='{'||ch==='['){
        const object=ch==='{',out=object?{}:[],keys=new Set();i++;ws();
        if(text[i]===(object?'}':']')){i++;return out;}
        for(;;){
          if(object){
            if(text[i]!=='"')bad('Expected an object key');
            const key=string();if(keys.has(key))bad('Duplicate JSON key '+key);
            if(key==='__proto__'||key==='prototype'||key==='constructor')bad('Unsupported object key');
            keys.add(key);ws();if(text[i++]!==':')bad('Expected a colon');
            out[key]=value(depth+1);
          }else out.push(value(depth+1));
          ws();if(text[i]===(object?'}':']')){i++;return out;}
          if(text[i++]!==',')bad('Expected a comma');ws();
        }
      }
      for(const [token,result] of [['true',true],['false',false],['null',null]])
        if(text.slice(i,i+token.length)===token){i+=token.length;return result;}
      const match=text.slice(i).match(/^-?(?:0|[1-9][0-9]*)/);
      if(match){
        i+=match[0].length;
        if(match[0]==='-0'||/[.eE0-9]/.test(text[i]||' '))bad('Use canonical integer JSON numbers');
        const result=Number(match[0]);if(!Number.isSafeInteger(result))bad('Large integers must be decimal strings');
        return result;
      }
      bad('Expected a JSON value');
    }
    const out=value(0);ws();if(i!==text.length)bad('Trailing JSON content');return out;
  }
  return {PALETTE,decodeSHI,encodeSHI,loadOriginalTable,parseJSON};
});
