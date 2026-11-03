import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs("FAIL: \(message)\n", stderr); exit(1) }
}

let fileManager = FileManager.default
let fixture = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
    .appendingPathComponent("replica-storage-scan-\(UUID().uuidString)", isDirectory: true)
let system = fixture.appendingPathComponent("System", isDirectory: true)
let documents = fixture.appendingPathComponent("Documents", isDirectory: true)
let outside = fixture.appendingPathComponent("Outside", isDirectory: true)
defer { try? fileManager.removeItem(at: fixture) }
for directory in [system, documents, outside] {
    try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
}
try Data(count: 4096).write(to: system.appendingPathComponent("one.bin"))
try Data(count: 8192).write(to: system.appendingPathComponent("two.bin"))
try Data(count: 2048).write(to: documents.appendingPathComponent("note.bin"))
try Data(count: 16384).write(to: outside.appendingPathComponent("outside.bin"))
try fileManager.createSymbolicLink(at: system.appendingPathComponent("linked-outside"),
                                   withDestinationURL: outside)

let startup = StorageVolume(id: "/", name: "Startup")
let requests = [
    StorageFolderScanRequest(category: .system, label: "System folder", roots: [system]),
    StorageFolderScanRequest(category: .applications, label: "Applications folder",
                             roots: [fixture.appendingPathComponent("Applications")]),
    StorageFolderScanRequest(category: .documents, label: "My Documents folder", roots: [documents])
]
let results = StorageFolderScanner.scan(requests: requests, volume: startup,
                                        limits: StorageFolderScanLimits(maxEntriesPerCategory: 100,
                                                                        maxSecondsPerCategory: 5))
check(results.count == 3, "all requested categories returned")
check(results[0].status == .complete && results[0].filesCounted == 2,
      "system fixture files counted but linked folder skipped")
check((results[0].bytes ?? 0) > 0, "system estimate has measured bytes")
check(results[1].status == .notPresent && results[1].bytes == nil,
      "missing folder is distinguished from empty folder")
check(results[2].status == .complete && results[2].filesCounted == 1,
      "documents fixture counted")
let mixed = StorageFolderScanRequest(category: .applications, label: "Mixed roots",
                                     roots: [system, system.appendingPathComponent("linked-outside")])
let mixedResult = StorageFolderScanner.scan(requests: [mixed], volume: startup)
check(mixedResult[0].status == .partial && mixedResult[0].filesCounted == 2,
      "skipped linked root marks a measured estimate partial")

let limited = StorageFolderScanner.scan(requests: [requests[0]], volume: startup,
                                        limits: StorageFolderScanLimits(maxEntriesPerCategory: 1,
                                                                        maxSecondsPerCategory: 5))
check(limited[0].status == .partial && limited[0].entriesVisited == 1,
      "entry budget stops with partial status")
let cancellation = StorageFolderScanCancellation()
cancellation.cancel()
let cancelled = StorageFolderScanner.scan(requests: [requests[0]], volume: startup,
                                          cancellation: cancellation)
check(cancelled[0].status == .cancelled, "pre-cancelled scan does not traverse")

let generated = StorageFolderScanner.requests(for: startup, homeURL: fixture)
check(generated.map(\.category) == [.system, .applications, .documents],
      "startup requests have expected category order")
check(generated[2].roots == [documents], "startup Documents is current user's folder")

if let external = StorageMetrics.availableVolumes().first(where: { $0.id != "/" }) {
    let remoteRoot = StorageFolderScanRequest(category: .documents,
                                              label: "Other volume", roots: [URL(fileURLWithPath: external.id)])
    let rejected = StorageFolderScanner.scan(requests: [remoteRoot], volume: startup)
    check(rejected[0].status == .notPresent && rejected[0].note?.contains("another volume") == true,
          "root on another mounted volume is not attributed to startup")
}
print("Storage folder scan checks passed.")
