// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "SimpleMenuStatusReplica", defaultLocalization: "en", platforms: [.macOS(.v12)], products: [.executable(name: "StatusReplica", targets: ["StatusReplica"])], targets: [.target(name: "StatusCore"), .executableTarget(name: "StatusReplica", dependencies: ["StatusCore"])])
