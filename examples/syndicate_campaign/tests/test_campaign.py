"""Authored source-free fixtures; no original save or game is bundled."""
from pathlib import Path
from copy import deepcopy
import io,json,struct,sys,tempfile,unittest,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from campaign import *
from save_seed import inspect_archive,qualification


def authored_save():
    b=bytearray(SAVE_SIZE)
    struct.pack_into('<I',b,20,30000)
    for i in range(50):b[8396+i*10+2]=1
    for start,count,stride,prog,base in [(8896,20,501,17,13),(18916,18,491,8,6)]:
        for i in range(count):
            o=start+i*stride;b[o]=i;struct.pack_into('<i',b,o+1,750);struct.pack_into('<H',b,o+base,4);struct.pack_into('<h',b,o+prog,0)
    b[27754:27757]=bytes([0,2,4]);struct.pack_into('<iH',b,27757,9,4)
    return bytes(b)


def authored_catalog():
    return {'source_sha256':MAIN_SHA256,'territories':[{'id':i,'label':f'Territory {i}',
             'mission_number':1 if i==9 else i+2,'outgoing':[4] if i==9 else []} for i in range(50)],
            'projects':{f:[{'id':i,'label':f'{f} project {i}'} for i in range(n)] for f,n in [('weapon',20),('mod',18)]}}


class CampaignTests(unittest.TestCase):
    def setUp(self):self.raw=authored_save();self.c=decode_save(self.raw,source_sha256=MAIN_SHA256);self.cat=authored_catalog()
    def test_size_partition(self):
        self.assertEqual(SECTIONS[0][1],20)
        for a,b in zip(SECTIONS,SECTIONS[1:]):self.assertEqual(a[1]+a[2],b[1])
        self.assertEqual(SECTIONS[-1][1]+SECTIONS[-1][2],SAVE_SIZE)
    def test_wrong_size(self):
        for data in [self.raw[:-1],self.raw+b'0',bytes(10288)]:
            with self.assertRaises(ValueError):decode_save(data,source_sha256=MAIN_SHA256)
    def test_foreign_source(self):
        with self.assertRaises(ValueError):decode_save(self.raw,source_sha256='0'*64)
    def test_counts(self):self.assertEqual((len(self.c['companies']),len(self.c['territories']),len(self.c['projects']['weapon']),len(self.c['projects']['mod'])),(8,50,20,18))
    def test_company_range(self):
        for i in [-1,8,True]:
            with self.assertRaises(ValueError):decode_save(self.raw,source_sha256=MAIN_SHA256,selected_company=i)
    def test_owner_range(self):
        b=bytearray(self.raw);b[8398]=8
        with self.assertRaises(ValueError):decode_save(bytes(b),source_sha256=MAIN_SHA256)
    def test_funding_range(self):
        for i in [-2,10,10000]:
            b=bytearray(self.raw);struct.pack_into('<i',b,27757,i)
            with self.assertRaises(ValueError):decode_save(bytes(b),source_sha256=MAIN_SHA256)
    def test_next_project_range(self):
        b=bytearray(self.raw);b[8896+499]=20
        with self.assertRaises(ValueError):decode_save(bytes(b),source_sha256=MAIN_SHA256)
    def test_unknown_kind(self):
        b=bytearray(self.raw);b[27755]=3
        with self.assertRaises(ValueError):decode_save(bytes(b),source_sha256=MAIN_SHA256)
    def test_unknown_status(self):
        b=bytearray(self.raw);b[27754]=4
        with self.assertRaises(ValueError):decode_save(bytes(b),source_sha256=MAIN_SHA256)
    def test_active_graph_overrides_stale_record(self):
        self.c['active']['history'][:6]=list(range(100,700,100));self.assertEqual(effective_progress(self.c,'weapon',4),600);self.assertEqual(self.c['projects']['weapon'][4]['stored_progress'],0)
    def test_inactive_uses_record(self):self.c['projects']['mod'][1]['stored_progress']=-1;self.assertEqual(effective_progress(self.c,'mod',1),-1)
    def test_graph_hole(self):
        with self.assertRaises(ValueError):graph_progress([100,0,200]+[0]*237)
    def test_graph_reversal(self):
        with self.assertRaises(ValueError):graph_progress([200,100]+[0]*238)
    def test_graph_length(self):
        with self.assertRaises(ValueError):graph_progress([0])
    def test_no_automatic_state_flag(self):
        c=deepcopy(self.c);c['companies'][0]['cash']=399;r=research_tick(c);self.assertEqual(r['return_al'],3);self.assertEqual(r['campaign']['active']['state'],0)
    def test_exact_affordability(self):
        self.c['companies'][0]['cash']=400;r=research_tick(self.c);self.assertEqual((r['charged'],r['campaign']['companies'][0]['cash'],r['return_al']),(400,0,0))
    def test_insufficient_does_not_consume_graph(self):
        self.c['companies'][0]['cash']=399;r=research_tick(self.c);self.assertEqual(r['campaign'],self.c)
    def test_no_selection_is_idle(self):self.c['active']['kind']=0;self.assertEqual(research_tick(self.c)['return_al'],2)
    def test_paused_no_charge(self):self.c['active']['funding_index']=-1;self.assertEqual(research_tick(self.c)['campaign'],self.c)
    def test_input_not_mutated(self):
        old=deepcopy(self.c);research_tick(self.c);self.assertEqual(old,self.c)
    def test_graph_full_refused(self):
        self.c['active']['history']=[10]*240
        with self.assertRaises(ValueError):research_tick(self.c)
    def test_completed_tick_refused(self):
        self.c['active']['history'][0]=2400
        with self.assertRaises(ValueError):research_tick(self.c)
    def test_daily_is_not_progress(self):
        r=funding_rows(4);self.assertEqual(r[0]['display_daily_charge'],96);self.assertEqual(r[9]['display_daily_charge'],9600);self.assertEqual(r[9]['progress_per_hour'],100)
    def test_original_word_rounding(self):
        self.c['active']['history'][0]=2390;self.c['active']['funding_index']=2;r=research_tick(self.c);self.assertEqual(r['campaign']['active']['history'][1],2420)
    def test_completion_unlock_not_price(self):
        a=self.c['active'];a['history'][:23]=range(100,2400,100)
        p=self.c['projects']['weapon'];p[4].update(price_signed=-750,next_project=5);p[5]['stored_progress']=-1
        r=research_tick(self.c);self.assertEqual(r['return_al'],1);self.assertEqual(r['campaign']['projects']['weapon'][5]['stored_progress'],0);self.assertEqual(r['campaign']['projects']['weapon'][4]['price_signed'],-750)
    def test_finalizer_separate(self):
        self.c['active']['history'][:23]=range(100,2400,100);self.c['projects']['weapon'][4]['price_signed']=-750
        r=research_tick(self.c);f=finalize_completed(r['campaign']);self.assertEqual(f['active']['kind'],0);self.assertEqual(f['projects']['weapon'][4]['price_signed'],750);self.assertEqual(f['active']['history'],[0]*240)
    def test_premature_finalize_refused(self):
        with self.assertRaises(ValueError):finalize_completed(self.c)
    def test_no_erase_already_unlocked_successor(self):
        self.c['active']['history'][:23]=range(100,2400,100);p=self.c['projects']['weapon'];p[4]['next_project']=5;p[5]['stored_progress']=100
        self.assertEqual(research_tick(self.c)['campaign']['projects']['weapon'][5]['stored_progress'],100)
    def test_mod_completion(self):
        self.c['active'].update(kind=1,project=1);self.c['active']['history'][:23]=range(100,2400,100);p=self.c['projects']['mod'];p[1]['next_project']=2;p[2]['stored_progress']=-1
        r=research_tick(self.c);self.assertEqual(r['campaign']['projects']['mod'][2]['stored_progress'],0);self.assertEqual(finalize_completed(r['campaign'])['active']['state'],2)
    def test_only_initial_mission(self):self.assertEqual([i for i in range(50) if available(self.c,self.cat,i,override=False)],[9])
    def test_unknown_runtime_flag(self):self.assertIsNone(available(self.c,self.cat,9,override=None))
    def test_owned_is_not_available(self):self.c['territories'][9]['owner_raw']=0;self.assertFalse(available(self.c,self.cat,9,override=False))
    def test_directed_unlock(self):
        self.c['territories'][9]['owner_raw']=0;self.assertTrue(available(self.c,self.cat,4,override=False));self.assertFalse(available(self.c,self.cat,10,override=False))
    def test_status255_path(self):self.c['territories'][10]['status_raw']=255;self.assertTrue(available(self.c,self.cat,10,override=False))
    def test_override_explicit(self):self.assertTrue(available(self.c,self.cat,49,override=True))
    def test_catalog_mismatch(self):
        self.cat['source_sha256']='bad'
        with self.assertRaises(ValueError):available(self.c,self.cat,0,override=False)
    def test_invalid_territory(self):
        for i in [-1,50,True]:
            with self.assertRaises(ValueError):available(self.c,self.cat,i,override=False)
    def test_passive_provider(self):
        p=CampaignProvider(self.c,self.cat,override=False);before=p.observe();self.assertEqual(p.observe(),before);self.assertEqual(p.act({'verb':'research'})['status'],'rejected');self.assertEqual(p.observe(),before)
    def test_existing_player(self):
        from fdisbull_player.player import Player
        p=CampaignProvider(self.c,self.cat,override=False);player=Player(p);before=p.observe()
        for cmd in ['look','examine mission selection','examine research','examine mods','examine equipment']:
            self.assertEqual(player.execute_result(cmd)['status'],'read')
        self.assertFalse(player.execute_result('research mods')['action_sent']);self.assertEqual(before,p.observe())
    def test_disabled_records_not_presented(self):self.c['projects']['weapon'][4]['disabled_record']=True;self.assertNotIn('weapon-04',render(self.c,self.cat))


class SaveCorpusTests(unittest.TestCase):
    def archive(self, rows):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            for name,data in rows:z.writestr(name,data)
        return buf.getvalue()
    def inspect(self,rows,expected={'SAVE/00.GAM'},**kwargs):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'candidate.zip';p.write_bytes(self.archive(rows));return inspect_archive(p,expected_paths=expected,**kwargs)
    def test_candidate_not_compatible(self):r=self.inspect([('SAVE/00.GAM',b'data')]);self.assertEqual(r['status'],'candidate');self.assertFalse(r['native_compatible'])
    def test_missing(self):self.assertEqual(self.inspect([],expected={'SAVE/00.GAM'})['missing'],['SAVE/00.GAM'])
    def test_executable(self):
        with self.assertRaises(ValueError):self.inspect([('RUN.EXE',b'MZ')],expected={'RUN.EXE'})
    def test_traversal(self):
        with self.assertRaises(ValueError):self.inspect([('../SAVE/00.GAM',b'x')])
    def test_extra(self):
        with self.assertRaises(ValueError):self.inspect([('SAVE/00.GAM',b'x'),('extra.txt',b'x')])
    def test_case_collision(self):
        with self.assertRaises(ValueError):self.inspect([('SAVE/00.GAM',b'x'),('save/00.gam',b'y')],expected={'SAVE/00.GAM','save/00.gam'})
    def test_budget(self):
        with self.assertRaises(ValueError):self.inspect([('SAVE/00.GAM',b'xx')],byte_budget=1)
    def test_parse_does_not_qualify(self):self.assertEqual(qualification({'parsed':True})['status'],'not-qualified')
    def test_loaded_does_not_qualify(self):self.assertEqual(qualification({'original_loader_completed':True})['status'],'not-qualified')
    def test_complete_gates_scoped(self):
        r={k:True for k in ['edition_identity_checked','bundle_complete','original_loader_completed','state_invariants_checked','required_system_observed','original_tick_observed','save_reload_checked','candidate_preserved']};r.update(origin='diagnostic-generated',scope='one project')
        q=qualification(r);self.assertEqual(q['status'],'qualified-for-recorded-slice');self.assertFalse(q['normal_progression_proven']);self.assertTrue(q['requires_intervention_label'])


if __name__=='__main__':unittest.main(verbosity=2)
