import AppKit

/// One compact vertical bar per logical CPU, using the existing sampler's
/// percentages. Missing readings show only a neutral track, never false usage.
enum CPUBarGraph {
    static func configure(button: NSButton, percentages: [Double?], memoryEmoji: String?, dark: Bool, scale: Double) {
        button.imagePosition = .imageLeading
        button.imageScaling = .scaleNone
        button.image = image(percentages: percentages, dark: dark, scale: scale)
        button.title = memoryEmoji ?? ""
    }

    static func image(percentages: [Double?], dark: Bool, scale: Double) -> NSImage {
        let values = percentages.isEmpty ? [nil] : Array(percentages.prefix(1024))
        let backingScale = scale.isFinite ? min(3, max(1, scale)) : 1
        let width = Double(values.count) * 3 + Double(values.count - 1) * 2 + 4
        let size = NSSize(width: width, height: 24)
        let image = NSImage(size: size)
        guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil,
            pixelsWide: Int(ceil(width * backingScale)), pixelsHigh: Int(ceil(24 * backingScale)),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return image }
        bitmap.size = size
        guard let context = NSGraphicsContext(bitmapImageRep: bitmap) else { return image }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
        defer { NSGraphicsContext.restoreGraphicsState() }

        let track = NSColor(white: dark ? 1 : 0, alpha: dark ? 0.18 : 0.15)
        for (index, percentage) in values.enumerated() {
            let x = 2 + Double(index) * 5
            track.setFill()
            NSBezierPath(roundedRect: NSRect(x: x, y: 5, width: 3, height: 14),
                         xRadius: 1.5, yRadius: 1.5).fill()
            guard let percentage, percentage.isFinite else { continue }
            let usage = min(100, max(0, percentage))
            let color: NSColor
            if usage < 75 {
                color = NSColor(calibratedRed: 0, green: 1, blue: 0, alpha: 1)
            } else if usage < 90 {
                color = NSColor(calibratedRed: 1, green: 140.0 / 255.0, blue: 0, alpha: 1)
            } else {
                color = NSColor(calibratedRed: 1, green: 0, blue: 0, alpha: 1)
            }
            color.setFill()
            NSBezierPath(roundedRect: NSRect(x: x, y: 5, width: 3,
                                           height: max(3, usage / 100 * 14)),
                         xRadius: 1.5, yRadius: 1.5).fill()
        }
        image.addRepresentation(bitmap)
        image.isTemplate = false
        return image
    }
}
