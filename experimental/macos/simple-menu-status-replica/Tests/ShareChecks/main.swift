import AppKit

let status = ShareCardData(cpuFraction: 0.42, memoryFraction: 0.63,
                           gpuPercent: 18, batteryPercent: nil)
let fields = Set(Mirror(reflecting: status).children.compactMap(\.label))
precondition(fields == ["cpuFraction", "memoryFraction", "gpuPercent", "batteryPercent"],
             "share payload acquired an unexpected, potentially private field")

_ = NSApplication.shared
guard let png = ShareImageRenderer.png(status, languageChoice: "English") else {
    fatalError("offscreen share card could not render")
}
precondition(png.starts(with: [137, 80, 78, 71, 13, 10, 26, 10]))
guard let bitmap = NSBitmapImageRep(data: png) else { fatalError("share PNG could not reopen") }
precondition(bitmap.pixelsWide >= 440 && bitmap.pixelsHigh >= 230)
let changed = ShareCardData(cpuFraction: 0.87, memoryFraction: 0.63,
                            gpuPercent: 18, batteryPercent: nil)
guard let changedPNG = ShareImageRenderer.png(changed, languageChoice: "English"),
      let changedBitmap = NSBitmapImageRep(data: changedPNG),
      let originalPixels = bitmap.bitmapData,
      let changedPixels = changedBitmap.bitmapData else {
    fatalError("changed share card could not render and reopen")
}
let pixelCount = bitmap.bytesPerRow * bitmap.pixelsHigh
precondition(pixelCount == changedBitmap.bytesPerRow * changedBitmap.pixelsHigh)
precondition(Data(bytes: originalPixels, count: pixelCount) !=
             Data(bytes: changedPixels, count: pixelCount),
             "a changed CPU reading did not change the rendered image")
for forbidden in ["192.0.2.44", "/users/example/private", "secretprocess",
                  "storage", "disk space", "processes"] {
    precondition(png.range(of: Data(forbidden.utf8)) == nil, "private text reached PNG metadata")
}
print("Offscreen share PNG and restricted payload checks passed")
