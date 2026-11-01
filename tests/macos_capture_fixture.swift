// Authored-only fixture for explicit native acceptance. Never starts implicitly.
import AppKit

@MainActor
final class FixtureDelegate: NSObject, NSApplicationDelegate {
    var item: NSStatusItem?
    func applicationDidFinishLaunching(_ notification: Notification) {
        let status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        status.button?.title = "FDB fixture"
        let menu = NSMenu(title: "fDisBull authored capture fixture")
        menu.addItem(withTitle: "Authored capture fixture", action: nil, keyEquivalent: "")
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit fixture", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "")
        status.menu = menu
        item = status
    }
}

@main
struct FixtureMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let delegate = FixtureDelegate()
        app.delegate = delegate
        app.run()
    }
}
