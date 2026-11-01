// Explicit, bounded macOS observation helper. No app is launched or activated.
import Foundation
import AppKit
import ApplicationServices
import CoreGraphics
import ScreenCaptureKit
import ImageIO
import UniformTypeIdentifiers

struct Refusal: Error { let message: String }

func require(_ condition: Bool, _ message: String) throws {
    if !condition { throw Refusal(message: message) }
}

func fields(_ request: [String: Any], required: Set<String>, optional: Set<String> = []) throws {
    try require(required.isSubset(of: Set(request.keys)) && Set(request.keys).isSubset(of: required.union(optional)), "invalid request fields")
}

func text(_ request: [String: Any], _ key: String, maximum: Int = 1024) throws -> String {
    guard let value = request[key] as? String else { throw Refusal(message: "\(key) must be a string") }
    try require(!value.isEmpty && value.utf8.count <= maximum && !value.contains("\0"), "invalid \(key)")
    return value
}

func bundleIdentifier(_ request: [String: Any]) throws -> String {
    let value = try text(request, "bundle_id", maximum: 255)
    try require(value.range(of: "^[A-Za-z0-9][A-Za-z0-9._-]*$", options: .regularExpression) != nil,
                "bundle_id must be a literal application identifier")
    return value
}

func launchIdentity(_ app: NSRunningApplication) -> String? {
    guard let date = app.launchDate else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: date)
}

func integer(_ value: Any?, _ name: String, minimum: Int = 0, maximum: Int = Int(UInt32.max)) throws -> Int {
    guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID() else {
        throw Refusal(message: "\(name) must be an integer")
    }
    let result = number.doubleValue
    try require(result.isFinite && result.rounded() == result && result >= Double(minimum) && result <= Double(maximum), "invalid \(name)")
    return Int(result)
}

func rectangle(_ rect: CGRect) -> [String: Double] {
    ["x": rect.origin.x, "y": rect.origin.y, "width": rect.width, "height": rect.height]
}

func readRect(_ object: Any) throws -> CGRect {
    guard let value = object as? [String: Any], Set(value.keys) == ["x", "y", "width", "height"] else {
        throw Refusal(message: "rect must contain x, y, width and height")
    }
    var numbers: [String: Double] = [:]
    for key in ["x", "y", "width", "height"] {
        guard let number = value[key] as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(), number.doubleValue.isFinite else {
            throw Refusal(message: "invalid rect coordinate")
        }
        numbers[key] = number.doubleValue
    }
    let result = CGRect(x: numbers["x"]!, y: numbers["y"]!, width: numbers["width"]!, height: numbers["height"]!)
    try require(result.width > 0 && result.height > 0 && result.width <= 32768 && result.height <= 32768, "invalid rect dimensions")
    return result
}

func displayInventory() throws -> [[String: Any]] {
    var count: UInt32 = 0
    try require(CGGetActiveDisplayList(0, nil, &count) == .success && count <= 32, "cannot enumerate bounded displays")
    var displays = [CGDirectDisplayID](repeating: 0, count: Int(count))
    try require(CGGetActiveDisplayList(count, &displays, &count) == .success, "cannot read displays")
    return displays.prefix(Int(count)).map { id in
        let bounds = CGDisplayBounds(id)
        let width = CGDisplayPixelsWide(id), height = CGDisplayPixelsHigh(id)
        let uuid = CGDisplayCreateUUIDFromDisplayID(id).takeRetainedValue()
        return ["id": id, "uuid": CFUUIDCreateString(nil, uuid)! as String,
                "global_bounds": rectangle(bounds), "pixel_width": width, "pixel_height": height,
                "scale_x": Double(width) / bounds.width, "scale_y": Double(height) / bounds.height,
                "rotation_degrees": CGDisplayRotation(id), "main": id == CGMainDisplayID(),
                "mirrors_display_id": CGDisplayMirrorsDisplay(id),
                "coordinate_system": "CoreGraphics-global-logical-top-left"]
    }
}

func attribute(_ element: AXUIElement, _ name: String) -> CFTypeRef? {
    var value: CFTypeRef?
    return AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success ? value : nil
}

func actionNames(_ element: AXUIElement) -> [String] {
    var names: CFArray?
    guard AXUIElementCopyActionNames(element, &names) == .success, let values = names as? [String] else { return [] }
    return Array(values.prefix(32)).map { String($0.prefix(128)) }
}

func elements(_ value: CFTypeRef?) -> [AXUIElement] {
    guard let value = value as? [AnyObject] else { return [] }
    return value.compactMap { item in
        CFGetTypeID(item) == AXUIElementGetTypeID() ? (item as! AXUIElement) : nil
    }
}

func axFrame(_ element: AXUIElement) -> CGRect? {
    guard let position = attribute(element, kAXPositionAttribute), let size = attribute(element, kAXSizeAttribute),
          CFGetTypeID(position) == AXValueGetTypeID(), CFGetTypeID(size) == AXValueGetTypeID() else { return nil }
    var point = CGPoint.zero, extent = CGSize.zero
    guard AXValueGetValue(position as! AXValue, .cgPoint, &point), AXValueGetValue(size as! AXValue, .cgSize, &extent),
          point.x.isFinite && point.y.isFinite && extent.width.isFinite && extent.height.isFinite else { return nil }
    return CGRect(origin: point, size: extent)
}

func short(_ value: String) -> String { String(value.prefix(256)) }

func windowFrame(_ window: [String: Any]) -> CGRect? {
    guard let bounds = window["bounds"] as? [String: Any] else { return nil }
    return CGRect(dictionaryRepresentation: bounds as CFDictionary)
}

struct AXObservation {
    var nodes: [[String: Any]] = []
    var truncated = false
    var visibleMenus: [Int] = []
    var nativeElements: [AXUIElement] = []
    var seen: [AXUIElement] = []
    var encodedBytes = 0

    mutating func visit(_ element: AXUIElement, depth: Int, parent: Int?) {
        if depth > 8 || nodes.count >= 400 || encodedBytes >= 192 * 1024 { truncated = true; return }
        if seen.contains(where: { CFEqual($0, element) }) { return }
        seen.append(element)
        let index = nodes.count
        var node: [String: Any] = ["index": index, "depth": depth]
        if let parent { node["parent"] = parent }
        for (key, name) in [("role", kAXRoleAttribute), ("subrole", kAXSubroleAttribute),
                            ("title", kAXTitleAttribute), ("description", kAXDescriptionAttribute),
                            ("identifier", kAXIdentifierAttribute), ("value", kAXValueAttribute)] {
            if let value = attribute(element, name) {
                if let string = value as? String { node[key] = short(string) }
                else if let number = value as? NSNumber, number.doubleValue.isFinite { node[key] = number }
            }
        }
        if let frame = axFrame(element) { node["global_frame"] = rectangle(frame) }
        if let enabled = attribute(element, kAXEnabledAttribute) as? Bool { node["enabled"] = enabled }
        if let expanded = attribute(element, "AXExpanded") as? Bool { node["expanded"] = expanded }
        node["actions"] = actionNames(element)
        let bytes = (try? JSONSerialization.data(withJSONObject: node).count) ?? 192 * 1024
        if encodedBytes + bytes > 192 * 1024 { encodedBytes = 192 * 1024; truncated = true; return }
        encodedBytes += bytes
        nodes.append(node)
        nativeElements.append(element)
        if node["role"] as? String == kAXMenuRole, let frame = axFrame(element), frame.width > 0 && frame.height > 0 {
            // An exposed AXMenu with a real frame is observation; no hidden-menu guess.
            if attribute(element, "AXVisible") as? Bool != false { visibleMenus.append(index) }
        }
        for child in elements(attribute(element, kAXChildrenAttribute)) {
            visit(child, depth: depth + 1, parent: index)
        }
    }
}

func application(_ request: [String: Any]) throws -> NSRunningApplication? {
    let bundle = try bundleIdentifier(request)
    let expected = try request["expected_launch_date"].map { _ in try text(request, "expected_launch_date", maximum: 64) }
    try require(expected == nil || request["pid"] != nil, "expected_launch_date requires an explicit PID")
    let matches = NSRunningApplication.runningApplications(withBundleIdentifier: bundle).filter { !$0.isTerminated }
    if let rawPID = request["pid"] {
        let pid = try integer(rawPID, "pid", minimum: 1, maximum: Int(Int32.max))
        guard let selected = matches.first(where: { $0.processIdentifier == pid_t(pid) }) else {
            throw Refusal(message: "running PID does not match the requested bundle")
        }
        if let expected {
            try require(launchIdentity(selected) == expected, "application launch identity changed")
        }
        return selected
    }
    try require(matches.count <= 1, "multiple running instances; select an explicit PID")
    return matches.first
}

func statusItems(_ appElement: AXUIElement) -> (items: [AXUIElement], readable: Bool) {
    var result: [AXUIElement] = []
    var readable = false
    for key in [kAXMenuBarAttribute, "AXExtrasMenuBar"] {
        if let bar = attribute(appElement, key), CFGetTypeID(bar) == AXUIElementGetTypeID() {
            readable = true
            let element = bar as! AXUIElement
            for item in elements(attribute(element, kAXChildrenAttribute)) {
                if attribute(item, kAXRoleAttribute) as? String == kAXMenuBarItemRole {
                    // Exclude the ordinary app menubar by choosing extras, or items with no app menu title.
                    if key == "AXExtrasMenuBar" || (attribute(item, kAXTitleAttribute) as? String ?? "").isEmpty {
                        if !result.contains(where: { CFEqual($0, item) }) { result.append(item) }
                    }
                }
            }
        }
    }
    return (result, readable)
}

func snapshot(_ request: [String: Any]) throws -> [String: Any] {
    let bundle = try bundleIdentifier(request)
    let app = try application(request)
    let axTrusted = AXIsProcessTrusted()
    let screenAllowed = CGPreflightScreenCaptureAccess()
    var target: [String: Any] = ["bundle_id": bundle, "running": app != nil,
                                "pid": NSNull(), "launch_date": NSNull(), "bundle_path": NSNull()]
    var menu: [String: Any] = ["open": NSNull(), "status_index": NSNull(), "confidence": "unknown", "evidence": []]
    var windows: [[String: Any]] = [], status: [[String: Any]] = []
    var observation = AXObservation()
    if let app {
        target["pid"] = app.processIdentifier
        target["launch_date"] = launchIdentity(app) ?? NSNull() as Any
        target["bundle_path"] = app.bundleURL?.path ?? NSNull() as Any
        let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
        for item in list where (item[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == app.processIdentifier {
            if windows.count >= 128 { break }
            var row: [String: Any] = [:]
            for (out, key) in [("id", kCGWindowNumber), ("layer", kCGWindowLayer), ("alpha", kCGWindowAlpha),
                               ("name", kCGWindowName), ("bounds", kCGWindowBounds)] {
                if let value = item[key as String] { row[out] = value }
            }
            windows.append(row)
        }
        if axTrusted {
            let element = AXUIElementCreateApplication(app.processIdentifier)
            AXUIElementSetMessagingTimeout(element, 1.0)
            let extracted = statusItems(element)
            observation.visit(element, depth: 0, parent: nil)
            for key in [kAXMenuBarAttribute, "AXExtrasMenuBar"] {
                if let bar = attribute(element, key), CFGetTypeID(bar) == AXUIElementGetTypeID() {
                    observation.visit(bar as! AXUIElement, depth: 1, parent: nil)
                }
            }
            for (index, item) in extracted.items.enumerated() {
                var row: [String: Any] = ["index": index]
                if let frame = axFrame(item) { row["global_frame"] = rectangle(frame) }
                for (key, attr) in [("title", kAXTitleAttribute), ("description", kAXDescriptionAttribute), ("identifier", kAXIdentifierAttribute)] {
                    if let value = attribute(item, attr) as? String { row[key] = short(value) }
                }
                status.append(row)
            }
            let visibleMenus = observation.visibleMenus.filter { index in
                guard let rawFrame = observation.nodes[index]["global_frame"], let frame = try? readRect(rawFrame) else { return false }
                return windows.contains { window in
                    guard let other = windowFrame(window) else { return false }
                    let intersection = frame.intersection(other)
                    return !intersection.isNull && intersection.width * intersection.height >= frame.width * frame.height * 0.5
                }
            }
            let statusFrames = extracted.items.compactMap(axFrame)
            let contentWindows = windows.filter { window in
                guard let frame = windowFrame(window), frame.width > 0, frame.height > 0 else { return false }
                return !statusFrames.contains { $0.insetBy(dx: -2, dy: -2).contains(frame) }
            }
            if !visibleMenus.isEmpty {
                menu = ["open": true, "status_index": status.count == 1 ? 0 : NSNull(),
                        "confidence": "observed_ax_menu_and_window", "evidence": visibleMenus]
            } else if extracted.readable && !extracted.items.isEmpty && !observation.truncated && contentWindows.isEmpty {
                menu = ["open": false, "status_index": status.count == 1 ? 0 : NSNull(),
                        "confidence": "observed_no_menu_or_window", "evidence": []]
            }
        }
    } else {
        menu = ["open": false, "status_index": NSNull(), "confidence": "app_not_running", "evidence": []]
    }
    #if arch(arm64)
    let architecture = "arm64"
    #elseif arch(x86_64)
    let architecture = "x86_64"
    #else
    let architecture = "unknown"
    #endif
    return ["format": "fdisbull-macos-snapshot-1", "host": ["system": "Darwin", "architecture": architecture],
            "permissions": ["accessibility": axTrusted, "screen_capture": screenAllowed, "prompted": false],
            "target": target, "menu": menu, "menu_open": menu["open"]!, "status_items": status,
            "displays": try displayInventory(), "windows": windows,
            "ax": ["nodes": observation.nodes, "truncated": observation.truncated, "max_nodes": 400, "max_depth": 8],
            "coordinate_system": "CoreGraphics-global-logical-top-left",
            "limitations": ["Menu state is unknown when AX or visible-window evidence is ambiguous.",
                            "Preference-domain access does not certify sandbox-container preference coverage."]]
}

func actionSnapshot(_ snapshot: [String: Any]) -> [String: Any] {
    // Full trees are retained by explicit snapshot operations, not duplicated after input.
    ["target": snapshot["target"] ?? NSNull(), "menu": snapshot["menu"] ?? NSNull(),
     "menu_open": snapshot["menu_open"] ?? NSNull()]
}

func observedTransition(_ request: [String: Any], desired: Bool) throws -> (snapshot: [String: Any], count: Int) {
    var last: [String: Any] = [:]
    for attempt in 1...3 {
        if attempt > 1 { Thread.sleep(forTimeInterval: 0.15) }
        last = try snapshot(request)
        if (last["menu"] as? [String: Any])?["open"] as? Bool == desired { return (last, attempt) }
        // Observe again, but never replay an input after incomplete delivery/observation.
    }
    return (last, 3)
}

func cancelableMenu(_ element: AXUIElement, before: [String: Any]) -> AXUIElement? {
    var observation = AXObservation()
    observation.visit(element, depth: 0, parent: nil)
    for key in [kAXMenuBarAttribute, "AXExtrasMenuBar"] {
        if let bar = attribute(element, key), CFGetTypeID(bar) == AXUIElementGetTypeID() {
            observation.visit(bar as! AXUIElement, depth: 1, parent: nil)
        }
    }
    let windows = before["windows"] as? [[String: Any]] ?? []
    for index in observation.visibleMenus {
        let menu = observation.nativeElements[index]
        guard let frame = axFrame(menu), actionNames(menu).contains(kAXCancelAction) else { continue }
        if windows.contains(where: { window in
            guard let other = windowFrame(window) else { return false }
            let overlap = frame.intersection(other)
            return !overlap.isNull && overlap.width * overlap.height >= frame.width * frame.height * 0.5
        }) { return menu }
    }
    return nil
}

func press(_ request: [String: Any], dismissOnly: Bool) throws -> [String: Any] {
    try require(AXIsProcessTrusted(), "Accessibility permission unavailable; no prompt requested")
    guard let app = try application(request) else { throw Refusal(message: "app is not running") }
    guard let launchDate = launchIdentity(app) else { throw Refusal(message: "application launch identity unavailable") }
    var boundRequest = request
    boundRequest["expected_launch_date"] = launchDate
    let index = try integer(request["index"], "index", maximum: 63)
    let before = try snapshot(boundRequest)
    guard let menu = before["menu"] as? [String: Any], let open = menu["open"] as? Bool else {
        throw Refusal(message: "menu state is unknown; refusing a blind toggle")
    }
    let desired = !dismissOnly
    if open == desired {
        return ["status": "confirmed", "changed": false, "before": actionSnapshot(before), "after": actionSnapshot(before),
                "delivery": ["method": "none", "status": "not_needed"],
                "observed_effect": ["requested": desired ? "open" : "closed", "state": open,
                                    "status": "confirmed", "snapshots": 0]]
    }
    let element = AXUIElementCreateApplication(app.processIdentifier)
    AXUIElementSetMessagingTimeout(element, 0.25)
    let items = statusItems(element).items
    try require(index < items.count, "selected status item is unavailable")
    var delivery: [String: Any]
    // Recheck source process identity immediately before the one input attempt.
    _ = try application(boundRequest)
    if dismissOnly {
        let menuElement = cancelableMenu(element, before: before)
        let ready = try snapshot(boundRequest)
        guard let readyOpen = (ready["menu"] as? [String: Any])?["open"] as? Bool else {
            throw Refusal(message: "menu state became unknown before dismissal; no input attempted")
        }
        if !readyOpen {
            return ["status": "confirmed", "changed": true, "before": actionSnapshot(before), "after": actionSnapshot(ready),
                    "delivery": ["method": "none", "status": "not_needed"],
                    "observed_effect": ["requested": "closed", "state": false, "status": "confirmed", "snapshots": 1]]
        }
        if let menuElement {
            let result = AXUIElementPerformAction(menuElement, kAXCancelAction as CFString)
            delivery = ["method": "AXCancel", "ax_error": result.rawValue,
                        "status": result == .success ? "returned_success" : "returned_error"]
        } else {
            // Target one PID, never the frontmost application or global keyboard stream.
            guard let source = CGEventSource(stateID: .privateState),
                  let down = CGEvent(keyboardEventSource: source, virtualKey: 53, keyDown: true),
                  let up = CGEvent(keyboardEventSource: source, virtualKey: 53, keyDown: false) else {
                throw Refusal(message: "cannot construct a targeted Escape event")
            }
            _ = try application(boundRequest)
            down.flags = []; up.flags = []
            down.postToPid(app.processIdentifier)
            up.postToPid(app.processIdentifier)
            delivery = ["method": "CGEvent.Escape.postToPid", "status": "posted_without_acknowledgement",
                        "pid": app.processIdentifier]
        }
    } else {
        let ready = try snapshot(boundRequest)
        guard let readyOpen = (ready["menu"] as? [String: Any])?["open"] as? Bool else {
            throw Refusal(message: "menu state became unknown before opening; no input attempted")
        }
        if readyOpen {
            return ["status": "confirmed", "changed": true, "before": actionSnapshot(before), "after": actionSnapshot(ready),
                    "delivery": ["method": "none", "status": "not_needed"],
                    "observed_effect": ["requested": "open", "state": true, "status": "confirmed", "snapshots": 1]]
        }
        let result = AXUIElementPerformAction(items[index], kAXPressAction as CFString)
        delivery = ["method": "AXPress", "ax_error": result.rawValue,
                    "status": result == .success ? "returned_success" : "returned_error"]
    }
    Thread.sleep(forTimeInterval: 0.25)
    let observed = try observedTransition(boundRequest, desired: desired)
    let afterState = (observed.snapshot["menu"] as? [String: Any])?["open"] as? Bool
    let confirmed = afterState == desired
    return ["status": confirmed ? "confirmed" : "partial",
            "changed": afterState.map { $0 != open } ?? NSNull() as Any,
            "before": actionSnapshot(before), "after": actionSnapshot(observed.snapshot), "delivery": delivery,
            "observed_effect": ["requested": desired ? "open" : "closed", "state": afterState ?? NSNull() as Any,
                                "status": confirmed ? "confirmed" : "partial", "snapshots": observed.count]]
}

func preferenceValue(_ bundle: String, _ key: String) throws -> [String: Any] {
    guard let value = CFPreferencesCopyValue(key as CFString, bundle as CFString, kCFPreferencesCurrentUser, kCFPreferencesAnyHost) else {
        return ["present": false, "value_base64": NSNull()]
    }
    let data = try PropertyListSerialization.data(fromPropertyList: ["value": value], format: .binary, options: 0)
    try require(data.count <= 48 * 1024, "encoded preference value would exceed 64 KiB")
    return ["present": true, "value_base64": data.base64EncodedString()]
}

func preferences(_ request: [String: Any], write: Bool) throws -> [String: Any] {
    let bundle = try bundleIdentifier(request)
    if write {
        if request["pid"] != nil || request["expected_launch_date"] != nil { _ = try application(request) }
        let key = try text(request, "key", maximum: 255)
        var restored: CFPropertyList?
        if !(request["value_base64"] is NSNull) {
            let base64 = try text(request, "value_base64", maximum: 64 * 1024)
            guard let data = Data(base64Encoded: base64), data.count <= 48 * 1024,
                  let wrapped = try PropertyListSerialization.propertyList(from: data, options: [], format: nil) as? [String: Any],
                  Set(wrapped.keys) == ["value"] else { throw Refusal(message: "invalid wrapped binary plist") }
            restored = wrapped["value"] as CFPropertyList?
        }
        CFPreferencesSetValue(key as CFString, restored, bundle as CFString, kCFPreferencesCurrentUser, kCFPreferencesAnyHost)
        try require(CFPreferencesSynchronize(bundle as CFString, kCFPreferencesCurrentUser, kCFPreferencesAnyHost), "preference synchronization failed")
        return ["key": key, "preference": try preferenceValue(bundle, key), "domain": bundle,
                "scope": "current-user-any-host; sandbox coverage unverified"]
    }
    guard let keys = request["keys"] as? [String] else { throw Refusal(message: "keys must be an array of strings") }
    try require(keys.count <= 64 && Set(keys).count == keys.count && keys.allSatisfy { !$0.isEmpty && $0.utf8.count <= 255 && !$0.contains("\0") }, "invalid preference keys")
    var values: [String: Any] = [:]
    var encodedBytes = 0
    for key in keys {
        let value = try preferenceValue(bundle, key)
        encodedBytes += (value["value_base64"] as? String)?.utf8.count ?? 0
        try require(encodedBytes <= 128 * 1024, "preference snapshot exceeds 128 KiB")
        values[key] = value
    }
    return ["domain": bundle, "preferences": values, "encoding": "base64-binary-plist-wrapped-value",
            "scope": "current-user-any-host; sandbox coverage unverified"]
}

@available(macOS 14.0, *)
func capture(_ request: [String: Any]) async throws -> [String: Any] {
    try require(CGPreflightScreenCaptureAccess(), "Screen Recording permission unavailable; no prompt requested")
    let displayID = CGDirectDisplayID(try integer(request["display_id"], "display_id", minimum: 1))
    let displays = try displayInventory()
    guard let displayInfo = displays.first(where: { ($0["id"] as? CGDirectDisplayID) == displayID }) else {
        throw Refusal(message: "selected display is not active")
    }
    let bounds = CGDisplayBounds(displayID)
    let region = try request["rect"].map(readRect) ?? bounds
    try require(bounds.contains(region), "global capture rect must be contained in the selected display")
    let scaleX = Double(CGDisplayPixelsWide(displayID)) / bounds.width
    let scaleY = Double(CGDisplayPixelsHigh(displayID)) / bounds.height
    let pixelWidth = Int((region.width * scaleX).rounded()), pixelHeight = Int((region.height * scaleY).rounded())
    try require(pixelWidth > 0 && pixelHeight > 0 && pixelWidth <= 32768 && pixelHeight <= 32768 && pixelWidth * pixelHeight <= 100000000, "capture pixel budget exceeded")
    let outputPath = try text(request, "output", maximum: 4096)
    try require(outputPath.hasPrefix("/"), "capture output must be an absolute path")
    let output = URL(fileURLWithPath: outputPath)
    try require(!FileManager.default.fileExists(atPath: output.path), "capture output must be a new path")
    let parent = output.deletingLastPathComponent()
    var isDirectory: ObjCBool = false
    try require(FileManager.default.fileExists(atPath: parent.path, isDirectory: &isDirectory) && isDirectory.boolValue, "capture output directory does not exist")
    let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
    guard let selected = content.displays.first(where: { $0.displayID == displayID }) else { throw Refusal(message: "ScreenCaptureKit cannot access selected display") }
    let filter = SCContentFilter(display: selected, excludingWindows: [])
    let config = SCStreamConfiguration()
    let local = CGRect(x: region.minX - bounds.minX, y: region.minY - bounds.minY, width: region.width, height: region.height)
    config.sourceRect = local
    config.width = pixelWidth
    config.height = pixelHeight
    config.showsCursor = false
    let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
    try require(image.width == pixelWidth && image.height == pixelHeight, "captured pixel dimensions do not match the requested display scale")
    let temporary = parent.appendingPathComponent(".fdisbull-capture-\(UUID().uuidString).png")
    defer { try? FileManager.default.removeItem(at: temporary) }
    guard let destination = CGImageDestinationCreateWithURL(temporary as CFURL, UTType.png.identifier as CFString, 1, nil) else {
        throw Refusal(message: "cannot create PNG destination")
    }
    CGImageDestinationAddImage(destination, image, nil)
    try require(CGImageDestinationFinalize(destination), "cannot finalize PNG")
    try FileManager.default.moveItem(at: temporary, to: output)
    return ["format": "fdisbull-macos-capture-1", "display": displayInfo,
            "global_rect": rectangle(region), "display_local_rect": rectangle(local),
            "pixel_width": image.width, "pixel_height": image.height, "scale_x": scaleX, "scale_y": scaleY,
            "coordinate_system": "CoreGraphics-global-logical-top-left", "output": output.path,
            "cursor_included": false, "backend": "ScreenCaptureKit.SCScreenshotManager"]
}

@main
struct Main {
    @MainActor static func main() async {
        do {
            var input = Data()
            while input.count <= 2 * 1024 * 1024 {
                let chunk = try FileHandle.standardInput.read(upToCount: min(65536, 2 * 1024 * 1024 + 1 - input.count)) ?? Data()
                if chunk.isEmpty { break }
                input.append(chunk)
            }
            try require(input.count <= 2 * 1024 * 1024, "request exceeds 2 MiB")
            guard let request = try JSONSerialization.jsonObject(with: input) as? [String: Any] else { throw Refusal(message: "request must be an object") }
            let op = try text(request, "op", maximum: 32)
            let result: [String: Any]
            let identity: Set<String> = ["pid", "expected_launch_date"]
            switch op {
            case "snapshot":
                try fields(request, required: ["op", "bundle_id"], optional: identity)
                result = try snapshot(request)
            case "press_status", "dismiss_menu":
                try fields(request, required: ["op", "bundle_id", "pid", "index"], optional: ["expected_launch_date"])
                result = try press(request, dismissOnly: op == "dismiss_menu")
            case "prefs_get":
                try fields(request, required: ["op", "bundle_id", "keys"])
                result = try preferences(request, write: false)
            case "prefs_set":
                try fields(request, required: ["op", "bundle_id", "key", "value_base64"], optional: identity)
                result = try preferences(request, write: true)
            case "capture":
                try fields(request, required: ["op", "display_id", "output"], optional: ["rect"])
                if #available(macOS 14.0, *) { result = try await capture(request) }
                else { throw Refusal(message: "ScreenCaptureKit screenshot capture requires macOS 14 or later") }
            default: throw Refusal(message: "unknown operation")
            }
            let data = try JSONSerialization.data(withJSONObject: ["ok": true, "result": result], options: [.sortedKeys])
            try require(data.count <= 256 * 1024, "response exceeds 256 KiB")
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([10]))
        } catch {
            let message = (error as? Refusal)?.message ?? error.localizedDescription
            let response: [String: Any] = ["ok": false, "error": ["type": "MacObservationRefused", "message": String(message.prefix(1024))]]
            if let data = try? JSONSerialization.data(withJSONObject: response, options: [.sortedKeys]) {
                FileHandle.standardOutput.write(data)
                FileHandle.standardOutput.write(Data([10]))
            }
            exit(1)
        }
    }
}
