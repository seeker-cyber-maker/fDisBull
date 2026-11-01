# Simple Menu Status Replica

An independent native macOS menu bar replica in progress, based on observed Simple Menu STATUS 1.8 behavior. It uses its own bundle identifier (`local.codex.simple-menu-status-replica`) and preferences; it does not modify the installed app. The parity gaps are tracked in [PARITY.md](PARITY.md).

An executable, bounded [UIL candidate](experiments/uil/simple-menu-status/README.md) models selected controls using fDisBull's existing interaction IL. It includes verification receipts and [tooling recommendations](experiments/uil/simple-menu-status/FEATURE_RECOMMENDATIONS.md), with original native equivalence left unresolved.

## Build and run

Requires macOS and Swift command-line tools. From this directory:

```sh
./test.sh
./build-app.sh
open "build/Simple Menu Status Replica.app"
```

Use the menu bar icon to open the popover. The sliders open a nested Dashboard layout menu with section switches, the gear opens Settings, and the share button opens a local image preview with Copy image and native Share… actions. Right-click the replica’s menu bar icon for Quit. The app refreshes every two seconds; GPU and process sampling run only while the dashboard is open (process sampling also requires its section). Its memory emoji uses macOS memory-pressure notifications: normal 😊, warning 😐, critical 😰, unknown ❔. At startup, before an event arrives, the icon uses a reclaimable-aware estimate based on free and inactive pages; its 30% and 15% available-memory thresholds are replica choices, not system pressure levels. Later system events override that estimate. This mapping is a replica design choice; the original app's logic and the cause of any particular emoji are not established. Memory used is an estimate of active, wired, and compressed pages; it is not the same as memory pressure or Activity Monitor's calculation. CPU needs two samples before showing a percentage. Storage starts on the macOS startup volume (shown as Macintosh HD on the development Mac) and can be changed with the Storage volume menu. It uses macOS's estimated capacity available for important writes; that can include reclaimable space and differs from ordinary free bytes. Network lists active non-loopback IPv4 interfaces and shows estimated throughput for one selected interface, not proof of internet access. Battery is unavailable on machines without an accessible battery. The compact Network section lists local addresses and requests Global IP once when Network Info first becomes visible; the refresh button can request it again. The request contacts ipify, which sees the request’s public IP. Interface rates and system VPN controls are in the optional CPU and memory details / Developer view.

The sliders menu contains a Dashboard layout submenu, including Local AI directly above Custom. AppKit positions the two menu levels within the visible screen. Changing a section switch selects Custom. APFS volumes can share container capacity, so the Storage used and available figures describe capacity on that shared container rather than files owned by one APFS volume.

## Preferences

The original app uses macOS UserDefaults inside its sandbox container. This unsigned replica also uses UserDefaults, with its own bundle identifier and plist at `~/Library/Preferences/local.codex.simple-menu-status-replica.plist`; it never writes the original app's domain or container. The current app persists the icon choice, dashboard layout and section switches, selected storage volume, sleep-prevention mode and duration, process threshold, three alert thresholds, alert hold duration, recovery preference, and enabled state. It copies an earlier replica `iconChoice` value to `menuBarIconType` once, without reading the Store app's preferences. Some key names match observed original keys, but the replica's string values are its own; their encoding is not claimed to match the original. Launch at Login is controlled by macOS login state and is also recorded in the replica's defaults after an explicit change.

## Scope and gaps

The dashboard includes live CPU, memory, storage, battery and network-interface status. Settings exposes the seven observed icon choices and additional CPU Graph and CPU Graph + Memory Emoji choices; two earlier replica choices remain recognized for saved preferences. It does not yet reproduce the exact original icon artwork or behavior, complete VPN inventory, exact dashboard presets, full Japanese localization, or precise original layout and calculations. Sharing produces a numeric-only in-memory PNG; the original image artwork and live share flow have not been compared. The controls and emoji thresholds should not be interpreted as evidence of original internals. CPU, memory-usage, and selected-volume storage alerts are off by default and request notification permission only when enabled. Their local defaults are 90% thresholds and a 30-second hold; Alert options can change these values, the hold time, and recovery notices. A five-minute cooldown applies per metric. The enabled preference is restored only while macOS notification authorization remains available; a new launch resets the in-memory hold state. The original app's alert defaults and post-enable layout have not been verified. Cache review is manual, limited to this replica’s own cache files older than seven days. Eligible files start selected in a separate confirmation sheet and require an explicit move to Trash. The path-based move revalidates before moving but cannot rule out a concurrent replacement race. Launch at Login requires explicit user action. The unsigned local bundle uses a per-user LaunchAgent; team-signed bundles can use macOS ServiceManagement. Registration changes take effect at a later login and can be disabled in Settings. There is no elevated operation. Tests exercise pressure mapping, initial estimation, network rate math, process sampling and caffeine timing; they do not verify real pressure transitions or interactive sleep assertions. The app is unsigned and local. The current build was launched locally as a separate menu-bar process; its visual fidelity, interactions, event delivery, and sharing require separate verification.

The Language setting uses the replica's own Japanese text for the visible dashboard, Local AI layout, Settings and main detail labels. Some backend messages and detailed diagnostics remain English. The replica switches languages immediately; the installed app's language resource says a restart is required. The live Japanese check was ended with the replica's prior unset language preference restored, and the replica was stopped.

The measured-indicators banner reports an issue only when a locally measured value crosses a replica-defined threshold (CPU or GPU at least 90%, memory warning/critical, or available storage at most 10%). It waits for a CPU sample before showing “No issues in measured indicators.” CPU card colors change at 50% and 80% usage. These rules match some observed presentation states; the original app's thresholds are unknown.

| Area | This slice | Not yet implemented |
| --- | --- | --- |
| CPU | Aggregate utilization, recent history, attached per-core panel, and E/P cluster readings in Local AI | Exact core topology on other Macs and original graph presentation |
| Memory | Estimated used/total, recent history, attached colored breakdown and memory-pressure emoji | Original app's calculation and exact appearance |
| Storage | Visible mounted-volume picker; selected volume, mount point, total, used, available, format, location, write status, and optional folder-size estimates | Exact macOS System/Applications/Documents category totals and original dashboard options |
| Battery | Capacity and power-source state, plus optional cycle/health details where available | Full battery presentation and time details |
| Network | Active non-loopback IPv4 addresses with copy buttons and estimated byte rates for one interface | Network history and other network actions; app-managed VPNs may not appear |
| VPN | Read-only SystemConfiguration service status, explicit connect/disconnect and Settings actions | App-managed VPN inventory and guaranteed connection success |
| GPU | Best-effort device, renderer and tiler utilization, core count, recent history, and host GPU shared-memory counters when exposed by the driver | Broader device support and exact original presentation |
| Processes | Top five accessible processes by CPU usage | Process detail, controls and original presentation |
| Caffeine | Opt-in system or system + display idle sleep prevention, timed or process-based; collapsible Additional options | Exact original controls, child-process tracking and presentation |
| Dashboard | Configurable sections and approximate layout presets with selected checkmark; separate Local AI layout with CPU clusters, thermal/load/uptime, GPU shared memory, and unified RAM; height adjusts to shorter layouts | Exact original preset behavior and full presentation |
| Alerts | Opt-in CPU, memory, and selected-volume storage thresholds, hold duration, five-minute cooldown, and recovery notices | Exact original defaults, post-enable layout, and notification behavior |
| Cache | Review preselected eligible replica cache files before moving them to Trash | Original behavior; path-based revalidation is not atomic |
| Sharing | Local PNG preview with CPU, memory, GPU and battery percentages, Copy image, and a native picker anchored to its Share… button | Original image artwork and live picker behavior |
| Menu icon | Nine visible choices saved locally, with two earlier replica values still recognized | Original styling or behavior; the older two-line choice is rendered on one line and fan speed is unavailable |

Process-based Prevent Sleep is opt-in in Details. Choose a specific process lifetime and CPU threshold, then press Start. The replica samples that process every two seconds and stops its own sleep assertion on verified exit or five consecutive checks with a rolling one-minute arithmetic sample average below the threshold. Missing readings reset the sequence rather than proving exit. This is replica-defined behavior; the original app’s precise process semantics are unknown.

The Local AI layout follows the host-stat definitions in [oMLX's menu-bar panels](https://github.com/jundot/omlx/blob/96361a5883fcf50f9eb7f22a9f2cecfe76bb62fb/apps/omlx-mac/Sources/Menubar/SystemStatsPanels.swift) and [sampler](https://github.com/jundot/omlx/blob/96361a5883fcf50f9eb7f22a9f2cecfe76bb62fb/apps/omlx-mac/Sources/Menubar/SystemStatsSampler.swift). On Apple Silicon, the displayed GPU memory is driver-reported use of shared system RAM, not dedicated VRAM or one model's allocation. oMLX's separate admin-screen “GPU Wired Memory” is supplied by its server and is not shown without connecting to that server. The Storage picker lists visible mounted volumes. Its detail panel shows values available from the selected volume; selecting a removed volume falls back to the startup volume. Press **Estimate** in Storage Details to calculate readable System, Applications, and Documents *folder* sizes on the selected volume. The scan is optional, runs off the UI thread, checks a limit of 12,000 entries or two seconds per group, can be stopped, and reports partial results. These folder estimates are not macOS Storage Settings category totals; symlinks and other mounted volumes are skipped.

The development build lives on `/Volumes/CODEX`. The installed replacement is at `~/Applications/Simple Menu Status Replica.app`; its login agent uses that local path and does not depend on the external development volume.

## CPU Graph representation

Select **Settings → Icon Display → CPU Graph** to replace the menu-bar emoji
with one vertical bar per logical CPU. The graph uses the existing per-core
samples and the app's two-second refresh interval, including while the dashboard
is closed. Green indicates below 75% usage, orange 75% to below 90%, and red 90% or
above. Neutral tracks represent unavailable readings. Its compact layout and
calibrated colors follow the cpuinfo renderer verified during this project.
The graph adapts to the menu bar's appearance/backing scale, and the coffee
indicator remains visible while Prevent Sleep is active.

The choice is saved through the existing menuBarIconType preference in the
replica's own domain. Memory Emoji and the other representations remain
selectable. The saved choice/default is preserved by this build.

## Replacing an active keep-awake app

An explicit `--resume-display-awake` launch argument starts this replica's
System + Display Prevent Sleep mode until stopped. It exists for handing over
an already-active assertion during app replacement. Normal launches and the
login agent do not include this argument and do not automatically enable
Prevent Sleep. Check the new process's power assertion before stopping the old
app. The installed replacement uses the user-local Applications folder so login
startup does not depend on mounting the development volume.

## CPU Graph + Memory Emoji

Choose **Settings → Icon Display → CPU Graph + Memory Emoji** to show the
per-core CPU bars and memory-pressure emoji together in one menu-bar item.
The existing pressure mapping drives the emoji independently of CPU activity:
normal 😊, warning 😐, critical 😰, unknown ❔. The coffee indicator is appended
while Prevent Sleep is active. Graph-only and emoji-only choices remain
available; the combined choice is saved through the same icon preference.
