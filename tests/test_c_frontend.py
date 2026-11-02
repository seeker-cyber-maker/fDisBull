"""Independent small contract cases for the Clang-backed C importer.

These run real Clang and the installed fDisBull evaluator. They do not run Ghidra.
"""
from pathlib import Path
import ctypes
import hashlib
import importlib.util
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]
MODULE=next((p for p in (BASE/'src/fdisbull/console_synthesis/c_frontend.py',
                       BASE/'fdisbull/console_synthesis/c_frontend.py') if p.is_file()),None)
if MODULE is None: raise RuntimeError('C frontend source file not found')
spec=importlib.util.spec_from_file_location('route_c_frontend_tests',MODULE)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
CLANG=Path(shutil.which('clang') or '/unavailable/clang')


class CompilerAvailabilityTests(unittest.TestCase):
    def test_missing_clang_is_an_explicit_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.c'
            source.write_text('unsigned f(unsigned x){return x;}\n')
            with self.assertRaisesRegex(m.CFrontendRefused, 'explicit Clang path required'):
                m.import_c(source, 'f', clang=root / 'missing-clang')


@unittest.skipUnless(CLANG.is_file(), 'Clang is required for typed-C AST and native-oracle checks')
class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def get(self,text,bindings=None):
        path=self.root/'input.c';path.write_text(text+'\n')
        return m.import_c(path,'f',clang=CLANG,bindings=bindings)
    def native(self,text,argtype,restype=ctypes.c_uint8):
        key=hashlib.sha256(text.encode()).hexdigest()[:16]
        source=self.root/(key+'.c');out=self.root/(key+'.so');source.write_text(text)
        subprocess.run([str(CLANG),'-O2','-std=c11','-shared','-fPIC',str(source),'-o',str(out)],check=True,capture_output=True,timeout=15)
        self.lib=ctypes.CDLL(str(out));fn=self.lib.f;fn.argtypes=[argtype,argtype];fn.restype=restype;return fn
    def test_promoted_arithmetic_before_narrowing(self):
        f=self.get('unsigned char f(unsigned char x){return (unsigned char)(x+x+x+7);}')
        for x in range(256):self.assertEqual(f.run({'$arg_x':x})['return'],(3*x+7)%256)
    def test_unsigned_negative_conversion(self):
        f=self.get('unsigned char f(unsigned char x){return (unsigned char)(x-200);}')
        for x in range(256):self.assertEqual(f.run({'$arg_x':x})['return'],(x-200)%256)
    def test_branch_join(self):
        f=self.get('unsigned char f(unsigned char x){unsigned char y;if(x<128)y=5;else y=9;return y;}')
        for x in (0,127,128,255):self.assertEqual(f.run({'$arg_x':x})['return'],5 if x<128 else 9)
    def test_early_return_preserves_continuation(self):
        f=self.get('unsigned char f(unsigned char x){if(x==1)return 7;x=42;return x;}')
        for x in range(256):self.assertEqual(f.run({'$arg_x':x})['return'],7 if x==1 else 42)
    def test_branch_local_return_initialization(self):
        f=self.get('unsigned char f(unsigned char x){unsigned char y;if(x)return 7;else y=9;return y;}')
        self.assertEqual(f.run({'$arg_x':0})['return'],9);self.assertEqual(f.run({'$arg_x':1})['return'],7)
    def test_bool_input_rejected_explicitly(self):
        f=self.get('unsigned char f(unsigned char x){return x;}')
        with self.assertRaises(m.CFrontendRefused):f.run({'$arg_x':True})
    def test_c_scalar_argument_is_mutable_copy(self):
        f=self.get('unsigned char f(unsigned char x){x=3;return x;}')
        self.assertEqual(f.run({'$arg_x':12})['return'],3)
    def test_all_six_signed32_relations(self):
        values=[-2147483648,-2147483647,-65536,-1,0,1,65535,2147483646,2147483647]
        for op in ('<','<=','>','>=','==','!='):
            with self.subTest(op=op):
                text='unsigned char f(int x,int y){return x '+op+' y;}'
                imp=self.get(text);fn=self.native(text,ctypes.c_int32)
                for x in values:
                    for y in values:self.assertEqual(imp.run({'$arg_x':x,'$arg_y':y})['return'],fn(x,y))
    def test_all_six_unsigned32_relations(self):
        values=[0,1,255,256,65535,2147483647,2147483648,4294967294,4294967295]
        for op in ('<','<=','>','>=','==','!='):
            with self.subTest(op=op):
                text='unsigned char f(unsigned x,unsigned y){return x '+op+' y;}'
                imp=self.get(text);fn=self.native(text,ctypes.c_uint32)
                for x in values:
                    for y in values:self.assertEqual(imp.run({'$arg_x':x,'$arg_y':y})['return'],fn(x,y))
    def test_mask_and_shift(self):
        f=self.get('unsigned char f(unsigned char x){return (x>>3)&7;}')
        for x in range(256):self.assertEqual(f.run({'$arg_x':x})['return'],(x>>3)&7)
    def test_partial_output_write_refused(self):
        with self.assertRaisesRegex(m.CFrontendRefused,'unspecified initial memory'):
            self.get('unsigned f(unsigned *p,unsigned x){if(x)p[0]=7;return 0;}',
                     {'p':{'kind':'output_buffer','cells':[{'label':'$out'}]}})
    def test_output_written_on_all_paths(self):
        f=self.get('unsigned f(unsigned *p,unsigned char x){if(x)p[0]=7;else p[0]=9;return 0;}',
                   {'p':{'kind':'output_buffer','cells':[{'label':'$out'}]}})
        self.assertEqual(f.run({'$arg_x':0}),{'return':0,'$out':9})
        self.assertEqual(f.run({'$arg_x':1}),{'return':0,'$out':7})
    def test_full_input_domain_in_serialized_uil(self):
        from fdisbull.interaction_il import execute_il
        f=self.get('unsigned f(unsigned x){return x+1;}',{'x':{'max':7}})
        state=f.state({'$arg_x':3});state['$arg_x']=8
        self.assertEqual(execute_il(f.document,state)['status'],'refused')
    def test_private_return_flag_reset(self):
        from fdisbull.interaction_il import execute_il
        f=self.get('unsigned f(unsigned x){return x;}');state=f.state({'$arg_x':3})
        state['$returned']=True
        self.assertEqual(execute_il(f.document,state)['state']['$return_value'],3)
    def test_repeat_import_ignores_clang_internal_pointer_ids(self):
        text='unsigned char f(unsigned char x){return (unsigned char)(x+7);}'
        a=self.get(text);b=self.get(text)
        self.assertEqual(a.document,b.document)
        self.assertEqual(a.source_sha256,b.source_sha256)
    def test_loop_refused(self):
        with self.assertRaises(m.CFrontendRefused):self.get('unsigned f(unsigned x){while(x)x=x-1;return x;}')
    def test_signed_overflow_refused(self):
        with self.assertRaisesRegex(m.CFrontendRefused,'signed arithmetic overflow'):self.get('int f(int x){return x+1;}')
    def test_signed_conversion_refused(self):
        with self.assertRaisesRegex(m.CFrontendRefused,'signed conversion'):self.get('short f(unsigned x){return (short)x;}')
    def test_unknown_calls_refused(self):
        with self.assertRaises(m.CFrontendRefused):self.get('unsigned g(unsigned);unsigned f(unsigned x){return g(x);}')
    def test_uninitialized_local_refused(self):
        with self.assertRaises(m.CFrontendRefused):self.get('unsigned f(unsigned x){unsigned y;if(x)y=1;return y;}')
    def test_unbound_aliasing_refused(self):
        with self.assertRaises(m.CFrontendRefused):self.get('unsigned f(unsigned *p,unsigned *q){*p=1;return *q;}')
    def test_variadic_refused(self):
        with self.assertRaises(m.CFrontendRefused):self.get('unsigned f(unsigned x,...){return x;}')
    def test_out_of_bounds_buffer_refused(self):
        with self.assertRaises(m.CFrontendRefused):self.get('unsigned f(unsigned *p){return p[1];}',{'p':{'kind':'input_buffer','cells':[{'label':'$in'}]}})

    def test_existing_c_generator_roundtrips_all_owned_fields(self):
        from fdisbull.console_synthesis import Bindings, NativeBacking, emit_c, recover
        from fdisbull.interaction_il import execute_il

        # Authored eight-byte stack fixture; no original game or CPU execution.
        block = recover(
            NativeBacking('authored-stack-fixture', 'A', 0x8000,
                          bytes.fromhex('A9 01 48 A9 02 68 85 10')),
            Bindings(((0x10, 'result'),)),
        )
        document = block.document()
        names = sorted(document['variables'])
        limits = {'u8': 255, 'u16': 65535, 'bool': 1}
        source = self.root / 'generated.c'
        source.write_text(emit_c(document))
        bindings = {
            'input': {'kind': 'input_buffer', 'cells': [
                {'label': '$in_' + name[1:], 'min': 0,
                 'max': limits[document['variables'][name]['type']]}
                for name in names]},
            'output': {'kind': 'output_buffer', 'cells': [
                {'label': '$out_' + name[1:]} for name in names]},
            'n': {'kind': 'constant', 'value': len(names)},
            'm': {'kind': 'constant', 'value': len(names)},
        }
        imported = m.import_c(source, 'synth_run', clang=CLANG, bindings=bindings)
        native_path = self.root / 'generated.so'
        subprocess.run([str(CLANG), '-O2', '-std=c11', '-shared', '-fPIC',
                        str(source), '-o', str(native_path)],
                       check=True, capture_output=True, timeout=15)
        library = ctypes.CDLL(str(native_path))
        native = library.synth_run
        native.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t,
                           ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t]
        native.restype = ctypes.c_int
        array = ctypes.c_uint32 * len(names)
        rng = random.Random(20261102)
        for case in range(256):
            state = {}
            for name, description in document['variables'].items():
                value = (0 if case == 0 else limits[description['type']] if case == 1
                         else rng.randrange(limits[description['type']] + 1))
                state[name] = bool(value) if description['type'] == 'bool' else value
            expected = execute_il(document, state)
            self.assertEqual(expected['status'], 'complete')
            observed = imported.run({'$in_' + name[1:]: int(state[name]) for name in names})
            inputs = array(*[int(state[name]) for name in names])
            outputs = array(*([0xdeadbeef] * len(names)))
            self.assertEqual(native(inputs, len(names), outputs, len(names)), 0)
            self.assertEqual(observed['return'], 0)
            for index, name in enumerate(names):
                with self.subTest(case=case, field=name):
                    self.assertEqual(observed['$out_' + name[1:]], int(expected['state'][name]))
                    self.assertEqual(outputs[index], int(expected['state'][name]))

if __name__=='__main__':unittest.main(verbosity=2)
