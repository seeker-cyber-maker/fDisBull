# Agent QA friction to authorized tool improvements

Use this reference only after a concrete tool/skill friction event, not on every investigation. The independent test agent reports attempted command, expected and observed result, reproducible inputs, tool/source version, evidence references and effort. The optional salty_note contains honest tester impressions separate from objective facts; don't score agent hostility or leak private game content.

First check whether the capability exists but is undiscoverable, is defective, or is truly missing. Small repairs and deterministic helpers within scope can proceed. A reusable processor or major backend requires an explicit human decision: go_with_it to implement on a review branch; do_your_best to continue with existing tools; stop_here to park affected work. The approval does not authorize CI, release, publication, or weakening verification.

Development and test agents are different. After any implementation, run the original blocked task again plus regression and a held-out transfer where relevant. Keep initial failure and QA observations as version-bound evidence. Review before promoting to the skill. No tool silently self-certifies.

Pilot API: python -m fdisbull.agent_friction report.json --capability-status unknown. It only validates and triages a saved JSON report. No command execution, repository changes or user approvals occur.
