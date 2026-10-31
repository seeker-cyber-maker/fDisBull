import AppKit
import ServiceManagement

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var item: NSStatusItem?
    private var timer: Timer?
    private let sampler = MachSampler()
    private var options = DisplayOptions()
    private var latest = CPUSample(capturedAt: "", overall: nil, cores: [], error: nil)
    private var menu: NSMenu!
    private let defaults: UserDefaults
    private let strings: MenuStrings
    var currentOptions: DisplayOptions { options }

    init(defaults: UserDefaults = .standard, strings: MenuStrings = MenuStrings()) {
        self.defaults = defaults
        self.strings = strings
        super.init()
    }

    func prepareMenu() -> NSMenu {
        options = DisplayPreferences.load(from: defaults)
        menu = makeMenu()
        refreshMenu()
        return menu
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item?.button?.setAccessibilityIdentifier("cpuinfo-replica.status")
        item?.button?.setAccessibilityLabel("cpuinfo replica CPU meter")
        item?.button?.toolTip = "Cpuinfo Replica"
        item?.menu = prepareMenu()
        latest = sampler.initialSample()
        redraw()
        schedule()
    }

    private func makeMenu() -> NSMenu {
        let menu = NSMenu()
        menu.autoenablesItems = false
        menu.delegate = self
        func add(_ title: String, _ action: Selector?, tag: Int = 0, role: MenuRole? = nil, to parent: NSMenu) -> NSMenuItem {
            let child = NSMenuItem(title: title, action: action, keyEquivalent: "")
            child.target = self; child.tag = tag
            child.identifier = role.map { NSUserInterfaceItemIdentifier($0.rawValue) }
            parent.addItem(child)
            return child
        }
        _ = add(strings.title(.login), #selector(toggleLogin), role: .login, to: menu)
        menu.addItem(.separator())
        let intervals = add(strings.title(.interval), nil, role: .interval, to: menu)
        let intervalMenu = NSMenu(title: intervals.title)
        for (index, value) in DisplayOptions.intervals.enumerated() {
            _ = add(strings.interval(index), #selector(changeInterval), tag: value, to: intervalMenu)
        }
        intervalMenu.autoenablesItems = false; intervalMenu.delegate = self
        intervals.submenu = intervalMenu
        let view = add(strings.title(.view), nil, role: .view, to: menu)
        let viewMenu = NSMenu(title: view.title)
        _ = add(strings.title(.image), #selector(toggleImage), tag: 1, role: .image, to: viewMenu)
        _ = add(strings.title(.text), #selector(toggleText), tag: 2, role: .text, to: viewMenu)
        viewMenu.autoenablesItems = false; viewMenu.delegate = self
        view.submenu = viewMenu
        let themes = add(strings.title(.theme), nil, role: .theme, to: menu)
        let themeMenu = NSMenu(title: themes.title)
        _ = add("Default", #selector(changeTheme), to: themeMenu)
        _ = add("B/W", #selector(changeTheme), to: themeMenu)
        themeMenu.autoenablesItems = false; themeMenu.delegate = self
        themes.submenu = themeMenu
        _ = add(strings.title(.cores), #selector(toggleCores), role: .cores, to: menu)
        menu.addItem(.separator())
        let activity = add(strings.title(.activity), #selector(activityMonitor), role: .activity, to: menu)
        if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.ActivityMonitor") {
            let image = NSWorkspace.shared.icon(forFile: url.path)
            image.size = NSSize(width: 16, height: 16); activity.image = image
        }
        _ = add(strings.title(.quit), #selector(quit), role: .quit, to: menu)
        return menu
    }

    func menuWillOpen(_ menu: NSMenu) { refreshMenu() }

    func refreshMenu() {
        guard let menu else { return }
        for child in menu.items {
            switch child.identifier?.rawValue {
            case MenuRole.login.rawValue:
                child.state = SMAppService.mainApp.status == .enabled ? .on : .off
            case MenuRole.interval.rawValue:
                child.submenu?.items.forEach { $0.state = $0.tag == options.intervalMilliseconds ? .on : .off }
            case MenuRole.view.rawValue:
                child.isEnabled = !options.showCoresIndividually
                let image = child.submenu?.items.first
                let text = child.submenu?.items.last
                image?.state = options.showImage ? .on : .off
                text?.state = options.showText ? .on : .off
                image?.isEnabled = options.showText
                text?.isEnabled = options.showImage
            case MenuRole.theme.rawValue:
                child.submenu?.items.forEach { $0.state = $0.title == options.theme ? .on : .off }
            case MenuRole.cores.rawValue: child.state = options.showCoresIndividually ? .on : .off
            default: break
            }
        }
    }

    private func schedule() {
        timer?.invalidate()
        guard item != nil else { return }
        let timer = Timer(timeInterval: Double(options.intervalMilliseconds) / 1000,
                          target: self, selector: #selector(sampleAndRedraw), userInfo: nil, repeats: true)
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }
    @objc private func sampleAndRedraw() {
        latest = sampler.sample(mode: options.showCoresIndividually ? .cores : .host)
        redraw()
    }
    private func redraw() {
        guard let item else { return }
        let dark = item.button?.effectiveAppearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
        let scale = item.button?.window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 2
        let image = MeterRenderer.image(sample: latest, options: options, dark: dark, scale: scale)
        item.length = image.size.width
        item.button?.image = image; item.button?.needsDisplay = true
    }
    private func persist() {
        DisplayPreferences.save(options, to: defaults)
        refreshMenu()
        redraw()
    }
    @objc private func changeInterval(_ sender: NSMenuItem) {
        options.setInterval(sender.tag); persist(); schedule()
    }
    @objc private func toggleImage(_ sender: NSMenuItem) {
        guard options.showText else { return }
        options.showImage.toggle(); persist()
    }
    @objc private func toggleText(_ sender: NSMenuItem) {
        guard options.showImage else { return }
        options.showText.toggle(); persist()
    }
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

#if !CPUINFO_TESTING
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

#endif
