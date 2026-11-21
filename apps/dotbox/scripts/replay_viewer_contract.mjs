import fs from 'node:fs';
import vm from 'node:vm';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';

// Offline analysis only: no app attachment, accounts, transport or live input.
// The exact source digest is required; Node's vm is not a security boundary.
const path = process.argv[2];
if (!path) {
  console.error('Usage: node scripts/replay_viewer_contract.mjs /path/to/extracted/423400.5f97d1f55f.js');
  process.exit(2);
}
const raw = fs.readFileSync(path);
const hash = crypto.createHash('sha256').update(raw).digest('hex');
assert.equal(hash, '677f26e365d928c58703a314ed87d1fc72e1dee67af7c39c6ecc1cec65ffc580');
const start = raw.indexOf(Buffer.from('function a(e)'), 8000);
const end = raw.indexOf(Buffer.from('},v7is('), start);
assert.equal(start, 8903);
assert.equal(end, 22964);
const id = '11111111-1111-4111-8111-111111111111';
const stale = '22222222-2222-4222-8222-222222222222';
let forbiddenCalls = 0;
const forbidden = () => { forbiddenCalls++; throw Error('Live operation forbidden in offline replay'); };
class Keyboard { reset() {} }
const context = vm.createContext({FakeKeyboard: Keyboard, fetch: forbidden,
  RTCPeerConnection: forbidden, WebSocket: forbidden, setTimeout: forbidden,
  clearTimeout() {}, navigator: {platform: 'Linux'}, crypto: {randomUUID: () => id},
  getComputedStyle: () => ({objectFit: 'contain'}), console: {log() {},warn() {}}});
new vm.Script('var r,o; var s=FakeKeyboard;\n' + raw.subarray(start,end).toString('utf8') +
              '\nthis.ViewerClient=m;').runInContext(context, {timeout:1000});
const Viewer = context.ViewerClient;
const checks = [];
const plain = x => JSON.parse(JSON.stringify(x));
function check(name, fn) { fn(); checks.push({name,passed:true}); }
function client(shared=true) {
  const c = new Viewer('',null,forbidden,undefined,shared);
  c.sent=[]; c.events=[];
  c.dataChannel={readyState:'open',send:x=>c.sent.push(x),close(){this.readyState='closed';}};
  for (const name of ['controlowner','modechange','disconnected'])
    c.addEventListener(name,(...args)=>c.events.push({name,args:plain(args)}));
  c._handleMessage({data:JSON.stringify({event:'system/init',session_id:'peer-A'})});
  return c;
}
const message=(c,payload)=>c._handleMessage({data:JSON.stringify(payload)});
const grant=c=>{c.setMode('control',id);message(c,{event:'control/locked',id:'peer-A',request_id:id});};

check('shared owner human event, independent of local mode',()=>{
  const c=client();message(c,{event:'control/host',has_host:true,owner:{kind:'human',display_name:'Fixture User'}});
  assert.deepEqual(c.events.at(-1),{name:'controlowner',args:[{kind:'human',displayName:'Fixture User'}]});
  assert.equal(c.mode,'observe');
});
check('shared owner dot event',()=>{
  const c=client();message(c,{event:'control/host',has_host:false});
  assert.deepEqual(c.events.at(-1),{name:'controlowner',args:[{kind:'dot'}]});
});
check('missing host boolean does not manufacture owner',()=>{
  const c=client();message(c,{event:'control/host',has_host:'false'});assert.equal(c.events.length,0);
});
check('ordinary nonshared client has no shared owner event',()=>{
  const c=client(false);message(c,{event:'control/host',has_host:false});assert.equal(c.events.length,0);
});
check('observe mode refuses binary input',()=>{
  const c=client();c.sendData('mousemove',{x:123,y:45});assert.equal(c.sent.length,0);
});
check('takeover request is correlated and not a local grant',()=>{
  const c=client();c.setMode('control',id);
  assert.deepEqual(JSON.parse(c.sent[0]),{event:'control/request',request_id:id,shared_dot_takeover:true});
  assert.equal(c.mode,'observe');c.setMode('control',id);assert.equal(c.sent.length,1);
});
check('closed channel refuses shared request',()=>{
  const c=client();c.dataChannel.readyState='closed';c.setMode('control',id);assert.equal(c.sent.length,0);
});
check('wrong peer acknowledgement ignored',()=>{
  const c=client();c.setMode('control',id);message(c,{event:'control/locked',id:'peer-B',request_id:id});assert.equal(c.mode,'observe');
});
check('stale and invalid supplied request identifiers ignored',()=>{
  const c=client();c.setMode('control',id);
  for(const request_id of [stale,'invalid'])message(c,{event:'control/locked',id:'peer-A',request_id});
  assert.equal(c.mode,'observe');
});
check('matching acknowledgement grants local mode',()=>{
  const c=client();grant(c);assert.equal(c.mode,'control');
  assert.deepEqual(c.events.at(-1),{name:'modechange',args:['control',id,null]});
});
check('omitted request id compatibility acknowledgement is accepted',()=>{
  const c=client();c.setMode('control',id);message(c,{event:'control/locked',id:'peer-A'});assert.equal(c.mode,'control');
});
check('absolute mouse packet uses unchanged x and y, not accumulated deltas',()=>{
  const c=client();grant(c);c.sent=[];
  c.sendData('mousemove',{x:123,y:45});c.sendData('mousemove',{x:123,y:45});
  const a=Buffer.from(c.sent[0]),b=Buffer.from(c.sent[1]);
  assert.equal(a.length,7);assert.equal(a[0],1);assert.equal(a.readUInt16LE(3),123);assert.equal(a.readUInt16LE(5),45);assert.deepEqual(a,b);
});
check('key down and up packet encoding',()=>{
  const c=client();grant(c);c.sent=[];c.sendData('keydown',{key:97});c.sendData('keyup',{key:97});
  const a=Buffer.from(c.sent[0]),b=Buffer.from(c.sent[1]);assert.equal(a.length,11);assert.equal(a[0],3);assert.equal(b[0],4);assert.equal(a.readBigUInt64LE(3),97n);
});
check('closed channel refuses binary input even while mode control',()=>{
  const c=client();grant(c);c.sent=[];c.dataChannel.readyState='closed';c.sendData('keydown',{key:97});assert.equal(c.sent.length,0);
});
check('release sends request without inventing immediate mode acknowledgement',()=>{
  const c=client();grant(c);c.sent=[];c.setMode('observe');
  assert.deepEqual(JSON.parse(c.sent[0]),{event:'control/release'});assert.equal(c.mode,'control');
  message(c,{event:'control/release',id:'peer-A'});assert.equal(c.mode,'observe');
});
check('late grant after cancellation is released, not adopted',()=>{
  const c=client();c.setMode('control',id);c.setMode('observe');c.sent=[];
  message(c,{event:'control/locked',id:'peer-A',request_id:id});assert.equal(c.mode,'observe');assert.deepEqual(JSON.parse(c.sent[0]),{event:'control/release'});
});
check('peer replacement clears owner and control mode',()=>{
  const c=client();grant(c);c.events=[];message(c,{event:'system/init',session_id:'peer-B'});
  assert.equal(c.mode,'observe');assert.deepEqual(c.events[0],{name:'controlowner',args:[null]});
});
check('disconnect clears local mode but does not emit an owner-null update',()=>{
  const c=client();grant(c);c.events=[];c.disconnect();assert.equal(c.mode,'observe');
  assert.deepEqual(c.events.map(x=>x.name),['disconnected']);assert.equal(c.dataChannel,null);
});
check('letterboxed video point scales to absolute original video pixels',()=>{
  const video={videoWidth:320,videoHeight:200,getBoundingClientRect:()=>({width:640,height:480})};
  assert.deepEqual(plain(Viewer.getScaledOffset({x:320,y:240},video)),{x:160,y:100});
  assert.deepEqual(plain(Viewer.getScaledOffset({x:0,y:0},video)),{x:0,y:0});
});
assert.equal(forbiddenCalls,0);
console.log(JSON.stringify({schema:'dotbox-viewer-offline-contract-replay-1',member_sha256:hash,
  source_range:{start,end,encoding:'UTF-8 bytes',end_exclusive:true},passed:checks.length,checks,
  forbidden_live_calls:forbiddenCalls,scope:'Exact extracted client class/helpers; fake keyboard, channel and DOM geometry; no live app, WebRTC, server, account or cloud execution.'},null,2));
