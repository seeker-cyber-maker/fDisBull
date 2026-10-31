import AppKit

@main struct MenuTests {
    @MainActor static func main() throws {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        let arguments = Array(CommandLine.arguments.dropFirst())
        if arguments.count == 2 && ["--write", "--read"].contains(arguments[0]) {
            let suite = arguments[1]
            precondition(suite.hasPrefix("local.codex.cpuinfo-replica.tests."))
            let defaults = UserDefaults(suiteName: suite)!
            let delegate = AppDelegate(defaults: defaults, strings: MenuStrings(language: "en"))
            let menu = delegate.prepareMenu()
            func row(_ role: MenuRole) -> NSMenuItem {
                menu.items.first { $0.identifier?.rawValue == role.rawValue }!
            }
            func click(_ item: NSMenuItem) {
                item.menu!.performActionForItem(at: item.menu!.index(of: item))
            }
            if arguments[0] == "--write" {
                click(row(.cores))
                click(row(.view).submenu!.items[1])
                click(row(.view).submenu!.items[0])
                click(row(.theme).submenu!.items[1])
                click(row(.interval).submenu!.items.first { $0.tag == 1000 }!)
                precondition(defaults.synchronize())
            }
            let value = delegate.currentOptions
            precondition(!value.showCoresIndividually && !value.showImage && value.showText)
            precondition(value.theme == "B/W" && value.intervalMilliseconds == 1000)
            precondition(row(.view).isEnabled)
            precondition(row(.view).submenu!.items[1].state == .on)
            precondition(!row(.view).submenu!.items[1].isEnabled)
            precondition(row(.theme).submenu!.items[1].state == .on)
            precondition(row(.interval).submenu!.items.first { $0.state == .on }!.tag == 1000)
            print(arguments[0] == "--write" ? "settings written through menu actions" : "settings and checkmarks survived process restart")
            return
        }

        var checks = 0
        func check(_ value: Bool, _ message: String) {
            precondition(value, message); checks += 1
        }
        let suite = "local.codex.cpuinfo-replica.tests." + UUID().uuidString.lowercased()
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite); defaults.synchronize() }
        for language in ["en", "ja"] {
            defaults.removePersistentDomain(forName: suite)
            let strings = MenuStrings(language: language)
            let delegate = AppDelegate(defaults: defaults, strings: strings)
            let menu = delegate.prepareMenu()
            func row(_ role: MenuRole) -> NSMenuItem {
                menu.items.first { $0.identifier?.rawValue == role.rawValue }!
            }
            func click(_ item: NSMenuItem) {
                item.menu!.performActionForItem(at: item.menu!.index(of: item))
            }
            let expected = language == "en" ? ["Start at Login", "Update Interval", "View Mode", "Theme", "Show cores individually", "Open Activity Monitor", "Quit"] : ["ログイン時に開始", "更新間隔", "表示", "テーマ", "コアを個別に表示", "アクティビティモニタを開く", "終了"]
            check(menu.items.filter { !$0.isSeparatorItem }.map(\.title) == expected, "localized root order")
            check(!row(.view).isEnabled && row(.cores).state == .on, "per-core mode disables overall view menu")
            check(row(.interval).submenu!.items.map(\.title) == (language == "en" ? ["0.1sec", "0.2sec", "0.5sec", "1.0sec", "5sec", "10sec", "30sec"] : ["0.1秒", "0.2秒", "0.5秒", "1.0秒", "5秒", "10秒", "30秒"]), "all localized intervals")
            click(row(.cores))
            check(row(.view).isEnabled && !delegate.currentOptions.showCoresIndividually, "real core menu action")
            let image = row(.view).submenu!.items[0], text = row(.view).submenu!.items[1]
            check(image.title == (language == "en" ? "Image" : "アイコン") && text.title == (language == "en" ? "Text" : "テキスト"), "localized mode titles")
            check(image.state == .on && !image.isEnabled && text.isEnabled, "cannot disable sole image mode")
            click(image)
            check(delegate.currentOptions.showImage && !delegate.currentOptions.showText, "action itself rejects invisible meter")
            click(text)
            check(image.isEnabled && text.isEnabled && image.state == .on && text.state == .on, "both modes enabled")
            click(image)
            check(!delegate.currentOptions.showImage && delegate.currentOptions.showText, "text-only action")
            check(image.isEnabled && !text.isEnabled && image.state == .off && text.state == .on, "cannot disable sole text mode")
            click(text)
            check(delegate.currentOptions.showText, "sole text action is guarded")
            click(image)
            click(text)
            check(delegate.currentOptions.showImage && !delegate.currentOptions.showText, "return to image-only")
            for item in row(.interval).submenu!.items {
                click(item)
                check(delegate.currentOptions.intervalMilliseconds == item.tag && row(.interval).submenu!.items.filter { $0.state == .on }.count == 1, "interval action and single checkmark")
            }
            click(row(.theme).submenu!.items[1])
            check(delegate.currentOptions.theme == "B/W" && row(.theme).submenu!.items[1].state == .on, "theme action independent of language")
            click(row(.theme).submenu!.items[0])
            check(delegate.currentOptions.theme == "Default", "restore default theme")
            check(menu.font == nil || menu.font!.pointSize == NSFont.menuFont(ofSize: 0).pointSize, "native menu font")
        }
        defaults.set(false, forKey: "showImage")
        defaults.set(false, forKey: "showText")
        let repaired = DisplayPreferences.load(from: defaults)
        check(repaired.showImage && !repaired.showText && defaults.bool(forKey: "showImage"), "recover old invisible preferences")
        check(MenuStrings(language: "fr-CA").language == "en", "unsupported language falls back to English")

        defaults.removePersistentDomain(forName: suite)
        defaults.synchronize()
        for operation in ["--write", "--read"] {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
            process.arguments = [operation, suite]
            try process.run(); process.waitUntilExit()
            check(process.terminationReason == .exit && process.terminationStatus == 0, "separate-process persistence")
        }
        print("\(checks) menu/settings checks passed; no status item, login changes or original preferences")
    }
}
