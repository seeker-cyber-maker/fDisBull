import AppKit

enum MeterRenderer {
    static func image(sample: CPUSample, options: DisplayOptions, dark: Bool, scale: Double) -> NSImage {
        let width = options.showCoresIndividually ? MeterLayout.width(coreCount: sample.cores.count) : options.widthWithoutCores
        let size = NSSize(width: max(1, width), height: MeterLayout.height)
        let representation = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(ceil(size.width * scale)),
            pixelsHigh: Int(ceil(size.height * scale)), bitsPerSample: 8, samplesPerPixel: 4,
            hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        representation.size = size
        let context = NSGraphicsContext(bitmapImageRep: representation)!
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = context
        // NSGraphicsContext honors representation.size versus its pixel extent.
        // Applying the backing scale a second time would clip/shift Retina bars.
        let track = NSColor(white: dark ? 1 : 0, alpha: dark ? 0.18 : 0.15)
        if options.showCoresIndividually {
            for bar in MeterLayout.bars(sample.cores, monochrome: options.theme == "B/W") {
                let rect = NSRect(x: bar.x, y: bar.y, width: bar.width, height: bar.trackHeight)
                track.setFill()
                NSBezierPath(roundedRect: rect, xRadius: 1.5, yRadius: 1.5).fill()
                if let height = bar.fillHeight {
                    color(bar.color, dark: dark).setFill()
                    NSBezierPath(roundedRect: NSRect(x: bar.x, y: bar.y, width: bar.width, height: height),
                                 xRadius: 1.5, yRadius: 1.5).fill()
                }
            }
        } else {
            var x = 0.0
            if options.showImage {
                track.setFill()
                NSBezierPath(roundedRect: NSRect(x: x, y: 8, width: 24, height: 8), xRadius: 4, yRadius: 4).fill()
                if let usage = sample.overall {
                    color(MeterLayout.color(usage, monochrome: options.theme == "B/W"), dark: dark).setFill()
                    NSBezierPath(roundedRect: NSRect(x: x, y: 8, width: max(8, MeterLayout.clamped(usage) * 24), height: 8),
                                 xRadius: 4, yRadius: 4).fill()
                }
                x += 24
            }
            if options.showText {
                let text = sample.overall.map { "\(Int((MeterLayout.clamped($0) * 100).rounded()))%" } ?? "—"
                let style = NSMutableParagraphStyle(); style.alignment = .center
                NSAttributedString(string: text, attributes: [
                    .font:NSFont.menuBarFont(ofSize: NSFont.systemFontSize), .paragraphStyle:style,
                    .foregroundColor:dark ? NSColor.white : NSColor.black
                ]).draw(in: NSRect(x: x, y: 2, width: 36, height: 20))
            }
        }
        NSGraphicsContext.restoreGraphicsState()
        let image = NSImage(size: size)
        image.addRepresentation(representation)
        image.isTemplate = false
        return image
    }

    static func color(_ value: MeterColor, dark: Bool) -> NSColor {
        switch value {
        // Upstream themes use calibrated RGB, whose color management differs
        // from the sRGB initializer even when the numeric components match.
        case .green: return NSColor(calibratedRed: 0, green: 1, blue: 0, alpha: 1)
        case .orange: return NSColor(calibratedRed: 1, green: 140.0 / 255.0, blue: 0, alpha: 1)
        case .red: return NSColor(calibratedRed: 1, green: 0, blue: 0, alpha: 1)
        case .monochrome: return dark ? .white : .black
        case .unknown: return .clear
        }
    }

    static func png(sample: CPUSample, options: DisplayOptions, dark: Bool, scale: Double) -> Data {
        let image = image(sample: sample, options: options, dark: dark, scale: scale)
        return (image.representations[0] as! NSBitmapImageRep).representation(using: .png, properties: [:])!
    }
}
