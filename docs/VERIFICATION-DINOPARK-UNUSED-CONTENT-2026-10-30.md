# DinoPark unused-content investigation follow-up

This resumes the whole-binary and resource investigation after the driver
study. It adds research findings and a bounded original-game cohort, with no
production-code change, package, release or installation. The tested Python
source is **0.26.1**, commit
`ee49111ab3993b23dd9ccb008a9a1f56a000d963`, selected through an explicit source
import path. The native backend is the existing 0.26.1-f783f2a macOS arm64
DOSBox-X executable, SHA-256
`bcf318de2a22d49d1b28888a312e12b774cf1f041fdd8862fc4ab3335ea59b60`.

Original files, native instructions, addresses, databases, media, saves and
raw runtime captures remain private. No original file or routine is certified
globally unused.

## Actor filename producers

The retained graph contains **28 direct call sites** to the full actor reader.
Local straight-line propagation identifies 24 filename candidates under the
static data-segment assumption. The remaining paths use:

- Species IDs and the external string table, containing 19 dinosaur actor
  filenames.
- A numbered plant filename format, with three supplied plant files. The file
  inventory does not establish the runtime index bound.
- A six-record table of staff artwork filenames.
- A helper that forwards its caller's filename. This helper has no known
  incoming control reference or relocation-backed callback candidate in the
  retained ledger; indirect use remains unresolved.

There is also a **separate selective sprite reader**, with two stored direct
call sites using `PENS.ACT` and `DINOS.ACT`. Together, these producers account
for filenames of **54 of the 57 ACT files**. This identifies argument sources;
it does not establish that every path runs or that all indirect calls have
been recovered. `BUS.ACT`, `OFFICE.ACT` and `PEOPLE.ACT` still have no identified
producer.

The native cohort returned a total of **1,084 read bytes from `DINOS.ACT`**,
without a full actor-reader entry for that file. This is positive consumption
evidence and demonstrates why a single loader hook is insufficient. It does
not identify the exact sprite, distinct byte ranges or final display.
`PENS.ACT` was not observed in this route.

## Older containers and library candidates

`BUS.ACT` and `PEOPLE.ACT` are the only two `UNCS` containers; the other 55 use
`UNC2`. The native full actor reader handles the extra UNC2 header field and
routes uncompressed containers through an `UNC` prefix comparison. The older
magic is therefore not rejected at that dispatch. This rules out a header-only
incompatibility explanation; it is not a forced native rendering test.

The preserved inventory also contains **48 sequence bodies in 11 ACT files**.
Loading a file and executing its sequences are separate coverage questions.

Nine of the 210 no-known-reference entry candidates contain recognizable
INT66 audio API calls in their retained entry instructions, bounded at a
return or unconditional jump. They can be classified as candidate linked
audio helpers. Their missing-reference evidence is unchanged, and their role
does not prove either execution or abandoned gameplay. API meanings remain
conditional on the installed handler and version.

## Muted original-game cohort

One fresh guest used ordinary public Z Player commands and a private passive
observer. The observer made no guest code, register or data writes and forced
no asset load. No checkpoint restore or raw-input fallback was used.
Actual launch arguments retained `mixer nosound=true` and
`midi mididevice=none`, with `SDL_AUDIODRIVER=dummy`.

The park route completed all eight main locations, setup and purchases,
hiring a guide, buying food, opening the park and **24 time advances**.

| Native report | Day counter | Cash | Small feeders | Guide / dinosaur |
| --- | ---: | ---: | ---: | --- |
| After opening | 5 | $2,600 | 20 | 1 / 1 Coelophysis |
| After time advances | 28 | $5,756 | 16 | 1 / 1 Coelophysis |
| After returning to the office | 29 | $5,850 | 16 | 1 / 1 Coelophysis |

The reported dinosaur hunger counter remained zero. These are native report
observations, not a claim that one time command always advances exactly one
calendar day.

Sixty-six distinct filenames returned positive reads. All 13 retained resource
candidates still had zero successful opens and zero returned read bytes.
BUS, OFFICE and PEOPLE also had zero full actor-reader entries. This strengthens
the bounded route evidence; it does not prove global non-use.

The candidate visitor field was read passively **245 times**, with values
0, 27, 54 and 81. Static code passes that field to the game's positive
yesterday-visitors message. The message-formatting trap was not reached, so
the live message/UI binding remains unqualified. No new certified visitor
field was added to the public Z report.

## Controller limitation and cleanup

The optional terminal extension reached the original quit confirmation. Its
accepted/partial result correctly identified the confirmation scene. The
private driver then held because it incorrectly required an
`acknowledge notice` continuation for every accepted result. This is a test
controller limitation, not a rejected game action, unknown quit outcome or
observed game crash.

The cohort retained **49 Player results**: 48 completed results and one
accepted modal transition, across 195 provider requests. The original held
driver result is preserved. No confirmation or replay was sent afterward.
Owned processes were closed; native host return code was zero and no owned
process remained. **Selected DOS termination was not verified in this cohort**;
host cleanup is separate evidence. Earlier terminal verification remains in
its own record.

The observer reported no failures. Its 245 counter-read checkpoints also found
the DOS file-service vector unchanged. All **192 current original files**,
the **183-file input copy**, and every file in the **147-file earlier research
seal** matched their retained hashes.

## Follow-up and tool friction

1. Qualify the enclosing scene/control for the visitor-message dispatch, then
   observe its native formatted message before exposing a certified Z binding.
2. Keep selective sprite consumption, full actor loading, sequence execution
   and displayed pixels separate in resource-use evidence. Native file events
   should retain consumer identity, optional sprite index and seek/read ranges;
   the private logger currently lacks seek positions.
3. Distinguish explicit modal next actions from provider-authorized action
   continuations in test controllers. Neither authorizes replaying the original
   intent. The public provider's quit confirmation was correct here.
4. Continue sequence-use and indirect-call analysis. The earlier whole-binary
   snapshot still has 144 partial derived jobs; this follow-up does not change
   its stability or semantic-completion status.

The private evidence manifest binds the producer records, observer source,
requests/results, preservation checks and report. The compact public record
deliberately contains no original binary or media payload.

Private seal: 964 files, 110,434,983 bytes; manifest SHA-256
`aa15efcf2e700686f77271892b570bb5bb6f3239cc6bf23a99f24eec0a5f53d3`.
