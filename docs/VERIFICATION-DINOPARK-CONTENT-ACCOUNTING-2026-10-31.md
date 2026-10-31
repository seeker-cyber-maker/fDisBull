# DinoPark content and executable byte accounting

The October 30–31 follow-up accounts for every file in the original 183-file
intake and every byte of the supplied main executable. This closes the inventory
and format-accounting work. It does **not** establish complete semantic analysis,
global reachability, or that any candidate is globally unused.

The source under test is **0.26.1**, commit
`428b6ac801a99a64956d056db9010ccd55b9b2f8`. The native backend is the existing
0.26.1-f783f2a macOS arm64 DOSBox-X executable, SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.
The original executable SHA-256 remains
`2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c`.
Sound stayed off. No package, release, installation or original-file patch was
made. Original instructions, addresses, media, databases and captures remain in
the private research packet `content-accounting-20261030-01`.

## Executable accounting

The complete 268,480-byte file consists of an 18,432-byte MZ header and a
250,048-byte load image. The header has 4,139 relocation records; there is no
appended overlay. The load image separates into 197,120 bytes before DGROUP and
52,928 bytes of file-backed data/stack space.

| Pre-DGROUP classification | Distinct physical bytes |
| --- | ---: |
| Stored native instruction representations, including hypothesis roots | 195,954 |
| Recognized bounded snapshot switch-table words | 804 |
| Inline state, lookup tables and character data with native consumers | 197 |
| NOP alignment hypotheses | 128 |
| Zero reserve/alignment hypotheses | 37 |
| **Total** | **197,120** |

The derived copy stores 75,950 instruction rows. Added roots recovered
representations for another 1,122 physical bytes. An instruction representation
is weaker evidence than a reachable instruction or confirmed function: aliases,
internal blocks and speculative roots remain qualified. The 37 zero bytes stay
reserve/alignment hypotheses, rather than certified dead padding.

The inline ranges include graphics masks/state, path and time-format character
tables, linked audio callbacks, a mutable sound-decoder delta table, saved
registers across DOS execution, a renderer counter and a saved interrupt vector.
An all-zero range can hold live state.

All native discovery queues closed. The derived worker processed 1,075 newly
pending or changed jobs, ending at **1,410 done / 172 partial** with no newly
pending jobs. Overall semantic stability remains **false**. Unchanged partial
jobs were not reset or repeatedly retried with larger budgets. The 1,582 stored
entry candidates include block hypotheses and are not a confirmed function count.

All **107 indirect calls** have retained owner/slot evidence. Of **58 indirect
jumps**, 53 have bounded snapshot table hypotheses; the other five use a runtime
callback, a saved nonlocal continuation, two computed blitter entries and an old
interrupt-vector chain. This inventory does not resolve every dynamic target.
Nine explicit far-pointer constructions reference seven of the original 210
no-reference entry candidates. Two more now have stored incoming references;
201 still lack a modeled incoming reference. None is certified dead code.

## Resource formats and use evidence

Every original intake file has a role, hash, format evidence, scoped native-use
evidence where available, and an explicit unused-status qualification. The
current directory also contains eight pre-existing native saves and one IDA
database; these nine local artifacts are accounted for separately from the
original intake. Qualified original-game and configuration-utility cohorts have
positive DOS-read evidence for **68 distinct intake filenames**. Reading a file,
decoding it, executing its script and displaying or playing it remain separate
claims.

| Resource family | Accounting result |
| --- | --- |
| 57 actor files | 1,514 sprites; 48 programs in 11 script-bearing files; all 679 instructions inspected; 32 used opcode values |
| 25 picture files | 166 frames; directories, extents, palettes and decoded pixel counts validated |
| 44 sampled sounds | All decode completely to 636,978 unsigned 8-bit PCM samples; no unconsumed source bytes |
| 7 XMIDI files | Seven sequences and 4,098 events through end-of-track; one explicit zero trailer byte in one event chunk |
| FM timbre bank | 256 directory entries and 256 distinct 14-byte records; 126 unindexed zero tail bytes |
| 36 audio/helper modules | 19 DIGPAK drivers, nine AIL drivers, one MIDPAK resident service and seven helpers; recognition is not a live test of every hardware card |
| Remaining files | Main/setup executables, 242-string directory, demo, configuration/coefficient data, leaderboard, product structure, icon, launchers, documentation and cache-name marker |

The actor programs contain 39 locally unreachable terminal bytes following
closed-loop paths. This is local control-flow evidence under the inspected
model, which does not model arbitrary external program-counter changes. It is
not a claim of globally unreachable original code or native execution parity
for all 32 used opcodes.

The actor filename producers still cover 54 of 57 supplied files. The selective
sprite reader was observed reading a dinosaur icon by index, so
full-file actor-loader events alone would undercount consumption.

The same 13 resource candidates remain qualified: `BUS.ACT`, `OFFICE.ACT`,
`PEOPLE.ACT`, `MECC.PIC`, eight sound files and the `SBP1FM.ADV` alias. Their
formats/content are accounted for, but no positive original read was observed
in the qualified scopes. The alias is byte-identical to `MIDPAK.ADV`; reading
the latter does not establish use of the former filename. These are possible
legacy/unreferenced content, not certified globally unused resources.
Both legacy `UNCS` actor files are accepted by the recovered reader; their
different header spelling alone does not explain their lack of observed use.

## Original-backed isolated effect

The sound expander was invoked in one disposable native guest for all 44 input
files, using guarded buffers and its original calling convention. Every PCM
output matched the authored decoder byte for byte; returned lengths, buffer
guards and far-return stack state matched too. The original function's code
remained unchanged. The 44-case fixture took 5.145 host seconds.

This demonstrates a useful UDL/UDC boundary: an original-backed decoding effect
can run outside its scene without executing an audio-playback action. Its
contract must include input/output bounds, calling-convention clobbers, return
state and mutable lookup memory. The authored translation matches PCM outputs
and lengths on these 44 inputs. Full machine-state equivalence, malformed-input
behavior, every possible bitstream and audio-device timing are not established.
The forced fixture contributes no natural-use evidence for otherwise
unreferenced sound files.

## Independent Luna verification

A fresh **gpt-6-luna** verifier independently reran the 44-case native fixture
in one disposable guest. All PCM buffers, returned lengths, source readbacks,
stack positions, buffer guards and function-code checks passed. The native
process exited with code 0, stderr was empty, and all 183 copied inputs stayed
unchanged. Her fixture copy changed only its root/output paths.

Luna also checked the 192 current file hashes, the 183-file intake ledger,
executable arithmetic/hash, immutable database integrity and all 1,258 recorded
payloads against the retained original/diagnostic receipts. She did not relaunch
the demo. No material overclaim was found in that reviewed scope. The private
packet retains her fixture, report, machine-readable verification and raw logs
separately from the parent-run evidence.

## Demo recording and original early-stop condition

The 17,987-byte recording is fully partitioned into a two-byte seed, a
4,147-byte native park snapshot and **1,258 eleven-byte input records**. There
are 1,133 input-state records and 125 delay records. Delay values are loop
counters, not a verified duration in seconds.

An unchanged native run read the first valid record and returned **11** from
the original stream wrapper. The caller expected **1**, took the stop path and
returned to the title screen. Native instructions confirm that the wrapper
normalizes the request to byte-sized elements. The initial 4,608-byte DOS
prefetch therefore was not evidence that the whole recording had played.

A separately labeled diagnostic variant changed only the comparison immediate
in disposable guest RAM, with expected-byte and readback guards. Neither the
executable file nor recording was changed. A counted replay then matched **all
1,258 native records in order** against the file, observed the following EOF
return of zero, entered the stop routine once and returned to the title screen.
It took 278.752 host seconds, with no observer failures and native exit code 0.
The variant's asset accesses remain excluded from canonical original-use counts.
No original executable bug fix is included in this PR.

For UDC definitions, preservation of the original early-stop behavior and an
optional compatibility correction must be distinct, reviewable variants. A
correction cannot silently become the reference behavior for equivalence tests.

## Original scene qualification and tool friction

The office ticket-stack control now has a qualified visitor-count binding.
Native messages confirmed both zero visitors and a positive count of **54**;
the positive formatted argument matched the original displayed popup. The
private batch checked 2,920 positive DOS reads against original file contents
and retained 374 seek events. This research binding is not added to the shipped
Z object catalogue by this documentation change.

The following proposals belong to the next implementation pass:

1. Give screenshot artifacts one documented frame-metadata accessor. A private
   adapter read mode identity at the wrong nesting level and failed before
   input. Its failed cohort was retained; a corrected fresh cohort qualified
   the binding.
2. Separate request-validation failures from internal observation/binding
   exceptions. The broad request catch can describe an internal `KeyError` as
   an invalid request with no input sent. This observed case failed before
   input; it does not demonstrate a mislabeled post-input effect. Shutdown
   receipts should make an unresolved pending action equally visible beside a
   clean worker completion.
3. Carry the canonical root action through every continuation. A private
   recursive client substituted the latest `continue` action for the root DOS
   exit action on its second continuation. The public guard correctly refused
   before sending more input. That cohort's DOS-exit intent remains unresolved;
   host cleanup is not a selected-DOS-exit certificate.
4. Retain consumer identity, optional sprite index and seek/read ranges in
   resource-use telemetry. The private observer now provides these; this PR
   does not add them to the product protocol.
5. Record instruction-built far-pointer provenance and distinguish pointer
   registration from invocation. Data-relocation scans alone miss these
   references.
6. Support non-function code/block roots and show native queue closure,
   physical representation, partial derived jobs and unknown targets separately.

No emulator crash was observed in the completed new cohorts. Adapter/controller
failures and unresolved effects remain visible rather than promoted to passing
gameplay. These bounded results do not clear the earlier reports of stuck chats.
