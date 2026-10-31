import AppKit
import ServiceManagement

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var item: NSStatusItem!
    private var timer: Timer?
    private let sampler = MachSampler()
    private var options = DisplayOptions()
    private var latest = CPUSample(capturedAt: "", overall: nil, cores: [], error: nil)
    private var menu: NSMenu!

    func applicationDidFinishLaunching(_ notification: Notification) {
        let defaults = UserDefaults.standard
        defaults.register(defaults: ["updateInterval":500, "showImage":true,
            "showText":false, "showCoresIndividually":true, "theme":"Default"])
        options.setInterval(defaults.integer(forKey: "updateInterval"))
        options.showImage = defaults.bool(forKey: "showImage")
        options.showText = defaults.bool(forKey: "showText")
        options.showCoresIndividually = defaults.bool(forKey: "showCoresIndividually")
        options.theme = defaults.string(forKey: "theme") == "B/W" ? "B/W" : "Default"
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.setAccessibilityIdentifier("cpuinfo-replica.status")
        item.button?.setAccessibilityLabel("cpuinfo replica CPU meter")
        menu = makeMenu(); menu.delegate = self
        item.menu = menu
        latest = sampler.sample()
        redraw()
        schedule()
    }

    private func makeMenu() -> NSMenu {
        let menu = NSMenu()
        menu.autoenablesItems = false
        func add(_ title: String, _ action: Selector?, tag: Int = 0, to parent: NSMenu) -> NSMenuItem {
            let child = NSMenuItem(title: title, action: action, keyEquivalent: "")
            child.target = self; child.tag = tag; parent.addItem(child)
            return child
        }
        _ = add("Start at Login", #selector(toggleLogin), to: menu)
        menu.addItem(.separator())
        let intervals = add("Update Interval", nil, to: menu)
        let intervalMenu = NSMenu(title: intervals.title)
        let names = ["0.1sec", "0.2sec", "0.5sec", "1.0sec", "5sec", "10sec", "30sec"]
        for (index, value) in DisplayOptions.intervals.enumerated() {
            _ = add(names[index], #selector(changeInterval), tag: value, to: intervalMenu)
        }
        intervals.submenu = intervalMenu
        let view = add("View Mode", nil, to: menu)
        let viewMenu = NSMenu(title: view.title)
        _ = add("Image", #selector(toggleImage), tag: 1, to: viewMenu)
        _ = add("Text", #selector(toggleText), tag: 2, to: viewMenu)
        view.submenu = viewMenu
        let themes = add("Theme", nil, to: menu)
        let themeMenu = NSMenu(title: themes.title)
        _ = add("Default", #selector(changeTheme), to: themeMenu)
        _ = add("B/W", #selector(changeTheme), to: themeMenu)
        themes.submenu = themeMenu
        _ = add("Show cores individually", #selector(toggleCores), to: menu)
        menu.addItem(.separator())
        let activity = add("Open Activity Monitor", #selector(activityMonitor), to: menu)
        if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.ActivityMonitor") {
            let image = NSWorkspace.shared.icon(forFile: url.path)
            image.size = NSSize(width: 16, height: 16); activity.image = image
        }
        _ = add("Quit", #selector(quit), to: menu)
        return menu
    }

    func menuWillOpen(_ menu: NSMenu) {
        for child in menu.items {
            switch child.title {
            case "Start at Login":
                if #available(macOS 13, *) { child.state = SMAppService.mainApp.status == .enabled ? .on : .off }
            case "Update Interval":
                child.submenu?.items.forEach { $0.state = $0.tag == options.intervalMilliseconds ? .on : .off }
            case "View Mode":
                child.isEnabled = !options.showCoresIndividually
                child.submenu?.items.first?.state = options.showImage ? .on : .off
                child.submenu?.items.last?.state = options.showText ? .on : .off
            case "Theme":
                child.submenu?.items.forEach { $0.state = $0.title == options.theme ? .on : .off }
            case "Show cores individually": child.state = options.showCoresIndividually ? .on : .off
            default: break
            }
        }
    }

    private func schedule() {
        timer?.invalidate()
        let timer = Timer(timeInterval: Double(options.intervalMilliseconds) / 1000,
                          target: self, selector: #selector(sampleAndRedraw), userInfo: nil, repeats: true)
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }
    @objc private func sampleAndRedraw() { latest = sampler.sample(); redraw() }
    private func redraw() {
        let dark = item.button?.effectiveAppearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
        let scale = item.button?.window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2
        let image = MeterRenderer.image(sample: latest, options: options, dark: dark, scale: scale)
        item.length = image.size.width
        item.button?.image = image; item.button?.needsDisplay = true
    }
    private func persist() {
        let defaults = UserDefaults.standard
        defaults.set(options.intervalMilliseconds, forKey: "updateInterval")
        defaults.set(options.showImage, forKey: "showImage")
        defaults.set(options.showText, forKey: "showText")
        defaults.set(options.showCoresIndividually, forKey: "showCoresIndividually")
        defaults.set(options.theme, forKey: "theme")
        redraw()
    }
    @objc private func changeInterval(_ sender: NSMenuItem) {
        options.setInterval(sender.tag); persist(); schedule()
    }
    @objc private func toggleImage(_ sender: NSMenuItem) { options.showImage.toggle(); persist() }
    @objc private func toggleText(_ sender: NSMenuItem) { options.showText.toggle(); persist() }
    @objc private func toggleCores(_ sender: NSMenuItem) { options.showCoresIndividually.toggle(); persist() }
    @objc private func changeTheme(_ sender: NSMenuItem) { options.theme = sender.title; persist() }
    @objc private func activityMonitor(_ sender: NSMenuItem) {
        guard let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.ActivityMonitor") else { return }
        NSWorkspace.shared.openApplication(at: url, configuration: NSWorkspace.OpenConfiguration())
    }
    @objc private func toggleLogin(_ sender: NSMenuItem) {
        if #available(macOS 13, *) {
            do {
                if SMAppService.mainApp.status == .enabled { try SMAppService.mainApp.unregister() }
                else { try SMAppService.mainApp.register() }
            } catch {
                let alert = NSAlert()
                alert.messageText = "Start at Login could not be changed"
                alert.informativeText = error.localizedDescription
                alert.runModal()
            }
        }
    }
    @objc private func quit(_ sender: NSMenuItem) { NSApplication.shared.terminate(nil) }
    func applicationWillTerminate(_ notification: Notification) { timer?.invalidate() }
}

struct FixtureInput: Decodable {
    var cores: [Double?]
    var overall: Double?
    var showCoresIndividually: Bool?
    var showImage: Bool?
    var showText: Bool?
    var theme: String?
}

@main
struct CpuinfoReplica {
    @MainActor static func main() throws {
        let arguments = Array(CommandLine.arguments.dropFirst())
        func option(_ name: String) -> String? {
            guard let index = arguments.firstIndex(of: name), index + 1 < arguments.count else { return nil }
            return arguments[index + 1]
        }
        if let path = option("--fixture") {
            guard let output = option("--output"), let scale = Double(option("--scale") ?? "2"),
                  (scale == 1 || scale == 2 || scale == 3) else { throw NSError(domain: "CpuinfoReplica", code: 1) }
            let data = try Data(contentsOf: URL(fileURLWithPath: path))
            guard data.count <= 65536 else { throw NSError(domain: "CpuinfoReplica", code: 2) }
            let input = try JSONDecoder().decode(FixtureInput.self, from: data)
            guard input.cores.count <= 1024 else { throw NSError(domain: "CpuinfoReplica", code: 3) }
            var options = DisplayOptions()
            options.showCoresIndividually = input.showCoresIndividually ?? true
            options.showImage = input.showImage ?? true; options.showText = input.showText ?? false
            options.theme = input.theme == "B/W" ? "B/W" : "Default"
            let sample = CPUSample(capturedAt: "authored-fixture", overall: input.overall, cores: input.cores, error: nil)
            let app = NSApplication.shared; app.setActivationPolicy(.prohibited)
            let dark = option("--appearance") != "light"
            try MeterRenderer.png(sample: sample, options: options, dark: dark, scale: scale)
                .write(to: URL(fileURLWithPath: output), options: .withoutOverwriting)
            let diagnostic: [String: Any] = ["mode":"authored-fixture", "host_effects":[],
                "width_points":options.showCoresIndividually ? MeterLayout.width(coreCount: input.cores.count) : options.widthWithoutCores,
                "height_points":24, "scale":scale, "cores":input.cores.count,
                "menu_created":false, "preferences_accessed":false]
            print(String(data: try JSONSerialization.data(withJSONObject: diagnostic, options: [.sortedKeys]), encoding: .utf8)!)
            return
        }
        if arguments.contains("--diagnostic") {
            let count = min(20, max(1, Int(option("--sample-count") ?? "2") ?? 2))
            let interval = min(30000, max(100, Int(option("--interval-ms") ?? "500") ?? 500))
            let sampler = MachSampler()
            var samples: [CPUSample] = []
            for index in 0..<count {
                if index > 0 { Thread.sleep(forTimeInterval: Double(interval) / 1000) }
                samples.append(sampler.sample())
            }
            print(String(data: try JSONEncoder().encode(samples), encoding: .utf8)!)
            return
        }
        guard arguments.isEmpty else {
            FileHandle.standardError.write(Data("Use --fixture FILE --output PNG [--scale 1|2|3] [--appearance dark|light], --diagnostic [--sample-count N --interval-ms N], or no arguments for the menu app.\n".utf8))
            exit(2)
        }
        let application = NSApplication.shared
        application.setActivationPolicy(.accessory)
        let delegate = AppDelegate(); application.delegate = delegate
        withExtendedLifetime(delegate) { application.run() }
    }
}
