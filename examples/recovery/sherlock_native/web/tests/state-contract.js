'use strict';
/* Focused browser-state controls. Native C comparison is a separate harness. */
const assert = require('node:assert/strict');
const Core = require('../engine.js');
const State = require('../state.js');
const Proof = require('../proof.js');
let checks = 0;
function check(condition, message) { assert.ok(condition, message); checks++; }
function equal(actual, expected, message) { assert.deepEqual(actual, expected, message); checks++; }
function rejects(fn, message) { assert.throws(fn, message); checks++; }
function matrix(value) { return Array.from({length: 6}, function () { return Array(6).fill(value); }); }
function puzzle(clues) {
    clues = clues || [];
    const p = {number: 0, given: matrix(-1), clue_count: clues.length,
        clues: clues, original_slot: Array(clues.length).fill(255)};
    Object.defineProperty(p, 'solution', {
        enumerable: true, get: function () { throw new Error('Hidden solution was read.'); }
    });
    return p;
}
function rowBytes(game, row) { return Array.from({length: 6}, function (_, column) { return State.cellByte(game, row, column); }); }
function cloneJSON(value) { return JSON.parse(JSON.stringify(value)); }

/* Recovered native cell-byte policy, explicit choices and board-only undo. */
{
    const p = puzzle(); p.given[0][4] = 2;
    const g = State.createGame(p);
    equal(rowBytes(g, 0), [59,59,59,59,132,59]);
    equal(State.remove(g,0,0,0),1);
    equal(State.choose(g,0,0,1),1);
    equal(rowBytes(g,0),[66,57,57,57,132,57]);
    equal(State.remove(g,0,0,1),1);
    equal(rowBytes(g,0),[0,57,57,57,132,57]);
    equal(State.undo(g),1);
    equal(rowBytes(g,0),[66,57,57,57,132,57]);
    equal(State.restore(g,0,0,0),1);
    equal(State.cellByte(g,0,0),3);
    equal(g.board.chosen[0][0],-1);
    equal(State.choose(g,0,4,1),0);
    equal(State.remove(g,0,4,2),0);
    equal(State.restore(g,0,4,1),0);
    check(!Object.prototype.hasOwnProperty.call(g.puzzle,'solution'));
    const owned = State.createGame(p);
    owned.puzzle.given[0][4] = 3;
    equal(p.given[0][4],2);
}
{
    const p = puzzle([{type:4,a:0,b:5,c:255}]);
    let g = State.createGame(p);
    for (let item=1;item<6;item++) State.remove(g,0,0,item);
    equal(g.board.candidates[0][0],1);
    equal(g.board.chosen[0][0],-1,'A singleton is not automatically chosen.');
    for (let row=0;row<6;row++) for (let column=0;column<6;column++) State.choose(g,row,column,column);
    equal(g.outcome,State.SH_WON);
    const saved = State.exportGame(g);
    equal(State.importGame(saved).outcome,State.SH_WON);
    g=State.createGame(p);
    for (let row=0;row<6;row++) for (let column=0;column<6;column++) State.choose(g,row,column,(column+1)%6);
    equal(g.outcome,State.SH_WRONG);
    equal(State.importGame(State.exportGame(g)).outcome,State.SH_WRONG);
}

/* Both clue banks retain holes; moving a card and undoing own independent arrays. */
{
    const p=puzzle([{type:2,a:0,b:6,c:255},{type:4,a:1,b:7,c:255},
        {type:5,a:2,b:8,c:14},{type:0,a:3,b:9,c:255}]);
    const g=State.createGame(p);
    equal(State.archiveClue(g,0),1);
    equal(g.board.clue_slots[0][1].slice(0,3),[-1,1,2]);
    equal(State.clueLocation(g,0),{bank:1,group:1,slot:0});
    equal(State.undo(g),1);
    equal(State.moveClue(g,0,1),1);
    equal(g.board.clue_slots[0][1].slice(0,4),[-1,0,1,2]);
    equal(State.undo(g),1);
    equal(State.moveClue(g,2,0),1);
    equal(g.board.clue_slots[0][1].slice(0,3),[2,0,1]);
    const h=State.createGame(p);
    for(let i=0;i<26;i++) equal(State.remove(h,Math.floor(i/6),i%6,0),1);
    equal(h.undo_count,25);
    const save=State.exportGame(h), restored=State.importGame(save);
    equal(restored.undo_count,25);
    for(let i=0;i<25;i++) equal(State.undo(restored),1);
    equal(State.undo(restored),0);
    equal(restored.board.candidates[0].slice(0,2),[62,63]);
    equal(h.board.candidates[0][1],62,'Restore did not alias live input arrays.');
    check(Buffer.byteLength(JSON.stringify(save))<16384,'A normal full undo history fits the Space state budget.');
}

/* Offer, elapsed wall time, acceptance fee, expiration priority and no refund. */
{
    const p=puzzle([{type:0,a:0,b:6,c:255}]); p.given[1][2]=0;
    const g=State.createGame(p);
    State.tick(g,1000);
    const before=State.cloneBoard(g.board);
    equal(State.requestHint(g,0,1000),1);
    equal(g.elapsed_ms,1000n);
    equal(g.board,before);
    equal(State.remove(g,0,0,0),0);
    equal(State.requestHint(g,0,1000),0);
    State.tick(g,2000);
    equal(g.elapsed_ms,3000n);
    const save=State.exportGame(g), restored=State.importGame(JSON.stringify(save));
    equal(State.exportGame(restored),save);
    equal(State.acceptHint(restored),1);
    equal(restored.elapsed_ms,33000n);
    equal(State.acceptHint(restored),0);
    equal(State.undo(restored),1);
    equal(restored.board,before);
    equal(restored.elapsed_ms,33000n);
    const limited=State.createGame(p,20);
    State.requestHint(limited);
    State.tick(limited,25000n);
    equal(limited.outcome,State.SH_PLAYING);
    equal(State.displayTimeMs(limited),0n);
    const pending=State.importGame(State.exportGame(limited));
    equal(State.acceptHint(pending),1);
    equal(pending.outcome,State.SH_TIMED_OUT);
    equal(pending.elapsed_ms,55000n);
    equal(State.importGame(State.exportGame(pending)).outcome,State.SH_TIMED_OUT);
}
{
    for(const limit of [0,30]) {
        const g=State.createGame(puzzle(),limit);
        for(let row=0;row<6;row++) for(let column=0;column<6;column++) {
            if(row!==5||column!==5) State.choose(g,row,column,column);
        }
        State.tick(g,1000);
        equal(State.requestHint(g),1);
        equal(State.acceptHint(g),1);
        equal(g.elapsed_ms,31000n);
        equal(g.outcome,limit?State.SH_TIMED_OUT:State.SH_WON);
    }
    const g=State.createGame(puzzle(),3601);
    State.tick(g,1000);
    equal(State.displayTimeMs(g),3600000n);
    State.setPaused(g,true); State.tick(g,50000);
    equal(g.elapsed_ms,1000n);
    State.setPaused(g,false); State.tick(g,3600000);
    equal(g.outcome,State.SH_TIMED_OUT);
    const saturated=State.createGame(puzzle());
    saturated.elapsed_ms=State.UINT64_MAX-10n;
    saturated.board.candidates[0][0]=1;
    State.requestHint(saturated);
    State.acceptHint(saturated);
    equal(saturated.elapsed_ms,State.UINT64_MAX);
    equal(State.tick(saturated,1n),1);
    equal(saturated.elapsed_ms,State.UINT64_MAX);
    equal(State.tick(saturated,Number.MAX_SAFE_INTEGER+1),-1);
    equal(saturated.elapsed_ms,State.UINT64_MAX);
}

/* JSON saves are untrusted input; reject corruption before returning a game. */
{
    const g=State.createGame(Core.generate('42').puzzle);
    State.remove(g,0,0,0);
    const baseline=State.exportGame(g);
    const changes=[
        function(s){s.outcome=State.SH_WON;},
        function(s){s.outcome=State.SH_WRONG;},
        function(s){s.outcome=State.SH_TIMED_OUT;},
        function(s){s.elapsed_ms='18446744073709551616';},
        function(s){s.elapsed_ms=5;},
        function(s){s.elapsed_ms='-1';},
        function(s){s.paused=2;},
        function(s){s.undo_count=9;},
        function(s){s.undo=Array(26).fill(s.board);s.undo_count=26;},
        function(s){s.board.cells[0]=255;},
        function(s){s.board.cells[0]=64|3;},
        function(s){s.board.clue_slots[0][0][0]=256;},
        function(s){s.board.clue_slots[0][0][1]=s.board.clue_slots[0][0][0];},
        function(s){s.board.clue_slots[0][0].pop();},
        function(s){s.board.unrecognized=true;},
        function(s){s.puzzle.solution=matrix(0);},
        function(s){s.puzzle.given[0][0]=-2;},
        function(s){s.puzzle.public_fingerprint.hex='0000000000000000';},
        function(s){s.puzzle.challenge_id+='x';},
        function(s){s.pending_hint.explanation='\u0000';},
        function(s){s.puzzle.clues[0].a=36;},
        function(s){delete s.undo[0];},
        function(s){delete s.puzzle.given[0][0];}
    ];
    for(const change of changes) {
        const bad=cloneJSON(baseline);change(bad);
        rejects(function(){State.importGame(bad);});
        equal(State.exportGame(g),baseline,'Failed import leaves the active game unchanged.');
    }
    const json=JSON.stringify(baseline);
    rejects(function(){State.importGame(json.replace('"outcome":0','"outcome":0,"outcome":0'));});
    rejects(function(){State.importGame(json.replace('"outcome":0','"outcome":0,"\\u006futcome":0'));});
    rejects(function(){State.importGame(json+' trailing');});
    rejects(function(){State.importGame(baseline,Core.generate('43').puzzle);});
    const noClues=State.createGame(puzzle()), fake=State.exportGame(noClues);
    fake.hint_pending=1;
    fake.pending_hint={kind:State.SH_HINT_CHOOSE,row:0,column:0,item:0,clue_index:-1,explanation:'Claim'};
    rejects(function(){State.importGame(fake);},'A supplied forced-move claim must be proved.');
    const givenPuzzle=puzzle();givenPuzzle.given[2][3]=1;
    const givenSave=State.exportGame(State.createGame(givenPuzzle));
    givenSave.board.cells[15]=63;
    rejects(function(){State.importGame(givenSave);},'A save cannot remove a given.');
    const entirelyGiven=puzzle();
    for(let row=0;row<6;row++) for(let column=0;column<6;column++) entirelyGiven.given[row][column]=column;
    const starting=State.createGame(entirelyGiven);
    equal(State.importGame(State.exportGame(starting)).outcome,State.SH_PLAYING,
        'Native initialization does not run the completion verdict.');
}
{
    const p=puzzle(), sparse=Array.from({length:6},function(){return Array(6);});
    equal(State.checkCandidates(p,sparse,123),{status:-2,remaining_nodes:123,nodes_used:0});
    const g=State.createGame(p);
    equal(State.findHint(g,2).result,-1);
    equal(State.requestHint(g,0,-1),-1);
    equal(State.checkCandidates(p,matrix(63),0),{status:-1,remaining_nodes:0,nodes_used:0});
    const h=State.findHint(State.createGame(Core.generate('42').puzzle));
    check(h.result===1 && Proof.explainHint(State.createGame(Core.generate('42').puzzle),h).status===1);
}

console.log('Browser state contract: '+checks+' checks passed.');
