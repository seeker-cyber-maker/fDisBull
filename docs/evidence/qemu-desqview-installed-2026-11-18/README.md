# Installed Mac DESQview witness

A fresh private DESQview disk run passed on the installed source package and corrected Mac QEMU producer. It opened two DOS windows, returned through the DESQview menus, switched back to the first window and executed `echo x1`, observing the separate `x1` output and prompt. The [verification receipt](verification.json) records exact source, producer, package, disk and controller identities.

The first run stopped because the historical controller accepted only a plain `timeout`. fDisBull had correctly returned an internal tracking deadline at the end of the requested host interval. A separate controller accepts that specific `timed_out=true` deadline result and journals every interval; it still fails on other stops. AST comparison verified that no native run, retry or delay was added. The failed receipt remains retained.

The accepted run recorded 46 execution intervals: 36 ordinary timeouts and ten internal tracking deadlines. It completed in 43.63 seconds under a 150-second bound. Original media, runtime dependencies and all 720 installed payload files remained unchanged, and no owned process remained.

This is a scoped vendor workload observation. It does not qualify arbitrary QEMM configurations, task-lifetime authority, protected memory, driver timing or checkpoint behavior. No commercial/private media, raw screen captures, database or emulator state is included here.

