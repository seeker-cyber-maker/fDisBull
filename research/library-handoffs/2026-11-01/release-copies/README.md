# Three Library release copies

> **Review status, November 3:** source identities and earlier tests, MR states,
> uploads and installation statements below are November 1 intake records.
> Read the [current review](../REVIEW_2026-11-03.md) for superseding findings and checks.
> Historical upload receipts do not verify present remote availability or privacy.

These are the three standalone files described in the interrupted handoff.
Their fresh Library URLs, observed sizes and full hashes are in
[library-comparison.json](library-comparison.json) and the parent inventory.

| Library copy | Observed bytes | Fresh package comparison |
| --- | ---: | --- |
| `fdisbull-0.29.0.tar(1).gz` | 2,234,060 | Byte-identical by size/SHA-256 to GitLab package file `381580946`; already preserved canonically. |
| `fdisbull-0.29.0-linux-x86_64-dependencies.tar(2).gz` | 50,475,916 | Byte-identical by size/SHA-256 to GitLab package file `381581034`; already preserved canonically. |
| `fdisbull-0.29.0-tool(1).zip` | 2,649,440 | Different from published file `381580949`, which is 2,650,174 bytes. Preserve this distinct source snapshot separately. |

The matching source distribution has SHA-256
`c839319fd153d9c2f6933afd9662a0c837889d2dc9a2fb80310e2c51d0ae65e8`;
the matching dependency archive has SHA-256
`e45801015b0d8e0dc7a6396997e01bd2b5c7dc01bfec0cf18f692fa83ac48ce6`.
They need no duplicate upload. Their complete file-member hashes are recorded
in [sdist/manifest.json](sdist/manifest.json) and
[dependencies/manifest.json](dependencies/manifest.json).

The differing tool snapshot has SHA-256
`ca0b76fdbf896862fd718dbbb70cc98b952783a5a9e82ed58669c2becf185c82`.
The canonical tool ZIP remains SHA-256
`4bb1b5227ce39a4b1095e15e20d8e52a3c603c634a2426c63aaaddbb551fbf26`.
See the [tool snapshot comparison](tool-variant/README.md) for the bounded
source differences. None of these files was installed or executed.

The [ten-file publisher inventory](../release-intake/publisher-package-files.json)
also accounts for the 103,013,282-byte native offline kit and 106,905,600-byte
source companion already present in GitLab. Their current server metadata is
recorded; their large payloads were not downloaded for this intake. Metadata
presence, local byte comparison and native qualification are separate gates.
