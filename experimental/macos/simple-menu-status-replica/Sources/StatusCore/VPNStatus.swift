import Foundation
import SystemConfiguration

/// High-level state reported by SystemConfiguration. Invalid or unavailable
/// connections stay unknown rather than being presented as disconnected.
public enum VPNConnectionStatus: String, Equatable {
    case disconnected, connecting, connected, disconnecting, unknown

    public init(systemStatus: SCNetworkConnectionStatus) {
        switch systemStatus {
        case .disconnected: self = .disconnected
        case .connecting: self = .connecting
        case .connected: self = .connected
        case .disconnecting: self = .disconnecting
        default: self = .unknown
        }
    }
}

public struct VPNServiceStatus: Equatable, Identifiable {
    public let id: String
    public let name: String
    public let status: VPNConnectionStatus
}

/// This is a view of services exposed by SystemConfiguration, not an inventory
/// of VPNs controlled by other apps or network extensions.
public struct VPNStatusSnapshot: Equatable {
    public let services: [VPNServiceStatus]
    public let querySucceeded: Bool
    public let appManagedVPNsMayBeMissing = true
}

public enum VPNActionResult: Equatable {
    /// The system accepted the asynchronous request; refresh to observe state.
    case requested
    case serviceUnavailable
    case failed(errorCode: Int32)
}

public final class VPNStatusProvider {
    public init() {}

    /// URL for the user to open; constructing it does not open Settings.
    public static let settingsURL = URL(string: "x-apple.systempreferences:com.apple.Network-Settings.extension?VPN")!

    public func refresh() -> VPNStatusSnapshot {
        guard let preferences = SCPreferencesCreate(nil, "VPN Status" as CFString, nil),
              let services = SCNetworkServiceCopyAll(preferences) as? [SCNetworkService] else {
            return VPNStatusSnapshot(services: [], querySucceeded: false)
        }
        let entries = services.compactMap { service -> VPNServiceStatus? in
            guard let interface = SCNetworkServiceGetInterface(service), Self.isVPN(interface),
                  let identifier = SCNetworkServiceGetServiceID(service) as String?,
                  let name = SCNetworkServiceGetName(service) as String? else { return nil }
            let connection = SCNetworkConnectionCreateWithServiceID(nil, identifier as CFString, nil, nil)
            let status = connection.map { VPNConnectionStatus(systemStatus: SCNetworkConnectionGetStatus($0)) } ?? .unknown
            return VPNServiceStatus(id: identifier, name: name, status: status)
        }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
        return VPNStatusSnapshot(services: entries, querySucceeded: true)
    }

    /// Requests are asynchronous and can fail or remain arbitrated by macOS.
    /// The caller must explicitly invoke these methods; refresh has no side effects.
    public func connect(serviceID: String) -> VPNActionResult {
        perform(serviceID: serviceID, connect: true)
    }

    public func disconnect(serviceID: String) -> VPNActionResult {
        perform(serviceID: serviceID, connect: false)
    }

    private func perform(serviceID: String, connect: Bool) -> VPNActionResult {
        let snapshot = refresh()
        guard snapshot.querySucceeded, snapshot.services.contains(where: { $0.id == serviceID }),
              let connection = SCNetworkConnectionCreateWithServiceID(nil, serviceID as CFString, nil, nil) else {
            return .serviceUnavailable
        }
        let accepted = connect ? SCNetworkConnectionStart(connection, nil, true) : SCNetworkConnectionStop(connection, true)
        return accepted ? .requested : .failed(errorCode: SCError())
    }

    private static func isVPN(_ interface: SCNetworkInterface) -> Bool {
        var current: SCNetworkInterface? = interface
        while let item = current {
            let type = SCNetworkInterfaceGetInterfaceType(item) as String?
            // L2TP and PPTP may be nested beneath a PPP interface. Avoid
            // treating ordinary PPP modem connections as VPNs.
            if type == "VPN" || type == (kSCNetworkInterfaceTypeIPSec as String) ||
                type == (kSCNetworkInterfaceTypeL2TP as String) || type == "PPTP" {
                return true
            }
            current = SCNetworkInterfaceGetInterface(item)
        }
        return false
    }
}
