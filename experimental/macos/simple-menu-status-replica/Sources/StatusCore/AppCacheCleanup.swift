import Foundation
import Darwin

/// A snapshot of one regular file in this application's cache directory.
public struct AppCacheCandidate: Hashable {
    public let url: URL
    public let size: UInt64
    public let modifiedAt: Date
    fileprivate let device: UInt64
    fileprivate let inode: UInt64
    fileprivate let changedSeconds: Int64
    fileprivate let changedNanos: Int64
}

public enum AppCacheCleanupError: Error {
    case invalidCacheDirectory
    case candidateChanged
}

/// Manual, opt-in cleanup of this replica's own cache. No cleanup runs on its own.
public final class AppCacheCleanup {
    public static let bundleIdentifier = "local.codex.simple-menu-status-replica"
    public static let minimumAge: TimeInterval = 7 * 24 * 60 * 60
    private let root: URL
    private let trash: (URL) throws -> Void

    public convenience init() throws {
        let caches = try FileManager.default.url(for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: false)
        self.init(root: caches.appendingPathComponent(Self.bundleIdentifier, isDirectory: true), trash: { url in
            var resultingURL: NSURL?
            try FileManager.default.trashItem(at: url, resultingItemURL: &resultingURL)
        })
    }

    // Internal injection confines tests to a disposable directory and a recorder.
    init(root: URL, trash: @escaping (URL) throws -> Void) {
        self.root = root.standardizedFileURL
        self.trash = trash
    }

    /// Missing cache directory means there is nothing to preview.
    public func preview(now: Date = Date()) throws -> [AppCacheCandidate] {
        guard try validRoot() else { return [] }
        guard let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil, options: [], errorHandler: { _, _ in false }) else { throw AppCacheCleanupError.invalidCacheDirectory }
        var result: [AppCacheCandidate] = []
        while let url = enumerator.nextObject() as? URL {
            guard let info = metadata(url) else { continue }
            if info.kind == S_IFLNK { enumerator.skipDescendants(); continue }
            guard info.kind == S_IFREG, safePath(url), info.modifiedAt < now.addingTimeInterval(-Self.minimumAge) else { continue }
            result.append(info.candidate(url))
        }
        return result.sorted { $0.url.path < $1.url.path }
    }

    /// Revalidate every explicitly selected snapshot immediately before moving it.
    /// Returns the snapshots successfully moved; an error stops the remaining moves.
    public func moveToTrash(_ selected: [AppCacheCandidate], now: Date = Date()) throws -> [AppCacheCandidate] {
        guard try validRoot() else { throw AppCacheCleanupError.invalidCacheDirectory }
        var moved: [AppCacheCandidate] = []
        for candidate in selected {
            guard safePath(candidate.url), let info = metadata(candidate.url), info.kind == S_IFREG,
                  info.modifiedAt < now.addingTimeInterval(-Self.minimumAge), info.candidate(candidate.url) == candidate else {
                throw AppCacheCleanupError.candidateChanged
            }
            try trash(candidate.url)
            moved.append(candidate)
        }
        return moved
    }

    private func validRoot() throws -> Bool {
        guard let info = metadata(root) else {
            if errno == ENOENT { return false }
            throw AppCacheCleanupError.invalidCacheDirectory
        }
        guard info.kind == S_IFDIR, root.resolvingSymlinksInPath().standardizedFileURL == root else { throw AppCacheCleanupError.invalidCacheDirectory }
        return true
    }

    private func safePath(_ url: URL) -> Bool {
        let path = url.standardizedFileURL.path
        guard path.hasPrefix(root.path + "/"), url.standardizedFileURL.resolvingSymlinksInPath().path == path else { return false }
        return true
    }

    private struct Metadata {
        let kind: mode_t; let device: UInt64; let inode: UInt64; let size: UInt64
        let modifiedAt: Date; let changedSeconds: Int64; let changedNanos: Int64
        func candidate(_ url: URL) -> AppCacheCandidate {
            AppCacheCandidate(url: url.standardizedFileURL, size: size, modifiedAt: modifiedAt, device: device, inode: inode, changedSeconds: changedSeconds, changedNanos: changedNanos)
        }
    }
    private func metadata(_ url: URL) -> Metadata? {
        var value = stat()
        guard lstat(url.path, &value) == 0, value.st_size >= 0 else { return nil }
        return Metadata(kind: value.st_mode & mode_t(S_IFMT), device: UInt64(value.st_dev), inode: UInt64(value.st_ino), size: UInt64(value.st_size), modifiedAt: Date(timeIntervalSince1970: Double(value.st_mtimespec.tv_sec) + Double(value.st_mtimespec.tv_nsec) / 1_000_000_000), changedSeconds: Int64(value.st_ctimespec.tv_sec), changedNanos: Int64(value.st_ctimespec.tv_nsec))
    }
}
