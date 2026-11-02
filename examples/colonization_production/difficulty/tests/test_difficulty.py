"""Authored contract regressions, not additional original-game executions."""
import sys
from pathlib import Path
from copy import deepcopy
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from build_difficulty_uil import make
from build_uil import make as previous_make
from fdisbull.common_uil import digest
from fdisbull.uil_runtime import execute_program

def run(entry,args,edition='DOS'):
    p,v,_=make(edition);p['entry']=entry;v['program_sha256']=digest(p)
    r=execute_program(p,v,inputs=args)
    return r

def values(entry,args,edition='DOS'):
    r=run(entry,args,edition)
    assert r['status']=='complete', r
    return r['outputs']

class DifficultyTests(unittest.TestCase):
    def test_first_penalty_boundary_at_each_level(self):
        for difficulty,limit in enumerate((10,9,8,7,6)):
            self.assertEqual(values(7,[difficulty,limit-1,0,True,False,False]),[limit-1,limit,0])
            self.assertEqual(values(7,[difficulty,limit,0,True,False,False]),[limit,limit,-1])
    def test_multiple_penalties(self):
        self.assertEqual(values(7,[4,18,0,True,False,False]),[18,6,-3])
    def test_rounding_boundary(self):
        for sol,tories in ((49,1),(50,1),(51,0)):
            self.assertEqual(values(7,[4,1,sol,True,False,False])[0],tories)
    def test_nonhuman_bypasses_tories(self):
        for d in range(5):
            self.assertEqual(values(7,[d,31,0,False,False,False]),[0,10,0])
    def test_status_flags_are_independent_inputs(self):
        for a,b in ((False,False),(True,False),(False,True),(True,True)):
            self.assertEqual(values(7,[4,12,0,True,a,b])[-1],-2+int(a)+int(b))
    def test_sol_does_not_silently_create_flags(self):
        self.assertEqual(values(7,[4,12,100,True,False,False])[-1],0)
        self.assertEqual(values(7,[4,12,100,True,True,True])[-1],2)
    def test_center_food_bonus(self):
        # Authored terrain 13 belongs to the tested two-food classification.
        self.assertEqual([values(8,[d,13])[0] for d in range(5)],[4,3,2,2,2])
    def test_zero_base_food_is_still_modified(self):
        self.assertEqual([values(8,[d,24])[0] for d in range(5)],[2,1,0,0,0])
    def test_secondary_good_present_bonus(self):
        self.assertEqual([values(9,[d])[0] for d in range(5)],[1,0,0,0,0])
    def test_building_modifier_order(self):
        self.assertEqual(values(10,[3,-1,2,False]),[5])
        self.assertNotEqual(values(10,[3,-1,2,False]),[(3-1)*2])
        self.assertEqual(values(10,[3,-1,3,False]),[7])
    def test_expert_uses_already_adjusted_output(self):
        self.assertEqual(values(10,[3,-1,3,True]),[14])
    def test_output_clamps_at_zero(self):
        self.assertEqual(values(10,[1,-5,3,True]),[0])
    def test_bad_difficulty_refused(self):
        for d in (5,255):
            self.assertEqual(run(7,[d,12,0,True,False,False])['status'],'refused')
    def test_bad_population_refused(self):
        self.assertEqual(run(7,[0,32,0,True,False,False])['status'],'refused')
    def test_bad_rebel_percent_refused(self):
        self.assertEqual(run(7,[0,12,101,True,False,False])['status'],'refused')
    def test_bad_worker_profile_refused(self):
        for args in ([0,0,3,False],[4,0,3,False],[3,-6,3,False],[3,3,3,False],[3,0,4,False]):
            self.assertEqual(run(10,args)['status'],'refused')
    def test_integer_does_not_impersonate_boolean(self):
        try:r=run(10,[3,0,3,1])
        except ValueError:return
        self.assertEqual(r['status'],'refused')
    def test_fixed_gross_discrepancy_all_five_levels(self):
        for d in range(5):
            inputs=[d,12,0,0,0,0,13,3,False,3,9,0,0,False]
            self.assertEqual(values(11,inputs,'DOS')[-1],0)
            self.assertEqual(values(11,inputs,'WIN')[-1],3)
    def test_lower_building_grade_rejoins(self):
        for d in range(5):
            inputs=[d,12,0,0,0,0,13,3,False,2,9,0,0,False]
            self.assertEqual(values(11,inputs,'DOS'),values(11,inputs,'WIN'))
    def test_coupled_modifier_changes_size_not_rule_identity(self):
        for d in range(5):
            inputs=[d,12,0,0,0,0,13,3,False,3,9,0,0,True]
            dos=values(11,inputs,'DOS');win=values(11,inputs,'WIN')
            self.assertEqual(dos[-1],0)
            self.assertEqual(win[-1],3 if d<4 else 2)
            self.assertEqual(dos[5],7 if d<4 else 6)
    def test_new_modifier_functions_identical_in_both_editions(self):
        p,v,_=make('DOS');q,w,_=make('WIN')
        self.assertEqual(p['functions'][7:11],q['functions'][7:11])
        self.assertEqual(v['functions'][7:11],w['functions'][7:11])
    def test_previous_definitions_preserved(self):
        for edition in ('DOS','WIN'):
            p,v,_=make(edition);old,ov,_=previous_make(edition)
            self.assertEqual(p['functions'][:7],old['functions'])
            self.assertEqual(v['functions'][:7],ov['functions'])
    def test_incorrect_fixed_divisor_is_detected(self):
        self.assertEqual(values(7,[4,6,0,True,False,False])[-1],-1)
        self.assertNotEqual(values(7,[4,6,0,True,False,False])[-1],-(6//10))
    def test_incorrect_linear_food_bonus_is_detected(self):
        self.assertNotEqual(values(8,[4,13])[0],2+(2-4))

if __name__=='__main__': unittest.main(verbosity=2)
