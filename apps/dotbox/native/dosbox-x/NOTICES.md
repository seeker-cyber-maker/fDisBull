# DOSBox-X native source notices

This directory retains the complete stable agent patch and its source manifest
from [fDisBull](https://github.com/seeker-cyber-maker/fDisBull), commit
`ce91c303f2fccd1db9b1e3917ecc8c98473bfdb9`, path `experimental/dosbox-x`.
The files `headless-agent.patch`, `source-manifest.json` and `COPYING` are copied
without modification from that commit. They are build inputs owned by this
DotBox source delivery; preparation does not contact or import fDisBull.

The patch applies to [DOSBox-X](https://github.com/joncampbell123/dosbox-x),
commit `029bd65c5dcc7cdc7f2e14e35278620d9707d969`. Its source files retain the
upstream contributor and copyright notices. Modified DOSBox-X source is under
GPL-2.0-or-later; the upstream GPL version 2 text is retained in `COPYING`.
The DotBox cooperative-input overlay in the parent directory is also modified
DOSBox-X source under GPL-2.0-or-later. No upstream endorsement is claimed.

Preserve these notices, the upstream notices, the complete patch chain and
corresponding source when redistributing the native program. A binary delivery
also needs the notices/source required by the actual libraries linked into that
delivery. DotBox's Python package license does not replace the native license.

Historical build and verification fields in the copied source manifest retain
their original provenance. They do not qualify a new DotBox build, a different
host, or Dot's desktop takeover flow. DotBox's source recipe and its separate
native acceptance records determine those claims.

No emulator binary, commercial game, game asset, save or machine state is
included in this directory.
