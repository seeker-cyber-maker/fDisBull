from pathlib import Path
import hashlib,json,shutil,sqlite3,subprocess,tarfile,zipfile
R=Path('${USER_HOME}/.codex/tmp/snake-desktop-x64-2026-10-31')
ROOT=Path('${USER_HOME}/.codex/worktrees/web-udc/fDisBull')
D=Path('${USER_HOME}/Documents/Codex_Projects/fDisBull-local-studies/Snake-native-x64-2026-10-31')
assert not D.exists() and not any((p/'.git').exists() for p in (D,*D.parents))
D.mkdir(parents=True,mode=0o700);(D/'.gitignore').write_text('*\n')
(D/'builds').mkdir();(D/'applications').mkdir();(D/'receipts').mkdir();(D/'images').mkdir();(D/'tooling').mkdir()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
for platform in ('linux','windows'):
 src=R/(platform+'-build-03');dst=D/'builds'/platform;shutil.copytree(src,dst)
 m=json.loads((dst/'native/native-shell.json').read_text());b=json.loads((dst/'build.json').read_text())
 assert b['native_manifest_sha256']==sha(dst/'native/source-shell.json')
 with sqlite3.connect((dst/'snake-native.fdb').as_uri()+'?mode=ro',uri=True) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 app=D/'applications'/platform;app.mkdir();shutil.copy2(dst/'native'/m['application'],app/m['application'])
 shutil.copy2(R/(platform+'-verification-final-03/verification.json'),D/'receipts'/(platform+'-qualification.json'))
 shutil.copy2(R/(platform+'-linkage.json'),D/'receipts'/(platform+'-linkage.json'))
 for image in (R/(platform+'-verification-final-03/images')).glob('*.png'):
  dest=D/'images'/image.name
  if dest.exists():assert dest.read_bytes()==image.read_bytes()
  else:shutil.copy2(image,dest)
for source,name in [('original-oracle-01/verification.json','original-code.json'),('original-oracle-01/refresh-receipt.json','original-refresh.json'),('pytest-compatible-macos-final-01-receipt.json','test-suite.json'),('pytest-compatible-macos-final-01.log','tests.log'),('packaging-01/verification.json','tool-package.json'),('packaging-01/installed-tests.log','installed-tests.log'),('packaging-01/installed-emission-verification.json','installed-source-emission.json'),('final-qualification-binding.json','native-bindings.json'),('x11-adapter-regressions-03.json','generic-x11.json'),('win32-adapter/verification-02.json','generic-win32.json'),('refusal-observer-counterexample-01/verification.json','observer-counterexample.json')]:
 shutil.copy2(R/source,D/'receipts'/name)
shutil.copy2(ROOT/'docs/evidence/snake-desktop-x64/verification.json',D/'receipts/milestone.json')
for p in (R/'packaging-01/source/dist').iterdir():shutil.copy2(p,D/'tooling'/p.name)
with zipfile.ZipFile(D/'private-evidence.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for dirname in ('linux-verification-final-03','windows-verification-final-03','original-oracle-01','refusal-observer-counterexample-01'):
  for p in sorted((R/dirname).rglob('*')):
   if p.is_file():z.write(p,str(Path(dirname)/p.relative_to(R/dirname)))
 for name in ('environment-receipt.json','hello-verification.json','identity.json','desktop_vm.py','guest_broker.py','init.sh','snake_vm_runner.py','export_native_frames.py'):
  p=R/'environments'/name
  if p.is_file():z.write(p,'environments/'+name)
with zipfile.ZipFile(D/'reference-study.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 p=Path('${USER_HOME}/Documents/Codex_Projects/fDisBull-local-studies/Snake-selectable-RNG-2026-10-31/rng-study-02.json');z.write(p,p.name)
readme='''# Snake: native Win64 and Linux x86-64

These are standalone native reconstructions from the same recovered UDL/UIL as the browser and macOS ARM64 pilots. The game rules and renderer compile to native code. The host adapters supply the window, physical keys, pointer coordinates/capture, selectors and clock. Both source projects and the original DOS executable remain unchanged.

## Play

On Windows, extract **Snake-Win64.zip** and open **program.exe**. This PE64 app uses the Windows GUI subsystem and imports only GDI32, KERNEL32, msvcrt and USER32. It embeds the game core; no separate game DLL, browser, Python, DOSBox or original executable is required to play.

On Linux x86-64, extract **Snake-Linux-x86_64.tar.gz** and run **./program** inside the extracted folder in an X11 session. The binary requires libX11 and glibc symbols through GLIBC_2.34. It was tested with Linux 6.1 / glibc 2.39 / Xvfb 24-bit TrueColor under local QEMU. Other distributions/visuals/compositors are not established by that finite result.

Click the game to focus it. Arrows/WASD turn; Space/P pauses; N advances one step; R resets; Esc quits. The blue in-game controls also accept left clicks. The game starts paused. Windows uses a Random generator combo box; Linux cycles the labelled selector by click. Original LCG is the default; LFSR16 changes future food placement without changing the board or reseeding at selection time.

Win64 execution was tested through Win32/GDI APIs under Wine 9 in the offline local QEMU guest. Execution on Microsoft Windows OS and physical hardware remains unqualified. The application is a genuine AMD64 PE/GUI artifact, but that artifact fact is separate from the tested OS environment.

## Results

Fresh isolated original DOS execution matched 342 kernel cases and 26 route steps: 368 original CPU calls, zero mismatches. The 3,851-byte original SNAKE.EXE remains SHA256 f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be.

Each platform passed 342 original-RNG kernel cases and 342 intentional LFSR reference cases. Each RNG passed 69 carried core observations and 69 native UI observations, comparing all 621 state words, 64,000 indexed pixels, palette RGBA and native surface RGBA. Each UI arm consumed 53 keyboard commands covering all 14 declared keys, 22 left-button press/release commands and four timer-clock commands. Intrinsic, integer2x, wide and tall surfaces matched exactly. One declared full-board RAM-prefix intervention remains labelled; ordinary events carry state without answer resets.

Each platform also passed three 26-move native UI routes, ten one-word seed probes and refusal/close checks. The same26 moves finish at length5 / score2 / dead with original LCG, and length4 / score1 / alive with LFSR16. Switching after move4 preserves seed10589 and food389; the next meal uses LFSR and produces seed41134 / food334, with one actual invocation of each generator. The alternative is deliberately different from DOS.

Final qualification used 21 native reconstruction processes per platform (16 core,5 GUI), 42 total, with 2,231 command rows per platform. Exact admission manifests were saved and artifact hashes rechecked before acceptance. All nine corresponding exported PNG files are byte-identical between Linux and Win64. Images come from stored native surfaces, not desktop screenshots.

Generic adapter checks separately passed: six Linux/X11 checks and seven Win32/GDI checks. They cover channel/origin conversion, scaled picking, modifiers/focus, all three buttons, captured drags/releases, focus-loss cleanup, selector preservation, timer services, retained final frames and Windows minimize/max-size behavior. A deliberately faulty core regression confirms that rejected-call observation reads actual live core words, rather than hiding mutations behind a stale display cache.

The final compatible macOS source suite passed 2469 tests, with 145 skips and two deselections in77.78s. All164 production Python/C/header/Objective-C sources stayed unchanged. GNU/Linux ELF fixture builders were excluded on the macOS host; these exclusions and runtime skips remain unqualified by that run. The built local wheel passed51 installed native/source tests and regenerated byte-identical desktop sources for both qualified builds. Tool wheel/sdist passed exact package-payload and private-input/path scans. Their0.26.0 metadata identifies a local development snapshot; no system installation changed.

## Design and scope

UIL SHA256 a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720.
UDL SHA256 986713c25859408dcefe33186b74eb249956934d71d69ad71797c787da9c56d1.

Both platforms use identical source programs, plans, cuts, regions and source endpoints. Emitted game-function C sources are identical. Platform C ABIs and OS services remain explicit adapters; machine-code byte identity across those ABIs is not asserted. Existing Wasm/WebGPU selection metadata remains source provenance.

The core owns staged transactions on its module-load thread, validates footprints/guards/budgets and commits declared state/frame ranges atomically. Hosts keep independent owned snapshots. Selectors affect future region invocations, and explicit close is terminal. Native integer coordinates use the same pixel-center sampling for painting and picking. Win32 studies send native window messages to production procedures; X11 studies traverse XSendEvent, the X server queue, XNextEvent and the production dispatcher. Physical devices and global window hit-testing remain outside this evidence. These are finite comparisons, not all-input or whole-binary proofs.

## Contents and reproduction

- applications/: standalone compiled applications.
- builds/: private project copies, exact generated C/config/object/library/probe, immutable source/compiled manifests and compiler receipts.
- images/: nine stored-native-surface exports, shared across the two platforms by exact identity.
- receipts/: qualification, original-code, generic adapter, test and installed-package receipts.
- private-evidence.zip: full hash-bound compressed inputs/outputs, source snapshots, original oracle probes, test-VM identity and explicitly invoked local runner/controller source. The633MB runtime/kernel are referenced by identity and are not duplicated in this delivery.
- reference-study.zip: exact qualified reference corpus.
- tooling/: local wheel/sdist without private game data.
- snake-native-x64.patch and .bundle: offline source handoff relative to the preceding macOS milestone.

The source recipes are examples/recovery/snake_desktop.py and verify_snake_desktop.py. Emit into a NEW private directory using the prior sibling Snake-selectable-RNG-2026-10-31 delivery and target linux-x64 or windows-x64. Compile the recorded recipe in the appropriate GCC/MinGW environment, then admit artifacts with seal_memory_desktop_shell. The source-only manifest is retained as source-shell.json; compiled receipts are immutable. Extract reference-study.zip and pass the native build, rng-study-02.json and a NEW evidence directory to the verifier. Use --runner only with an explicitly chosen authorized local runner.

The full profile/API is documented in docs/UDC_MEMORY_DESKTOP.md. All work is local: no GitHub action, push, PR, publication or system installation occurred. The disposable test guest has networking disabled.
'''
for old,new in [('integer2x','integer 2x'),('same26','same 26'),('length5','length 5'),('score2','score 2'),('length4','length 4'),('score1','score 1'),('move4','move 4'),('seed10589','seed 10589'),('food389','food 389'),('seed41134','seed 41134'),('food334','food 334'),('(16 core,5 GUI)','(16 core, 5 GUI)'),('in77.78s','in 77.78 seconds'),('All164','All 164'),('passed51','passed 51'),('Their0.26.0','Their 0.26.0'),('The633MB','The 633 MB')]:readme=readme.replace(old,new)
(D/'README.md').write_text(readme)
for platform in ('linux','windows'):(D/'applications'/platform/'README.md').write_text(readme)
with zipfile.ZipFile(D/'Snake-Win64.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted((D/'applications/windows').iterdir()):z.write(p,'Snake-Win64/'+p.name)
with tarfile.open(D/'Snake-Linux-x86_64.tar.gz','w:gz',compresslevel=9) as t:
 for p in sorted((D/'applications/linux').iterdir()):
  info=t.gettarinfo(str(p),'Snake-Linux-x86_64/'+p.name);info.uid=info.gid=0;info.uname=info.gname='';info.mode=0o755 if p.name=='program' else 0o644
  with p.open('rb') as f:t.addfile(info,f)
for zp in D.glob('*.zip'):
 with zipfile.ZipFile(zp) as z:assert z.testzip() is None
with tarfile.open(D/'Snake-Linux-x86_64.tar.gz') as t:assert len(t.getmembers())==2
print(json.dumps({'delivery':str(D),'windows_zip_bytes':(D/'Snake-Win64.zip').stat().st_size,'linux_archive_bytes':(D/'Snake-Linux-x86_64.tar.gz').stat().st_size,'bytes':sum(p.stat().st_size for p in D.rglob('*') if p.is_file())},indent=2))
