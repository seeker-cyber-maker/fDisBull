# fDisBull 0.32.0 source intake and qualification

[intake.json](intake.json) records the selected source revisions and exclusions.
The release retains the published 0.31.1 lineage and composes the protected-DOS
and screenshot-codec native patches rather than replacing either feature.

Full local qualification requires ordinary package/test checks, both native
DOSBox profiles, and complete installed-wheel PE/DOS/boot acceptance on the
exact source commit. Required native cases may not skip. New signed-return
regressions and each selected optional backend have separate explicit coverage.

The manual GitLab release carries the source-bound validation receipt, package
SHA-256 inventory and supported-platform limits. Neither this file nor the
source intake alone claims that a build passed. No private runtime inputs are
part of the source or tool packages.
