# Research artifact publication audit

This is a reviewed **subset** of 53 current Library artifacts, not a mirror of their original ZIP files. `catalog.json` identifies source versions, source and output SHA-256 hashes, and derivations. Historical baseline evidence is retained under its original pack lineage.

## Included
- 1,432 documents, measurements, decoded-flow and semantic game/UIL representations.
- 9 rebuilt, sanitized SQLite databases (gzip).
- 5 sanitized Zork semantic UIL/IR JSON representations (gzip).
- Reviewed standalone Mechanics HTML and an active authored Algorithm Lab semantic simulator are among the documents.

## Excluded
Original executables and game resources; whole original archives; raw target memory/opcode/relocation caches; raw observations; screenshots/media; nested wheels; game source/build targets; and private conversation inputs. The original databases and Zork archives contain original target bytes and must not be substituted for these derivatives. Concept illustrations and some public tool metadata are conservatively held too, rather than asserted unsafe.

## Important limitations
These sanitized databases/UIL files are **research exports, not runnable or reopening-equivalent original projects**. Raw payload-dependent predicates/artifacts are deliberately incomplete. Embedded historical checksums and receipts describe their original packages; the catalog gives authoritative output hashes for this subset. Large text and databases use deterministic gzip.

Static archive/JSON/SQLite review found and removed original-image, raw cache and media payloads. SQLite derivatives were freshly rebuilt; integrity checks pass, freelists are empty, and retained BLOB payloads are empty. Private Library links and local work paths were redacted. No bundled code or target was executed; originals were not changed.

Secret/privacy detection is heuristic. This audit does not guarantee copyright clearance, platform-policy compliance, or GitHub account safety. User-permitted semantic representations and original-derived narrative content remain; a future semantic/content sanitation pass is separate.
