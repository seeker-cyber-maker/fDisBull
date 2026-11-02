from switch_guard import md,prove_sequence,Unsupported
# Authored snippets, not original game code.
def check(data,guard,expected):
 seq=list(md.disasm(bytes.fromhex(data),0x1000))
 r=prove_sequence(seq,guard)
 assert r['verdict']==expected,(data,r)
 return {'bytes':data,'guard_index':guard,'expected':expected,'actual':r['verdict']}
# Register value to a zero-extended table index.
r=[check('6683f910777f31c06689c8ff248500200000',0,'unsat'),
# Removing high-register clear admits an out-of-range index.
check('6683f910777f6689c8ff248500200000',0,'sat'),
# Same stable-memory byte compared and reloaded.
check('8a530380fa0c777f31c08a4303ff248500200000',1,'unsat'),
# One-byte change of address between comparison/reload breaks equality.
check('8a530380fa0c777f31c0438a4303ff248500200000',1,'sat'),
# High-byte source copied before masking.
check('80fe03777f88f281e2ff000000ff249500200000',0,'unsat')]
# Detect impossible guards rather than calling them a useful proof.
try:
 prove_sequence(list(md.disasm(bytes.fromhex('b9140000006683f910770731c06689c8ff248500200000'),0x1000)),1)
 raise AssertionError('vacuity accepted')
except Unsupported as e:assert 'vacuous' in str(e)
# Nonflat-address and write semantics are not smuggled into this profile.
try:
 prove_sequence(list(md.disasm(bytes.fromhex('8a530380fa0c770731c0678a07ff248500200000'),0x1000)),1)
 raise AssertionError('address override accepted')
except Unsupported as e:assert 'address-size' in str(e)
import json
# Initial seven checks retained; final aggregate below.
# A stack store cannot be ignored when it might alias the later reload.
r.append(check('8a660d8954240880fc3a777f31c08a460dff248500200000',2,'sat'))
# A previously guarded register stays bounded even if an unrelated store occurs.
r.append(check('6683fa05777f31c06689d0890c24ff248500200000',0,'unsat'))
# Scaled offset held in a base register is a different encoding of the same table.
r.append(check('80fa10777f88d025ff0000008d148500000000ffa200200000',0,'unsat'))
print(json.dumps({'final_passed':10,'details':r,'vacuity_refused':True,'address_override_refused':True},indent=2))
