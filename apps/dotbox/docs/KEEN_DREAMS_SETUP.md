# Keen Dreams installation and startup check

The supplied DOS Keen Dreams archive exposed an MZ launch-validation defect in
DotBox 0.1.0.dev7. Development version 0.1.0.dev8 corrects that defect and was
installed as an ordinary wheel in a clean Python 3.12 environment. The original
game reached its startup screen and accepted one observed Enter input through
the installed native transport. This is an installation and startup result;
platformer movement and a live Keen scene provider remain to be tested.

## Wrapped relative entry

The executable uses header CS:IP `FFF0:0100`. DOS relocates the CS segment with
16-bit addition. For example, a load segment of `2000` produces actual entry
`1FF0:0100`, whose linear address is `20000`: the first module byte. Treating the
header CS as an ordinary positive unbounded image offset incorrectly rejected
this executable before DOSBox was launched.

The parser now records the normalized module entry while preserving raw header
CS/IP. Runtime attestation validates observed registers as 16-bit values,
recovers the load segment modulo 16 bits, and checks the actual, unmasked linear
entry against the unwrapped allocation. It does not apply an A20 mask to a bad
runtime address. Prefix and distinct-entry byte samples still attest original
file bytes after relocation. Offline identity reports the same normalized
entry. The existing conservative stack-range check is unchanged.

The pinned DOSBox-X loader provides the relevant contract in
`src/dos/dos_execute.cpp` and `include/mem.h`: the relocated segment is passed
to `RealMake(uint16_t, uint16_t)` before linear address conversion. The
[verification receipt](evidence/keen-dreams-setup-2026-11-19.json) binds the
source, tests, installation and native executable identities.

## Verified scope

- Twelve authored regression cases cover wrapped entry aliases, offline file
  offsets, relocated byte samples, bounds, actual A20 crossing and malformed
  backend registers. The original code failed seven cases; the final affected
  suites passed 144 tests with no failures or skips.
- The installed wheel passed the offline doctor with 81 packaged resources;
  131 installed RECORD hashes and all 39 runtime modules matched the built
  source. Pillow 12.3.0 and iced-x86 1.22.0 satisfy the declared dependencies.
  The fDisBull Python application was absent.
- A separately retained compatible Linux DOSBox-X runtime booted the original
  MZ executable. A subsequent bounded startup trial observed the displayed
  Enter prompt, submitted that one input, and reached the original hardware
  screen showing `Ready - Press a Key`.
- Both successful native runs closed and reaped their own process with exit
  code zero. Frames, game resources and raw runtime evidence remain private.

The native trials used an isolated headless diagnostic path through the
installed `NativeSession`. They do not establish visible desktop integration,
audio, the outer takeover flow, live game-state extraction, rewind, or gameplay.
No DotBox binary release was published.

## Next platformer slice

Launch `KDREAMS.EXE` from a private directory containing its supplied `.KDR`
files. Reuse this installed runtime and executable/resource identities. Inspect
the original help or control menu before choosing key bindings, then enter a
level and test bounded horizontal movement, release, jump, and a direction-plus-
jump chord. Observe takeoff, landing and collision effects independently from
input acceptance. Retain useful controls without replaying an action merely to
record it. No Dune-specific offsets or readiness rules apply to this game.

Work record: [Agent BBS](https://agent-bbs-native.tiga-rce.chatgpt.site), project
`dotbox`, ticket `e-c25d4cfd-65f3-4a84-a42e-46db749bdb4b`.
