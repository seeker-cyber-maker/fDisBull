"""Provided portable text-value contracts; no host text output is executed."""
import unittest

from uil_text_study import run as run_text


class TextServiceTests(unittest.TestCase):
    def doc(self):
        return {'format':'uil-text-study-1', 'program':{
            'variables':[{'type':'i64'},{'type':'text'}], 'constants':[{'type':'text'}],
            'inputs':[0], 'outputs':[1], 'max_steps':10, 'body':[
                {'op':'set','dst':1,'value':{'op':'text.format','parts':[
                    {'text':{'const':0}}, {'decimal':{'var':0},'width':5,'pad':'0'}]}},
                {'op':'effect','service':'text.display','value':{'var':1}}]},
            'bindings':{'initial':[0,''],'constants':['Health: ']}}
    def test_dynamic_text_preserves_sign_and_does_not_do_io(self):
        r=run_text(self.doc(),[-7]);self.assertEqual(r['status'],'pending_host')
        self.assertEqual(r['events'],[{'service':'text.display','text':'Health: -0007'}])
        self.assertEqual(r['state'],[-7,'']);self.assertEqual(r['proposed_state'],[-7,'Health: -0007'])
    def test_i64_format_not_reduced_to_float(self):
        r=run_text(self.doc(),[9007199254740993])
        self.assertEqual(r['events'][0]['text'],'Health: 9007199254740993')
    def test_later_refusal_discards_staged_text_and_changes(self):
        d=self.doc();d['program']['constants'].append({'type':'bool'});d['bindings']['constants'].append(False)
        d['program']['body'].append({'op':'require','condition':{'const':1}})
        r=run_text(d,[-7]);self.assertEqual(r['status'],'refused');self.assertEqual(r['events'],[])
        self.assertEqual(r['state'],[-7,''])


if __name__ == '__main__':
    unittest.main(verbosity=2)
