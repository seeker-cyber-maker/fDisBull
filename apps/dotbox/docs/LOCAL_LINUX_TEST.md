# Local cloud Linux build and gameplay test

On 17 November 2026, DotBox was compiled and tested on the coordinator's own
cloud Linux computer. The native gate passed all eight fixtures, and an
ordinary-input Police Quest EGA run completed the locker-to-shower endpoint.
This work does not depend on reconnecting to the Mac Studio.

## Native build and gate

The build host was Linux 6.18.57 x86_64 with Python 3.12.14. The measured DotBox
input was local commit `dee1213f1701917fd523911c3a477645c5bd2054`, tree
`1911d22aceeb546712e90f7bcc2894f4389c8315`. The prepared native source matched all
38 recipe-declared result hashes. See the [sanitized native receipt](evidence/local-linux-native-2026-11-17.json)
for source pins, package identities, build stages and exact test selection.

The existing portable Autotools recipe was used with two compiler jobs:

```sh
./autogen.sh
./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent \
  --enable-agent-zstd --disable-avcodec --disable-libslirp --disable-libfluidsynth
make -j2
```

Missing dependencies were fetched from the official Debian trixie package
repository, checked against package SHA-256 metadata and extracted into a
private user-owned prefix. No system installation or elevated execution was
required. Autotools paths and the pkg-config sysroot were bound to that prefix.
The first compile stopped on a missing `X11/Xlib.h`; staging the X11 development
files allowed the same compilation to finish. Both attempts remain recorded.

The native executable's SHA-256 is
`c12db47a54ebfb9d0abc077d5d60715d5ba247ed85d1217cf7e2a974f087acfa`.
The full gate executed four headless and four visible fixtures, with **8 passed
in 3.59 seconds**, zero skips, failures or errors, and a stable executable hash.
The visible gate ran through the cloud desktop's Terminal. A separate shell
workspace does not imply access to the desktop display or its temporary files.

These fixtures cover authored COM/MZ programs, native ownership/input fences,
restore admission and service/control persistence. A fixture whose name includes
`real_game` still uses an authored test program; the commercial-game run below
is separate evidence.

## Police Quest functional controls pass

The original EGA edition was launched with `SIERRA.COM` from an independent
game copy through DotBox's default desktop service. One coordinator used
ordinary desktop keyboard controls to enter the locker room, approach and open
Sonny's locker, remove clothes once, close the locker and walk to the usable
shower. The towel outfit was visibly confirmed. The game acknowledged shower
activation and rendered water; the ordinary turn-off command removed it.

The [controls receipt](evidence/police-quest-local-controls-2026-11-17.json)
records scope and input hashes. The [acceptance document](POLICE_QUEST_ACCEPTANCE.md)
records the route's practical findings: latched arrow movement, modal NPC
interruptions, a collision barrier and a narrow interaction boundary. The live
game response was the arrival assertion. No live coordinate or flag mapping
was invented to replace it.

## What this result leaves open

This is one successful functional controls run with retained preparation, not
a measured seamless-play or cold-start result. A reusable route, complete
movement/delay trace, live scene-state extraction, original-Dot takeover
synchronization and missed-briefing memory rewind remain unqualified. The
fixture restore fence does not provide the complete player-facing rewind API.

The Linux run used checkout source and the existing Python environment; it
does not repeat the earlier Mac installed-wheel doctor acceptance. The native
binary has a private dependency RUNPATH and host-library requirements. A saved
developer snapshot preserves the executable and corresponding source; it is
not a qualified portable offline package, signed application or published
release. No game assets, session credentials, saves or raw memory belong in
the public evidence or developer snapshot.
