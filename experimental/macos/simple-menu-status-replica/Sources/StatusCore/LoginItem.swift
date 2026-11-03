import Foundation
import Darwin
import Security
import ServiceManagement

/// The system's current login-item state, including conditions that require user action.
public enum LoginItemStatus: Equatable {
    case enabled
    case notRegistered
    case requiresApproval
    case notFound
    case unsupported(String)
    case unknown
}

public enum LoginItemError: LocalizedError {
    case unsupported(String)
    case conflict(String)
    public var errorDescription: String? {
        switch self { case .unsupported(let reason), .conflict(let reason): return reason }
    }
}

/// A per-user LaunchAgent for an unsigned local app. The exact expected plist,
/// owner and file type are checked before an existing file is accepted or removed.
public struct LocalLoginAgent {
    public static let label = "local.codex.simple-menu-status-replica.login"
    public let home: URL
    public let executable: URL
    public init(home: URL, executable: URL) { self.home = home; self.executable = executable }
    public var fileURL: URL { home.appendingPathComponent("Library/LaunchAgents/\(Self.label).plist") }
    private var expected: [String: Any] {
        ["Label": Self.label, "ProgramArguments": [executable.path], "RunAtLoad": true]
    }
    private func existingIsOurs() throws -> Bool {
        var info = stat()
        if lstat(fileURL.path, &info) != 0 {
            if errno == ENOENT { return false }
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        }
        guard (info.st_mode & S_IFMT) == S_IFREG, info.st_uid == getuid(),
              let data = try? Data(contentsOf: fileURL),
              let plist = try? PropertyListSerialization.propertyList(from: data, options: [], format: nil),
              let dict = plist as? NSDictionary, dict.isEqual(to: expected) else {
            throw LoginItemError.conflict("The login agent file is not the expected file owned by this user. It was left unchanged.")
        }
        return true
    }
    public func status() -> LoginItemStatus {
        do { return try existingIsOurs() ? .enabled : .notRegistered }
        catch { return .unsupported(error.localizedDescription) }
    }
    public func setEnabled(_ enabled: Bool) throws {
        guard executable.isFileURL, executable.path.hasPrefix("/"), !executable.path.isEmpty else {
            throw LoginItemError.unsupported("The application executable must have an absolute path.")
        }
        if try existingIsOurs() {
            if !enabled { try FileManager.default.removeItem(at: fileURL) }
            return
        }
        guard enabled else { return }
        let directory = fileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try PropertyListSerialization.data(fromPropertyList: expected, format: .xml, options: 0)
        let temporary = directory.appendingPathComponent(".\(Self.label).\(UUID().uuidString).tmp")
        // Exclusive temporary creation followed by a hard link makes publication
        // atomic and refuses to overwrite a file created concurrently.
        let fd = open(temporary.path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        defer { close(fd); unlink(temporary.path) }
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let count = Darwin.write(fd, bytes.baseAddress!.advanced(by: offset), bytes.count - offset)
                guard count > 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
                offset += count
            }
        }
        guard link(temporary.path, fileURL.path) == 0 else {
            if errno == EEXIST { throw LoginItemError.conflict("The login agent file already exists. It was left unchanged.") }
            throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO)
        }
    }
}

/// Reading status never changes login settings. Registration is only attempted
/// by calling setEnabled explicitly. ServiceManagement is available on macOS 13+.
public struct LoginItemController {
    public init() {}

    /// A conservative eligibility check: running an executable directly, an
    /// unsigned app, or an ad-hoc signed development app is not offered as a
    /// reliable persistent login item. Signing alone does not guarantee approval.
    public static func bundleProblem(_ bundle: Bundle) -> String? {
        guard bundle.bundleURL.pathExtension.lowercased() == "app",
              let identifier = bundle.bundleIdentifier, !identifier.isEmpty else {
            return "Launch at login requires an installed, identified app bundle."
        }
        var code: SecStaticCode?
        guard SecStaticCodeCreateWithPath(bundle.bundleURL as CFURL, [], &code) == errSecSuccess,
              let code,
              SecStaticCodeCheckValidity(code, [], nil) == errSecSuccess else {
            return "Launch at login requires a valid signed app bundle; this development bundle is unsigned or invalid."
        }
        var info: CFDictionary?
        guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &info) == errSecSuccess,
              let dictionary = info as? [String: Any],
              let team = dictionary[kSecCodeInfoTeamIdentifier as String] as? String,
              !team.isEmpty else {
            return "Launch at login requires a team-signed app; ad-hoc development signing is not supported."
        }
        return nil
    }

    private var localAgent: LocalLoginAgent? {
        guard Bundle.main.bundleURL.pathExtension.lowercased() == "app",
              Bundle.main.bundleIdentifier != nil,
              let executable = Bundle.main.executableURL else { return nil }
        return LocalLoginAgent(home: FileManager.default.homeDirectoryForCurrentUser, executable: executable)
    }

    /// Explains which mechanism is in use; the local agent takes effect at next login.
    public var mechanismDescription: String {
        if #available(macOS 13.0, *), Self.bundleProblem(.main) == nil {
            return "Managed by macOS Login Items."
        }
        return localAgent == nil ? "Available only from an app bundle." : "Per-user login agent; changes take effect at next login."
    }

    public func status() -> LoginItemStatus {
        if #available(macOS 13.0, *), Self.bundleProblem(.main) == nil {
            return managedStatus()
        }
        guard let agent = localAgent else { return .unsupported("Launch at login requires an identified app bundle.") }
        return agent.status()
    }

    @available(macOS 13.0, *)
    private func managedStatus() -> LoginItemStatus {
        switch SMAppService.mainApp.status {
        case .enabled: return .enabled
        case .notRegistered: return .notRegistered
        case .requiresApproval: return .requiresApproval
        case .notFound: return .notFound
        @unknown default: return .unknown
        }
    }

    public func setEnabled(_ enabled: Bool) throws {
        if #available(macOS 13.0, *), Self.bundleProblem(.main) == nil {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
            return
        }
        guard let agent = localAgent else { throw LoginItemError.unsupported("Launch at login requires an identified app bundle.") }
        try agent.setEnabled(enabled)
    }
}
