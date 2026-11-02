"""Authored event-stream tests. No original game or native timing is simulated."""
import copy,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from world_history import WorldHistory,HistoryBackend,render_summary

def hit(**overrides):
    e={'kind':'damage','guest_tick':10,'victim_id':'person-0','health_before':16,'health_after':15,'amount':1,
       'cause':{'actor_id':'guard','damage_type':'projectile'},'certainty':'authored','observation_basis':'authored committed store'}
    e.update(overrides);return e

class Base:
    def __init__(self):self.calls=0
    def observe(self):
        return {'complete':True,'context':{'id':'room','token':'base','title':'Room','description':'Authored scene'},'coverage':{'partial':True},'objects':[],'inventory':[]}
    def act(self,a):self.calls+=1;raise AssertionError('No history read may act')

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'events.sqlite';self.h=WorldHistory(self.path)
        self.h.stream('run',metadata={'source':'authored'})
    def tearDown(self):self.h.close();self.tmp.cleanup()
    def add(self,key='one',event=None,**kw):return self.h.append('run','observer',key,event or hit(),**kw)
    def test_identical_hits_distinct(self):
        a=self.add('a');b=self.add('b');self.assertNotEqual(a['id'],b['id']);self.assertEqual(self.h.high_watermark,2)
    def test_identical_tick_distinct(self):
        for i in range(10):self.add(str(i))
        self.assertEqual(len(self.h.events()['events']),10)
    def test_retransmit_idempotent(self):
        a=self.add();b=self.add();self.assertFalse(b['inserted']);self.assertEqual(a['id'],b['id']);self.assertEqual(self.h.high_watermark,1)
    def test_conflicting_duplicate(self):
        self.add()
        with self.assertRaisesRegex(ValueError,'Conflicting'):self.add(event=hit(guest_tick=11))
        self.assertEqual(self.h.high_watermark,1)
    def test_producers_independent(self):
        self.add();self.h.append('run','other','one',hit());self.assertEqual(self.h.high_watermark,2)
    def test_streams_independent(self):
        self.add();self.h.stream('other',metadata={});self.h.append('other','observer','one',hit());self.assertEqual(self.h.high_watermark,2)
    def test_restart_persists(self):
        a=self.add();self.h.close();self.h=WorldHistory(self.path);self.assertEqual(self.h.get(a['id'])['amount'],1)
    def test_reopen_deduplicates(self):
        a=self.add();self.h.close();self.h=WorldHistory(self.path);self.assertEqual(self.add()['id'],a['id'])
    def test_restore_branch_repeats_are_new(self):
        a=self.add();self.h.stream('rewound',metadata={'restore':True},parent={'stream':'run','through_seq':a['seq']})
        b=self.h.append('rewound','observer','one',hit());self.assertNotEqual(a['id'],b['id'])
    def test_unknown_parent_rejected(self):
        with self.assertRaises(ValueError):self.h.stream('x',metadata={},parent={'stream':'missing','through_seq':0})
    def test_parent_foreign_event(self):
        self.h.stream('other',metadata={});e=self.h.append('other','p','1',hit())
        with self.assertRaises(ValueError):self.h.stream('x',metadata={},parent={'stream':'run','through_seq':e['seq']})
    def test_metadata_cannot_change(self):
        with self.assertRaises(ValueError):self.h.stream('run',metadata={'source':'changed'})
    def test_schema_unknown_rejected(self):
        self.h.db.execute('PRAGMA user_version=99');self.h.db.commit()
        with self.assertRaises(ValueError):WorldHistory(self.path)
    def test_no_update(self):
        self.add()
        with self.assertRaises(sqlite3.IntegrityError):self.h.db.execute("UPDATE events SET kind='changed'")
    def test_no_delete(self):
        self.add()
        with self.assertRaises(sqlite3.IntegrityError):self.h.db.execute('DELETE FROM events')
    def test_source_object_mutation_no_effect(self):
        e=hit();a=self.add(event=e);e['cause']['actor_id']='wrong';self.assertEqual(self.h.get(a['id'])['cause']['actor_id'],'guard')
    def test_query_mutation_no_effect(self):
        a=self.add();v=self.h.get(a['id']);v['cause']['actor_id']='wrong';self.assertEqual(self.h.get(a['id'])['cause']['actor_id'],'guard')
    def test_reserved_identity_rejected(self):
        for k in ('seq','id','stream','producer','occurrence','fingerprint'):
            with self.subTest(k=k),self.assertRaises(ValueError):self.add(event=hit(**{k:'forged'}))
    def test_missing_stream_rejected(self):
        with self.assertRaises(ValueError):self.h.append('missing','p','1',hit())
    def test_oversize_rejected(self):
        with self.assertRaises(ValueError):self.add(event=hit(message='x'*17000))
        self.assertEqual(self.h.high_watermark,0)
    def test_capacity_holds_without_eviction(self):
        self.h.max_events=1;first=self.add()
        with self.assertRaises(OverflowError):self.add('two')
        self.assertEqual(self.h.get(first['id'])['amount'],1)
    def test_duplicate_at_capacity_allowed(self):
        self.h.max_events=1;self.add();self.assertFalse(self.add()['inserted'])
    def test_storage_failure_preserves_previous(self):
        a=self.add();self.h.db.execute('PRAGMA query_only=ON')
        with self.assertRaises(sqlite3.OperationalError):self.add('two')
        self.assertEqual(self.h.high_watermark,1);self.assertIsNotNone(self.h.get(a['id']))
    def test_player_hidden_by_default(self):
        a=self.add();self.assertEqual(self.h.events(perspective='player')['events'],[]);self.assertIsNone(self.h.get(a['id'],perspective='player'))
    def test_player_does_not_inherit_attacker(self):
        public=hit(cause={'actor_id':None,'damage_type':'unknown'},observation_basis='authored HUD')
        a=self.add(player=public);self.assertIsNone(self.h.get(a['id'],perspective='player')['cause']['actor_id'])
    def test_invalid_projection(self):
        with self.assertRaises(ValueError):self.add(player={'kind':'objective'})
    def test_cause_mapping(self):
        with self.assertRaises(ValueError):self.add(event=hit(cause='nearest entity'))
    def test_unknown_cause_preserved(self):
        a=self.add(event=hit(cause={'actor_id':None,'damage_type':'unknown'}));self.assertIsNone(self.h.get(a['id'])['cause']['actor_id'])
    def test_same_slot_different_occurrences(self):
        for i in range(2):self.add(str(i),hit(context={'effect_slot':0}))
        self.assertEqual(self.h.high_watermark,2)
    def test_negative_sentinel_not_damage_amount(self):
        with self.assertRaises(ValueError):self.add(event=hit(health_after=-1,amount=17))
    def test_terminal_state_no_fabricated_damage(self):
        a=self.add(event={'kind':'terminal-state','health_before':16,'health_after':-1,'damage_amount':None})
        self.assertIsNone(self.h.get(a['id'])['damage_amount'])
    def test_snapshot_aggregate_not_hit_count(self):
        self.add(event={'kind':'health-change','health_before':16,'health_after':10,'hit_count':None})
        text=render_summary(self.h.summarize());self.assertNotIn('hit occurrence',text)
    def test_amount_bool_refused(self):
        with self.assertRaises(ValueError):self.add(event=hit(amount=True))
    def test_amount_mismatch(self):
        with self.assertRaises(ValueError):self.add(event=hit(amount=2))
    def test_tick_bound(self):
        for tick in (-1,1.5,True):
            with self.subTest(tick=tick),self.assertRaises(ValueError):self.add(event=hit(guest_tick=tick))
    def test_nan(self):
        with self.assertRaises(ValueError):self.add(event=hit(value=float('nan')))
    def test_group_only_display(self):
        for i in range(10):self.add(str(i))
        page=self.h.summarize();self.assertEqual(page['groups'][0]['count'],10);self.assertEqual(self.h.high_watermark,10)
    def test_notice_splits_burst(self):
        self.add('a');self.add('notice',{'kind':'objective','message':'Door unlocked'});self.add('b')
        self.assertEqual([g['kind'] for g in self.h.summarize()['groups']],['damage','objective','damage'])
    def test_changed_source_splits(self):
        self.add('a');self.add('b',hit(cause={'actor_id':'other','damage_type':'projectile'}));self.assertEqual(len(self.h.summarize()['groups']),2)
    def test_changed_amount_splits(self):
        self.add('a');self.add('b',hit(health_after=14,amount=2));self.assertEqual(len(self.h.summarize()['groups']),2)
    def test_changed_damage_type_splits(self):
        self.add('a');self.add('b',hit(cause={'actor_id':'guard','damage_type':'collision'}));self.assertEqual(len(self.h.summarize()['groups']),2)
    def test_changed_stream_splits(self):
        self.add();self.h.stream('new',metadata={});self.h.append('new','p','1',hit());self.assertEqual(len(self.h.summarize()['groups']),2)
    def test_time_gap_splits(self):
        self.add('a');self.add('b',hit(guest_tick=2000));self.assertEqual(len(self.h.summarize()['groups']),2)
    def test_time_backwards_splits(self):
        self.add('a');self.add('b',hit(guest_tick=1));self.assertEqual(len(self.h.summarize()['groups']),2)
    def test_pagination_no_loss(self):
        for i in range(30):self.add(str(i),{'kind':'notice','message':str(i)})
        after=0;seen=[]
        while after<self.h.high_watermark:
            p=self.h.summarize(after=after,max_rows=3);seen.extend(g['first_seq'] for g in p['groups']);after=p['consumed_through']
        self.assertEqual(seen,list(range(1,31)))
    def test_stable_upper_watermark(self):
        self.add('a');high=self.h.high_watermark;self.add('b');self.assertEqual(len(self.h.events(through=high)['events']),1)
    def test_read_does_not_ack(self):
        self.add();self.h.summarize();self.assertEqual(self.h.cursor('reader'),0)
    def test_ack_independent_consumers(self):
        self.add();p=self.h.summarize();self.h.acknowledge('a',p);self.assertEqual(self.h.cursor('a'),1);self.assertEqual(self.h.cursor('b'),0)
    def test_no_backwards_ack(self):
        self.add();self.h.acknowledge('a',self.h.summarize())
        with self.assertRaises(ValueError):self.h.acknowledge('a',{'perspective':'diagnostic','consumed_through':0,'high_watermark':1})
    def test_diagnostic_ack_does_not_ack_player(self):
        self.add();self.h.acknowledge('a',self.h.summarize());self.assertEqual(self.h.cursor('a',perspective='player'),0)
    def test_export_never_overwrites(self):
        self.add();p=self.path.parent/'events.jsonl';self.h.export_jsonl(p)
        with self.assertRaises(FileExistsError):self.h.export_jsonl(p)
    def test_export_individual_hits(self):
        self.add('a');self.add('b');p=self.path.parent/'events.jsonl';self.h.export_jsonl(p);self.assertEqual(len(p.read_text().splitlines()),2)
    def test_display_is_bounded(self):
        for i in range(20):self.add(str(i),{'kind':'notice','message':'x'*1000})
        text=render_summary(self.h.summarize(max_rows=20),max_chars=300);self.assertLessEqual(len(text),300);self.assertIn('clipped',text)
    def test_player_reads_are_passive(self):
        from fdisbull_player import Player
        self.add();base=Base();b=HistoryBackend(base,self.h);p=Player(b)
        self.assertIn('1 hit',p.execute('examine history'));self.assertIn('"victim_id"',p.execute('examine event 1'));self.assertEqual(base.calls,0)
    def test_history_never_grants_action(self):
        b=HistoryBackend(Base(),self.h);self.assertEqual(b.act({'verb':'fire'})['effects'],'none-confirmed')
    def test_history_observation_isolated_copy(self):
        self.add();b=HistoryBackend(Base(),self.h);a=b.observe();a['objects'].clear();self.assertTrue(b.observe()['objects'])
    def test_burst_does_not_bury_notice(self):
        self.add('notice',{'kind':'objective','message':'Target escaped'})
        # One SQLite transaction per real event, including repeated identical data.
        for i in range(4200):self.add(str(i))
        ns=self.h.recent(notices_only=True);self.assertEqual(ns[0]['message'],'Target escaped')
        b=HistoryBackend(Base(),self.h);obs=b.observe();s=next(e for e in obs['objects'] if e['id']=='world-history-notices');self.assertIn('Target escaped',s['description'])
    def test_two_connections_preserve_origin(self):
        with WorldHistory(self.path) as other:
            a=self.add();b=other.append('run','observer','one',hit());self.assertEqual(a['id'],b['id'])

class CausalHistoryTests(unittest.TestCase):
    setUp=HistoryTests.setUp
    tearDown=HistoryTests.tearDown
    add=HistoryTests.add
    def test_terminal_links_contact(self):
        a=self.add('contact',{'kind':'damage-contact','victim_id':'person-0','cause':{'source_entity_id':'car','damage_type':'vehicle-contact'}})
        b=self.add('terminal',{'kind':'terminal-state','health_before':16,'health_after':-1,'damage_amount':None,'causal_parents':[a['id']]})
        self.assertEqual(self.h.get(b['id'])['causal_parents'],[a['id']])
    def test_unknown_parent_refused(self):
        with self.assertRaises(ValueError):self.add(event=hit(causal_parents=['invented']))
    def test_cross_timeline_cause_refused(self):
        a=self.add();self.h.stream('other',metadata={})
        with self.assertRaises(ValueError):self.h.append('other','p','1',hit(causal_parents=[a['id']]))
    def test_duplicate_parent_refused(self):
        a=self.add()
        with self.assertRaises(ValueError):self.add('b',hit(causal_parents=[a['id'],a['id']]))
    def test_contacts_not_counted_as_health_hits(self):
        for i in range(3):self.add(str(i),{'kind':'damage-contact','victim_id':'p','cause':{'damage_type':'laser'},'amount':0})
        t=render_summary(self.h.summarize());self.assertIn('3 contact observation',t);self.assertNotIn('hit occurrence',t)
    def test_contact_does_not_hide_notice(self):
        self.add('n',{'kind':'objective','message':'done'})
        self.add('c',{'kind':'damage-contact','victim_id':'p'})
        self.assertEqual([x['kind'] for x in self.h.recent(notices_only=True)],['objective'])
    def test_contact_source_change_splits(self):
        for i in range(2):self.add(str(i),{'kind':'damage-contact','victim_id':'p','cause':{'source_entity_id':'car'+str(i)}})
        self.assertEqual(len(self.h.summarize()['groups']),2)
    def test_health_and_contact_do_not_coalesce(self):
        self.add('a');e=hit();e['kind']='damage-contact';self.add('b',e)
        self.assertEqual(len(self.h.summarize()['groups']),2)
    def test_metadata_history_label_visible(self):
        self.add();self.assertIn('[run]',render_summary(self.h.summarize()))


class ForeignDatabaseTests(unittest.TestCase):
    def test_other_log_database_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'other.sqlite';db=sqlite3.connect(p);db.execute('CREATE TABLE logs(message TEXT)');db.execute("INSERT INTO logs VALUES('keep')");db.commit();db.close();before=p.read_bytes()
            with self.assertRaises(ValueError):WorldHistory(p)
            self.assertEqual(p.read_bytes(),before)
    def test_broken_history_not_recreated(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.sqlite';db=sqlite3.connect(p);db.execute('PRAGMA user_version=1');db.close()
            with self.assertRaises(ValueError):WorldHistory(p)
    def test_bool_capacity_not_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):WorldHistory(Path(d)/'x',max_events=True)

if __name__=='__main__':unittest.main()
