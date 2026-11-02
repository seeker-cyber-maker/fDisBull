import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs("FAIL: \(message)\n", stderr); exit(1) }
}
final class MemoryStore: ReplicaPreferenceStore {
    var values: [String: Any] = [:]
    func object(forKey key: String) -> Any? { values[key] }
    func set(_ value: Any?, forKey key: String) { values[key] = value }
}
let store = MemoryStore()
let prefs = ReplicaPreferences(store: store)
check(prefs.menuBarIconType == "Memory emoji", "default icon")
store.set("CPU Emoji", forKey: "iconChoice")
prefs.migrateLegacyIcon()
check(prefs.menuBarIconType == "CPU Emoji", "legacy icon copied")
check(store.object(forKey: "iconChoice") as? String == "CPU Emoji", "legacy value retained")
prefs.menuBarIconType = "Animated Dots"
prefs.migrateLegacyIcon()
check(prefs.menuBarIconType == "Animated Dots", "existing destination wins")
prefs.menuBarIconType = ReplicaPreferences.cpuGraphIcon
prefs.migrateLegacyIcon()
check(ReplicaPreferences(store: store).menuBarIconType == "CPU Graph", "graph selection restores through the existing preference key")
check(store.object(forKey: ReplicaPreferences.iconKey) as? String == "CPU Graph", "graph uses menuBarIconType rather than a separate setting")
prefs.menuBarIconType = ReplicaPreferences.cpuGraphMemoryIcon
check(ReplicaPreferences(store: store).menuBarIconType == "CPU Graph + Memory Emoji", "combined representation restores through the existing icon preference")
prefs.menuBarIconType = ReplicaPreferences.defaultIcon
check(prefs.menuBarIconType == "Memory emoji", "memory-only option remains selectable after combined mode")
prefs.caffeinePowerMode = "test-power"
prefs.caffeineProcessStopMode = "test-stop"
prefs.caffeineStartMode = "test-start"
prefs.launchAtLogin = true
check(prefs.caffeinePowerMode == "test-power" && prefs.caffeineProcessStopMode == "test-stop" && prefs.caffeineStartMode == "test-start", "string preferences round trip")
check(prefs.launchAtLogin == true, "boolean preference round trip")
let invalid = MemoryStore()
invalid.set(42, forKey: "iconChoice")
ReplicaPreferences(store: invalid).migrateLegacyIcon()
check(invalid.object(forKey: "menuBarIconType") == nil, "invalid legacy value ignored")
print("In-memory preference checks passed.")
