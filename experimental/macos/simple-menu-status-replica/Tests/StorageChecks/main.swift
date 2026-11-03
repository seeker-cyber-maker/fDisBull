import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs("FAIL: \(message)\n", stderr); exit(1) }
}

let volumes = StorageMetrics.availableVolumes()
check(volumes.first?.id == StorageMetrics.startupVolumeID, "startup volume is offered first")
check(Set(volumes.map(\.id)).count == volumes.count, "mounts are unique")
check(volumes.allSatisfy { $0.id == "/" || $0.id.hasPrefix("/Volumes/") }, "helper volumes are hidden")

let startup = volumes[0]
check(!startup.displayName.isEmpty, "selected volume has a visible name")
let reading = StorageMetrics.sample(startup)
check(reading?.totalBytes ?? 0 > 0, "startup capacity is readable")
if let total = reading?.totalBytes, let available = reading?.availableBytes {
    check((0...total).contains(available), "available capacity is within total capacity")
}
if let other = volumes.first(where: { $0.id != StorageMetrics.startupVolumeID }) {
    let otherReading = StorageMetrics.sample(other)
    check(otherReading?.volume.id == other.id, "selected mounted volume is sampled")
    check(otherReading?.totalBytes ?? 0 > 0, "selected mounted volume has capacity")
}

let missing = StorageVolume(id: "/Volumes/ReplicaMissing-\(UUID().uuidString)", name: "Missing")
check(StorageMetrics.sample(missing) == nil, "removed volume does not silently become startup volume")
print("Storage volume checks passed.")
