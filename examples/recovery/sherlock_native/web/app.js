/* Browser presentation and host adapters. All game mutations go through the
 * portable state module; the view never substitutes the stored answer. */
(function () {
  'use strict';
  const root=document.getElementById('sherlock-app');
  if(!root)return;
  const C=globalThis.SherlockCore,S=globalThis.SherlockState,P=globalThis.SherlockProof,A=globalThis.SherlockAssets,V=globalThis.SherlockProtocol;
  const $=id=>root.querySelector('#'+id);
  if(!C||!S||!P||!A||!V){$('sh-notice').textContent='The game engine did not load. Reopen the complete browser package.';return;}
  const ROWS=['Faces','Houses','Letters','Fruit','Vehicles','Dice'];
  const SYMBOLS=[['🙂','😎','👩','👨','🧑','🧔'],['🏠','🏡','🏢','🏰','⛺','🏛'],['A','B','C','D','E','F'],['🍐','🍒','🍎','🍓','🍊','🍌'],['⛵','✈','🚗','🚂','🚲','🚀'],['⚀','⚁','⚂','⚃','⚄','⚅']];
  const TITLES=['Same column','Different columns','Next to each other','Not neighbors','Left of','Between two neighbors','Not in the middle','Reference picture'];
  const RULES=['A and B belong in the same column.','A and B belong in different columns.','A and B occupy neighboring columns, in either order.','A and B are not in neighboring columns. This clue allows them to share a column.','A is somewhere to the left of B. They do not have to be neighbors.','B is directly between A and C, next to both. The order can be A–B–C or C–B–A.','A and C are exactly two columns apart, in either order. B is not in their middle column.','A is a reference picture. This card adds no relationship constraint.'];
  const SAVE_KEY='sherlock-replica-browser-v1';
  let game=null,art=null,artName='Built-in symbols',table=null,tableName='',mode='remove',bank=0;
  let selectedCell=[0,0],selectedClue=-1,pendingProof=null,lastProof=null,hintClock=null;
  let lastSample=performance.now(),fraction=0,history=[],dialogKind=null,whyPage=0,whyOpen=false;
  let provenance='generated-v1',busy=false,lastOutcome=0,lastSaveId='',lastAutoSave=0;
  const canonicalCache=new Map();
  function esc(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function json(value){return JSON.stringify(value,(_,v)=>typeof v==='bigint'?v.toString():v,2);}
  function plain(value){return JSON.parse(json(value));}
  function notice(message,kind=''){const el=$('sh-notice');el.textContent=message;el.className='sh-notice'+(kind?' sh-'+kind:'');}
  function diagnose(value){$('sh-diagnostic').textContent=typeof value==='string'?value:json(value);}
  function on(id,event,fn){$(id).addEventListener(event,e=>{try{Promise.resolve(fn(e)).catch(error=>notice(error.message,'error'));}catch(error){notice(error.message,'error');}});}
  function source(){return game&&game.puzzle.source;}
  function fingerprint(puzzle){return C.publicFingerprint(puzzle);}
  function decorate(puzzle){
    const challenge=C.toChallenge(puzzle);
    puzzle.challenge_id=challenge.challenge_id;puzzle.public_fingerprint=challenge.public_fingerprint;
    return puzzle;
  }
  function objectHTML(id,extra=''){
    const row=Math.floor(id/6),item=id%6,code=String.fromCharCode(65+row)+(item+1);
    if(id<0||id>=36)return '';
    const label=ROWS[row]+' '+(item+1)+' ('+code+')';
    return '<span class="sh-object '+extra+'" aria-label="'+esc(label)+'">'+
      (art?'<canvas data-art="'+id+'" width="32" height="32" aria-hidden="true"></canvas>':'<span class="sh-symbol" aria-hidden="true">'+esc(SYMBOLS[row][item])+'</span><span class="sh-object-code" aria-hidden="true">'+code+'</span>')+'</span>';
  }
  function drawImages(container=root){
    if(!art)return;
    for(const canvas of container.querySelectorAll('canvas[data-art]')){
      const id=Number(canvas.dataset.art),ctx=canvas.getContext('2d');if(!ctx)continue;
      const data=ctx.createImageData(32,32);
      for(let i=0;i<1024;i++){const rgb=A.PALETTE[art.pixels[id*1024+i]];data.data[i*4]=rgb[0];data.data[i*4+1]=rgb[1];data.data[i*4+2]=rgb[2];data.data[i*4+3]=255;}
      ctx.putImageData(data,0,0);
    }
    for(const canvas of container.querySelectorAll('canvas[data-clue-art]')){
      const layout=clueLayout(Number(canvas.dataset.clueArt)),ctx=canvas.getContext('2d');if(!ctx)continue;
      const indices=new Uint8Array(layout.width*layout.height);
      for(let part=0;part<layout.tiles.length;part++){
        const left=layout.horizontal?part*32:0,top=layout.horizontal?0:part*32,id=layout.tiles[part];
        for(let y=0;y<32;y++)for(let x=0;x<32;x++)indices[(top+y)*layout.width+left+x]=art.pixels[id*1024+y*32+x];
      }
      // SHI overlays operate on palette indices: (picture AND mask) OR ink.
      // Alpha blending the marker images would change the original pixels.
      for(const [left,top,mask,ink] of layout.overlays){
        for(let y=0;y<32;y++)for(let x=0;x<32;x++){
          const offset=(top+y)*layout.width+left+x,pixel=y*32+x;
          indices[offset]=((indices[offset]&art.pixels[mask*1024+pixel])|art.pixels[ink*1024+pixel])&15;
        }
      }
      const data=ctx.createImageData(layout.width,layout.height);
      for(let i=0;i<indices.length;i++){const rgb=A.PALETTE[indices[i]];data.data[i*4]=rgb[0];data.data[i*4+1]=rgb[1];data.data[i*4+2]=rgb[2];data.data[i*4+3]=255;}
      ctx.putImageData(data,0,0);
    }
  }
  function clueLayout(index){
    // Keep the original card compositor (app/SHClueImages.m) in both banks and
    // Show why. Reference-only cards inherit orientation from their source slot.
    const clue=game.puzzle.clues[index],horizontal=S.puzzleClueGroup(game.puzzle,index)===1;
    const tiles=[clue.a,clue.b,clue.c],overlays=[];
    if(clue.type===2||clue.type===3)tiles[2]=clue.a;
    if(clue.type===4){tiles[1]=45;tiles[2]=clue.b;}
    if(clue.type===7)tiles[1]=tiles[2]=36;
    if(clue.type===5||clue.type===6)for(let part=0;part<3;part++)overlays.push([part*32,0,39+part*2,40+part*2]);
    if(clue.type===1)overlays.push([0,16,37,38]);
    if(clue.type===3||clue.type===6)overlays.push([32,0,37,38]);
    return {clue,horizontal,tiles:tiles.slice(0,horizontal?3:2),overlays,width:horizontal?96:32,height:horizontal?32:64};
  }
  function pictures(index){
    const layout=clueLayout(index),clue=layout.clue;
    const labels=layout.tiles.filter(id=>id<36).map(id=>ROWS[Math.floor(id/6)]+' '+(id%6+1)).join(', ');
    let html='<span class="sh-clue-pictures '+(layout.horizontal?'sh-horizontal':'sh-vertical')+'" role="img" aria-label="'+esc(TITLES[clue.type]+': '+labels+'. '+RULES[clue.type])+'">';
    if(art)html+='<canvas data-clue-art="'+index+'" width="'+layout.width+'" height="'+layout.height+'" aria-hidden="true"></canvas>';
    else {
      html+=layout.tiles.map(id=>id<36?objectHTML(id):'<span class="sh-object sh-clue-filler" aria-hidden="true">'+(id===45?'•••':'')+'</span>').join('');
      if(clue.type===5||clue.type===6)html+='<span class="sh-clue-arrow" aria-hidden="true"></span>';
      if(clue.type===1||clue.type===3||clue.type===6)html+='<span class="sh-clue-not" aria-hidden="true"></span>';
    }
    return html+'</span>';
  }
  function clockText(value){
    let seconds=BigInt(value)/1000n;const h=seconds/3600n,m=(seconds/60n)%60n,s=seconds%60n;
    return(h?h.toString()+':':'')+m.toString().padStart(2,'0')+':'+s.toString().padStart(2,'0');
  }
  function sampleClock(){
    const now=performance.now(),total=Math.max(0,now-lastSample)+fraction,ms=Math.floor(total);lastSample=now;fraction=total-ms;
    if(game&&ms)S.tick(game,ms);
  }
  function resetClockSample(){lastSample=performance.now();fraction=0;}
  function log(action,details={}){
    history.push({action,...plain(details),elapsed_ms:game.elapsed_ms.toString()});if(history.length>1000)history.shift();
  }
  function updateClock(){
    if(!game)return;
    $('sh-clock').textContent=clockText(game.hint_pending&&hintClock!==null?hintClock:S.displayTimeMs(game));
    $('sh-clock').setAttribute('aria-label',(game.limit_ms?'Time remaining ':'Elapsed time ')+$('sh-clock').textContent);
    const words=['Playing','Solved','Check answer','Time expired','Quit'];$('sh-outcome').textContent=game.paused?'Paused':words[game.outcome];
    $('sh-progress').textContent=game.board.chosen.flat().filter(x=>x>=0).length+' / 36';
  }
  function renderBoard(){
    let html='<span aria-hidden="true"></span>'+Array.from({length:6},(_,i)=>'<span class="sh-col-label">'+(i+1)+'</span>').join('');
    for(let r=0;r<6;r++){
      html+='<span class="sh-row-label">'+ROWS[r]+'</span>';
      for(let c=0;c<6;c++){
        const mask=game.board.candidates[r][c],chosen=game.board.chosen[r][c],fixed=game.fixed[r][c];
        const selected=selectedCell[0]===r&&selectedCell[1]===c;
        const hint=game.hint_pending&&game.pending_hint.row===r&&game.pending_hint.column===c;
        html+='<div class="sh-cell'+(selected?' sh-selected':'')+(fixed?' sh-fixed':'')+(!mask?' sh-empty':'')+(hint?' sh-hint-target':'')+'" data-cell="'+r+','+c+'" role="group" aria-label="'+ROWS[r]+', column '+(c+1)+(fixed?', given':'')+'">';
        if(chosen>=0)html+='<button type="button" class="sh-chosen" data-candidate="'+r+','+c+','+chosen+'" data-focus="cell-'+r+'-'+c+'-'+chosen+'" aria-label="'+ROWS[r]+' '+(chosen+1)+', column '+(c+1)+', '+(fixed?'given':'chosen')+'" '+(fixed?'disabled':'')+'>'+objectHTML(r*6+chosen)+'</button>';
        else {
          html+='<div class="sh-candidates">';
          for(let item=0;item<6;item++)html+='<button type="button" class="sh-candidate'+(mask&(1<<item)?'':' sh-removed')+'" data-candidate="'+r+','+c+','+item+'" data-focus="cell-'+r+'-'+c+'-'+item+'" aria-label="'+ROWS[r]+' '+(item+1)+', column '+(c+1)+', '+(mask&(1<<item)?'possible':'eliminated')+'">'+objectHTML(r*6+item)+'</button>';
          html+='</div>';
        }
        html+='<button type="button" class="sh-mobile-select" data-select-cell="'+r+','+c+'" aria-label="Select '+ROWS[r]+', column '+(c+1)+'"></button></div>';
      }
    }
    $('sh-board').innerHTML=html;
    $('sh-pause-cover').hidden=!game.paused;
    for(const selector of ['.sh-board-pane','.sh-clue-pane']){const pane=root.querySelector(selector);pane.style.visibility=game.paused?'hidden':'';pane.inert=!!game.paused;}
    $('sh-agent-panel').hidden=!!game.paused;
    const [r,c]=selectedCell,mask=game.board.candidates[r][c];
    $('sh-cell-label').textContent=ROWS[r]+' · column '+(c+1)+(game.fixed[r][c]?' · given':'');
    $('sh-cell-picker').innerHTML=Array.from({length:6},(_,item)=>'<button type="button" class="'+(mask&(1<<item)?'':'sh-removed ')+(game.board.chosen[r][c]===item?'sh-picked':'')+'" data-candidate="'+r+','+c+','+item+'" data-focus="picker-'+item+'" aria-label="'+mode+' '+ROWS[r]+' '+(item+1)+' in column '+(c+1)+'" '+(game.fixed[r][c]?'disabled':'')+'>'+objectHTML(r*6+item)+'</button>').join('');
  }
  function renderClues(){
    let html='';
    for(let group=0;group<2;group++){
      const cap=group?21:18,slots=game.board.clue_slots[bank][group].slice(0,cap);
      // Empty slots remain visible through the final occupied position so card
      // organization and the hint selector's order are inspectable.
      let last=slots.length-1;while(last>=0&&slots[last]<0)last--;
      if(last<0)continue;
      html+='<span class="sh-clue-separator">'+(group?'Horizontal cards':'Vertical cards')+'</span>';
      for(let slot=0;slot<=last;slot++){
        const index=slots[slot];
        if(index<0){html+='<div class="sh-clue-card sh-blank" aria-label="Empty slot '+(slot+1)+'"><span class="sh-clue-caption">'+(slot+1)+'</span></div>';continue;}
        const clue=game.puzzle.clues[index];
        html+='<button type="button" class="sh-clue-card'+(selectedClue===index?' sh-active':'')+'" data-clue="'+index+'" data-focus="clue-'+index+'" aria-label="Clue '+(index+1)+', '+TITLES[clue.type]+', slot '+(slot+1)+'">'+pictures(index)+'<span class="sh-clue-caption">'+(index+1)+' · '+TITLES[clue.type]+'</span></button>';
      }
    }
    $('sh-clues').innerHTML=html||'<p class="sh-instruction">This clue bank is empty.</p>';
    $('sh-game-bank').setAttribute('aria-pressed',String(bank===0));$('sh-other-bank').setAttribute('aria-pressed',String(bank===1));
    const clue=game.puzzle.clues[selectedClue];$('sh-inspector').hidden=!clue||!!game.paused;
    if(clue){
      $('sh-clue-title').textContent='Clue '+(selectedClue+1)+' · '+TITLES[clue.type];
      $('sh-clue-rule').textContent=RULES[clue.type];
      const location=S.clueLocation(game,selectedClue),cap=S.puzzleClueGroup(game.puzzle,selectedClue)?21:18;
      $('sh-slot').innerHTML=Array.from({length:cap},(_,i)=>'<option value="'+i+'" '+(location&&location.slot===i?'selected':'')+'>'+(i+1)+'</option>').join('');
      $('sh-archive').textContent=location&&location.bank===1?'Return to game bank':'Move to other bank';
    }
  }
  function render(){
    if(!game)return;
    const focus=document.activeElement&&document.activeElement.dataset&&document.activeElement.dataset.focus;
    const src=source();
    $('sh-identity').textContent=src&&src.kind==='original'?'Original puzzle '+src.number:'Generated seed '+(src?src.seed:'?');
    $('sh-provenance').textContent=(provenance==='generated-v1'?'Unique · generator v1':provenance==='local-original-table'?'Original table · loaded locally':'Imported public constraints')+' · '+fingerprint(game.puzzle).slice(0,8);
    renderBoard();renderClues();updateClock();drawImages();
    root.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===mode)));
    const locked=busy||!!game.hint_pending||game.outcome!==0,editingLocked=locked||!!game.paused;
    for(const id of ['sh-hint','sh-archive','sh-move','sh-game-bank','sh-other-bank'])$(id).disabled=editingLocked;
    $('sh-undo').disabled=editingLocked||!game.undo_count;
    $('sh-pause').disabled=locked;$('sh-pause').textContent=game.paused?'Resume':'Pause';
    for(const id of ['sh-new','sh-random','sh-restart','sh-json-file','sh-load-json-text'])$(id).disabled=busy||!!game.hint_pending;
    $('sh-mode-description').textContent=mode==='remove'?'Eliminate pictures that cannot belong in this column. Right-click chooses; Shift-click restores.':mode==='choose'?'Choose a picture for this cell. It is removed from the other cells in its row.':'Restore an eliminated picture. Earlier eliminations elsewhere are left as they are.';
    if(focus){const target=root.querySelector('[data-focus="'+focus+'"]');if(target)target.focus({preventScroll:true});}
    if(game.outcome!==lastOutcome){lastOutcome=game.outcome;if(game.outcome)announceOutcome();}
  }
  function session(){return {format:'sherlock-browser-session-1',saved_at:new Date().toISOString(),game:S.exportGame(game),ui:{mode,bank,selected_cell:selectedCell.slice(),hint_display_ms:game.hint_pending&&hintClock!==null?hintClock.toString():null},art_name:artName};}
  function persist(){
    if(!game)return;
    const saved=session(),id=saved.saved_at+'-'+Math.random().toString(36).slice(2);lastSaveId=id;
    let local=false,host=false;
    try{localStorage.setItem(SAVE_KEY,JSON.stringify(saved));local=true;}catch(_){/* Sandboxed embeds may deny local storage. */}
    const state={format:'sherlock-space-state-1',revision:id,session:saved};
    if(globalThis.openai&&typeof globalThis.openai.setWidgetState==='function'&&new TextEncoder().encode(JSON.stringify(state)).length<=16384){
      try{Promise.resolve(globalThis.openai.setWidgetState(state)).catch(()=>{$('sh-save-status').textContent=local?'Progress saved in this browser.':'Use Save game to keep a JSON copy.';});host=true;}catch(_){}
    }
    $('sh-save-status').textContent=host?'Progress saved in this Space.':local?'Progress saved in this browser.':'Automatic saving unavailable here. Use Save game.';
    lastAutoSave=performance.now();
  }
  function canonicalPuzzle(puzzle){
    C.fromChallenge(C.toDocument(puzzle));
    const src=puzzle.source;
    if(src&&src.kind==='native'){
      const key=src.seed+':'+JSON.stringify(src.limits);let canonical=canonicalCache.get(key);
      if(!canonical){const generated=C.generate(src.seed,src.limits);if(generated.status!==0)throw new Error('Could not reconstruct this generated challenge.');canonical=generated.puzzle;canonicalCache.set(key,canonical);if(canonicalCache.size>8)canonicalCache.delete(canonicalCache.keys().next().value);}
      if(fingerprint(canonical)!==fingerprint(puzzle))throw new Error('The imported puzzle does not match its native generator seed.');
      if(puzzle.generation&&['classification','attempts','nodes'].some(key=>String(puzzle.generation[key])!==String(canonical.generation[key])))throw new Error('The saved generation report does not match this seed and its limits.');
      return {puzzle:canonical,provenance:'generated-v1'};
    }
    if(src&&src.kind==='original'&&table){const canonical=decorate(table.getPuzzle(src.number));if(fingerprint(canonical)!==fingerprint(puzzle))throw new Error('The imported puzzle does not match the loaded original table.');return {puzzle:canonical,provenance:'local-original-table'};}
    return {puzzle,provenance:'imported-public-constraints'};
  }
  function adopt(newGame,origin,ui){
    if(!newGame.puzzle.source)throw new Error('Saved games must identify their original number or native generator seed.');
    C.toChallenge(newGame.puzzle);
    const restoredProof=newGame.hint_pending?P.explainHint(newGame,newGame.pending_hint,20000):null;
    if(restoredProof&&restoredProof.status!==1)throw new Error('The saved pending hint could not be verified.');
    let restoredHintClock=newGame.hint_pending?S.displayTimeMs(newGame):null;
    if(ui&&ui.hint_display_ms!==undefined&&ui.hint_display_ms!==null){
      if(!newGame.hint_pending||typeof ui.hint_display_ms!=='string'||!/^(0|[1-9][0-9]*)$/.test(ui.hint_display_ms)||ui.hint_display_ms.length>20)throw new Error('Invalid saved hint display clock.');
      const clock=BigInt(ui.hint_display_ms);
      if(clock>18446744073709551615n||(newGame.limit_ms?(clock>newGame.limit_ms||clock<S.displayTimeMs(newGame)):clock>newGame.elapsed_ms))throw new Error('The saved hint display clock is inconsistent.');
      restoredHintClock=clock;
    }
    game=newGame;provenance=origin;selectedClue=-1;selectedCell=[0,0];bank=0;mode='remove';
    if(ui&&['remove','choose','restore'].includes(ui.mode)&&[0,1].includes(ui.bank)&&Array.isArray(ui.selected_cell)&&ui.selected_cell.length===2&&ui.selected_cell.every(x=>Number.isInteger(x)&&x>=0&&x<6)){mode=ui.mode;bank=ui.bank;selectedCell=ui.selected_cell.slice();}
    pendingProof=null;hintClock=null;lastProof=null;lastOutcome=game.outcome;history=[];resetClockSample();closeDialog();
    if(source()){$('sh-source').value=source().kind==='original'?'original':'native';$('sh-seed').value=source().kind==='original'?source().number:source().seed;sourceForm();}
    const seconds=game.limit_ms/1000n;if([...$('sh-limit').options].some(o=>o.value===seconds.toString()))$('sh-limit').value=seconds.toString();
    if(game.hint_pending){pendingProof=restoredProof;lastProof=pendingProof;hintClock=restoredHintClock;}
    render();if(game.hint_pending)hintDialog();
  }
  function importDocument(document,restoreOnly=false){
    const {incoming,ui}=V.unwrap(document);
    if(incoming&&incoming.format==='sherlock-browser-save-1'){
      const candidate=S.importGame(incoming),canonical=canonicalPuzzle(candidate.puzzle);
      const admitted=S.importGame(incoming,canonical.puzzle);
      admitted.puzzle=S.createGame(canonical.puzzle).puzzle;
      adopt(admitted,canonical.provenance,ui);
    }else{
      if(restoreOnly)throw new Error('Expected a saved session.');
      const imported=C.fromChallenge(incoming),canonical=canonicalPuzzle(imported);
      const initialized=S.createGame(canonical.puzzle,Number($('sh-limit').value));
      if(initialized.outcome!==0)throw new Error('This challenge exceeds the visible clue-grid capacity.');
      adopt(initialized,canonical.provenance);
    }
    notice('Loaded the puzzle and saved board. Local artwork can be loaded separately.','success');
  }
  async function newPuzzle(){
    if(busy||game&&game.hint_pending)return;
    busy=true;if(game)render();notice('Preparing and checking the puzzle…');
    await new Promise(resolve=>setTimeout(resolve,0));
    try{
      const type=$('sh-source').value,seed=$('sh-seed').value.trim(),limit=Number($('sh-limit').value);let puzzle,origin;
      if(!/^[0-9]+$/.test(seed)||seed.length>20)throw new Error('Enter an unsigned decimal seed or original puzzle number.');
      if(type==='original'){
        if(!table){$('sh-files-panel').open=true;throw new Error('Load sherlock_puzzles.bin in Local files first.');}
        puzzle=decorate(table.getPuzzle(Number(seed)));origin='local-original-table';
      }else{
        const generated=C.generate(seed);if(generated.status!==0)throw new Error(generated.report.reason||'Generation did not finish within its budget.');
        puzzle=generated.puzzle;origin='generated-v1';
      }
      adopt(S.createGame(puzzle,limit),origin);log('new',{source:source()});persist();notice('Find each picture’s column. Every row contains its six pictures exactly once.','success');
    }finally{busy=false;if(game)render();}
  }
  function sourceForm(){const original=$('sh-source').value==='original';$('sh-seed-label').textContent=original?'Number · 0–65535':'Seed';$('sh-seed').setAttribute('aria-label',original?'Original puzzle number':'Puzzle seed');$('sh-random').textContent=original?'Random number':'Random seed';}
  function perform(kind,r,c,item){
    if(!game)return -1;sampleClock();selectedCell=[r,c];
    const result=S[kind](game,r,c,item);
    if(result===1){log(kind,{row:r,column:c,item});notice((kind==='choose'?'Chose ':kind==='restore'?'Restored ':'Eliminated ')+ROWS[r]+' '+(item+1)+' in column '+(c+1)+'.');persist();}
    else if(game.fixed[r]&&game.fixed[r][c])notice('This is a given picture.');
    render();return result;
  }
  function closeDialog(){dialogKind=null;$('sh-dialog').hidden=true;}
  function showDialog(kind,title,content,buttons){
    dialogKind=kind;$('sh-dialog-title').textContent=title;$('sh-dialog-content').innerHTML=content;
    const actions=$('sh-dialog-actions');actions.replaceChildren();
    for(const spec of buttons){const button=document.createElement('button');button.type='button';button.textContent=spec.text;if(spec.primary)button.className='sh-primary';button.addEventListener('click',()=>{try{spec.action();}catch(error){notice(error.message,'error');}});actions.append(button);}
    $('sh-dialog').hidden=false;drawImages($('sh-dialog'));const first=actions.querySelector('button');if(first)first.focus({preventScroll:true});
  }
  function announceOutcome(){
    if(!game||!game.outcome)return;
    const title=game.outcome===1?'Puzzle solved':game.outcome===3?'Time expired':game.outcome===2?'The completed board does not fit the clues':'Game ended';
    const text=game.outcome===1?'Every row, given, and relationship clue has been verified.':game.outcome===3?'The deadline takes priority over a final placement. You can inspect or save this board, then restart.':'The engine checks the completed answer against the public constraints. Save a bug capture if this result looks wrong.';
    notice(title,game.outcome===1?'success':'error');
    showDialog('outcome',title,'<p>'+esc(text)+'</p><p>Elapsed time: <strong>'+clockText(game.elapsed_ms)+'</strong>.</p>',[{text:'Inspect board',action:closeDialog},{text:'Restart puzzle',primary:true,action:restart}]);
  }
  function requestHint(){
    if(!game)return;sampleClock();const result=S.requestHint(game,bank,20000);
    if(result!==1){render();const h=game.pending_hint;notice(h&&h.explanation||'No applicable hint is available.');return null;}
    const proof=P.explainHint(game,game.pending_hint,20000);
    if(proof.status!==1){game.hint_pending=0;notice('The selected move could not be proved: '+proof.report.reason,'error');render();return proof;}
    pendingProof=proof;lastProof=proof;hintClock=S.displayTimeMs(game);whyOpen=false;whyPage=0;
    log('hint-offered',{bank,target:game.pending_hint});persist();render();hintDialog();return proof;
  }
  function hintDialog(){
    if(!game.hint_pending)return;
    const hint=game.pending_hint,support=pendingProof.record.support||[],count=support.length;
    let html='<div class="sh-hint-target-line">'+objectHTML(hint.row*6+hint.item)+'<strong>'+(hint.kind===1?'Eliminate':'Choose')+' '+ROWS[hint.row]+' '+(hint.item+1)+' · column '+(hint.column+1)+'</strong></div>';
    if(!whyOpen)html+='<p>'+esc(hint.explanation)+'</p><p>Accepting applies this move and adds <strong>30 seconds</strong>. The clock display is frozen while the hint is open; elapsed time continues.</p>';
    else {
      if(count){whyPage=Math.min(whyPage,count-1);const entry=support[whyPage],clue=entry.clue;html+='<div class="sh-support-card">'+pictures(entry.index)+'<div><strong>Clue '+(entry.index+1)+' · '+TITLES[clue.type]+'</strong><p>'+esc(RULES[clue.type])+'</p></div></div><p>Supporting card '+(whyPage+1)+' of '+count+'.</p>';}
      else html+='<p>This deduction needs the row-permutation rule and current candidate marks; no relationship card is needed.</p>';
      html+='<p>The current marks and givens have a valid completion. The opposite of this move has none.</p><p class="sh-instruction">Earlier candidate edits are assumptions. This check does not certify that those earlier edits were correct.</p>';
      if(!pendingProof.report.reduction_complete)html+='<p class="sh-instruction">The move is proved. Support reduction reached its budget before finishing.</p>';
    }
    const buttons=[];
    if(whyOpen&&count>1){buttons.push({text:'Previous card',action:()=>{whyPage=(whyPage+count-1)%count;hintDialog();}});buttons.push({text:'Next card',action:()=>{whyPage=(whyPage+1)%count;hintDialog();}});}
    buttons.push({text:whyOpen?'Back to hint':'Show why',action:()=>{whyOpen=!whyOpen;hintDialog();}});
    buttons.push({text:'Capture hint',action:()=>downloadJSON(captureBug('Hint overlay'),'sherlock-hint-capture.json')});
    buttons.push({text:'Apply hint · +30s',primary:true,action:()=>{sampleClock();const target=plain(game.pending_hint),changed=S.acceptHint(game);hintClock=null;pendingProof=null;closeDialog();log('hint-accepted',{target,changed});persist();render();if(!game.outcome)notice(changed?'Hint applied; 30 seconds added.':'The hint did not change the board.');}});
    showDialog('hint',whyOpen?'Why this move follows':'Verified hint',html,buttons);
  }
  function restart(){
    if(!game||game.hint_pending)return;
    const puzzle=game.puzzle,limit=game.limit_ms/1000n;
    adopt(S.createGame(puzzle,Number(limit)),provenance);log('restart');persist();notice('Restarted this puzzle.');
  }
  function writeJSON(value){$('sh-json').value=json(value);$('sh-agent-panel').open=true;return value;}
  function downloadJSON(value,filename){
    writeJSON(value);const blob=new Blob([json(value)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=filename;root.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    notice('JSON prepared. If a download is blocked, copy it from Agent JSON.');
  }
  function captureBug(note){sampleClock();return {format:'sherlock-browser-repro-1',browser_version:1,native_reference:'ee62716e53f84c3f02814db4d7ff3a8884f2f152',note:String(note||'').slice(0,4000),session:session(),provenance,challenge:C.toDocument(game.puzzle),recent_actions:history.slice(),last_hint_evidence:lastProof?plain(lastProof):null,assets:{art_name:artName,original_table_loaded:!!table,table_name:tableName,bytes_included:false}};}
  function bugDialog(){showDialog('bug','Capture a reproducible bug','<p>The capture keeps the exact puzzle, candidate marks, clue positions, clock, undo history, and recent actions.</p><label>What did you expect, and what happened?<textarea id="sh-bug-note" class="sh-bug-note" rows="4" maxlength="4000" placeholder="Expected… Observed… Steps…"></textarea></label><p class="sh-instruction">Original artwork and file bytes are not included.</p>',[{text:'Cancel',action:closeDialog},{text:'Capture JSON',primary:true,action:()=>{const note=$('sh-bug-note').value;closeDialog();downloadJSON(captureBug(note),'sherlock-bug.json');}}]);}
  function checkSolution(input){
    return V.verify(game.puzzle,input);
  }
  function checkMove(input){
    const value=typeof input==='string'?A.parseJSON(input):input;
    if(!value||Array.isArray(value)||Object.keys(value).sort().join(',')!=='column,item,kind,row'||!['remove','choose'].includes(value.kind)||![value.row,value.column,value.item].every(x=>Number.isInteger(x)&&x>=0&&x<6))throw new Error('A move needs kind remove/choose, row, column, and item (0–5).');
    const target={kind:value.kind==='remove'?1:2,row:value.row,column:value.column,item:value.item,clue_index:-1,explanation:'Submitted browser move.'};
    return P.explainHint(game,target,20000);
  }
  function analyze(){return V.analyze(game.puzzle,200000);}
  function helpDialog(){showDialog('help','How to play','<p>Place each row’s six pictures in its six columns. Pictures from different rows can share a column. Use the relationship cards to eliminate impossible positions.</p><ol><li>Select <strong>Eliminate</strong>, <strong>Choose</strong>, or <strong>Restore</strong>, then click a picture.</li><li>Right-click chooses a picture. Shift-click restores one. On a narrow screen, tap a cell and use the six larger buttons below the board.</li><li>Click a clue to read its exact rule. Move finished clues to the Other bank; they remain logical constraints.</li><li>A hint is free to inspect. <strong>Apply hint</strong> adds 30 seconds. Undo restores the board but never refunds time.</li></ol><p><strong>Between:</strong> the middle picture touches both outer pictures. <strong>Not in the middle:</strong> the outer pictures are still exactly two columns apart.</p><p class="sh-instruction">Keyboard: H hint, U undo, P pause, E eliminate, C choose, R restore. Original art and numbered puzzles load from your local files.</p>',[{text:'Start playing',primary:true,action:closeDialog}]);}

  root.addEventListener('click',event=>{
    const candidate=event.target.closest('[data-candidate]');
    if(candidate){const [r,c,item]=candidate.dataset.candidate.split(',').map(Number);perform(event.shiftKey?'restore':mode,r,c,item);return;}
    const cell=event.target.closest('[data-select-cell]');if(cell){selectedCell=cell.dataset.selectCell.split(',').map(Number);render();return;}
    const clue=event.target.closest('[data-clue]');if(clue){if(game.hint_pending||game.paused)return;selectedClue=Number(clue.dataset.clue);render();return;}
    const button=event.target.closest('[data-mode]');if(button){mode=button.dataset.mode;render();persist();}
  });
  root.addEventListener('contextmenu',event=>{const candidate=event.target.closest('[data-candidate]');if(candidate){event.preventDefault();const [r,c,item]=candidate.dataset.candidate.split(',').map(Number);perform('choose',r,c,item);}});
  root.addEventListener('keydown',event=>{
    if(dialogKind){
      if(event.key==='Escape'){event.preventDefault();if(dialogKind==='hint'){if(whyOpen){whyOpen=false;hintDialog();}}else closeDialog();}
      if(event.key==='Tab'){const controls=[...$('sh-dialog').querySelectorAll('button:not(:disabled),input,textarea,select')];const first=controls[0],last=controls[controls.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}
      return;
    }
    if(event.ctrlKey||event.metaKey||event.altKey||/INPUT|TEXTAREA|SELECT/.test(event.target.tagName))return;
    const key=event.key.toLowerCase(),buttons={h:'sh-hint',u:'sh-undo',p:'sh-pause'};
    if(buttons[key]){event.preventDefault();$(buttons[key]).click();}
    else if({e:'remove',c:'choose',r:'restore'}[key]){mode={e:'remove',c:'choose',r:'restore'}[key];render();persist();}
  });
  on('sh-source','change',sourceForm);on('sh-new','click',newPuzzle);
  on('sh-random','click',()=>{const values=new Uint32Array(2);crypto.getRandomValues(values);$('sh-seed').value=$('sh-source').value==='original'?String(values[0]&65535):((BigInt(values[0])<<32n)|BigInt(values[1])).toString();return newPuzzle();});
  on('sh-undo','click',()=>{sampleClock();const result=S.undo(game);if(result===1){log('undo');persist();notice('Board restored. Time is unchanged.');}render();});
  on('sh-hint','click',requestHint);
  const pause=()=>{sampleClock();S.setPaused(game,!game.paused);log(game.paused?'pause':'resume');persist();render();};
  on('sh-pause','click',pause);on('sh-resume','click',pause);on('sh-restart','click',restart);
  on('sh-game-bank','click',()=>{bank=0;selectedClue=-1;render();persist();});on('sh-other-bank','click',()=>{bank=1;selectedClue=-1;render();persist();});
  on('sh-archive','click',()=>{sampleClock();const index=selectedClue,result=S.archiveClue(game,index);if(result===1){selectedClue=-1;log('archive-clue',{clue:index});persist();notice('Card moved to the other bank.');}render();});
  on('sh-move','click',()=>{sampleClock();const slot=Number($('sh-slot').value),result=S.moveClue(game,selectedClue,slot);if(result===1){log('move-clue',{clue:selectedClue,slot});persist();notice('Card position updated.');}render();});
  on('sh-close-clue','click',()=>{selectedClue=-1;render();});on('sh-help','click',helpDialog);on('sh-bug','click',bugDialog);
  on('sh-save','click',()=>{sampleClock();persist();downloadJSON(session(),'sherlock-save.json');});
  on('sh-shi-file','change',async e=>{const file=e.target.files[0];if(!file)return;if(file.size!==23920)throw new Error('Expected a 23,920-byte SHI file.');const decoded=A.decodeSHI(await file.arrayBuffer());art=decoded;artName=file.name;$('sh-art-name').textContent=artName;render();if(game.hint_pending)hintDialog();persist();notice('Loaded all 46 SHI images locally.','success');});
  on('sh-table-file','change',async e=>{const file=e.target.files[0];if(!file)return;if(file.size>32*1024*1024)throw new Error('Puzzle tables are limited to 32 MiB.');const candidate=A.loadOriginalTable(await file.arrayBuffer());if(source()&&source().kind==='original'&&fingerprint(candidate.getPuzzle(source().number))!==fingerprint(game.puzzle))throw new Error('The table does not match the current original puzzle.');table=candidate;tableName=file.name;if(source()&&source().kind==='original')provenance='local-original-table';$('sh-table-name').textContent=file.name+' · 65,536 original puzzle numbers';render();notice('Original table loaded. Choose Original numbered puzzle and a number.','success');});
  on('sh-default-art','click',()=>{art=null;artName='Built-in symbols';$('sh-art-name').textContent=artName;render();if(game.hint_pending)hintDialog();persist();});
  on('sh-json-file','change',async e=>{const file=e.target.files[0];if(!file)return;if(file.size>1024*1024)throw new Error('JSON imports are limited to 1 MiB.');importDocument(await file.text());log('import-session');persist();});
  on('sh-load-json-text','click',()=>{importDocument($('sh-json').value);log('import-session');persist();});
  on('sh-export-challenge','click',()=>writeJSON(C.toDocument(game.puzzle)));
  on('sh-export-state','click',()=>writeJSON({candidates:game.board.candidates.map(r=>r.slice()),chosen:game.board.chosen.map(r=>r.slice())}));
  on('sh-export-proof','click',()=>{if(!lastProof)throw new Error('Request a hint or check a proposed move first.');writeJSON(lastProof);});
  on('sh-analyze','click',()=>diagnose(analyze()));
  on('sh-check-answer','click',()=>{const result=checkSolution($('sh-json').value);diagnose(result);notice(result.accepted?'Solution accepted by the public-constraint verifier.':result.reason||(result.error&&result.error.message)||'The answer could not be checked.',result.accepted?'success':'error');});
  on('sh-check-move','click',()=>{const result=checkMove($('sh-json').value);lastProof=result;diagnose(result);notice(result.report.reason,result.status===1?'success':'error');});
  on('sh-copy-json','click',async()=>{try{await navigator.clipboard.writeText($('sh-json').value);notice('JSON copied.','success');}catch(_){$('sh-json').focus();$('sh-json').select();notice('JSON selected. Use your browser’s Copy command.');}});
  on('sh-download-json','click',()=>downloadJSON(A.parseJSON($('sh-json').value),'sherlock-data.json'));
  globalThis.addEventListener('openai:set_globals',event=>{
    const state=event.detail&&event.detail.globals&&event.detail.globals.widgetState;
    if(!state||state.format!=='sherlock-space-state-1'||state.revision===lastSaveId)return;
    try{importDocument(state.session,true);lastSaveId=state.revision;notice('Loaded the latest board saved in this Space.');}catch(error){notice('The shared saved board could not be loaded: '+error.message,'error');}
  });
  document.addEventListener('visibilitychange',()=>{if(game){sampleClock();if(document.hidden)persist();else{render();resetClockSample();}}});
  globalThis.addEventListener('pagehide',()=>{if(game){sampleClock();persist();}});
  setInterval(()=>{if(!game)return;const before=game.outcome;sampleClock();updateClock();if(game.outcome!==before){persist();render();}else if(!game.paused&&!game.hint_pending&&performance.now()-lastAutoSave>30000)persist();},250);
  // Deliberate agent seam. These methods return plain JSON-safe data and use
  // exactly the same public constraints and state mutations as the buttons.
  globalThis.SherlockReplica=Object.freeze({
    version:1,challenge:()=>C.toDocument(game.puzzle),
    state:()=>({candidates:game.board.candidates.map(r=>r.slice()),chosen:game.board.chosen.map(r=>r.slice())}),
    snapshot:()=>{sampleClock();return session();},verifySolution:checkSolution,checkHint:checkMove,analyze,
    move:value=>{if(!value||!['remove','restore','choose'].includes(value.kind)||![value.row,value.column,value.item].every(x=>Number.isInteger(x)&&x>=0&&x<6))throw new Error('Invalid board move.');return perform(value.kind,value.row,value.column,value.item);},
    requestHint,exportBug:captureBug,
    load:value=>{if(game&&game.hint_pending)throw new Error('Acknowledge the pending hint before loading another board.');importDocument(value);persist();return session();}
  });
  (async()=>{
    let saved=null;
    try{const host=globalThis.openai&&globalThis.openai.widgetState;if(host&&host.format==='sherlock-space-state-1'){saved=host.session;lastSaveId=host.revision;}else{const text=localStorage.getItem(SAVE_KEY);if(text)saved=A.parseJSON(text);}}catch(_){}
    if(saved){try{importDocument(saved,true);notice('Resumed your saved board. Load local SHI artwork again if you want the original pictures.','success');return;}catch(error){notice('Saved board could not be resumed: '+error.message,'error');}}
    await newPuzzle();
  })().catch(error=>notice(error.message,'error'));
})();
