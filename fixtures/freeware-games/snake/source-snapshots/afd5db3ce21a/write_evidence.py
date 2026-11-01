from pathlib import Path
import hashlib,json
R=Path('${USER_HOME}/.codex/tmp/snake-macos-arm64-2026-10-31')
ROOT=Path('${USER_HOME}/.codex/worktrees/web-udc/fDisBull')
load=lambda n:json.loads((R/n).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
o=load('oracle/verification.json');c=load('native-verification-02/verification.json');a=load('appkit-verification-03/verification.json');b=load('build-04/build.json')
m=load('build-04/native/native-shell.json');m2=load('build-02/native/native-shell.json')
assert o['mismatches']==0 and c['status']==a['status']=='passed'
for k in ('program','execution_program','source_endpoints','source_selections','cuts','regions','module_uil_sha256','module_udl_sha256'):
 assert m[k]==m2[k]
same_files=['memory-runtime.c','memory-runtime.h','memory-runtime.o','memory-runtime.dylib','config.json','initial.json']
for n in same_files:assert (R/'build-04/native'/n).read_bytes()==(R/'build-02/native'/n).read_bytes()
assert a['application_sha256']==sha(R/'build-04/native/MemoryGame.app/Contents/MacOS/program')
assert c['library_sha256']==sha(R/'build-04/native/memory-runtime.dylib')
assert a['manifest_sha256']==sha(R/'build-04/native/native-shell.json')
original=Path('${PRIVATE_PROJECTS}/fDisBull-targets-private/targets/fixture-snake/SNAKE.EXE')
assert sha(original)==o['original_sha256']
arms={}
for name,v in a['arms'].items():
 assert v['status']=='passed' and len(v['observations'])==69
 arms[name]={k:v[k] for k in ('status','normalized_events','native_event_commands','declared_ram_interventions','ordinary_answer_resets','view_checks','closed','script_sha256','raw_receipt_sha256','process_exit','process_reaped')}
 arms[name]['observations']=len(v['observations'])
 if 'event_coverage' in v:arms[name]['event_coverage']=v['event_coverage']
 arms[name]['all_state_words']=621;arms[name]['all_indexed_pixels']=64000
 arms[name]['intrinsic_actual_drawrect_rgba_exact']=True
receipt={'format':'fdisbull-snake-native-arm64-milestone-1','status':'passed-finite-qualification',
 'platform':{'native':'macOS ARM64','computation_host':c['platform'],'target':m['target'],'profile':m['profile']},
 'identities':{'original_sha256':o['original_sha256'],'original_bytes_unchanged':True,'canonical_uil_sha256':b['module_uil_sha256'],'udl_sha256':b['udl_sha256'],'source_package_sha256':b['source_package_sha256'],'source_database_sha256':b['source_database_sha256'],'prior_delivery_unchanged':b['source_unchanged'],'native_manifest_sha256':a['manifest_sha256'],'native_library_sha256':c['library_sha256'],'native_application_sha256':a['application_sha256'],'native_config_sha256':a['config_sha256'],'native_adapter_source_sha256':sha(ROOT/'src/fdisbull/native_runtime/memory-appkit.m')},
 'implementation':{'same_source_udl_uil':True,'native_generated_arm64':True,'runtime_uil_interpretation':False,'shell':'AppKit','rng_choices':['original','lfsr16'],'selection_changes_future_draws_without_reseeding':True,'ownership':'synchronous main-thread owner; private staging; atomic validated commit; owned display snapshots; terminal close','stored_source_layers_relabelled_as_native':False},
 'original_to_uil':o,
 'uil_to_native':{'cases':c['cases'],'carried_observations_per_rng':69,'complete_state_words':621,'complete_raster_indices':64000,'outcome_route_steps_per_arm':26,'route_arms':['original','lfsr16','hot_swap'],'seed_probes':len(c['seed_probes']),'natural_switch':c['natural_switch'],'guard_refusals':c['guard_refusals'],'closed':c['closed'],'scope':c['scope']},
 'native_core_receipt_binding':{'receipt_manifest_sha256':c['manifest_sha256'],'final_manifest_sha256':a['manifest_sha256'],'same_source_program_cuts_regions_endpoints':True,'byte_identical_files':same_files,'explanation':'Core comparison ran on build02; final build04 changes only the AppKit presentation adapter. Core source/object/library, config, initial arena and source identities remain byte-identical.'},
 'native_adapters':{'arms':arms,'scope':a['scope'],'source_coverage_per_arm':{'keyboard_commands':53,'all_declared_key_codes':14,'left_button_down_up_commands':22,'timer_commands':4},'generic_regressions':['shortcut-modifiers','focus','unknown-key-refusal','all-three-mouse-buttons','captured-drag-and-release-clipping','focus-loss-release','letterbox-ignore','selector-preserves-state','config-byte-identity','owned-preclose-frame','prefix-replacement-preserves-frame-font','fractional-edge-no-blending']},
 'default_bundle_launch':load('app-launch-04.json'),
 'test_suite':{'command':'python -m pytest -q --ignore=tests/test_elf_metadata.py --ignore=tests/test_platform_calls.py -k "not test_actual_elf_exports_and_unresolved_imports_are_honest and not test_real_elf_retains_entry_and_named_function"','passed':2463,'skipped':132,'deselected':2,'seconds':72.19,'exit_code':0,'production_source_files':156,'unchanged_source_map_sha256':'1b5e774fb85244e263192cae10b8304cf01c5506be929e647c78035052c6b925','log_sha256':sha(R/'pytest-compatible-macos-20261031-03.log'),'exclusion_reason':'GNU/Linux ELF fixtures require a Linux compiler/linker; these tests and runtime skips remain unqualified'},
 'privacy':{'original_files_font_full_observations_database_generated_code_and_app':'private outside Git','tracked_evidence':'authored recipes and sanitized counts/hashes only','github_network_or_publication':False,'system_installation_changed':False},
 'limits':['Finite original-code kernel and recorded native observations, not a proof for all inputs or whole-binary recovery.','Alternative RNG is intentionally different from DOS and verified against its explicit variant reference.','Programmatic native window-key and view-pointer responders; physical hardware and global window hit-testing not qualified.','Intrinsic and integer2x RGBA exact; noninteger resizing accepts only mathematically exact nearest/outer-edge tie sets, without blended colors.','Original native observation corpus includes one declared diagnostic full-board RAM-prefix intervention; ordinary events carry state without answer resets.']}
# The original receipt contains only hashes, counts and palette values.
path=ROOT/'docs/evidence/snake-macos-arm64/verification.json';path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'file':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}))
