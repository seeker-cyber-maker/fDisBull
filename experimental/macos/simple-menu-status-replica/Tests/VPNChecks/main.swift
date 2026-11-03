import Foundation
import SystemConfiguration

precondition(VPNConnectionStatus(systemStatus: .invalid) == .unknown)
precondition(VPNConnectionStatus(systemStatus: .disconnected) == .disconnected)
precondition(VPNConnectionStatus(systemStatus: .connecting) == .connecting)
precondition(VPNConnectionStatus(systemStatus: .connected) == .connected)
precondition(VPNConnectionStatus(systemStatus: .disconnecting) == .disconnecting)
let snapshot = VPNStatusProvider().refresh()
precondition(snapshot.appManagedVPNsMayBeMissing)
precondition(Set(snapshot.services.map(\.id)).count == snapshot.services.count)
precondition(snapshot.services.allSatisfy { !$0.id.isEmpty && !$0.name.isEmpty })
precondition(VPNStatusProvider.settingsURL.scheme == "x-apple.systempreferences")
print("VPN status checks passed (query succeeded: \(snapshot.querySucceeded), services: \(snapshot.services.count))")
