import Foundation

public struct StorageVolume: Identifiable, Hashable {
    public let id: String
    public let name: String

    public var mountPath: String { id }
    public var displayName: String { name.isEmpty ? (id == "/" ? "Startup volume" : URL(fileURLWithPath: id).lastPathComponent) : name }
}

public struct StorageReading {
    public let volume: StorageVolume
    public let totalBytes: Int64?
    public let availableBytes: Int64?
    public let format: String?
    public let isLocal: Bool?
    public let isRemovable: Bool?
    public let isReadOnly: Bool?
}

public enum StorageMetrics {
    public static let startupVolumeID = "/"
    private static let keys: Set<URLResourceKey> = [
        .volumeNameKey, .volumeURLKey, .volumeTotalCapacityKey,
        .volumeAvailableCapacityForImportantUsageKey,
        .volumeLocalizedFormatDescriptionKey, .volumeIsLocalKey,
        .volumeIsRemovableKey, .volumeIsReadOnlyKey
    ]

    /// Only user-visible startup and /Volumes mounts are offered. APFS helper
    /// volumes such as Preboot and VM are intentionally excluded.
    public static func availableVolumes(fileManager: FileManager = .default) -> [StorageVolume] {
        let mounted = fileManager.mountedVolumeURLs(includingResourceValuesForKeys: Array(keys), options: [.skipHiddenVolumes]) ?? []
        let roots = [URL(fileURLWithPath: startupVolumeID)] + mounted
        var seen = Set<String>()
        return roots.compactMap { url -> StorageVolume? in
            let path = url.standardizedFileURL.path
            guard path == startupVolumeID || path.hasPrefix("/Volumes/"), seen.insert(path).inserted,
                  let values = try? url.resourceValues(forKeys: keys),
                  let capacity = values.volumeTotalCapacity, capacity > 0 else { return nil }
            return StorageVolume(id: path, name: values.volumeName ?? "")
        }.sorted { left, right in
            if left.id == startupVolumeID { return true }
            if right.id == startupVolumeID { return false }
            return left.displayName.localizedStandardCompare(right.displayName) == .orderedAscending
        }
    }

    /// Refuses a stale mount path after a drive is removed, rather than
    /// accidentally reporting the startup volume under the old drive name.
    public static func sample(_ volume: StorageVolume) -> StorageReading? {
        let url = URL(fileURLWithPath: volume.mountPath)
        guard let values = try? url.resourceValues(forKeys: keys),
              values.volume?.standardizedFileURL.path == volume.mountPath else { return nil }
        return StorageReading(volume: volume,
                              totalBytes: values.volumeTotalCapacity.map(Int64.init),
                              availableBytes: values.volumeAvailableCapacityForImportantUsage,
                              format: values.volumeLocalizedFormatDescription,
                              isLocal: values.volumeIsLocal,
                              isRemovable: values.volumeIsRemovable,
                              isReadOnly: values.volumeIsReadOnly)
    }
}
