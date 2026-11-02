import Foundation

/// Folder groups for a manual storage estimate. These are paths, not macOS
/// Storage Settings categories, and may omit files elsewhere on the volume.
public enum StorageFolderCategory: String, CaseIterable, Identifiable {
    case system, applications, documents
    public var id: String { rawValue }
}

public struct StorageFolderScanRequest {
    public let category: StorageFolderCategory
    public let label: String
    public let roots: [URL]

    public init(category: StorageFolderCategory, label: String, roots: [URL]) {
        self.category = category
        self.label = label
        self.roots = roots
    }
}

public enum StorageFolderScanStatus: Equatable {
    case complete, partial, notPresent, cancelled
}

public struct StorageFolderEstimate {
    public let category: StorageFolderCategory
    public let label: String
    /// Allocated file bytes where reported, otherwise logical file bytes.
    /// Nil means no requested root could be scanned.
    public let bytes: UInt64?
    public let entriesVisited: Int
    public let filesCounted: Int
    public let errors: Int
    public let status: StorageFolderScanStatus
    public let note: String?
}

public struct StorageFolderScanLimits {
    public let maxEntriesPerCategory: Int
    public let maxSecondsPerCategory: TimeInterval

    public static let `default` = StorageFolderScanLimits(maxEntriesPerCategory: 12_000,
                                                            maxSecondsPerCategory: 2)

    public init(maxEntriesPerCategory: Int, maxSecondsPerCategory: TimeInterval) {
        self.maxEntriesPerCategory = max(1, maxEntriesPerCategory)
        self.maxSecondsPerCategory = maxSecondsPerCategory.isFinite
            ? min(300, max(0.01, maxSecondsPerCategory)) : 2
    }
}

public final class StorageFolderScanCancellation {
    private let lock = NSLock()
    private var cancelled = false
    public init() {}
    public func cancel() { lock.lock(); cancelled = true; lock.unlock() }
    public var isCancelled: Bool { lock.lock(); defer { lock.unlock() }; return cancelled }
}

public enum StorageFolderScanner {
    /// The startup volume includes the current user's Documents folder. A
    /// Documents folder relocated to another volume will be rejected below.
    public static func requests(for volume: StorageVolume,
                                homeURL: URL = URL(fileURLWithPath: NSHomeDirectory())) -> [StorageFolderScanRequest] {
        let base = URL(fileURLWithPath: volume.mountPath, isDirectory: true)
        if volume.id == StorageMetrics.startupVolumeID {
            return [
                StorageFolderScanRequest(category: .system, label: "System folder",
                                         roots: [base.appendingPathComponent("System", isDirectory: true)]),
                StorageFolderScanRequest(category: .applications, label: "Applications folders",
                                         roots: [base.appendingPathComponent("Applications", isDirectory: true),
                                                 homeURL.appendingPathComponent("Applications", isDirectory: true)]),
                StorageFolderScanRequest(category: .documents, label: "My Documents folder",
                                         roots: [homeURL.appendingPathComponent("Documents", isDirectory: true)])
            ]
        }
        return [
            StorageFolderScanRequest(category: .system, label: "System folder",
                                     roots: [base.appendingPathComponent("System", isDirectory: true)]),
            StorageFolderScanRequest(category: .applications, label: "Applications folder",
                                     roots: [base.appendingPathComponent("Applications", isDirectory: true)]),
            StorageFolderScanRequest(category: .documents, label: "Documents folder",
                                     roots: [base.appendingPathComponent("Documents", isDirectory: true)])
        ]
    }

    /// Call on a background queue after a user action. Each category has a
    /// separate finite time and entry budget, and the token can stop the scan.
    public static func scan(requests: [StorageFolderScanRequest], volume: StorageVolume,
                            limits: StorageFolderScanLimits = .default,
                            cancellation: StorageFolderScanCancellation = StorageFolderScanCancellation(),
                            fileManager: FileManager = .default) -> [StorageFolderEstimate] {
        requests.map { scanOne($0, volume: volume, limits: limits,
                               cancellation: cancellation, fileManager: fileManager) }
    }

    private static func scanOne(_ request: StorageFolderScanRequest, volume: StorageVolume,
                                limits: StorageFolderScanLimits,
                                cancellation: StorageFolderScanCancellation,
                                fileManager: FileManager) -> StorageFolderEstimate {
        let keys: Set<URLResourceKey> = [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey,
                                         .volumeURLKey, .fileAllocatedSizeKey,
                                         .totalFileAllocatedSizeKey, .fileSizeKey]
        let started = DispatchTime.now().uptimeNanoseconds
        let budgetNanos = UInt64(limits.maxSecondsPerCategory * 1_000_000_000)
        var total: UInt64 = 0
        var entries = 0, files = 0, errors = 0, scannedRoots = 0
        var notes: [String] = []
        var partial = false
        var cancelled = false

        func timeExpired() -> Bool { DispatchTime.now().uptimeNanoseconds &- started >= budgetNanos }
        func addBytes(_ amount: UInt64) {
            let (sum, overflow) = total.addingReportingOverflow(amount)
            total = overflow ? UInt64.max : sum
            if overflow { partial = true; notes.append("Size counter overflowed.") }
        }

        for root in request.roots {
            if cancellation.isCancelled { cancelled = true; break }
            if entries >= limits.maxEntriesPerCategory || timeExpired() {
                partial = true; notes.append("Scan limit reached."); break
            }
            let path = root.standardizedFileURL
            let rootValues: URLResourceValues
            do { rootValues = try path.resourceValues(forKeys: keys) }
            catch {
                let problem = error as NSError
                if problem.domain != NSCocoaErrorDomain || problem.code != NSFileReadNoSuchFileError {
                    errors += 1; notes.append("Could not read \(path.lastPathComponent).")
                }
                continue
            }
            if rootValues.isSymbolicLink == true {
                partial = true
                notes.append("Skipped linked \(path.lastPathComponent) folder.")
                continue
            }
            guard rootValues.isDirectory == true else { continue }
            guard rootValues.volume?.standardizedFileURL.path == volume.mountPath else {
                partial = true
                notes.append("\(path.lastPathComponent) is on another volume.")
                continue
            }
            scannedRoots += 1
            var rootErrors = 0
            guard let enumerator = fileManager.enumerator(at: path,
                                                          includingPropertiesForKeys: Array(keys),
                                                          options: [], errorHandler: { _, _ in
                rootErrors += 1
                return true
            }) else {
                errors += 1; notes.append("Could not list \(path.lastPathComponent)."); continue
            }
            while let item = enumerator.nextObject() as? URL {
                if cancellation.isCancelled { cancelled = true; break }
                if entries >= limits.maxEntriesPerCategory || timeExpired() {
                    partial = true; notes.append("Scan limit reached."); break
                }
                entries += 1
                guard let values = try? item.resourceValues(forKeys: keys) else {
                    errors += 1; enumerator.skipDescendants(); continue
                }
                if values.isSymbolicLink == true {
                    enumerator.skipDescendants()
                    continue
                }
                if values.volume?.standardizedFileURL.path != volume.mountPath {
                    enumerator.skipDescendants()
                    continue
                }
                guard values.isRegularFile == true else { continue }
                let size = values.totalFileAllocatedSize ?? values.fileAllocatedSize ?? values.fileSize
                guard let size, size >= 0 else { errors += 1; continue }
                addBytes(UInt64(size))
                files += 1
            }
            errors += rootErrors
            if cancelled || partial { break }
        }

        if errors > 0 { partial = true; notes.append("Unreadable items were skipped.") }
        let status: StorageFolderScanStatus
        if cancelled { status = .cancelled; notes.append("Scan cancelled.") }
        else if scannedRoots == 0 {
            status = errors > 0 ? .partial : .notPresent
            if notes.isEmpty { notes.append("Folder not present on this volume.") }
        }
        else { status = partial ? .partial : .complete }
        return StorageFolderEstimate(category: request.category, label: request.label,
                                     bytes: scannedRoots == 0 ? nil : total,
                                     entriesVisited: entries, filesCounted: files,
                                     errors: errors, status: status,
                                     note: notes.isEmpty ? nil : notes.joined(separator: " "))
    }
}
