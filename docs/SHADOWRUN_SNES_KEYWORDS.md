# SNES Shadowrun's three unlearned keywords

The supplied USA ROM contains **Arena (`$03`), Norbert (`$24`) and Scalper
(`$29`)**, but the audited conversation and behavior-script catalogues contain
no teaching site for them. Norbert and Scalper retain dedicated replies. Arena
has no dedicated reply. This is a bounded static producer audit; the later
replies have not been reached by an ordinary gameplay route in the native build.

The source is the same 1,048,576-byte ROM used by the opening profile, SHA-256
`e6bc0a595d5c7c4bc0bbb61ffe35a70288a77eb78544ed74682d489a9e6f07f4`.
Other editions remain unqualified.

| Keyword | ID | Teaching sites in audited catalogues | Dedicated replies retained in the ROM |
| --- | --- | --- | --- |
| Arena | `$03` | 0 | 0 |
| Norbert | `$24` | 0 | 4 records: gunshop owner and Norbert, each in two conversation states |
| Scalper | `$29` | 0 | 2 records: the right mortician's two conversation states |

The four Norbert records share two text pointers (`$119C` and `$58AC`); the two
Scalper records share one (`$3B59`). All six are text-only responses with no
child script or newly learned keyword in their record. The character attribution
is consistent with The Admiral's external dialogue map; the record counts,
selectors, learning fields and text pointers were checked locally.

The game distinguishes a response selector from a keyword granted by that
response. The low nibble of a conversation entry's control byte counts its
explicitly taught keyword IDs. Merely mentioning a name in dialogue does not
insert it into Jake's sorted, `$FF`-terminated learned-keyword list at
`$7E:3CA3`. The source routine at `$80:908C` inserts those listed IDs. The
separate script-native operation `$71` calls the insertion routine at
`$80:90CF`. The keyword menu enumerates the learned list, so a retained name or
reply does not by itself make the keyword selectable.

The records therefore support missing teaching producers, rather than a keyword
menu capacity explanation. No patch, keyword injection or automatic unlock was
added. Calling an unused response directly would be an assisted experiment and
would not establish that the word can be learned normally.

## Repeatable audit

Run the repository checker with the caller's original ROM and a new external
receipt path:

```sh
python3 scripts/check_shadowrun_snes_keywords.py \
  --rom /private/original/Shadowrun.sfc \
  --output /private/new-keyword-audit.json
```

The checker refuses a different source hash. It decodes the 64 keyword-name
pointers privately, verifies the three labels, and separates the 53 named
keywords from 11 spare-word slots. It walks all 139 conversation-directory
roots at `$80:947A–958E`; their 731 entries form a contiguous, non-overlapping
catalogue at file offsets `$680C0–692AE`. All teaching fields and all dedicated
response selectors are counted. Forty-nine distinct named IDs are taught by
these records.

It also starts a conservative control-flow traversal at each of the 936 script
table roots. Opcode widths follow the source dispatch table at `$80:F27E`;
illegal operations, missing operands, out-of-extent branches and overlapping
instructions refuse the audit. Both conditional arms and local call targets
and continuations are visited. The qualified source yields 73 valid opcode
handlers and 46,273 distinct instruction addresses, with no unresolved decoding
frontier. Static traversal does not establish that every visited instruction is
reachable in normal play.

Four reachable script-native `$71` call sites remain. Each has exclusively an
immediate keyword push as its incoming instruction:

| Script | Bytecode PC | Learned ID |
| --- | --- | --- |
| `$09E` | `$0168` | `$07` (Cortex Bomb) |
| `$0C4` | `$00CB` | `$08` (Cyberware) |
| `$19E` | `$0004` | `$0E` (Drake) |
| `$352` | `$000F` | `$16` (Hiring) |

Cyberware supplies the fiftieth named ID; the other three are already present
in the dialogue teaching catalogue. Thus exactly the three reported names lack
a teaching site across these two catalogues. No reachable fixed-address
bytecode store targets the learned-keyword list. The report does **not** claim
a whole-game native control-flow or arbitrary indirect-write proof; debug
intervention and memory-corruption routes are outside this result.

The checker exports only authored labels, addresses, counts and hashes. It
exports no original bytes or decoded dialogue. Thirteen focused tests cover
selector-versus-teaching interpretation, malformed records, conditional arms,
unreachable bytes after a return, a branch that bypasses an immediate push,
invalid instruction boundaries and rejection of the wrong ROM.

## External lead and friction

The Admiral's technical walkthrough already identifies these three names and
reports that only Norbert and Scalper receive special responses. That was a
research lead, not the acceptance oracle. The original
[GameFAQs guide](https://gamefaqs.gamespot.com/snes/588651-shadowrun/faqs/19826)
could not be fetched in this run; an
[author-attributed mirror](https://shadowrun.fandom.com/pl/wiki/Przewodnik:Shadowrun_(SNES))
provided the keyword section. No guide text was copied into the implementation.

[Osteoclave's randomizer source](https://github.com/Osteoclave/shadowrun-randomizer/blob/main/shadowrun_randomizer.py)
provided useful leads for the script tables and `$71` operation. Its documented
USA ROM hash matches this supplied ROM, and the addresses and behavior were
then checked against the original bytes. The randomizer was read as source and
was not executed or used to modify the game.

Two investigation traps mattered. Scanning the whole ROM for `$58 $71` found
nine byte patterns, most outside script instructions; an early-return script
also retains an unreachable call. A traversal from actual script roots found
the four relevant sites. Secondly, the current conversation runtime accepts an
8-bit tag, but that interface limit does not mean the source directory has 256
records: it has 139, followed immediately by native code. Treating the remaining
bytes as pointers produces false records and false findings.
