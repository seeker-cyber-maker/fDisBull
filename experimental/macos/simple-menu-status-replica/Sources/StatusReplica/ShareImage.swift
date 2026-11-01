import AppKit
import SwiftUI

/// A deliberately narrow share payload. A full dashboard or Snapshot can
/// contain IP addresses, process names, mount paths, and disk-capacity data.
struct ShareCardData {
    let cpuFraction: Double?
    let memoryFraction: Double?
    let gpuPercent: Double?
    let batteryPercent: Double?

    private static func percentage(_ value: Double?, fraction: Bool) -> String {
        guard let value, value.isFinite else { return "—" }
        let percent = fraction ? value * 100 : value
        guard (0...100).contains(percent) else { return "—" }
        return String(format: "%.1f%%", percent)
    }

    var cpuLabel: String { Self.percentage(cpuFraction, fraction: true) }
    var memoryLabel: String { Self.percentage(memoryFraction, fraction: true) }
    var gpuLabel: String { Self.percentage(gpuPercent, fraction: false) }
    var batteryLabel: String { Self.percentage(batteryPercent, fraction: false) }
}

private struct ShareStatusCard: View {
    let data: ShareCardData
    let languageChoice: String

    private func text(_ english: String) -> String {
        ReplicaLocalization.text(english, choice: languageChoice)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 19) {
            HStack(spacing: 9) {
                Image(systemName: "waveform.path.ecg.rectangle")
                    .font(.system(size: 22, weight: .medium)).foregroundColor(.green)
                VStack(alignment: .leading, spacing: 3) {
                    Text(text("System status")).font(.system(size: 19, weight: .semibold))
                    Text(text("Created locally · No tracking"))
                        .font(.system(size: 10)).foregroundColor(.white.opacity(0.65))
                }
                Spacer()
            }
            Rectangle().fill(Color.white.opacity(0.18)).frame(height: 1)
            HStack(spacing: 10) {
                metric("CPU", data.cpuLabel, .green)
                metric("Memory", data.memoryLabel, .orange)
                metric("GPU", data.gpuLabel, .green)
                metric("Battery", data.batteryLabel, .blue)
            }
            Spacer(minLength: 0)
            Text(text("Local system measurements"))
                .font(.system(size: 10)).foregroundColor(.white.opacity(0.6))
        }
        .padding(22)
        .frame(width: 440, height: 230)
        .foregroundColor(.white)
        .background {
            RoundedRectangle(cornerRadius: 16)
                .fill(LinearGradient(colors: [Color(red: 0.15, green: 0.19, blue: 0.18),
                                             Color(red: 0.09, green: 0.12, blue: 0.11)],
                                     startPoint: .topLeading, endPoint: .bottomTrailing))
                .overlay(RoundedRectangle(cornerRadius: 16)
                    .strokeBorder(Color.white.opacity(0.15), lineWidth: 1))
        }
    }

    private func metric(_ title: String, _ value: String, _ tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(text(title)).font(.system(size: 11)).foregroundColor(.white.opacity(0.7))
            Text(value).font(.system(size: 18, weight: .semibold)).monospacedDigit()
                .foregroundColor(value == "—" ? .white.opacity(0.6) : tint)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

enum ShareImageRenderer {
    /// AppKit renders a fixed, privacy-scoped card without capturing the screen
    /// or depending on a key window. The PNG remains in memory until shared.
    static func png(_ data: ShareCardData, languageChoice: String) -> Data? {
        let size = NSSize(width: 440, height: 230)
        let card = ShareStatusCard(data: data, languageChoice: languageChoice)
            .environment(\.locale, ReplicaLocalization.locale(languageChoice))
        let view = NSHostingView(rootView: card)
        view.frame = NSRect(origin: .zero, size: size)
        view.layoutSubtreeIfNeeded()
        guard let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return nil }
        view.cacheDisplay(in: view.bounds, to: bitmap)
        return bitmap.representation(using: .png, properties: [:])
    }
}

/// NSSharingServicePicker needs a real view anchor. Its own NSButton provides
/// one even when the surrounding SwiftUI view lives in an NSPopover.
private struct NativeShareButton: NSViewRepresentable {
    let image: NSImage
    let title: String

    func makeCoordinator() -> Coordinator { Coordinator(image: image) }

    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(title: title, target: context.coordinator,
                              action: #selector(Coordinator.show(_:)))
        button.bezelStyle = .rounded
        return button
    }

    func updateNSView(_ button: NSButton, context: Context) {
        button.title = title
        context.coordinator.image = image
    }

    final class Coordinator: NSObject {
        var image: NSImage
        init(image: NSImage) { self.image = image }

        @objc func show(_ sender: NSButton) {
            NSSharingServicePicker(items: [image])
                .show(relativeTo: sender.bounds, of: sender, preferredEdge: .minY)
        }
    }
}

struct SharePreview: View {
    let image: NSImage
    let languageChoice: String
    let close: () -> Void

    private func text(_ english: String) -> String {
        ReplicaLocalization.text(english, choice: languageChoice)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(text("Share system status")).font(.headline)
            Image(nsImage: image).resizable().interpolation(.high)
                .aspectRatio(contentMode: .fit).frame(width: 352, height: 184)
            Text(text("IP addresses, user names, file paths, processes, and disk space are excluded."))
                .font(.caption).foregroundColor(.secondary)
            Text(text("Created locally · No tracking"))
                .font(.caption2).foregroundColor(.secondary)
            HStack {
                Button(text("Copy image")) {
                    NSPasteboard.general.clearContents()
                    if !NSPasteboard.general.writeObjects([image]) { NSSound.beep() }
                }
                NativeShareButton(image: image, title: text("Share…"))
                    .frame(width: 72, height: 25)
                Spacer()
                Button(text("Close"), action: close)
            }
        }
        .padding(16).frame(width: 384)
    }
}
