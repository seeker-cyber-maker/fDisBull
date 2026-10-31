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
    let language: String
    init(language: String = Bundle.main.preferredLocalizations.first ?? "en") {
        self.language = language.lowercased().hasPrefix("ja") ? "ja" : "en"
    }
    func title(_ role: MenuRole) -> String {
        switch (language, role) {
        case ("ja", .login): return "ログイン時に開始"
        case ("ja", .interval): return "更新間隔"
        case ("ja", .view): return "表示"
        case ("ja", .image): return "アイコン"
        case ("ja", .text): return "テキスト"
        case ("ja", .theme): return "テーマ"
        case ("ja", .cores): return "コアを個別に表示"
        case ("ja", .activity): return "アクティビティモニタを開く"
        case ("ja", .quit): return "終了"
        case (_, .login): return "Start at Login"
        case (_, .interval): return "Update Interval"
        case (_, .view): return "View Mode"
        case (_, .image): return "Image"
        case (_, .text): return "Text"
        case (_, .theme): return "Theme"
        case (_, .cores): return "Show cores individually"
        case (_, .activity): return "Open Activity Monitor"
        case (_, .quit): return "Quit"
        }
    }
    func interval(_ index: Int) -> String {
        let value = ["0.1", "0.2", "0.5", "1.0", "5", "10", "30"][index]
        return value + (language == "ja" ? "秒" : "sec")
    }
}
