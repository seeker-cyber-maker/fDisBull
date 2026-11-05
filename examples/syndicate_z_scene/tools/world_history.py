"""Append-only semantic world history, separate from presentation and game state.

The ledger is game-neutral. Native adapters supply occurrence identities and
qualified projections; this module neither inspects bullets nor guesses causes.
Each connection owns a file-backed journal. No original code/memory is stored.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _name(value, field):
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
        raise ValueError(f'Invalid {field}')
    return value


class WorldHistory:
    """Durable observations; identical occurrences are NOT deduplicated by text.

    An origin key is scoped to a stream and producer. Re-delivery of that exact
    observation is idempotent; conflicting re-delivery fails. Restores must create
    a new stream with an explicit parent, not reuse old guest timestamps as IDs.
    """
    def __init__(self, path, *, max_event_bytes=16384, max_events=1000000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if type(max_event_bytes) is not int or not 512 <= max_event_bytes <= 1048576:
            raise ValueError('Invalid per-event bound')
        if type(max_events) is not int or not 1 <= max_events <= 10000000:
            raise ValueError('Invalid history capacity')
        self.max_event_bytes, self.max_events = max_event_bytes, max_events
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        tables={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if (version==0 and tables) or (version==1 and not {'streams','events','cursors'}<=tables):
            self.db.close()
            raise ValueError('Not an empty database or recognized world history; unrelated logs left untouched')
        if version not in (0,1):
            self.db.close()
            raise ValueError('Unsupported history schema version')
        self.db.executescript('''
          PRAGMA journal_mode=WAL;
          PRAGMA synchronous=FULL;
          PRAGMA foreign_keys=ON;
          PRAGMA user_version=1;
          CREATE TABLE IF NOT EXISTS streams(
            id TEXT PRIMARY KEY, metadata TEXT NOT NULL, fingerprint TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            stream TEXT NOT NULL REFERENCES streams(id),
            producer TEXT NOT NULL,
            occurrence TEXT NOT NULL,
            kind TEXT NOT NULL,
            diagnostic TEXT NOT NULL,
            player TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            UNIQUE(stream,producer,occurrence));
          CREATE INDEX IF NOT EXISTS events_kind_sequence ON events(kind,seq);
          CREATE TABLE IF NOT EXISTS cursors(
            consumer TEXT NOT NULL, perspective TEXT NOT NULL,
            seq INTEGER NOT NULL, PRIMARY KEY(consumer,perspective));
          CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
            BEGIN SELECT RAISE(ABORT,'History events are immutable'); END;
          CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
            BEGIN SELECT RAISE(ABORT,'History events are append-only'); END;
          CREATE TRIGGER IF NOT EXISTS streams_no_update BEFORE UPDATE ON streams
            BEGIN SELECT RAISE(ABORT,'History streams are immutable'); END;
          CREATE TRIGGER IF NOT EXISTS streams_no_delete BEFORE DELETE ON streams
            BEGIN SELECT RAISE(ABORT,'History streams are append-only'); END;
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def __enter__(self): return self
    def __exit__(self, *_): self.close()

    def stream(self, identity, *, metadata, parent=None):
        _name(identity, 'stream')
        if not isinstance(metadata, dict): raise ValueError('Metadata must be a mapping')
        # A restore branches causal history; old events never disappear.
        if parent is not None:
            if not isinstance(parent, dict) or set(parent) != {'stream', 'through_seq'}:
                raise ValueError('Parent needs stream and through_seq')
            if not self.db.execute('SELECT 1 FROM streams WHERE id=?',(parent['stream'],)).fetchone():
                raise ValueError('Unknown parent stream')
            n=parent['through_seq']
            if type(n) is not int or n < 0 or n > self.high_watermark:
                raise ValueError('Invalid parent cursor')
            if n and not self.db.execute('SELECT 1 FROM events WHERE seq=? AND stream=?',(n,parent['stream'])).fetchone():
                raise ValueError('Parent event belongs to another stream')
        content={'metadata':deepcopy(metadata),'parent':deepcopy(parent)}
        text=canonical(content); sha=digest(content)
        if len(text.encode()) > self.max_event_bytes: raise ValueError('Oversize metadata')
        with self.db:
            old=self.db.execute('SELECT fingerprint FROM streams WHERE id=?',(identity,)).fetchone()
            if old and old['fingerprint']!=sha: raise ValueError('Conflicting stream identity')
            if not old: self.db.execute('INSERT INTO streams VALUES(?,?,?)',(identity,text,sha))
        return identity

    @property
    def high_watermark(self):
        return self.db.execute('SELECT coalesce(max(seq),0) FROM events').fetchone()[0]

    def append(self, stream, producer, occurrence, diagnostic, *, player=None):
        """Persist before resuming the guest. Storage errors propagate, never drop.

        Player projection must be explicitly provided from qualified perception.
        The default reveals no event payload. Sequence/cursor metadata is not a
        secrecy boundary; a fair-play bridge must not expose diagnostic cursors.
        """
        for value,label in ((stream,'stream'),(producer,'producer'),(occurrence,'occurrence')):
            _name(value,label)
        if not isinstance(diagnostic,dict): raise ValueError('Event must be a mapping')
        kind=_name(diagnostic.get('kind'),'kind')
        if player is None: player={}
        if not isinstance(player,dict): raise ValueError('Player projection must be a mapping')
        if player and player.get('kind')!=kind: raise ValueError('Projection kind mismatch')
        parents=diagnostic.get('causal_parents',[])
        if not isinstance(parents,list) or len(parents)>64 or any(not isinstance(x,str) for x in parents) or len(set(parents))!=len(parents):raise ValueError('Invalid causal parents')
        for payload in (diagnostic,player):
            if set(payload) & {'seq','id','stream','producer','occurrence','fingerprint'}:
                raise ValueError('Reserved event identity field')
            cause=payload.get('cause')
            if cause is not None and not isinstance(cause,dict):raise ValueError('Cause must be a mapping')
            if cause is not None:
                for key in ('actor_id','damage_type'):
                    if cause.get(key) is not None:_name(cause[key],key)
            if payload.get('kind')=='damage':
                for key in ('health_before','health_after'):
                    if type(payload.get(key)) is not int:raise ValueError('Damage needs exact integer health')
                if payload['health_after']<0:raise ValueError('Negative health needs a qualified sentinel/state event, not arithmetic damage')
                if payload['health_after']>=payload['health_before']:raise ValueError('Not a damage decrement')
                if type(payload.get('amount')) is not int or payload['amount']!=payload['health_before']-payload['health_after']:
                    raise ValueError('Damage amount mismatch')
                _name(payload.get('victim_id'),'victim')
            tick=payload.get('guest_tick')
            if tick is not None and (type(tick) is not int or tick<0):raise ValueError('Invalid guest tick')
        packed={'diagnostic':deepcopy(diagnostic),'player':deepcopy(player)}
        text=canonical(packed)
        if len(text.encode())>self.max_event_bytes:raise ValueError('Oversize event; retain raw evidence separately')
        sha=digest(packed)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            old=self.db.execute('SELECT * FROM events WHERE stream=? AND producer=? AND occurrence=?',(stream,producer,occurrence)).fetchone()
            if old:
                if old['fingerprint']!=sha:raise ValueError('Conflicting duplicate occurrence')
                return {'seq':old['seq'],'id':old['id'],'inserted':False}
            if not self.db.execute('SELECT 1 FROM streams WHERE id=?',(stream,)).fetchone():raise ValueError('Unknown stream')
            for parent_id in parents:
                parent_row=self.db.execute('SELECT stream FROM events WHERE id=?',(parent_id,)).fetchone()
                if parent_row is None or parent_row['stream']!=stream:raise ValueError('Causal parent missing or belongs to a different timeline')
            if self.high_watermark>=self.max_events:raise OverflowError('History capacity reached; hold capture, never evict old events')
            ident='event-'+uuid.uuid4().hex
            cur=self.db.execute('INSERT INTO events(id,stream,producer,occurrence,kind,diagnostic,player,fingerprint) VALUES(?,?,?,?,?,?,?,?)',
                (ident,stream,producer,occurrence,kind,canonical(diagnostic),canonical(player),sha))
            return {'seq':cur.lastrowid,'id':ident,'inserted':True}

    @staticmethod
    def _perspective(perspective):
        if perspective not in ('diagnostic','player'):raise ValueError('Invalid perspective')

    def events(self, *, after=0, through=None, limit=200, perspective='diagnostic'):
        self._perspective(perspective)
        if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=10000:raise ValueError('Invalid query bound')
        high=self.high_watermark if through is None else through
        if type(high) is not int or not after<=high<=self.high_watermark:raise ValueError('Invalid high watermark')
        rows=self.db.execute('SELECT * FROM events WHERE seq>? AND seq<=? ORDER BY seq LIMIT ?',(after,high,limit)).fetchall()
        visible=[]
        for r in rows:
            payload=json.loads(r[perspective])
            if payload:
                visible.append({'seq':r['seq'],'id':r['id'],'stream':r['stream'],**payload})
        return {'events':visible,'scanned_through':rows[-1]['seq'] if rows else high,'high_watermark':high,
                'more':bool(rows and rows[-1]['seq']<high)}

    def get(self, event_id, *, perspective='diagnostic'):
        self._perspective(perspective)
        row=self.db.execute('SELECT * FROM events WHERE id=?',(event_id,)).fetchone()
        if row is None:return None
        payload=json.loads(row[perspective])
        return {'seq':row['seq'],'id':row['id'],'stream':row['stream'],**payload} if payload else None

    def summarize(self, *, after=0, through=None, max_rows=12, scan_limit=4096, perspective='diagnostic'):
        """Run-length presentation only. Interleaved events split groups.

        A page exposes a stable upper watermark. Reading it does not acknowledge
        it. All group constituents remain individually addressable in the ledger.
        No assertion about exact native hit count follows from snapshot aggregates.
        """
        if type(max_rows) is not int or not 1<=max_rows<=100:raise ValueError('Invalid row limit')
        page=self.events(after=after,through=through,limit=scan_limit,perspective=perspective)
        groups=[]; consumed=after
        for ev in page['events']:
            cause=ev.get('cause',{})
            key=(ev['kind'],ev['stream'],ev.get('victim_id'),cause.get('actor_id'),cause.get('source_entity_id'),cause.get('damage_type'),
                 ev.get('amount'),ev.get('observation_basis'),ev.get('certainty')) if ev['kind'] in ('damage','damage-contact') else None
            # Only contiguous global records may coalesce. A hidden event also
            # prevents grouping rather than leaking its content.
            merge=(key is not None and groups and groups[-1].get('_key')==key and groups[-1]['last_seq']+1==ev['seq']
                   and (ev.get('guest_tick') is None or groups[-1]['last_tick'] is None or
                        0<=ev['guest_tick']-groups[-1]['last_tick']<=1000))
            if not merge:
                if len(groups)>=max_rows:break
                groups.append({'kind':ev['kind'],'first_seq':ev['seq'],'last_seq':ev['seq'],
                    'first_id':ev['id'],'last_id':ev['id'],'count':1,'total_amount':ev.get('amount',0),
                    'first_tick':ev.get('guest_tick'),'last_tick':ev.get('guest_tick'),
                    'example':ev,'_key':key})
            else:
                g=groups[-1];g.update(last_seq=ev['seq'],last_id=ev['id'],last_tick=ev.get('guest_tick'))
                g['count']+=1;g['total_amount']+=ev.get('amount',0)
            consumed=ev['seq']
        # Scan empty/hidden rows without claiming there were visible events.
        if len(groups)<max_rows:consumed=max(consumed,page['scanned_through'])
        for g in groups:g.pop('_key',None)
        return {'groups':groups,'after':after,'consumed_through':consumed,'high_watermark':page['high_watermark'],
                'more':consumed<page['high_watermark'],'perspective':perspective,
                'note':'Presentation groups only; raw occurrences remain append-only.'}

    def recent(self, *, limit=8, notices_only=False, perspective='diagnostic', through=None):
        """Query non-damage records independently; bursts cannot evict notices."""
        self._perspective(perspective)
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('Invalid recent limit')
        high=self.high_watermark if through is None else through
        if type(high) is not int or not 0<=high<=self.high_watermark:raise ValueError('Invalid watermark')
        clauses=['seq<=?', perspective+" != '{}' "]
        if notices_only:clauses.append("kind NOT IN ('damage','damage-contact')")
        rows=self.db.execute('SELECT * FROM events WHERE '+' AND '.join(clauses)+' ORDER BY seq DESC LIMIT ?', (high,limit)).fetchall()
        return [{**json.loads(r[perspective]),'seq':r['seq'],'id':r['id'],'stream':r['stream']} for r in reversed(rows)]

    def cursor(self, consumer, *, perspective='diagnostic'):
        _name(consumer,'consumer');self._perspective(perspective)
        r=self.db.execute('SELECT seq FROM cursors WHERE consumer=? AND perspective=?',(consumer,perspective)).fetchone()
        return r['seq'] if r else 0

    def acknowledge(self, consumer, page):
        """Explicit view-cursor update, never a game action or event deletion."""
        _name(consumer,'consumer');p=page['perspective'];self._perspective(p)
        n=page['consumed_through'];high=page['high_watermark']
        if type(n) is not int or type(high) is not int or not 0<=n<=high<=self.high_watermark:raise ValueError('Invalid acknowledgement')
        old=self.cursor(consumer,perspective=p)
        if n<old:raise ValueError('Cursor cannot go backwards')
        with self.db:self.db.execute('INSERT INTO cursors VALUES(?,?,?) ON CONFLICT(consumer,perspective) DO UPDATE SET seq=excluded.seq',(consumer,p,n))
        return n

    def export_jsonl(self, path):
        """Create a new semantic export. Existing files are never overwritten."""
        with Path(path).open('x',encoding='utf-8') as f:
            for row in self.db.execute('SELECT * FROM events ORDER BY seq'):
                f.write(canonical(dict(row)|{'diagnostic':json.loads(row['diagnostic']),'player':json.loads(row['player'])})+'\n')


def render_summary(page, *, max_chars=4000):
    if type(max_chars) is not int or not 256<=max_chars<=65536:raise ValueError('Invalid display bound')
    lines=['World history ('+page['perspective']+'); individual events are retained.']
    for g in page['groups']:
        e=g['example'];span=(f"#{g['first_seq']}" if g['count']==1 else f"#{g['first_seq']}..#{g['last_seq']}")+' ['+e['stream']+']'
        if g['kind']=='damage':
            c=e.get('cause',{});who=c.get('actor_id') or c.get('source_entity_id') or 'unattributed'
            line=f"{span} {g['count']} hit occurrence(s), {g['total_amount']} HP: {e['victim_id']} <- {who}; {c.get('damage_type','unknown')} [{e.get('certainty','unknown')}]."
        elif g['kind']=='damage-contact':
            c=e.get('cause',{});who=c.get('actor_id') or c.get('source_entity_id') or 'unattributed'
            line=f"{span} {g['count']} contact observation(s): {e.get('victim_id','unknown victim')} <- {who}; {c.get('damage_type','unknown')}; NOT a health-loss count."
        else:line=f"{span} {g['kind']}: {str(e.get('message','record retained'))[:240]}"
        if sum(len(x)+1 for x in lines)+len(line)+100>max_chars:
            lines.append('Display clipped; query the ledger/page cursor for all records.');break
        lines.append(line)
    if page['more']:lines.append('More records available; no automatic cursor advancement.')
    return '\n'.join(lines)


class HistoryBackend:
    """Passive history objects over an existing compatible Z provider.

    This wrapper does not subscribe to game events or grant actions. Diagnostic
    history and ordinary player perception are explicitly distinct projections.
    """
    def __init__(self, base, history, *, perspective='diagnostic', after=0):
        history._perspective(perspective)
        self.base,self.history,self.perspective,self.after=base,history,perspective,after
    def observe(self):
        obs=deepcopy(self.base.observe())
        if not obs.get('complete'):return obs
        page=self.history.summarize(after=self.after,perspective=self.perspective)
        def add(i,label,description,aliases):
            obs['objects'].append({'id':i,'label':label,'description':description,'aliases':aliases,'verbs':[]})
        add('world-event-history','world history',render_summary(page),['history','damage history','event history'])
        # Non-damage notices have their own small view, so a long burst cannot
        # erase a mission/state warning from the next observation.
        last=self.history.recent(limit=8,perspective=self.perspective,through=page['high_watermark'])
        notices=self.history.recent(limit=8,notices_only=True,perspective=self.perspective,through=page['high_watermark'])
        add('world-history-notices','history notices','\n'.join(f"#{e['seq']} {e['kind']}: {e.get('message','')}" for e in notices) or 'No projected notices recorded.',['other events','history warnings'])
        for ev in last[-8:]:add('history-'+ev['id'],'event '+str(ev['seq']),canonical(ev),[ev['id']])
        if self.perspective=='diagnostic':
            obs['context']['description'] += '\nHistory includes diagnostic evidence, not ordinary player perception.'
        obs['context']['token']=digest({'base':obs['context']['token'],'high':page['high_watermark'],'perspective':self.perspective})
        return obs
    def act(self,_):return {'status':'rejected','complete':True,'effects':'none-confirmed','message':'History view is read-only; no game action sent.'}
