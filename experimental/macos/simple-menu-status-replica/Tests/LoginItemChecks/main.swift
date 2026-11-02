import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs("FAIL: \(message)\n", stderr); exit(1) }
}
// This test runs as a command-line executable, never as a registered app.
// It exercises reads and the unsupported guard without mutating login items.
check(LoginItemController.bundleProblem(.main) != nil, "command-line bundle is unsupported")
let status = LoginItemController().status()
if case .unsupported(let reason) = status {
    check(!reason.isEmpty, "unsupported state explains why")
} else {
    check(false, "command-line execution must report unsupported")
}
check(LoginItemStatus.enabled != .requiresApproval, "approval is distinct from enabled")
check(LoginItemStatus.notRegistered != .notFound, "missing service is distinct from disabled")
print("Login-item read-only checks passed.")

let home = FileManager.default.temporaryDirectory.appendingPathComponent("login-item-check-\(UUID().uuidString)")
defer { try? FileManager.default.removeItem(at: home) }
let agent = LocalLoginAgent(home: home, executable: URL(fileURLWithPath: "/Applications/Example.app/Contents/MacOS/Example"))
check(agent.status() == .notRegistered, "agent initially absent")
try agent.setEnabled(true)
check(agent.status() == .enabled, "agent appears enabled after writing")
let data = try Data(contentsOf: agent.fileURL)
let plist = try PropertyListSerialization.propertyList(from: data, options: [], format: nil) as! [String: Any]
check(plist["Label"] as? String == LocalLoginAgent.label, "label is scoped")
check(plist["ProgramArguments"] as? [String] == ["/Applications/Example.app/Contents/MacOS/Example"], "absolute executable preserved")
check(plist["RunAtLoad"] as? Bool == true, "runs on next login")
try agent.setEnabled(true)
try agent.setEnabled(false)
check(agent.status() == .notRegistered, "disable removes own file")
let foreign = Data("foreign content".utf8)
try foreign.write(to: agent.fileURL)
if case .unsupported = agent.status() {} else { check(false, "foreign file reports conflict") }
for enabled in [true, false] {
    do { try agent.setEnabled(enabled); check(false, "foreign file must be preserved") }
    catch LoginItemError.conflict(_) {}
}
let preserved = try Data(contentsOf: agent.fileURL)
check(preserved == foreign, "foreign file remains unchanged")
try FileManager.default.removeItem(at: agent.fileURL)
try FileManager.default.createSymbolicLink(at: agent.fileURL, withDestinationURL: URL(fileURLWithPath: "/tmp"))
do { try agent.setEnabled(false); check(false, "symlink must be refused") }
catch LoginItemError.conflict(_) {}
print("Temporary-home login-agent checks passed.")
