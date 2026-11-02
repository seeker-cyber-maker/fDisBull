from demo import Provider,Game,from_binding
from pathlib import Path
import hashlib

for alg in ('lcg16','xorshift16'):
    a=Provider(alg,12345); b=Provider(alg,12345)
    xs=[a.die() for _ in range(10000)]; ys=[b.die() for _ in range(10000)]
    assert xs==ys and all(1<=x<=6 for x in xs)
# Scripted provider checks the same full transition and visible trace for same draws.
script=[1,2,3,4,5, 6,6,6,6, 6,6,6,6, 2,2,3,3,6, 4,4,4,4,4]
def trace():
    g=Game(Provider('script',0,script)); out=[g.view()]
    for c in ('1','R','R','R','S','S','S','S'):
        g.command(c); out.append(g.view())
    return out
a=trace(); b=trace(); assert a==b
assert a[1]['holds'][0] and a[2]['dice']==[1,6,6,6,6] and a[2]['rolls']==2
assert a[3]['rolls']==3 and a[4]==a[3]
assert a[5]['scores']==[25] and a[6]['scores']==[25,6]
assert a[7]['scores']==[25,6,50] and a[7]['done'] and a[8]==a[7]
for bad in ([],[0],[7]):
    try: Provider('script',0,bad).die(); raise AssertionError('accepted invalid draw')
    except ValueError: pass
x=from_binding('binding-lcg.json'); y=from_binding('binding-xorshift.json')
assert x.view()['dice'] != y.view()['dice']
for name in ('semantic-contract.txt','demo.py'):
    print(name,hashlib.sha256(Path(name).read_bytes()).hexdigest())
print('PASS: binding, bounds, repeatability, scripted transitions, hold, rerolls, scores, terminal, errors')
