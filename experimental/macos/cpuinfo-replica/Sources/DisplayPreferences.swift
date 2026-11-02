import Foundation

enum DisplayPreferences {
    static func load(from defaults: UserDefaults) -> DisplayOptions {
        defaults.register(defaults: ["updateInterval": 500, "showImage": true,
            "showText": false, "showCoresIndividually": true, "theme": "Default"])
        var value = DisplayOptions()
        value.setInterval(defaults.integer(forKey: "updateInterval"))
        value.showImage = defaults.bool(forKey: "showImage")
        value.showText = defaults.bool(forKey: "showText")
        value.showCoresIndividually = defaults.bool(forKey: "showCoresIndividually")
        value.theme = defaults.string(forKey: "theme") == "B/W" ? "B/W" : "Default"
        // Recover the invisible-meter state allowed by the earlier candidate.
        if !value.showImage && !value.showText {
            value.showImage = true
            defaults.set(true, forKey: "showImage")
        }
        return value
    }

    static func save(_ value: DisplayOptions, to defaults: UserDefaults) {
        defaults.set(value.intervalMilliseconds, forKey: "updateInterval")
        defaults.set(value.showImage, forKey: "showImage")
        defaults.set(value.showText, forKey: "showText")
        defaults.set(value.showCoresIndividually, forKey: "showCoresIndividually")
        defaults.set(value.theme, forKey: "theme")
    }
}

enum MenuRole: String {
    case login, interval, view, image, text, theme, cores, activity, quit
}

struct MenuStrings {
    func title(_ role: MenuRole) -> String {
        switch role {
        case .login: return "Start at Login"
        case .interval: return "Update Interval"
        case .view: return "View Mode"
        case .image: return "Image"
        case .text: return "Text"
        case .theme: return "Theme"
        case .cores: return "Show cores individually"
        case .activity: return "Open Activity Monitor"
        case .quit: return "Quit"
        }
    }
    func interval(_ index: Int) -> String {
        ["0.1", "0.2", "0.5", "1.0", "5", "10", "30"][index] + "sec"
    }
}