'use strict';
/* Small independent row-permutation enumeration checks the support claims.
 * It never calls the implementation's relation predicate or search routine.
 */
const assert=require('node:assert/strict');
const State=require('../state.js'), Proof=require('../proof.js');
let checks=0, enumerations=0;
function equal(actual,expected,message){assert.deepEqual(actual,expected,message);checks++;}
function check(value,message){assert.ok(value,message);checks++;}
function copy(value){return JSON.parse(JSON.stringify(value));}
function matrix(value){return Array.from({length:6},function(){return Array(6).fill(value);});}
function puzzle(clues){
    clues=clues||[];
    return {number:0,given:matrix(-1),clues:clues,clue_count:clues.length,original_slot:Array(clues.length).fill(255)};
}
function smallGame(clues){
    const g=State.createGame(puzzle(clues));
    for(let r=0;r<6;r++)for(let c=0;c<6;c++)g.board.candidates[r][c]=1<<c;
    return g;
}
function combinedGame(){
    const g=smallGame([{type:4,a:0,b:6,c:255},{type:0,a:6,b:13,c:255},
        {type:4,a:18,b:29,c:255},{type:7,a:35,b:255,c:255}]);
    for(let r=0;r<2;r++)for(let c=0;c<3;c++)g.board.candidates[r][c]=7;
    return g;
}
function hint(kind,row,column,item,clueIndex){
    return {kind:kind,row:row,column:column,item:item,clue_index:clueIndex===undefined?-1:clueIndex};
}
function independentRelation(clue,places){
    const a=places[clue.a],b=places[clue.b],c=places[clue.c];
    switch(clue.type){
        case 0:return a===b;
        case 1:return a!==b;
        case 2:return a+1===b||b+1===a;
        case 3:return a+1!==b&&b+1!==a;
        case 4:return a<b;
        case 5:return (a+2===c||c+2===a)&&a+c===2*b;
        case 6:return (a+2===c||c+2===a)&&a+c!==2*b;
        default:throw new Error('Unexpected relation in proof.');
    }
}
function oracle(record,skip){
    enumerations++;
    const rows=[];
    let combinations=1;
    for(let r=0;r<6;r++){
        const possibilities=[];
        function permute(c,used,row){
            if(c===6){possibilities.push(row.slice());return;}
            for(let item=0;item<6;item++){
                if((used&(1<<item))||!(record.candidates[r][c]&(1<<item)))continue;
                if(record.given[r][c]>=0&&record.given[r][c]!==item)continue;
                row.push(item);permute(c+1,used|(1<<item),row);row.pop();
            }
        }
        permute(0,0,[]);rows.push(possibilities);combinations*=possibilities.length;
        check(combinations<=100000,'Independent oracle must stay bounded.');
    }
    const selected=[],places=Array(36);let total=0,contrary=0;
    function join(row){
        if(row<6){for(const candidate of rows[row]){selected[row]=candidate;join(row+1);}return;}
        for(let r=0;r<6;r++)for(let c=0;c<6;c++)places[r*6+selected[r][c]]=c;
        for(let i=0;i<record.support_count;i++){
            if(i!==skip&&!independentRelation(record.support[i].clue,places))return;
        }
        total++;
        const t=record.target,present=selected[t.row][t.column]===t.item;
        if(present===(t.kind===State.SH_HINT_REMOVE))contrary++;
    }
    join(0);return {total:total,contrary:contrary};
}
function sufficient(record,minimal){
    const counts=oracle(record);
    check(counts.total>0&&counts.contrary===0);
    if(minimal)for(let i=0;i<record.support_count;i++){
        const dropped=oracle(record,i);
        check(dropped.total>0&&dropped.contrary>0);
    }
}
{
    const game=combinedGame(),selected=hint(1,0,1,0,0);
    const board=State.cloneBoard(game.board);
    const built=Proof.explainHint(game,selected,10000);
    equal(built.status,Proof.SH_PROOF_PROVED);
    equal(built.record.support.map(function(x){return x.index;}),[0,1]);
    equal(built.report.deletion_checks,3);
    equal(built.report.reduction_complete,1);
    equal(built.record.target,{kind:1,row:0,column:1,item:0});
    equal(game.board,board);
    sufficient(built.record,true);
    const before=copy(built.record), replay=Proof.replayHintProof(built.record,10000);
    equal(replay.status,1);equal(replay.report.reduction_complete,0);equal(replay.report.deletion_checks,0);
    equal(built.record,before);
    Object.defineProperty(game.puzzle,'solution',{get:function(){throw new Error('Read hidden solution.');}});
    game.board.chosen=matrix(5);game.board.clue_slots[0][0].fill(-1);
    game.elapsed_ms=987654n;game.paused=1;game.hint_pending=1;
    equal(Proof.explainHint(game,selected,10000),built,'Display state and the hidden answer are not premises.');
    const choose=Proof.explainHint(game,hint(2,0,0,0),10000);
    equal(choose.status,1);sufficient(choose.record,true);
    check(!JSON.stringify(choose.record).includes('solution'));
}
{
    const game=smallGame();
    game.board.candidates[0]=[15,15,12,12,48,48];
    const built=Proof.explainHint(game,hint(1,0,0,2),1000);
    equal(built.status,1);equal(built.record.support_count,0);sufficient(built.record,true);
    const relaxed=copy(built.record);relaxed.candidates[0][2]|=1;
    equal(Proof.replayHintProof(relaxed,1000).status,2);
    const game2=smallGame();game2.board.candidates[0][0]=game2.board.candidates[0][1]=3;
    game2.puzzle.given[0][0]=0;
    const given=Proof.explainHint(game2,hint(2,0,0,0),1000);
    equal(given.status,1);equal(given.record.support_count,0);sufficient(given.record,true);
    const relaxedGiven=copy(given.record);relaxedGiven.given[0][0]=-1;
    equal(Proof.replayHintProof(relaxedGiven,1000).status,2);
    equal(oracle(relaxedGiven),{total:2,contrary:1});
    game2.puzzle.given[0][0]=-1;
    equal(Proof.explainHint(game2,hint(1,0,0,0),1000).status,2);
    game2.board.candidates[5][5]=0;
    const inconsistent=Proof.explainHint(game2,hint(1,0,0,0),1000);
    equal(inconsistent.status,3);equal(inconsistent.report.deletion_checks,0);
    equal(oracle(inconsistent.record),{total:0,contrary:0});
}
{
    const game=smallGame([{type:0,a:0,b:12,c:255},{type:0,a:0,b:6,c:255},{type:0,a:6,b:12,c:255}]);
    for(let r=0;r<2;r++)game.board.candidates[r][0]=game.board.candidates[r][1]=3;
    const arbitrary=Proof.explainHint(game,hint(1,0,1,0),1000);
    equal(arbitrary.record.support.map(function(x){return x.index;}),[1,2]);sufficient(arbitrary.record,true);
    const preferred=Proof.explainHint(game,hint(1,0,1,0,0),1000);
    equal(preferred.record.support.map(function(x){return x.index;}),[0]);sufficient(preferred.record,true);
    game.board.candidates[0][0]=1;
    const redundant=Proof.explainHint(game,hint(2,0,0,0,0),1000);
    equal(redundant.status,1);equal(redundant.record.support_count,0);
}
{
    const game=combinedGame(),target=hint(1,0,1,0);
    const zero=Proof.explainHint(game,target,0);
    equal(zero.status,0);equal(zero.report.nodes_used,0);equal(zero.report.reduction_complete,0);
    const replay=Proof.replayHintProof(zero.record,10000);
    equal(replay.status,1);
    const proofOnly=Proof.explainHint(game,target,replay.report.nodes_used);
    equal(proofOnly.status,1);equal(proofOnly.report.reduction_complete,0);
    equal(proofOnly.report.deletion_checks,0);equal(proofOnly.record.support_count,3);
    sufficient(proofOnly.record,false);
    const partial=Proof.explainHint(game,target,replay.report.nodes_used+1);
    equal(partial.status,1);equal(partial.report.reduction_complete,0);equal(partial.report.deletion_checks,1);
    sufficient(partial.record,false);
    equal(Proof.replayHintProof(zero.record,0).status,0);
    equal(Proof.explainHint(game,target,-1).status,-1);
}
{
    const record=Proof.explainHint(combinedGame(),hint(1,0,1,0),10000).record;
    const omitted=copy(record);omitted.support.pop();omitted.support_count--;
    equal(Proof.replayHintProof(omitted,1000).status,2);
    const alternate=copy(record);alternate.target.column=0;
    equal(Proof.replayHintProof(alternate,1000).status,2);
    const changes=[
        function(p){p.version=2;},function(p){p.background_rules=3;},
        function(p){p.target.kind=3;},function(p){p.target.row=6;},
        function(p){p.target.column=-1;},function(p){p.target.item=6;},
        function(p){p.candidates[0][1]&=~1;},function(p){p.candidates[5][5]=128;},
        function(p){p.given[5][5]=6;},function(p){p.given[5][5]=-2;},
        function(p){p.source_clue_count=257;},function(p){p.support_count=257;},
        function(p){p.selected_clue_index=-2;},function(p){p.selected_clue_index=4;},
        function(p){p.support[1].index=p.support[0].index;},function(p){p.support[1].index=4;},
        function(p){p.support[0].clue.type=7;},function(p){p.support[0].clue.a=36;},
        function(p){p.support[0].clue.b=36;},function(p){p.support[0].clue.type=5;},
        function(p){p.fake_result='proved';},function(p){delete p.candidates[0][0];}
    ];
    for(const change of changes){
        const bad=copy(record);change(bad);
        const result=Proof.replayHintProof(bad,1000);
        equal(result.status,-1);equal(result.report.nodes_used,0);
    }
    equal(Proof.replayHintProof(null,1).status,-1);
    equal(Proof.explainHint(null,hint(1,0,1,0),1).status,-1);
}
{
    const clues=Array.from({length:255},function(){return {type:0,a:0,b:0,c:255};});
    clues.push({type:4,a:0,b:1,c:255});
    const game=smallGame(clues);game.board.candidates[0][0]=game.board.candidates[0][1]=3;
    const target=hint(2,0,0,0,255);
    const budgetStop=Proof.explainHint(game,target,0);
    equal(budgetStop.record.support_count,256);equal(budgetStop.record.support[255].index,255);
    const built=Proof.explainHint(game,target,10000);
    equal(built.status,1);equal(built.report.deletion_checks,256);
    equal(built.record.support_count,1);equal(built.record.support[0].index,255);
    sufficient(built.record,true);
    equal(Proof.replayHintProof(built.record,10000).status,1);
}
console.log('Browser proof contract: '+checks+' checks and '+enumerations+' independent enumerations passed.');
