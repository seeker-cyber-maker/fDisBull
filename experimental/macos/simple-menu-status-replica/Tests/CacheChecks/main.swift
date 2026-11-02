import Foundation

let fm = FileManager.default
let base = fm.temporaryDirectory.resolvingSymlinksInPath().appendingPathComponent("cache-check-\(UUID().uuidString)")
let root = base.appendingPathComponent("cache")
try fm.createDirectory(at: root, withIntermediateDirectories: true)
defer { try? fm.removeItem(at: base) }
let now = Date()
let old = now.addingTimeInterval(-8 * 86400)
let recent = now.addingTimeInterval(-6 * 86400)
func file(_ name: String, _ date: Date) throws -> URL {
    let url = root.appendingPathComponent(name)
    try Data("test".utf8).write(to: url)
    try fm.setAttributes([.modificationDate: date], ofItemAtPath: url.path)
    return url
}
let first = try file("old", old)
let second = try file("changed", old)
_ = try file("recent", recent)
let outside = base.appendingPathComponent("outside")
try Data("outside".utf8).write(to: outside)
try fm.createSymbolicLink(at: root.appendingPathComponent("link"), withDestinationURL: outside)
var recorded: [URL] = []
let cleanup = AppCacheCleanup(root: root, trash: { recorded.append($0) })
let candidates = try cleanup.preview(now: now)
precondition(candidates.count == 2 && candidates.allSatisfy { $0.size == 4 })
let selected = candidates.first { $0.url == first }!
let moved = try cleanup.moveToTrash([selected], now: now)
precondition(moved == [selected])
precondition(recorded == [first] && fm.fileExists(atPath: first.path))
let changed = candidates.first { $0.url == second }!
try Data("replacement content".utf8).write(to: second)
do { _ = try cleanup.moveToTrash([changed], now: now); fatalError("changed file accepted") }
catch AppCacheCleanupError.candidateChanged { }
precondition(recorded == [first])
let linkRoot = base.appendingPathComponent("link-root")
try fm.createSymbolicLink(at: linkRoot, withDestinationURL: root)
let unsafe = AppCacheCleanup(root: linkRoot, trash: { _ in fatalError("unexpected move") })
do { _ = try unsafe.preview(now: now); fatalError("symlink root accepted") }
catch AppCacheCleanupError.invalidCacheDirectory { }
print("Cache checks passed")
