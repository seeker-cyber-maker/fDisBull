import Foundation

/// Storage is kept in the replica's own defaults domain, never the original app's domain.
public protocol ReplicaPreferenceStore {
    func object(forKey key: String) -> Any?
    func set(_ value: Any?, forKey key: String)
}

extension UserDefaults: ReplicaPreferenceStore {}

public struct ReplicaPreferences {
    public static let domain = "local.codex.simple-menu-status-replica"
    public static let iconKey = "menuBarIconType"
    public static let legacyIconKey = "iconChoice"
    public static let defaultIcon = "Memory emoji"
    public static let cpuGraphIcon = "CPU Graph"
    public static let cpuGraphMemoryIcon = "CPU Graph + Memory Emoji"
    // Standard defaults already use this app's bundle identifier as their
    // persistent domain. A suite with that same name is rejected by macOS.
    public static let defaults = UserDefaults.standard

    private let store: ReplicaPreferenceStore

    public init(store: ReplicaPreferenceStore = ReplicaPreferences.defaults) {
        self.store = store
    }

    /// Copies the previous replica setting once without overwriting an existing new key.
    /// The legacy value is retained so that reverting to an earlier build remains safe.
    public func migrateLegacyIcon() {
        guard store.object(forKey: Self.iconKey) == nil,
              let value = store.object(forKey: Self.legacyIconKey) as? String else { return }
        store.set(value, forKey: Self.iconKey)
    }

    public var menuBarIconType: String {
        get { store.object(forKey: Self.iconKey) as? String ?? Self.defaultIcon }
        nonmutating set { store.set(newValue, forKey: Self.iconKey) }
    }
    public var caffeinePowerMode: String? {
        get { store.object(forKey: "caffeinePowerMode") as? String }
        nonmutating set { store.set(newValue, forKey: "caffeinePowerMode") }
    }
    public var caffeineProcessStopMode: String? {
        get { store.object(forKey: "caffeineProcessStopMode") as? String }
        nonmutating set { store.set(newValue, forKey: "caffeineProcessStopMode") }
    }
    public var caffeineStartMode: String? {
        get { store.object(forKey: "caffeineStartMode") as? String }
        nonmutating set { store.set(newValue, forKey: "caffeineStartMode") }
    }
    public var launchAtLogin: Bool? {
        get { store.object(forKey: "launchAtLogin") as? Bool }
        nonmutating set { store.set(newValue, forKey: "launchAtLogin") }
    }
}
