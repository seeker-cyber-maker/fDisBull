# Zork harness and source action verification

On 29 October 2026, the working source qualified a raw v3 story harness and a
single recovered mailbox action against the original DOS Zork I interpreter on
this Mac. This is uncommitted source work after published 0.21.0, with no tag,
publication or shared-installation change. The [machine-readable receipt](evidence/zork-2026-10-29/verification.json)
contains source identities, scope, observations and verification results.

This is the retained development verification snapshot. Version finalization
and subsequent CI are covered by [release verification](VERIFICATION-0.22.md).
Example replays linked below are checkout-only and excluded from tool-only
source archives; obtain them from the [tagged Zork example directory](https://github.com/seeker-cyber-maker/fDisBull/tree/v0.22.0/examples/zork).

The exact reference is Zork I release 88, serial 840726. The interpreter and
story are separate user-provided inputs. Structure recognition accepts an
arbitrary filename, checks the v3 tables and declared-length checksum, and
records trailing file bytes independently. Other VM versions, Blorb extraction
and early v3 files without length/checksum are outside this first profile.

## Source linked behavior

Native DOS execution at project `1000:17ab` writes the mailbox attribute word.
Two post-access stops identify source instructions `0x80a3: 4b 86 0b` and
`0x80a6: 4b 86 03`: set attributes 11 and 3 of the object selected by global
variable `0x86`. The runtime direct-object witness is 160. The resident story
base is established from the original interpreter's first 512-byte file read;
its bytes match the exact story. Native page/offset fields identify the next
virtual PCs `0x80a6` and `0x80a9` at the two writes.

The shared IL reproduces the declared object-state fields and normalized text
for first-open and already-open cases. Output resources are derived from source
literals, abbreviation tables, object names and the qualified one-child list
formatter. The input and output roles use the same blocks; changing `role`
from `udl` to `uil` leaves the evaluated result identical.

Qualification requires an action-entry RAM witness, including object 160,
its original names, container/transparent flags and properties, child 161 and
the selected one-child formatting conditions. Initial story bytes alone do not
establish the parser's direct-object binding. The recipe returns these as
`initial_story_state`, explicitly requiring a runtime witness for execution.
Other states refuse through a `require` block. The parser, turn loop, global
processes and other object/list states remain outside this extracted slice.

## Checkpoints and independent execution

The verifier passed all of the following on the original inputs:

- First and repeated action text and declared state fields agree with DOS.
- Jericho/Frotz first/repeated text and mapped state fields agree with DOS.
- Same-session native checkpoint continuation reproduces the action response.
- A fresh DOS process initializes to its opening prompt, restores, and reproduces
  the response. Initialization is part of this qualified recipe; cold restore
  directly at COM entry previously failed and remains unqualified.
- A fresh story-worker process restores its checkpoint with the same response
  and all nine captured engine-state components after the action.
- Immutable UDL and UIL revisions survive project close/reopen, including
  exact source-file and source-span verification.
- The privately installed candidate wheel runs the actual CLI, autosaves a
  command, resumes in another CLI process, and returns the source-derived
  repeated-open response. The extracted IL also runs in an isolated invocation
  with no story interpreter or database supplied to the evaluator.

Text comparison folds whitespace after attributing fresh DOS command output.
These comparisons do not establish complete RAM identity or whole-game
equivalence between the DOS interpreter and Frotz.

## Tests and packaging

Focused new and affected checks: **90 passed, 1 skipped**. The full Mac suite:
**1,362 passed, 104 skipped, 2 failed, 23 setup errors**. The failed/error names
match the prior local run and concern Linux ELF fixtures built with Apple gcc.
A separate captured compiler diagnostic confirms that the native assembler
rejects `.type _start,@function`. The full Mac suite is therefore not green;
no Linux CI result is claimed for this unpushed source.

The candidate wheel, sdist and source ZIP passed the distribution exclusion
checker. A private installation of the wheel passed the actual story-worker
and CLI checkpoint checks. The packaged recovery module contains profile
identities and code, with no retail story/message payload or native interpreter.

The text-host `--fair-play` startup policy refuses both kinds of assisted travel
before guest access, filters its public actions, binds freshness tokens to the
policy and retains the current policy when loading checkpoints. Ordinary
movement is unchanged. This is a voluntary policy, not a restriction on manual
memory editing or proof that a whole campaign followed benchmark rules.

## Reproduction and private evidence

Run [the verifier](../examples/zork/verify_harness.py) with a private extracted
game directory, tested DOSBox backend, Jericho 3.3.1 worker Python, and a new
output directory. It copies only the required game inputs and leaves originals
unchanged. Output includes game files, native/worker checkpoints, a project
database, source-derived IL messages, screenshots and a bounded native trace;
keep the entire output out of Git and delivery archives.

The local final output is under
`.recovery/2026-10-29/zork-implementation/qualified-source-final/`.
Its public receipt retains identities and comparison results without copying
those private payloads. The shared system installation remains at 0.21.0.
