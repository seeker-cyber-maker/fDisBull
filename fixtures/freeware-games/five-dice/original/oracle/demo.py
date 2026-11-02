"""Experimental binding demonstration; not a UIL or fDisBull UDC executor."""
import json, sys
from pathlib import Path

class Provider:
    def __init__(self, algorithm, seed, script=()):
        if algorithm not in ('lcg16','xorshift16','script'): raise ValueError('unknown provider')
        if not 0 <= seed <= 65535: raise ValueError('seed outside uint16')
        if algorithm=='xorshift16' and seed==0: raise ValueError('zero xorshift seed')
        self.algorithm,self.state,self.script,self.index=algorithm,seed,list(script),0
    def die(self):
        if self.algorithm=='script':
            if self.index>=len(self.script): raise ValueError('script exhausted')
            x=self.script[self.index]; self.index+=1
            if type(x)!=int or not 1<=x<=6: raise ValueError('invalid scripted die')
            return x
        x=self.state
        if self.algorithm=='lcg16': x=(x*25173+13849)&65535
        else:
            x ^= (x<<7)&65535; x ^= x>>9; x ^= (x<<8)&65535; x &=65535
        self.state=x
        return x%6+1

class Game:
    def __init__(self, provider):
        self.p=provider; self.turn=0; self.total=0; self.scores=[]; self.done=False
        self.start()
    def start(self):
        self.holds=[False]*5; self.dice=[0]*5; self.rolls=0; self.roll()
    def roll(self):
        if self.done or self.rolls>=3: return
        for i in range(5):
            if not self.holds[i]: self.dice[i]=self.p.die()
        self.rolls+=1
    def command(self, c):
        if self.done: return
        c=c.upper()
        if c in '12345' and len(c)==1: self.holds[int(c)-1]^=True
        elif c=='R': self.roll()
        elif c=='S':
            d=self.dice
            if self.turn==0: score=sum(d)
            elif self.turn==1: score=max((2*x for x in range(1,7) if d.count(x)>=2),default=0)
            else: score=50 if len(set(d))==1 else 0
            self.total+=score; self.scores.append(score); self.turn+=1
            if self.turn==3: self.done=True
            else: self.start()
    def view(self):
        return {'turn':self.turn+1,'rolls':self.rolls,'dice':self.dice[:],
                'holds':self.holds[:],'scores':self.scores[:],'total':self.total,'done':self.done}

def from_binding(path):
    b=json.loads(Path(path).read_text())
    if set(b)!={'algorithm','seed'}: raise ValueError('binding keys')
    return Game(Provider(b['algorithm'],b['seed']))

if __name__=='__main__':
    game=from_binding(sys.argv[1]); print(json.dumps(game.view()))
    for command in sys.argv[2:]: game.command(command); print(json.dumps(game.view()))
