from pathlib import Path
import hashlib,json,os,shutil,subprocess,zipfile
R=Path('${USER_HOME}/.codex/tmp/snake-macos-arm64-2026-10-31')
ROOT=Path('${USER_HOME}/.codex/worktrees/web-udc/fDisBull')
D=Path('${USER_HOME}/Documents/Codex_Projects/fDisBull-local-studies/Snake-macOS-ARM64-2026-10-31')
assert not D.exists()
assert not any((p/'.git').exists() for p in (D,*D.parents))
D.mkdir(parents=True,mode=0o700)
(D/'.gitignore').write_text('*\n')
shutil.copytree(R/'build-04',D/'build')
shutil.copytree(R/'build-04/native/MemoryGame.app',D/'Snake.app')
(D/'images').mkdir();shutil.copy2(R/'default-bundle-frame-04.png',D/'images/initial.png')
(D/'receipts').mkdir()
for source,name in [('oracle/verification.json','original-code.json'),('native-verification-02/verification.json','native-computation.json'),('appkit-verification-03/verification.json','native-appkit.json'),('app-launch-04.json','default-launch.json'),('pytest-compatible-macos-20261031-03-receipt.json','test-suite.json'),('packaging-01/verification.json','tool-package.json')]:
 shutil.copy2(R/source,D/'receipts'/name)
shutil.copy2(ROOT/'docs/evidence/snake-macos-arm64/verification.json',D/'receipts/milestone.json')
for source,name in [('pytest-compatible-macos-20261031-03.log','tests.log'),('packaging-01/installed-tests.log','installed-tests.log'),('pytest-compatible-macos-20261031-03-source-before.json','production-source-before.json'),('pytest-compatible-macos-20261031-03-source-after.json','production-source-after.json')]:
 shutil.copy2(R/source,D/'receipts'/name)
(D/'tooling').mkdir()
for p in (R/'packaging-01/source/dist').iterdir():shutil.copy2(p,D/'tooling'/p.name)
with zipfile.ZipFile(D/'private-evidence.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for source,prefix in [(R/'appkit-verification-03','appkit'),(R/'oracle','original-code')]:
  for p in sorted(source.rglob('*')):
   if p.is_file():z.write(p,str(Path(prefix)/p.relative_to(source)))
with zipfile.ZipFile(D/'reference-study.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 p=Path('${USER_HOME}/Documents/Codex_Projects/fDisBull-local-studies/Snake-selectable-RNG-2026-10-31/rng-study-02.json');z.write(p,p.name)
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
base='cc523477736956aa3019f98ceb3c928b7c6f6275'
with (D/'snake-macos-arm64.patch').open('wb') as out:
 subprocess.run(['git','diff','--binary',base,'HEAD'],cwd=ROOT,stdout=out,check=True)
subprocess.run(['git','bundle','create',str(D/'snake-macos-arm64.bundle'),'refs/heads/codex/snake-macos-arm64-20261031','^'+base],cwd=ROOT,check=True)
readme='''# Snake: native macOS ARM64 milestone

Open **Snake.app** in this folder, or extract **Snake-macOS-ARM64.zip** and open the app inside. It is a standalone ARM64 AppKit application. The recovered game rules and renderer compile to native code; Python and the browser are not required to play.

The game starts paused. Click the game to focus it. Arrows or WASD turn; Space/P pauses; N advances one step; R resets; Esc quits. The blue in-game controls also accept clicks. The **Random generator** selector defaults to **Original LCG**. Choose **LFSR16** to change future food placements without resetting the board or seed. A reset remains a separate game action.

The canonical UDL/UIL, source font/palette, input plan, exact cuts and RNG contracts are unchanged from the qualified browser pilot. The native shell supplies the window, palette presentation, physical-key translation, pointer coordinates and clock. The backend is generic; its source contains no Snake movement or RNG formulas. Existing Wasm/WebGPU database selections remain source provenance, with native realizations identified separately.

Original SNAKE.EXE is unchanged: 3,851 bytes, SHA256 f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be.
UIL SHA256 a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720.
UDL SHA256 986713c25859408dcefe33186b74eb249956934d71d69ad71797c787da9c56d1.

## Verification

Fresh isolated original DOS machine-code execution matched 342 kernel cases and 26 route steps. Native ARM64 matched all 342 original cases and 342 intentional LFSR reference cases. Both RNGs matched 69 carried observations, all 621 state words and all 64,000 framebuffer indices. Original-RNG results match the established DOS/Wasm/WebGPU projection hash.

The actual AppKit responder and drawing paths passed 79 normalized events per RNG: 53 key commands covering all 14 declared codes, 11 left-button presses, 11 releases and four timer events. Every intrinsic-resolution palette RGBA and stored-state drawRect RGBA buffer matched exactly. Integer2x views are byte-exact. Wide/tall views accept only mathematical nearest-pixel ties and binary coverage at exact image-edge ties; they reject all blended colors and other differences. The production adapter disables image-edge antialiasing within saved graphics state. One declared full-board RAM-prefix intervention appears in the recorded corpus; ordinary events carry state without answer resets.

Generic native tests also cover shortcut/focus filtering, unknown keys, all three mouse buttons, clipped captured drags/releases, focus-loss release, ignored letterbox presses, immutable-input/invalid-state refusal, transaction rollback, execution budgets, selector state preservation, owned display snapshots and terminal close.

The same26-move route ends with original LCG at length5/score2/dead, and LFSR16 at length4/score1/alive. A natural switch after move4 preserves seed10589 and food389; the next meal uses LFSR and produces seed41134/food334, with one actual invocation of each generator. These are deliberate behavior changes under the same canonical UIL.

Final sealed macOS suite: 2463 passed,132 skipped,2 deselected,72.19s. All156 production Python/Objective-C source hashes remained unchanged during the run. The Linux/GNU ELF fixture exclusions and runtime skips remain unqualified. Installed local-wheel native/AppKit tests:45 passed. Tool wheel/sdist passed private-input/path scans and exact package-payload comparison. The local tool artifacts retain the branch's0.26.0 metadata; they are development snapshots, and no system installation was changed.

This is finite qualification, not all-input equivalence or whole-binary recovery. AppKit input evidence uses programmatic NSEvents through native window-key and production-view pointer responders. Physical hardware and global window hit-testing remain outside the evidence. All images were exported from stored state, not desktop screenshots.

## Contents and reproduction

- Snake.app and Snake-macOS-ARM64.zip: runnable application, identical compiled bytes.
- build/: private project copy, generated C/object/library/app, exact manifests and original build receipt.
- receipts/: readable qualification, test and packaging receipts.
- private-evidence.zip: compressed executed scripts, raw observations, stored-state images and fresh original-code probes.
- reference-study.zip: the exact previously qualified RNG study consumed by both native verifiers.
- snake-macos-arm64.patch and .bundle: offline source handoff relative to base cc523477736956aa3019f98ceb3c928b7c6f6275.
- tooling/: local wheel/sdist, without private targets or generated game output.

The native-computation receipt ran on build02. Final build04 has byte-identical runtime C/header/object/dylib, config and initial arena, and identical source programs/cuts/regions/endpoints. Only the AppKit presentation adapter changed; its final receipt binds directly to build04. Original receipt paths are preserved as history; build/ is the relocated final build.

From the source checkout, use examples/recovery/snake_macos.py with the prior sibling Snake-selectable-RNG-2026-10-31 delivery and a new private output directory to rebuild. Extract reference-study.zip, then run examples/recovery/verify_snake_macos.py and verify_snake_appkit.py, each with build/native, the extracted rng-study-02.json and a new evidence directory. The native profile and JSON API are documented in docs/UDC_MEMORY_MACOS.md.

All work is local. No GitHub action, push, PR, publishing or system installation occurred.
'''
readme=readme.replace('same26','same 26').replace('length5/score2/dead','length 5 / score 2 / dead').replace('length4/score1/alive','length 4 / score 1 / alive').replace('move4','move 4').replace('seed10589','seed 10589').replace('food389','food 389').replace('seed41134/food334','seed 41134 / food 334').replace('passed,132','passed, 132').replace('skipped,2','skipped, 2').replace('deselected,72.19s','deselected, 72.19 s').replace('All156','All 156').replace('tests:45','tests: 45').replace("branch's0.26.0","branch's 0.26.0")
(D/'README.md').write_text(readme)
with zipfile.ZipFile(D/'Snake-macOS-ARM64.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 z.write(D/'README.md','Snake-macOS-ARM64/README.md')
 for p in sorted((D/'Snake.app').rglob('*')):
  if p.is_file():z.write(p,str(Path('Snake-macOS-ARM64')/p.relative_to(D)))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert (D/'Snake.app/Contents/MacOS/program').read_bytes()==(R/'build-04/native/MemoryGame.app/Contents/MacOS/program').read_bytes()
for zpath in D.glob('*.zip'):
 with zipfile.ZipFile(zpath) as z:assert z.testzip() is None
handoff={'format':'fdisbull-private-native-snake-handoff-1','status':'complete-local','source_worktree':str(ROOT),'branch':'codex/snake-macos-arm64-20261031','commit':commit,'base':base,'delivery':str(D),'application':'Snake.app','final_native_build':'build/native','source_build_number':4,'qualified_core_build_number':2,'core_library_identity_preserved':True,'system_installation_changed':False,'network_or_github_used':False,'artifacts':{str(p.relative_to(D)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(D.rglob('*')) if p.is_file()}}
(D/'HANDOFF.json').write_text(json.dumps(handoff,indent=2)+'\n')
print(json.dumps({'delivery':str(D),'commit':commit,'application_zip_bytes':(D/'Snake-macOS-ARM64.zip').stat().st_size,'evidence_zip_bytes':(D/'private-evidence.zip').stat().st_size,'total_bytes':sum(p.stat().st_size for p in D.rglob('*') if p.is_file())},indent=2))
