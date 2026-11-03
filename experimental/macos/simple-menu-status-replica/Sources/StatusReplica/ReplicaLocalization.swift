import Foundation

/// The visible language choice is stored only in the replica's defaults domain.
/// English is the source language; selected Japanese strings live in this
/// app's own, small Localizable.strings resource.
enum ReplicaLocalization {
    static func languageCode(_ choice: String) -> String {
        if choice == "English" { return "en" }
        if choice == "日本語" { return "ja" }
        return Locale.preferredLanguages.first?.lowercased().hasPrefix("ja") == true ? "ja" : "en"
    }

    static func locale(_ choice: String) -> Locale {
        Locale(identifier: languageCode(choice))
    }

    static func text(_ english: String, choice: String) -> String {
        guard languageCode(choice) == "ja",
              let path = Bundle.main.path(forResource: "ja", ofType: "lproj"),
              let bundle = Bundle(path: path) else { return english }
        return bundle.localizedString(forKey: english, value: english, table: "Localizable")
    }
}
