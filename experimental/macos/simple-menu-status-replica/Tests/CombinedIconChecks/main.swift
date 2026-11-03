import AppKit

// Exercise a real offscreen button without creating a status item or app window.
NSApplication.shared.setActivationPolicy(.prohibited)

var checks = 0
func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    precondition(condition(), message)
    checks += 1
}
func bitmap(_ button: NSButton) -> NSBitmapImageRep {
    button.image!.representations.first as! NSBitmapImageRep
}
func pixels(_ button: NSButton) -> Data {
    let image = bitmap(button)
    var result = Data()
    for row in 0..<image.pixelsHigh {
        result.append(image.bitmapData! + row * image.bytesPerRow,
                      count: image.pixelsWide * 4)
    }
    return result
}

let percentages: [Double?] = [10, 25, 50, 75, 90, 100, nil, 30, 60, 80]
let moods: [(MemoryMood, String)] = [
    (.relaxed, "😊"), (.concerned, "😐"), (.stressed, "😰"), (.unknown, "❔")
]

for dark in [false, true] {
    for scale in 1...3 {
        let button = NSButton(frame: .zero)
        button.isBordered = false
        button.font = .menuBarFont(ofSize: NSFont.systemFontSize)
        CPUBarGraph.configure(button: button, percentages: percentages,
                              memoryEmoji: nil, dark: dark, scale: Double(scale))
        check(button.title.isEmpty && button.image != nil, "graph-only representation")
        check(button.imagePosition == .imageLeading && button.imageScaling == .scaleNone,
              "graph remains leading and does not shrink when text is present")
        check(button.image!.size == NSSize(width: 52, height: 24), "ten-core graph logical dimensions")
        check(bitmap(button).pixelsWide == 52 * scale && bitmap(button).pixelsHigh == 24 * scale,
              "graph backing pixels at each display scale")
        let baseline = pixels(button)
        let graphWidth = button.intrinsicContentSize.width

        for (mood, expected) in moods {
            CPUBarGraph.configure(button: button, percentages: percentages,
                                  memoryEmoji: mood.emoji, dark: dark, scale: Double(scale))
            check(button.title == expected, "combined representation uses current memory pressure emoji")
            check(button.image!.size == NSSize(width: 52, height: 24) && pixels(button) == baseline,
                  "memory changes preserve graph geometry and pixels")
            check(button.intrinsicContentSize.width > graphWidth,
                  "button reserves additional width for the emoji")
            // The caller adds the coffee indicator afterward. A fresh update
            // must replace that old title rather than append another emoji.
            button.title += " ☕️"
        }

        CPUBarGraph.configure(button: button, percentages: percentages,
                              memoryEmoji: nil, dark: dark, scale: Double(scale))
        check(button.title.isEmpty, "returning to graph-only clears stale emoji and coffee text")
        check(pixels(button) == baseline, "returning to graph-only preserves graph pixels")
        check(button.intrinsicContentSize.width == graphWidth,
              "returning to graph-only releases the extra text width")
    }
}

print("\(checks) combined graph/emoji button checks passed; no status item, preferences or app window")
