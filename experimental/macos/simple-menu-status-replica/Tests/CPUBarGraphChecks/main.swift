import AppKit

var checks = 0
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
    checks += 1
}
func bitmap(_ image: NSImage) -> NSBitmapImageRep {
    image.representations.first as! NSBitmapImageRep
}
func pixel(_ image: NSBitmapImageRep, _ x: Int, _ y: Int) -> NSColor {
    image.colorAt(x: x, y: y)!.usingColorSpace(.deviceRGB)!
}
func sameRGB(_ actual: NSColor, _ expected: NSColor) -> Bool {
    let expected = expected.usingColorSpace(.deviceRGB)!
    return abs(actual.redComponent - expected.redComponent) <= 1.0 / 255
        && abs(actual.greenComponent - expected.greenComponent) <= 1.0 / 255
        && abs(actual.blueComponent - expected.blueComponent) <= 1.0 / 255
}

let green = NSColor(calibratedRed: 0, green: 1, blue: 0, alpha: 1)
let orange = NSColor(calibratedRed: 1, green: 140.0 / 255.0, blue: 0, alpha: 1)
let red = NSColor(calibratedRed: 1, green: 0, blue: 0, alpha: 1)
let readings: [Double?] = [0, 74.99, 75, 89.99, 90, 100, nil, .nan, -100, 200]

for dark in [false, true] {
    for scale in 1...3 {
        let image = CPUBarGraph.image(percentages: readings, dark: dark, scale: Double(scale))
        let pixels = bitmap(image)
        check(image.size == NSSize(width: 52, height: 24), "ten core logical dimensions")
        check(pixels.pixelsWide == 52 * scale && pixels.pixelsHigh == 24 * scale,
              "backing scale applied exactly once")
        check(!image.isTemplate, "preserve colored bars")
        check(sameRGB(pixel(pixels, 3 * scale, 17 * scale), green), "zero has the source green minimum nub")
        check(sameRGB(pixel(pixels, 8 * scale, 10 * scale), green), "below75 remains green")
        check(sameRGB(pixel(pixels, 13 * scale, 10 * scale), orange), "75 percent starts orange")
        check(sameRGB(pixel(pixels, 18 * scale, 10 * scale), orange), "below90 remains orange")
        check(sameRGB(pixel(pixels, 23 * scale, 10 * scale), red), "90 percent starts red")
        check(sameRGB(pixel(pixels, 28 * scale, 6 * scale), red), "full usage reaches the top")
        let missing = pixel(pixels, 33 * scale, 10 * scale)
        let invalid = pixel(pixels, 38 * scale, 10 * scale)
        check(missing.alphaComponent < 0.3 && invalid.alphaComponent < 0.3,
              "missing and invalid readings show tracks rather than colored fill")
        check(dark ? missing.redComponent > 0.9 : missing.redComponent < 0.1,
              "neutral tracks follow appearance")
        check(sameRGB(pixel(pixels, 43 * scale, 17 * scale), green), "negative input clamps to zero")
        check(sameRGB(pixel(pixels, 48 * scale, 6 * scale), red), "over100 clamps to full")

        var minimumX = pixels.pixelsWide, minimumY = pixels.pixelsHigh, maximumX = -1, maximumY = -1
        for y in 0..<pixels.pixelsHigh {
            for x in 0..<pixels.pixelsWide where pixel(pixels, x, y).alphaComponent > 0 {
                minimumX = min(minimumX, x); maximumX = max(maximumX, x)
                minimumY = min(minimumY, y); maximumY = max(maximumY, y)
            }
        }
        check([minimumX, minimumY, maximumX + 1, maximumY + 1] == [2 * scale, 5 * scale, 50 * scale, 19 * scale],
              "insets, baseline and track height at each backing scale")
    }
}
let empty = bitmap(CPUBarGraph.image(percentages: [], dark: true, scale: 1))
check(empty.pixelsWide == 7 && empty.pixelsHigh == 24, "empty data keeps one unknown placeholder")
check(pixel(empty, 3, 17).alphaComponent < 0.3, "empty data has no fabricated CPU fill")
let bounded = bitmap(CPUBarGraph.image(percentages: Array(repeating: 50, count: 1025), dark: true, scale: 1))
check(bounded.pixelsWide == 5122, "core array bounded to1024")
for scale in [Double.nan, .infinity, -1, 0] {
    check(bitmap(CPUBarGraph.image(percentages: [0], dark: true, scale: scale)).pixelsWide == 7,
          "malformed or low scale has safe one-times backing")
}
check(bitmap(CPUBarGraph.image(percentages: [100], dark: true, scale: 10)).pixelsWide == 21,
      "large scale bounded to three-times backing")
check(bitmap(CPUBarGraph.image(percentages: [.infinity], dark: true, scale: 1)).colorAt(x: 3, y: 17)!.alphaComponent < 0.3,
      "infinite usage remains unknown")
print("\(checks) CPU bar graph rendering checks passed; no status item, preferences or GUI")
