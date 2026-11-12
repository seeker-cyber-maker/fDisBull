// Local FSEvents wake-up hint. The worker owns all scans and synchronization.
import CoreServices
import Foundation
import Darwin

private func usage() -> Never {
    fputs("Usage: drive-sync-watcher --marker ABSOLUTE_PATH --root ABSOLUTE_PATH [--root ABSOLUTE_PATH ...]\n", stderr)
    exit(2)
}

private func checkedPath(_ value: String, directory: Bool) throws -> String {
    guard value.hasPrefix("/"), !value.contains("\0") else {
        throw NSError(domain: "DriveWatcher", code: 1, userInfo: [NSLocalizedDescriptionKey: "paths must be absolute"])
    }
    let standardized = URL(fileURLWithPath: value).standardizedFileURL.path
    var current = ""
    for part in standardized.split(separator: "/") {
        current += "/" + part
        var st = stat()
        guard lstat(current, &st) == 0 else {
            throw NSError(domain: "DriveWatcher", code: 2, userInfo: [NSLocalizedDescriptionKey: "path does not exist: \(current)"])
        }
        guard (st.st_mode & S_IFMT) != S_IFLNK else {
            throw NSError(domain: "DriveWatcher", code: 3, userInfo: [NSLocalizedDescriptionKey: "symlink path is not admitted: \(current)"])
        }
    }
    if directory {
        var st = stat()
        guard lstat(standardized, &st) == 0, (st.st_mode & S_IFMT) == S_IFDIR else {
            throw NSError(domain: "DriveWatcher", code: 4, userInfo: [NSLocalizedDescriptionKey: "root must be a directory"])
        }
    }
    return standardized
}

private final class Watcher {
    let marker: String
    private var timer: DispatchSourceTimer?
    init(marker: String) { self.marker = marker }

    func wake() {
        // A continuously busy intake must still wake the reconciler. Bound
        // coalescing from the first event instead of resetting its deadline.
        guard timer == nil else { return }
        let next = DispatchSource.makeTimerSource(queue: .main)
        next.schedule(deadline: .now() + .seconds(3))
        next.setEventHandler { [weak self] in self?.writeMarker() }
        timer = next
        next.resume()
    }

    private func writeMarker() {
        timer?.cancel()
        timer = nil
        let fd = open(marker, O_WRONLY | O_CREAT | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK, 0o600)
        guard fd >= 0 else {
            fputs("drive-sync-watcher: cannot write wake marker (errno \(errno))\n", stderr)
            return
        }
        defer { close(fd) }
        var st = stat()
        guard fstat(fd, &st) == 0, (st.st_mode & S_IFMT) == S_IFREG,
              st.st_nlink == 1, st.st_uid == getuid(), ftruncate(fd, 0) == 0 else {
            fputs("drive-sync-watcher: wake marker is not an owned, single-link regular file\n", stderr)
            return
        }
        let data = Array("\(Date().timeIntervalSince1970)\n".utf8)
        let count = data.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        if count != data.count {
            fputs("drive-sync-watcher: incomplete wake marker write\n", stderr)
        }
    }
}

private let callback: FSEventStreamCallback = { _, info, _, _, _, _ in
    guard let info = info else { return }
    let watcher = Unmanaged<Watcher>.fromOpaque(info).takeUnretainedValue()
    DispatchQueue.main.async { watcher.wake() }
}

var roots: [String] = []
var marker: String?
var index = 1
while index < CommandLine.arguments.count {
    let argument = CommandLine.arguments[index]
    guard index + 1 < CommandLine.arguments.count else { usage() }
    let value = CommandLine.arguments[index + 1]
    if argument == "--root" { roots.append(value) }
    else if argument == "--marker", marker == nil { marker = value }
    else { usage() }
    index += 2
}
guard !roots.isEmpty, let markerArg = marker else { usage() }

do {
    let resolvedRoots = try roots.map { try checkedPath($0, directory: true) }
    let markerURL = URL(fileURLWithPath: markerArg).standardizedFileURL
    guard markerArg.hasPrefix("/"), markerURL.lastPathComponent != "", markerURL.lastPathComponent != "." else { usage() }
    let parent = try checkedPath(markerURL.deletingLastPathComponent().path, directory: true)
    let markerPath = (parent as NSString).appendingPathComponent(markerURL.lastPathComponent)
    guard !resolvedRoots.contains(where: { markerPath == $0 || markerPath.hasPrefix($0 + "/") }) else {
        throw NSError(domain: "DriveWatcher", code: 5, userInfo: [NSLocalizedDescriptionKey: "marker must be outside watched roots"])
    }
    let watcher = Watcher(marker: markerPath)
    var context = FSEventStreamContext(version: 0, info: Unmanaged.passUnretained(watcher).toOpaque(),
                                       retain: nil, release: nil, copyDescription: nil)
    let flags = FSEventStreamCreateFlags(kFSEventStreamCreateFlagWatchRoot | kFSEventStreamCreateFlagNoDefer)
    guard let stream = FSEventStreamCreate(nil, callback, &context, resolvedRoots as CFArray,
                                            FSEventStreamEventId(kFSEventStreamEventIdSinceNow), 1.0, flags) else {
        throw NSError(domain: "DriveWatcher", code: 6, userInfo: [NSLocalizedDescriptionKey: "cannot create event stream"])
    }
    FSEventStreamSetDispatchQueue(stream, DispatchQueue.main)
    guard FSEventStreamStart(stream) else {
        FSEventStreamInvalidate(stream); FSEventStreamRelease(stream)
        throw NSError(domain: "DriveWatcher", code: 7, userInfo: [NSLocalizedDescriptionKey: "cannot start event stream"])
    }
    watcher.wake() // startup requires a full reconciliation, even without an event
    withExtendedLifetime(watcher) { dispatchMain() }
} catch {
    fputs("drive-sync-watcher: \(error.localizedDescription)\n", stderr)
    exit(1)
}
