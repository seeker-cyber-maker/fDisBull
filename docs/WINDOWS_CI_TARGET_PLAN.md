# Proposed Windows qualification targets

This is a plan, not a Windows support receipt or permission to start Windows CI.

Keep three axes separate: the fDisBull host OS; the execution environment
(native Windows, Linux, or Linux inside WSL2/QEMU); and the debuggee format/OS
(DOS, NE/Win16, PE32/x86, PE64/x64, and specifically qualified Windows APIs).

WSL2 supplies a Linux kernel in a managed VM. Running Linux QEMU there would
qualify the Linux stack on Windows hardware, not Windows Python, file locking,
paths or process control. Putting Windows and then WSL2 on the Linux OVH VPS
adds OS and memory overhead; it is unnecessary for the current Linux gate.

Proposed future order:
1. Native Windows 11 x64, pinning a supported GA release/build, for installation,
   imports, CLI, project restart, artifacts and selected portable tests.
2. A second supported Windows 11 release if users need upgrade-window coverage,
   using a selected smoke lane rather than duplicating every native build.
3. Windows Server 2025 x64 only for intended unattended server deployments.
   Core/Desktop Experience differ for GUI work; add 2022 only for a declared need.
4. Windows 11 ARM64 separately; x64 emulation does not establish native ARM64
   Python-wheel or backend support.
5. Windows 10 only for an explicit legacy/ESU/LTSC requirement, with its own
   lifecycle and scope. Ordinary general support has ended.

PE32/PE64/Win16 are not Windows release numbers. Wine execution does not prove
full Windows 3.x/9x/XP/7/10/11 compatibility. Historical OS guests require their
own licensed/private inputs, checkpoints and authored test cases.

Start with one Windows host smoke lane. Native backend builds/parity are later
gates. Avoid porting both historical DOSBox profiles merely to sunset them.

Recheck Microsoft sources when choosing actual versions:
- https://learn.microsoft.com/en-us/windows/wsl/compare-versions
- https://learn.microsoft.com/en-us/windows/release-health/windows11-release-information
- https://learn.microsoft.com/en-us/windows-server/get-started/windows-server-release-info
- https://learn.microsoft.com/en-us/windows/release-health/release-information

No Windows VM, runner, license purchase or CI run is started by this plan.
