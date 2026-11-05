# Matched task: recover Colonization production dependencies

This is a research-method pilot, not a game-porting task. Use the assigned fresh
workspace, the exact original DOS executable and its companion text resources.
Report item-production relationships supported by the original code. Game
knowledge is a hypothesis until its correspondence is checked.

## Common target and starting resources

- `VICEROY.EXE`: 494,910 bytes; SHA-256
  `a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3`.
- `NAMES.TXT`: 13,820 bytes; SHA-256
  `4bf5ba261f71e9215450801d0ac4b00a66e91b046a3b592516524bea03bd6061`.
- `LABELS.TXT`: 3,386 bytes; SHA-256
  `e4af0da201eb4df5ecdc2033d711d30f975c752f2967dc97b6a8159004582204`.

Both workers receive these same original resources. They are part of the target,
not outside guide assistance. Do not run the installer; neutral preparation has
already extracted and verified inputs. No preannotated FDB, recovered function
map, target-specific notebook or previous chat is included.

Allowed common tools: the same pinned disassembler/runtime, Python, binary/hex
inspection, generic processor documentation, and independent private output.
Tool installation and basic help are prepared before starting either clock.
Specify actual versions. No game modifications, release changes or Git writes.

## Output and scope

Recover a bounded directed graph of manufactured outputs and their material
inputs. Distinguish direct dependencies from chains through intermediates;
include non-cargo production counters when encountered. Identify the job and
building associations where supported. Do not force all fields into recipes.

For each proposed relationship give logical input/output IDs, the naming source,
original instruction/table locations and source identity, what the reader/writer
actually does, qualification scope, and one discriminating check. Unresolved
labels, dependencies and special cases remain explicit. A matched string or
adjacent table alone is not sufficient evidence of consumption.

Separate inventory/storage mutations from production accounting. Recovering a
shortage calculation is not a whole warehouse update. Do not claim quantities,
ratios, full-turn timing or normal-play reachability you did not establish.

Deliver:
1. `claims.json` following the attached schema/template;
2. `REPORT.md` with supported results and open frontiers;
3. authored scripts and compact sanitized evidence;
4. `events.jsonl`, actual model/tool settings, source-access log and usage if
   available. A missing usage count stays null, not estimated.

## Equal effort budget and stopping

Pilot proposal: same model/version/reasoning policy, 30 minutes of active wall
clock, at most 80 tool calls and 16,000 reported output tokens per worker. The
first hard limit stops the worker; unavailable token telemetry is declared.
Queue time and source staging are separately measured. Do not quietly restart an
unsuccessful attempt; preserve its outcome. These limits are study settings, not
an estimate of how long the task will take.

Start when the worker receives its task and can access the target. End-to-end
acceptance time includes research, analysis, repair and review feedback. Every
claim-submission checkpoint is retained, including wrong early candidates.

Log observable actions and brief evidence-based decisions, not private reasoning.
Never inspect the other worker's files, curator results or answer key.
