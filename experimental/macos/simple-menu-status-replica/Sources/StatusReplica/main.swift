import AppKit
import SwiftUI
import Combine
import UserNotifications
import Darwin
import IOKit.ps
import StatusCore

struct Snapshot {
    var cpu: Double?
    var memoryUsed: UInt64?
    var memoryTotal: UInt64 = ProcessInfo.processInfo.physicalMemory
    var diskFree: Int64?
    var diskTotal: Int64?
    var storage: StorageReading?
    var battery: String = "Not available"
    var network: NetworkMetrics = .unavailable
    var gpu: GPUSnapshot?
    var details: SystemDetails?
    var memoryFraction: Double? { guard let used = memoryUsed, memoryTotal > 0 else { return nil }; return min(1, Double(used) / Double(memoryTotal)) }
}

final class Monitor: ObservableObject {
    @Published var snapshot = Snapshot()
    @Published var shareImage: NSImage?
    @Published var sharePresented = false
    @Published var shareFailed = false
    @Published var page = 0
    @Published var showBattery = true
    @Published var showNetwork = true
    @Published var showStorage = true
    @Published var showGPU = true
    @Published var showDetails = false
    @Published var selectedPreset = "Custom"
    var layoutMenuController: DashboardLayoutMenuController?
    @Published var settingsExpanded = true
    @Published var iconDisplayExpanded = false
    @Published var languageExpanded = false
    @Published var cacheReviewPresented = false
    @Published var storageVolumes = StorageMetrics.availableVolumes()
    @Published var selectedStorageVolumeID = StorageMetrics.startupVolumeID {
        didSet { ReplicaPreferences.defaults.set(selectedStorageVolumeID, forKey: "replica.storageVolumeID") }
    }
    @Published var storageFolderEstimates: [StorageFolderEstimate] = []
    @Published var storageFolderScanInProgress = false
    @Published var storageFolderScanMessage = ""
    private var storageFolderScanToken: StorageFolderScanCancellation?
    private var storageFolderScanGeneration = 0
    var dashboardOpen = false
    @Published var cacheCandidates: [AppCacheCandidate] = []
    @Published var cacheSelected: Set<AppCacheCandidate> = []
    @Published var cacheMessage = ""
    @Published var alertThreshold = 90.0 {
        didSet { persistAlertSettings() }
    }
    @Published var memoryAlertThreshold = 90.0 { didSet { persistAlertSettings() } }
    @Published var storageAlertThreshold = 90.0 { didSet { persistAlertSettings() } }
    @Published var alertHoldDuration = 30 { didSet { persistAlertSettings() } }
    @Published var alertRecoveryEnabled = false { didSet { persistAlertSettings() } }
    @Published var alertOptionsPresented = false
    @Published var alertsEnabled = false {
        didSet { ReplicaPreferences.defaults.set(alertsEnabled, forKey: "replica.alertsEnabled") }
    }
    @Published var alertMessage = "Off"
    private var alertPolicy: AlertPolicy?
    private var restoringAlertSettings = false
    func previewCache() {
        do {
            cacheCandidates = try AppCacheCleanup().preview()
            cacheSelected = Set(cacheCandidates)
            cacheMessage = cacheCandidates.isEmpty ? "No eligible files" : ""
        } catch {
            cacheCandidates = []
            cacheSelected = []
            cacheMessage = "Cache preview unavailable"
        }
    }
    func trashSelected() {
        guard !cacheSelected.isEmpty else { return }
        do { _ = try AppCacheCleanup().moveToTrash(Array(cacheSelected)); previewCache(); cacheMessage = "Selected files moved to Trash." }
        catch { previewCache(); cacheMessage = "Move stopped; refresh and review the remaining files." }
    }
    func enableAlerts() {
        guard alertSettingsAreValid else { alertMessage = "Choose thresholds from 1 to 100% and a valid duration."; return }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { [weak self] granted, _ in
            DispatchQueue.main.async {
                guard let self else { return }
                self.alertsEnabled = granted
                self.alertMessage = granted ? "Alerts enabled" : "Notifications not allowed"
                self.configureAlertPolicy()
            }
        }
    }
    func disableAlerts() { alertsEnabled = false; alertPolicy = nil; alertMessage = "Off" }
    private var alertSettingsAreValid: Bool {
        [alertThreshold, memoryAlertThreshold, storageAlertThreshold].allSatisfy {
            $0.isFinite && (1...100).contains($0)
        } && (0...300).contains(alertHoldDuration)
    }
    private func persistAlertSettings() {
        guard !restoringAlertSettings, alertSettingsAreValid else { return }
        let defaults = ReplicaPreferences.defaults
        defaults.set(alertThreshold, forKey: "replica.cpuAlertThreshold")
        defaults.set(memoryAlertThreshold, forKey: "replica.memoryAlertThreshold")
        defaults.set(storageAlertThreshold, forKey: "replica.storageAlertThreshold")
        defaults.set(alertHoldDuration, forKey: "replica.alertHoldSeconds")
        defaults.set(alertRecoveryEnabled, forKey: "replica.alertRecoveryEnabled")
        if alertsEnabled { configureAlertPolicy() }
    }
    private func configureAlertPolicy() {
        guard alertsEnabled, alertSettingsAreValid else { alertPolicy = nil; return }
        let seconds = TimeInterval(alertHoldDuration)
        alertPolicy = AlertPolicy(rules: [
            .cpu: .init(threshold: alertThreshold, holdDuration: seconds, recoveryNotice: alertRecoveryEnabled),
            .memoryUsage: .init(threshold: memoryAlertThreshold, holdDuration: seconds, recoveryNotice: alertRecoveryEnabled),
            .storage: .init(threshold: storageAlertThreshold, holdDuration: seconds, recoveryNotice: alertRecoveryEnabled)
        ], cooldown: 300)
    }
    private func restoreAlertAuthorization() {
        guard ReplicaPreferences.defaults.bool(forKey: "replica.alertsEnabled") else { return }
        UNUserNotificationCenter.current().getNotificationSettings { [weak self] settings in
            DispatchQueue.main.async {
                guard let self else { return }
                let permitted = settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional
                self.alertsEnabled = permitted
                self.alertMessage = permitted ? "Alerts enabled" : "Notifications not allowed"
                self.configureAlertPolicy()
            }
        }
    }
    @Published var loginStatus: LoginItemStatus = .unknown
    @Published var loginMessage = ""
    func refreshLogin() { loginStatus = LoginItemController().status() }
    func setLogin(_ enabled: Bool) {
        do {
            try LoginItemController().setEnabled(enabled)
            let preferences = ReplicaPreferences()
            preferences.launchAtLogin = enabled
            loginMessage = ""
        }
        catch { loginMessage = error.localizedDescription }
        refreshLogin()
    }
    @Published var publicIP = "Not requested"
    func fetchPublicIPIfNeeded() {
        guard publicIP == "Not requested" else { return }
        fetchPublicIP()
    }
    func fetchPublicIP() {
        guard publicIP != "Looking up via ipify…" else { return }
        publicIP = "Looking up via ipify…"
        PublicIPProvider().fetch { [weak self] result in
            DispatchQueue.main.async {
                switch result { case .success(let address): self?.publicIP = address; case .failure: self?.publicIP = "Lookup unavailable" }
            }
        }
    }
    @Published var vpn: VPNStatusSnapshot?
    @Published var vpnMessage = ""
    private let vpnProvider = VPNStatusProvider()
    func vpnAction(_ service: VPNServiceStatus) {
        let result = service.status == .connected ? vpnProvider.disconnect(serviceID: service.id) : vpnProvider.connect(serviceID: service.id)
        switch result { case .requested: vpnMessage = "Request sent; status may take time to change."; case .serviceUnavailable: vpnMessage = "VPN service unavailable."; case .failed: vpnMessage = "VPN request failed." }
        vpn = vpnProvider.refresh()
    }
    @Published var interfaces: [(String, String)] = []
    @Published var gpuHistory: [Double] = []
    @Published var eCoreHistory: [Double] = []
    @Published var pCoreHistory: [Double] = []
    @Published var showProcesses = false
    @Published var processes: [ProcessCPU] = []
    @Published var caffeineActive = false
    @Published var caffeineDisplay = false {
        didSet { let preferences = ReplicaPreferences(); preferences.caffeinePowerMode = caffeineDisplay ? "systemAndDisplay" : "systemOnly" }
    }
    @Published var caffeineProcessMode = false {
        didSet {
            let preferences = ReplicaPreferences()
            preferences.caffeineStartMode = caffeineProcessMode ? "process" : "manual"
            preferences.caffeineProcessStopMode = caffeineProcessMode ? "lowActivityOrExit" : nil
        }
    }
    @Published var candidates: [ProcessCandidate] = []
    @Published var selectedProcess: ProcessIdentity?
    @Published var processThreshold = 5.0 {
        didSet { if processThreshold.isFinite, processThreshold >= 0 { ReplicaPreferences.defaults.set(processThreshold, forKey: "replica.processCPUThreshold") } }
    }
    @Published var processWatchState: ProcessWatchState?
    @Published var processMessage = ""
    private var processWatch: ProcessWatch?
    private var watchedSampler = ProcessSampler()
    func refreshCandidates() { candidates = watchedSampler.candidates(); if let selectedProcess, !candidates.contains(where: { $0.identity == selectedProcess }) { self.selectedProcess = nil } }
    func sampleWatch() {
        guard caffeine.isActive, let selectedProcess, var watch = processWatch else { return }
        let observed: ProcessWatchObservation
        switch watchedSampler.sampleSelected(selectedProcess) {
        case .sample(let time, let cpu): observed = .sample(identity: watch.identity, time: time, cpuPercent: cpu)
        case .unavailable: observed = .unavailable
        case .exited: observed = .exited
        }
        let state = watch.observe(observed)
        processWatch = watch; processWatchState = state
        if case .stopped(let reason) = state {
            caffeine.stop(); caffeineActive = false; processWatch = nil
            processMessage = reason == .lowActivity ? "Stopped: process CPU stayed below the threshold." : "Stopped: process exited."
        }
    }
    @Published var caffeineDuration = 0 {
        didSet { if caffeineDuration >= 0 { ReplicaPreferences.defaults.set(caffeineDuration, forKey: "replica.caffeineDurationMinutes") } }
    }
    @Published var showCaffeineDetails = false
    @Published var additionalOptionsExpanded = false
    @Published var detailPage = ""
    @Published var caffeineError: String?
    @Published var cpuHistory: [Double] = []
    @Published var memoryHistory: [Double] = []
    private let processSampler = ProcessSampler()
    private let caffeine = CaffeineController()
    func toggleCaffeine() {
        if caffeine.isActive {
            caffeine.stop(); caffeineActive = false; processWatch = nil; processWatchState = nil; processMessage = "Stopped"
        } else {
            do {
                var newWatch: ProcessWatch?
                if caffeineProcessMode {
                    guard let selectedProcess else { caffeineError = "Select a running process first."; return }
                    guard processThreshold.isFinite, processThreshold >= 0 else { caffeineError = "Enter a nonnegative CPU threshold."; return }
                    let identity = WatchedProcessIdentity(pid: selectedProcess.pid, startSeconds: selectedProcess.startSeconds, startMicroseconds: selectedProcess.startMicroseconds)
                    newWatch = try ProcessWatch(identity: identity, threshold: processThreshold)
                }
                try caffeine.start(mode: caffeineDisplay ? .systemAndDisplay : .systemOnly, duration: caffeineDuration == 0 ? nil : TimeInterval(caffeineDuration * 60))
                watchedSampler = ProcessSampler()
                processWatch = newWatch; processWatchState = newWatch?.state; processMessage = ""; caffeineActive = true; caffeineError = nil
            } catch { caffeineError = "Could not start sleep prevention."; caffeineActive = false }
        }
    }
    private var receivedPressure = false
    private var tick = 0
    @Published var memoryMood: MemoryMood = .unknown
    private var pressureSource: DispatchSourceMemoryPressure?
    private var timer: Timer?
    private let networkSampler = NetworkMetricsSampler()
    private let detailsSampler = SystemDetailsSampler()
    private var previousCPU: (UInt32, UInt32)?
    init() {
        restorePreferences()
        restoreAlertAuthorization()
        pressureSource = DispatchSource.makeMemoryPressureSource(eventMask: [.normal, .warning, .critical], queue: .main)
        pressureSource?.setEventHandler { [weak self] in
            guard let self, let event = self.pressureSource?.data else { return }
            self.receivedPressure = true
            if event.contains(.critical) { self.memoryMood = .from(pressure: .critical) }
            else if event.contains(.warning) { self.memoryMood = .from(pressure: .warning) }
            else if event.contains(.normal) { self.memoryMood = .from(pressure: .normal) }
        }
        pressureSource?.resume()
        refresh(); timer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.refresh() }
    }
    var animationFrame: Int { tick }
    func readInterfaces() -> [(String, String)] {
        var head: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&head) == 0 else { return [] }
        defer { freeifaddrs(head) }
        var rows: [(String, String)] = []
        var cursor = head
        while let node = cursor {
            let item = node.pointee; cursor = item.ifa_next
            guard let address = item.ifa_addr, address.pointee.sa_family == UInt8(AF_INET), item.ifa_flags & UInt32(IFF_UP) != 0, item.ifa_flags & UInt32(IFF_LOOPBACK) == 0 else { continue }
            let ip = address.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { String(cString: inet_ntoa($0.pointee.sin_addr)) }
            rows.append((String(cString: item.ifa_name), ip))
        }
        return rows.sorted { $0.0 < $1.0 }
    }
    func refreshStorageVolumes() {
        storageVolumes = StorageMetrics.availableVolumes()
        if !storageVolumes.contains(where: { $0.id == selectedStorageVolumeID }) {
            cancelStorageFolderScan()
            storageFolderEstimates = []
            selectedStorageVolumeID = StorageMetrics.startupVolumeID
        }
    }
    func selectStorageVolume(_ id: String) {
        guard storageVolumes.contains(where: { $0.id == id }) else { return }
        cancelStorageFolderScan()
        storageFolderEstimates = []
        selectedStorageVolumeID = id
        refresh()
    }
    func estimateStorageFolders() {
        guard let volume = storageVolumes.first(where: { $0.id == selectedStorageVolumeID }) else { return }
        cancelStorageFolderScan()
        storageFolderScanGeneration &+= 1
        let generation = storageFolderScanGeneration
        let token = StorageFolderScanCancellation()
        let requests = StorageFolderScanner.requests(for: volume)
        storageFolderScanToken = token
        storageFolderEstimates = []
        storageFolderScanInProgress = true
        storageFolderScanMessage = "Estimating folder sizes…"
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let estimates = StorageFolderScanner.scan(requests: requests, volume: volume, cancellation: token)
            DispatchQueue.main.async {
                guard let self, self.storageFolderScanGeneration == generation,
                      self.selectedStorageVolumeID == volume.id else { return }
                self.storageFolderEstimates = estimates
                self.storageFolderScanInProgress = false
                self.storageFolderScanToken = nil
                self.storageFolderScanMessage = estimates.contains(where: { $0.status == .partial }) ? "Some estimates stopped at the scan limit." : ""
            }
        }
    }
    func cancelStorageFolderScan() {
        storageFolderScanToken?.cancel()
        if storageFolderScanInProgress { storageFolderScanMessage = "Stopping scan…" }
    }
    func applyPreset(_ preset: String) {
        guard ["Simple", "Developer", "Battery", "Custom", "Local AI"].contains(preset) else { return }
        showGPU = preset != "Battery"
        showStorage = preset != "Simple"
        showBattery = preset == "Battery" || preset == "Custom"
        showNetwork = preset != "Simple" && preset != "Local AI"
        showProcesses = preset == "Developer"
        showDetails = preset == "Developer"
        selectedPreset = preset
        persistDisplayPreferences()
        if dashboardOpen && showNetwork { fetchPublicIPIfNeeded() }
    }
    func persistDisplayPreferences() {
        let defaults = ReplicaPreferences.defaults
        defaults.set(selectedPreset, forKey: "replica.dashboardLayout")
        defaults.set(showGPU, forKey: "replica.showGPU")
        defaults.set(showStorage, forKey: "replica.showStorage")
        defaults.set(showBattery, forKey: "replica.showBattery")
        defaults.set(showNetwork, forKey: "replica.showNetwork")
        defaults.set(showProcesses, forKey: "replica.showProcesses")
        defaults.set(showDetails, forKey: "replica.showDetails")
    }
    var desiredPopoverHeight: CGFloat {
        if selectedPreset == "Local AI" {
            let visibleHeight = NSScreen.main?.visibleFrame.height ?? 840
            return min(820, max(390, visibleHeight - 20))
        }
        var height: CGFloat = 720
        if !showGPU { height -= 94 }
        if !showStorage { height -= 63 }
        if !showNetwork { height -= 166 }
        if showDetails { height += 90 }
        if showProcesses { height += 100 }
        if showBattery && snapshot.details?.battery.isPresent == true { height += 65 }
        let visibleHeight = NSScreen.main?.visibleFrame.height ?? 840
        return min(max(390, visibleHeight - 20), max(390, height))
    }
    private func restorePreferences() {
        restoringAlertSettings = true
        defer { restoringAlertSettings = false }
        let defaults = ReplicaPreferences.defaults
        if let value = defaults.object(forKey: "replica.showGPU") as? Bool { showGPU = value }
        if let value = defaults.object(forKey: "replica.showStorage") as? Bool { showStorage = value }
        if let value = defaults.object(forKey: "replica.showBattery") as? Bool { showBattery = value }
        if let value = defaults.object(forKey: "replica.showNetwork") as? Bool { showNetwork = value }
        if let value = defaults.object(forKey: "replica.showProcesses") as? Bool { showProcesses = value }
        if let value = defaults.object(forKey: "replica.showDetails") as? Bool { showDetails = value }
        if let value = defaults.string(forKey: "replica.dashboardLayout"), ["Simple", "Developer", "Battery", "Custom", "Local AI"].contains(value) { selectedPreset = value }
        if let value = defaults.string(forKey: "replica.storageVolumeID") { selectedStorageVolumeID = value }
        if let value = defaults.string(forKey: "caffeinePowerMode") { caffeineDisplay = value == "systemAndDisplay" }
        if let value = defaults.string(forKey: "caffeineStartMode") { caffeineProcessMode = value == "process" }
        if let value = defaults.object(forKey: "replica.caffeineDurationMinutes") as? Int, [0, 30, 60, 120].contains(value) { caffeineDuration = value }
        if let value = defaults.object(forKey: "replica.processCPUThreshold") as? Double, value.isFinite, value >= 0 { processThreshold = value }
        if let value = defaults.object(forKey: "replica.cpuAlertThreshold") as? Double, value.isFinite, (1...100).contains(value) { alertThreshold = value }
        if let value = defaults.object(forKey: "replica.memoryAlertThreshold") as? Double, value.isFinite, (1...100).contains(value) { memoryAlertThreshold = value }
        if let value = defaults.object(forKey: "replica.storageAlertThreshold") as? Double, value.isFinite, (1...100).contains(value) { storageAlertThreshold = value }
        if let value = defaults.object(forKey: "replica.alertHoldSeconds") as? Int, (0...300).contains(value) { alertHoldDuration = value }
        if let value = defaults.object(forKey: "replica.alertRecoveryEnabled") as? Bool { alertRecoveryEnabled = value }
        persistDisplayPreferences()
    }
    func refresh() {
        tick += 1
        var next = Snapshot()
        var vm = vm_statistics64_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<vm_statistics64_data_t>.size / MemoryLayout<integer_t>.size)
        let status = withUnsafeMutablePointer(to: &vm) { $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { host_statistics64(mach_host_self(), HOST_VM_INFO64, $0, &count) } }
        if status == KERN_SUCCESS {
            var pageSize: vm_size_t = 0
            let validPage = host_page_size(mach_host_self(), &pageSize) == KERN_SUCCESS && pageSize > 0
            let pages = UInt64(vm.active_count) + UInt64(vm.wire_count) + UInt64(vm.compressor_page_count)
            if validPage { next.memoryUsed = min(next.memoryTotal, pages * UInt64(pageSize)) }
            if !receivedPressure && validPage {
                let page = UInt64(pageSize)
                // Inactive includes purgeable pages, so avoid counting those twice.
                memoryMood = .estimated(total: next.memoryTotal, free: UInt64(vm.free_count) * page, inactive: UInt64(vm.inactive_count) * page, purgeable: 0)
            }
        }
        var cpu = host_cpu_load_info_data_t()
        var cpuCount = mach_msg_type_number_t(MemoryLayout<host_cpu_load_info_data_t>.size / MemoryLayout<integer_t>.size)
        let cpuStatus = withUnsafeMutablePointer(to: &cpu) { $0.withMemoryRebound(to: integer_t.self, capacity: Int(cpuCount)) { host_statistics(mach_host_self(), HOST_CPU_LOAD_INFO, $0, &cpuCount) } }
        if cpuStatus == KERN_SUCCESS {
            let ticks = cpu.cpu_ticks
            let idle = ticks.2
            let total = ticks.0 &+ ticks.1 &+ ticks.2 &+ ticks.3
            if let previousCPU {
                let all = total &- previousCPU.0, idleDelta = idle &- previousCPU.1
                if all > 0 { next.cpu = max(0, min(1, 1 - Double(idleDelta) / Double(all))) }
            }
            previousCPU = (total, idle)
        }
        if let volume = storageVolumes.first(where: { $0.id == selectedStorageVolumeID }),
           let reading = StorageMetrics.sample(volume) {
            next.storage = reading
            next.diskTotal = reading.totalBytes
            next.diskFree = reading.availableBytes
        } else {
            refreshStorageVolumes()
            if let startup = storageVolumes.first(where: { $0.id == StorageMetrics.startupVolumeID }),
               let reading = StorageMetrics.sample(startup) {
                next.storage = reading
                next.diskTotal = reading.totalBytes
                next.diskFree = reading.availableBytes
            }
        }
        if (next.diskFree == nil || next.diskTotal == nil), let reading = next.storage,
           let attrs = try? FileManager.default.attributesOfFileSystem(forPath: reading.volume.mountPath) {
            next.diskFree = next.diskFree ?? (attrs[.systemFreeSize] as? NSNumber)?.int64Value
            next.diskTotal = next.diskTotal ?? (attrs[.systemSize] as? NSNumber)?.int64Value
        }
        if let info = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(), let sources = IOPSCopyPowerSourcesList(info)?.takeRetainedValue() as? [CFTypeRef] {
            for source in sources {
                guard let dict = IOPSGetPowerSourceDescription(info, source)?.takeUnretainedValue() as? [String: Any],
                      let current = dict[kIOPSCurrentCapacityKey] as? Int, let max = dict[kIOPSMaxCapacityKey] as? Int, max > 0 else { continue }
                let state = dict[kIOPSPowerSourceStateKey] as? String ?? ""
                next.battery = "\(current * 100 / max)% · \(state)"
                break
            }
        }
        next.details = detailsSampler.sample()
        next.network = networkSampler.sample()
        if dashboardOpen { next.gpu = GPUMetrics.sample(); interfaces = readInterfaces(); vpn = vpnProvider.refresh() }
        if let gpu = next.gpu?.utilizationPercent { gpuHistory = Array((gpuHistory + [gpu / 100]).suffix(30)) }
        if let usage = next.details?.eCorePercentage { eCoreHistory = Array((eCoreHistory + [usage / 100]).suffix(30)) }
        if let usage = next.details?.pCorePercentage { pCoreHistory = Array((pCoreHistory + [usage / 100]).suffix(30)) }
        if dashboardOpen && showProcesses { processes = processSampler.sample(limit: 5) }
        if !caffeine.isActive && processWatch != nil { processWatch = nil; processWatchState = nil; processMessage = "Stopped: duration expired." }
        caffeineActive = caffeine.isActive
        if caffeineActive && processWatch != nil { sampleWatch() }
        if let cpu = next.cpu { cpuHistory = Array((cpuHistory + [cpu]).suffix(30)) }
        if let memory = next.memoryFraction { memoryHistory = Array((memoryHistory + [memory]).suffix(30)) }
        sampleAlerts(next)
        snapshot = next
    }
    private func sampleAlerts(_ snapshot: Snapshot) {
        guard alertsEnabled else { return }
        let readings = AlertReadings(cpuFraction: snapshot.cpu, memoryUsed: snapshot.memoryUsed,
                                     memoryTotal: snapshot.memoryTotal, storageAvailable: snapshot.diskFree,
                                     storageTotal: snapshot.diskTotal)
        let samples: [(AlertPolicy.Metric, Double?)] = [
            (.cpu, readings.cpuPercent), (.memoryUsage, readings.memoryPercent),
            (.storage, readings.storagePercent)
        ]
        let now = Date()
        for (metric, value) in samples {
            if let event = alertPolicy?.sample(metric, value: value, at: now) {
                postAlert(event, observedPercent: value)
            }
        }
    }
    private func postAlert(_ event: AlertPolicy.Event, observedPercent: Double?) {
        let metric: AlertPolicy.Metric
        let recovered: Bool
        switch event {
        case .triggered(let value): metric = value; recovered = false
        case .recovered(let value): metric = value; recovered = true
        }
        let name: String
        let threshold: Double
        switch metric {
        case .cpu: name = "CPU usage"; threshold = alertThreshold
        case .memoryUsage: name = "Memory usage"; threshold = memoryAlertThreshold
        case .storage: name = "Storage usage"; threshold = storageAlertThreshold
        }
        let content = UNMutableNotificationContent()
        content.title = recovered ? "\(name) recovered" : "\(name) alert"
        if recovered {
            content.body = String(format: "%@ is below the configured %.0f%% threshold.", name, threshold)
        } else {
            let hold = alertHoldDuration == 0 ? "" : " for \(alertHoldDuration) seconds"
            content.body = String(format: "%@ reached %.0f%% (threshold %.0f%%)%@.",
                                  name, observedPercent ?? threshold, threshold, hold)
        }
        UNUserNotificationCenter.current().add(UNNotificationRequest(
            identifier: UUID().uuidString, content: content, trigger: nil))
    }
}

/// AppKit keeps both levels of this menu on screen. SwiftUI's nested Menu could
/// place the layout submenu beyond the left edge when the status item was near it.
final class DashboardLayoutMenuController: NSObject {
    private let monitor: Monitor

    init(monitor: Monitor) { self.monitor = monitor }

    func show() {
        let menu = NSMenu()
        menu.autoenablesItems = false
        let language = ReplicaPreferences.defaults.string(forKey: "language") ?? "System Default"
        let layout = NSMenu()
        for name in ["Simple", "Developer", "Battery", "Local AI", "Custom"] {
            let item = NSMenuItem(title: ReplicaLocalization.text(name, choice: language),
                                  action: #selector(selectLayout(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = name
            item.state = monitor.selectedPreset == name ? .on : .off
            layout.addItem(item)
        }
        let layoutItem = NSMenuItem(title: ReplicaLocalization.text("Dashboard layout", choice: language),
                                    action: nil, keyEquivalent: "")
        layoutItem.submenu = layout
        menu.addItem(layoutItem)
        menu.addItem(.separator())
        for (name, enabled) in [
            ("GPU", monitor.showGPU), ("Storage", monitor.showStorage),
            ("Battery", monitor.showBattery), ("Network", monitor.showNetwork),
            ("Processes", monitor.showProcesses), ("CPU and memory details", monitor.showDetails)
        ] {
            let item = NSMenuItem(title: ReplicaLocalization.text(name, choice: language),
                                  action: #selector(toggleOption(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = name
            item.state = enabled ? .on : .off
            menu.addItem(item)
        }
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first(where: { $0.frame.contains(mouse) }) ?? NSScreen.main
        let visible = screen?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1024, height: 768)
        // Reserve room to the right for the layout submenu, including its shadow.
        let widthForBothMenus: CGFloat = 390
        let x = max(visible.minX + 8, min(mouse.x - 12, visible.maxX - widthForBothMenus))
        menu.popUp(positioning: nil, at: NSPoint(x: x, y: mouse.y - 8), in: nil)
    }

    @objc private func selectLayout(_ sender: NSMenuItem) {
        guard let name = sender.representedObject as? String else { return }
        monitor.applyPreset(name)
    }

    @objc private func toggleOption(_ sender: NSMenuItem) {
        guard let name = sender.representedObject as? String else { return }
        switch name {
        case "GPU": monitor.showGPU.toggle()
        case "Storage": monitor.showStorage.toggle()
        case "Battery": monitor.showBattery.toggle()
        case "Network": monitor.showNetwork.toggle()
        case "Processes": monitor.showProcesses.toggle()
        case "CPU and memory details": monitor.showDetails.toggle()
        default: return
        }
        monitor.selectedPreset = "Custom"
        monitor.persistDisplayPreferences()
        if monitor.dashboardOpen && monitor.showNetwork { monitor.fetchPublicIPIfNeeded() }
    }
}

struct Dashboard: View {
    @ObservedObject var monitor: Monitor
    @AppStorage(ReplicaPreferences.iconKey, store: ReplicaPreferences.defaults) var iconChoice = ReplicaPreferences.defaultIcon
    @AppStorage("language", store: ReplicaPreferences.defaults) private var languageChoice = "System Default"
    private func tr(_ english: String) -> String { ReplicaLocalization.text(english, choice: languageChoice) }
    private func percent(_ n: Double?) -> String { n.map { String(format: "%.1f%%", $0 * 100) } ?? "—" }
    private func headlineMemory(_ n: UInt64?) -> String { n.map { String(format: "%.1f GB", Double($0) / 1_073_741_824) } ?? "—" }
    private func headlineMemoryTotal(_ n: UInt64) -> String {
        let gib = Double(n) / 1_073_741_824
        return abs(gib - gib.rounded()) < 0.01 ? String(format: "%.0f GB", gib) : String(format: "%.1f GB", gib)
    }
    private func bytes(_ n: UInt64?) -> String { n.map { ByteCountFormatter.string(fromByteCount: Int64(clamping: $0), countStyle: .memory) } ?? "—" }
    var body: some View {
        ScrollView(.vertical, showsIndicators: false) { VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(hardwareModel()).fontWeight(.bold)
                    Text("Simple Menu STATUS")
                }.font(.system(size: 12))
                Spacer()
                Button {
                    let controller = DashboardLayoutMenuController(monitor: monitor)
                    monitor.layoutMenuController = controller
                    controller.show()
                } label: { Image(systemName: "slider.horizontal.3") }.frame(width: 28).help("Dashboard layout")
                Button(action: share) { Image(systemName: "square.and.arrow.up") }
                    .help("Share system status")
                    .popover(isPresented: $monitor.sharePresented, arrowEdge: .trailing) {
                        if let shareImage = monitor.shareImage {
                            SharePreview(image: shareImage, languageChoice: languageChoice) {
                                monitor.sharePresented = false
                            }
                        }
                    }
                    .alert("Could not prepare image", isPresented: $monitor.shareFailed) {
                        Button("OK", role: .cancel) { }
                    }
                Button(action: { monitor.refreshLogin(); monitor.page = monitor.page == 2 ? 0 : 2 }) { Image(systemName: "gearshape") }.help("Settings")
                    .popover(isPresented: Binding(get: { monitor.page == 2 }, set: { monitor.page = $0 ? 2 : 0 }), arrowEdge: .trailing) { settings }
            }.buttonStyle(.plain).padding(12).background {
                RoundedRectangle(cornerRadius: 11)
                    .fill(LinearGradient(colors: [Color.primary.opacity(0.14), Color.primary.opacity(0.07)], startPoint: .top, endPoint: .bottom))
                    .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Color.primary.opacity(0.12), lineWidth: 1))
                    .shadow(color: .black.opacity(0.20), radius: 3, y: 2)
            }.padding(8)
            HStack { Image(systemName: "checkmark.circle"); Text(tr(health.label)); Spacer() }.font(.system(size: 12, weight: .semibold)).padding(12).background(RoundedRectangle(cornerRadius: 10).fill(Color.primary.opacity(0.05))).padding(.horizontal, 10).padding(.bottom, 4)
            if monitor.selectedPreset == "Local AI" {
                LocalAIView(gpu: monitor.snapshot.gpu, details: monitor.snapshot.details,
                            eCoreHistory: monitor.eCoreHistory, pCoreHistory: monitor.pCoreHistory,
                            gpuHistory: monitor.gpuHistory)
            } else {
                metric("cpu", "CPU Usage", String(format: tr("Average: %@"), percent(monitor.snapshot.cpu)), monitor.snapshot.cpu, monitor.cpuHistory, usageColor(monitor.snapshot.cpu), "cpu")
                if monitor.showGPU { metric("rectangle.3.group", "GPU Usage", monitor.snapshot.gpu?.utilizationPercent.map { String(format: tr("Usage: %@"), String(format: "%.1f%%", $0)) } ?? tr("Unavailable"), monitor.snapshot.gpu?.utilizationPercent.map { $0 / 100 }, monitor.gpuHistory, .green, "gpu") }
                metric("memorychip", "Memory Usage", "\(headlineMemory(monitor.snapshot.memoryUsed)) / \(headlineMemoryTotal(monitor.snapshot.memoryTotal))", monitor.snapshot.memoryFraction, monitor.memoryHistory, .orange, "memory")
            }
            if monitor.showDetails, let details = monitor.snapshot.details {
                section("info.circle", "System Details") {
                    Text("CPU cores: " + details.cpuPercentages.enumerated().map { "\($0.offset):" + ($0.element.map { "\(Int($0.rounded()))%" } ?? "—") }.joined(separator: "  ")).font(.system(size: 10)).monospacedDigit().fixedSize(horizontal: false, vertical: true)
                    Text("App \(bytes(details.memory.appBytes)) · Wired \(bytes(details.memory.wiredBytes)) · Compressed \(bytes(details.memory.compressedBytes))").font(.system(size: 10)).fixedSize(horizontal: false, vertical: true)
                    Text("Cached \(bytes(details.memory.cachedBytes)) · Swap \(bytes(details.memory.swapUsedBytes))").font(.system(size: 10))
                    if details.battery.isPresent {
                        Text("Battery cycles: \(details.battery.cycleCount.map(String.init) ?? "—") · Health: \(details.battery.healthPercentage.map { "\(Int($0.rounded()))%" } ?? "—")").font(.system(size: 10))
                    }
                }
            }
            if monitor.showStorage { storageSection }
            if monitor.showBattery && monitor.snapshot.details?.battery.isPresent == true { section("battery.100", "Battery") { Text(monitor.snapshot.battery).font(.system(size: 11)) } }
            if monitor.showNetwork { section("network", "Network Info") {
                VStack(spacing: 6) {
                ForEach(monitor.interfaces, id: \.0) { row in
                    HStack { Image(systemName: "antenna.radiowaves.left.and.right").frame(width: 14).foregroundColor(.secondary); Text("\(row.0): \(row.1)").font(.system(size: 11, weight: .medium)).monospacedDigit(); Spacer(); Button(action: { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(row.1, forType: .string) }) { Image(systemName: "doc.on.doc") }.buttonStyle(.plain).help("Copy address") }.frame(height: 23)
                }
                HStack {
                    Image(systemName: "globe").frame(width: 14).foregroundColor(.green)
                    Text("\(tr("Global")): \(tr(monitor.publicIP))").font(.system(size: 11, weight: .medium)).monospacedDigit().lineLimit(1)
                    Spacer()
                    Button(action: { monitor.fetchPublicIP() }) { Image(systemName: "arrow.clockwise") }
                        .buttonStyle(.plain).help("Refresh public IP using ipify")
                    if monitor.publicIP != "Not requested" && monitor.publicIP != "Looking up via ipify…" && monitor.publicIP != "Lookup unavailable" {
                        Button(action: { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(monitor.publicIP, forType: .string) }) { Image(systemName: "doc.on.doc") }.buttonStyle(.plain).help("Copy public IP")
                    }
                }.frame(height: 23)
                }
            } }
            if monitor.showNetwork && monitor.showDetails { section("network", "Network Details") {
                Text(networkDescription).font(.system(size: 10)).monospacedDigit().lineLimit(2)
                Text("Public IP lookup contacts api.ipify.org; the service receives your public IP.").font(.caption2).foregroundColor(.secondary)
                if let vpn = monitor.vpn {
                    if !vpn.querySucceeded { Text("VPN status unavailable").foregroundColor(.secondary) }
                    else if vpn.services.isEmpty { Text("No system VPN services listed").foregroundColor(.secondary) }
                    ForEach(vpn.services) { service in
                        HStack {
                            Text("\(service.name): \(service.status.rawValue)"); Spacer()
                            if service.status == .connected || service.status == .disconnected { Button(service.status == .connected ? "Disconnect" : "Connect") { monitor.vpnAction(service) } }
                        }
                    }
                    Text("App-managed VPNs may be missing.").font(.caption2).foregroundColor(.secondary)
                    if !monitor.vpnMessage.isEmpty { Text(monitor.vpnMessage).font(.caption2) }
                    Button("VPN Settings…") { NSWorkspace.shared.open(VPNStatusProvider.settingsURL) }
                }
            } }
            if monitor.showProcesses {
                section("list.bullet", "Processes") {
                    if monitor.processes.isEmpty { Text("Waiting for process samples…").font(.caption) }
                    ForEach(monitor.processes, id: \.pid) { process in HStack { Text(process.name).lineLimit(1); Spacer(); Text(String(format: "%.1f%%", process.cpuPercent)) }.font(.system(size: 11)).monospacedDigit() }
                }
            }
            VStack(alignment: .leading, spacing: 5) {
                HStack { Image(systemName: "cup.and.saucer"); Text("Prevent Sleep").font(.system(size: 12, weight: .semibold)); Spacer(); Button { monitor.toggleCaffeine() } label: { Text(LocalizedStringKey(monitor.caffeineActive ? "Stop" : "Start")) }; Button("Details") { if !monitor.showCaffeineDetails { monitor.refreshCandidates(); monitor.additionalOptionsExpanded = false }; monitor.showCaffeineDetails.toggle() }.popover(isPresented: $monitor.showCaffeineDetails, arrowEdge: .trailing) { caffeineDetails } }
                Text(LocalizedStringKey(monitor.caffeineDisplay ? "System + Display" : "System only")).foregroundColor(monitor.caffeineActive ? .primary : .secondary)
                Text(monitor.caffeineActive ? (monitor.caffeineDuration == 0 ? tr("Until stopped") : (ReplicaLocalization.languageCode(languageChoice) == "ja" ? "\(monitor.caffeineDuration)分" : "\(monitor.caffeineDuration) minutes")) : tr("Off")).foregroundColor(monitor.caffeineActive ? .primary : .secondary)
                if let error = monitor.caffeineError { Text(error).foregroundColor(.red) }
            }.font(.system(size: 11)).frame(minHeight: 62, alignment: .topLeading).padding(10).background(RoundedRectangle(cornerRadius: 10).fill(Color.primary.opacity(0.07))).padding(8)
        }.frame(width: 280) }.frame(maxHeight: monitor.desiredPopoverHeight)
            .environment(\.locale, ReplicaLocalization.locale(languageChoice))
    }
    private var settings: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                Button { monitor.settingsExpanded.toggle() } label: {
                    HStack {
                        Image(systemName: "gearshape").frame(width: 15)
                        Text("Settings").fontWeight(.semibold)
                        Spacer()
                        Image(systemName: monitor.settingsExpanded ? "chevron.up" : "chevron.down")
                    }.frame(height: 24)
                }
                if monitor.settingsExpanded { settingsContent }
            }
            .padding(15)
            .frame(width: 280)
            .frame(minHeight: monitor.settingsExpanded ? 475 : 54, alignment: .topLeading)
        }
        .frame(width: 280)
        .frame(maxHeight: (NSScreen.main?.visibleFrame.height ?? 800) - 80)
        .font(.system(size: 12))
        .buttonStyle(.plain)
        .sheet(isPresented: $monitor.cacheReviewPresented) { cacheReview }
    }
    private var settingsContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            settingsRule
            settingsUptime
            settingsRule
            settingsIconDisplay
            settingsRule
            settingsLanguage
            settingsRule
            settingsLogin
            settingsAlertsAndCache
        }
    }
    private var settingsUptime: some View {
        HStack {
            Image(systemName: "clock.arrow.circlepath").frame(width: 15)
            Text("Uptime")
            Spacer()
            Text(uptime).monospacedDigit()
        }.frame(height: 27)
    }
    private var settingsIconDisplay: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { monitor.iconDisplayExpanded.toggle() } label: {
                HStack {
                    Image(systemName: "rectangle.topthird.inset.filled").frame(width: 15)
                    Text("Icon Display")
                    Spacer()
                    Image(systemName: monitor.iconDisplayExpanded ? "chevron.up" : "chevron.down")
                }.frame(height: 27)
            }
            if monitor.iconDisplayExpanded {
                ForEach(iconChoices.indices, id: \.self) { index in
                    let choice = iconChoices[index]
                    Button { iconChoice = choice.value } label: {
                        HStack(spacing: 6) {
                            Image(systemName: iconChoice == choice.value ? "checkmark" : "").frame(width: 15)
                            Text(LocalizedStringKey(choice.label))
                            Spacer()
                        }.frame(height: 23)
                    }
                }
            }
        }
    }
    private var settingsLanguage: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { monitor.languageExpanded.toggle() } label: {
                HStack {
                    Image(systemName: "globe").frame(width: 15)
                    Text("Language")
                    Spacer()
                    Image(systemName: monitor.languageExpanded ? "chevron.up" : "chevron.down")
                }.frame(height: 27)
            }
            if monitor.languageExpanded {
                ForEach(["System Default", "English", "日本語"], id: \.self) { name in
                    Button { languageChoice = name } label: {
                        HStack(spacing: 6) {
                            Image(systemName: languageChoice == name ? "checkmark" : "").frame(width: 15)
                            Text(LocalizedStringKey(name))
                            Spacer()
                        }.frame(height: 23)
                    }
                }
            }
        }
    }
    private var settingsLogin: some View {
        VStack(alignment: .leading, spacing: 2) {
            Button {
                switch monitor.loginStatus {
                case .enabled: monitor.setLogin(false)
                case .notRegistered: monitor.setLogin(true)
                default: break
                }
            } label: {
                HStack {
                    Image(systemName: "power").frame(width: 15)
                    Text("Launch at Login")
                    Spacer()
                    Image(systemName: monitor.loginStatus == .enabled ? "checkmark.circle.fill" : "circle")
                        .foregroundColor(monitor.loginStatus == .enabled ? .accentColor : .secondary)
                }.frame(height: 27)
            }.disabled(monitor.loginStatus != .enabled && monitor.loginStatus != .notRegistered)
            if !monitor.loginMessage.isEmpty { Text(monitor.loginMessage).font(.caption2).foregroundColor(.secondary) }
            if case .unsupported(let reason) = monitor.loginStatus { Text(reason).font(.caption2).foregroundColor(.secondary) }
        }
    }
    private var settingsAlertsAndCache: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Spacer()
                Toggle("Enable Alerts", isOn: Binding(
                    get: { monitor.alertsEnabled },
                    set: { $0 ? monitor.enableAlerts() : monitor.disableAlerts() }
                )).toggleStyle(.checkbox)
                Spacer()
            }.padding(.top, 38).padding(.bottom, monitor.alertsEnabled ? 10 : 40)
            if monitor.alertsEnabled {
                HStack {
                    Spacer()
                    Button("Alert options…") { monitor.alertOptionsPresented.toggle() }
                    Spacer()
                }.padding(.bottom, 18)
                if monitor.alertOptionsPresented { alertOptions.padding(.bottom, 18) }
            } else if monitor.alertMessage == "Notifications not allowed" {
                Text(tr(monitor.alertMessage)).font(.caption2).foregroundColor(.secondary)
                    .frame(maxWidth: .infinity).padding(.bottom, 12)
            }
            Text("Cache Cleanup").fontWeight(.semibold)
            Text("Only this app’s cache files older than seven days. Other apps, logs, and temporary files are excluded.")
                .fixedSize(horizontal: false, vertical: true).padding(.top, 8)
            Button("Review cache files…") {
                monitor.previewCache()
                monitor.cacheReviewPresented = true
            }.buttonStyle(.bordered).padding(.top, 12)
            Spacer(minLength: 96)
        }
    }
    private var alertOptions: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Alert thresholds").font(.headline)
            Stepper(value: $monitor.alertThreshold, in: 1...100, step: 1) {
                HStack { Text("CPU"); Spacer(); Text("\(Int(monitor.alertThreshold))%") }
            }
            Stepper(value: $monitor.memoryAlertThreshold, in: 1...100, step: 1) {
                HStack { Text("Memory"); Spacer(); Text("\(Int(monitor.memoryAlertThreshold))%") }
            }
            Stepper(value: $monitor.storageAlertThreshold, in: 1...100, step: 1) {
                HStack { Text("Storage"); Spacer(); Text("\(Int(monitor.storageAlertThreshold))%") }
            }
            Picker("Sustained for", selection: $monitor.alertHoldDuration) {
                Text("Immediately").tag(0)
                Text("10 seconds").tag(10)
                Text("30 seconds").tag(30)
                Text("1 minute").tag(60)
                Text("2 minutes").tag(120)
            }
            Toggle("Notify on recovery", isOn: $monitor.alertRecoveryEnabled)
                .toggleStyle(.checkbox)
            Text("Each alert repeats no more than once every five minutes.")
                .font(.caption2).foregroundColor(.secondary)
            HStack { Spacer(); Button("Done") { monitor.alertOptionsPresented = false } }
        }.padding(10).frame(maxWidth: .infinity)
            .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.05)))
    }
    private var settingsRule: some View { Divider().padding(.vertical, 3) }
    private var iconChoices: [(label: String, value: String)] {
        [
            ("CPU & Memory", "CPU & Memory"), ("CPU & Battery", "CPU & Battery"),
            ("CPU Emoji", "CPU Emoji"), ("Memory Emoji", "Memory emoji"),
            ("CPU Graph", ReplicaPreferences.cpuGraphIcon),
            ("CPU Graph + Memory Emoji", ReplicaPreferences.cpuGraphMemoryIcon),
            ("Animated Pulse", "Animated Pulse"), ("Animated Dots", "Animated Dots"),
            ("Car Animation", "Car Animation")
        ]
    }
    private var cacheReview: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Confirm files to move to Trash").font(.headline)
            Text("Only this app’s cache files older than seven days are eligible.")
                .font(.caption).foregroundColor(.secondary)
            if monitor.cacheCandidates.isEmpty {
                Text(tr(monitor.cacheMessage)).foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(monitor.cacheCandidates, id: \.self) { candidate in
                            Toggle(isOn: Binding(
                                get: { monitor.cacheSelected.contains(candidate) },
                                set: { selected in
                                    if selected { monitor.cacheSelected.insert(candidate) }
                                    else { monitor.cacheSelected.remove(candidate) }
                                }
                            )) {
                                VStack(alignment: .leading) {
                                    Text(candidate.url.lastPathComponent)
                                    Text(candidate.url.path).font(.caption2).foregroundColor(.secondary).lineLimit(1)
                                }
                                Spacer()
                                Text(ByteCountFormatter.string(fromByteCount: Int64(clamping: candidate.size), countStyle: .file))
                                    .font(.caption).foregroundColor(.secondary)
                            }.toggleStyle(.checkbox)
                        }
                    }
                }
            }
            if !monitor.cacheMessage.isEmpty && !monitor.cacheCandidates.isEmpty {
                Text(tr(monitor.cacheMessage)).font(.caption).foregroundColor(.secondary)
            }
            HStack {
                Spacer()
                Button("Cancel") { monitor.cacheReviewPresented = false }
                Button("Move selected files to Trash") {
                    monitor.trashSelected()
                    if monitor.cacheMessage == "Selected files moved to Trash." { monitor.cacheReviewPresented = false }
                }.disabled(monitor.cacheSelected.isEmpty)
            }
        }
        .padding(20).frame(width: 500, height: 310)
    }
    private var storageSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 4) {
                Label("Storage", systemImage: "internaldrive").font(.system(size: 12, weight: .semibold))
                Spacer(minLength: 4)
                Menu {
                    ForEach(monitor.storageVolumes) { volume in
                        Toggle(volume.displayName, isOn: Binding(
                            get: { monitor.selectedStorageVolumeID == volume.id },
                            set: { selected in if selected { monitor.selectStorageVolume(volume.id) } }
                        ))
                    }
                } label: {
                    HStack(spacing: 3) {
                        Text(monitor.snapshot.storage?.volume.displayName ?? tr("Choose volume")).lineLimit(1)
                        Image(systemName: "chevron.down").font(.system(size: 8))
                    }.font(.system(size: 10)).foregroundColor(.secondary)
                }.menuStyle(.borderlessButton).frame(maxWidth: 155, alignment: .trailing)
            }
            HStack {
                Text(storage).font(.system(size: 11, weight: .semibold)).monospacedDigit()
                Spacer()
                Text(storagePercent).font(.system(size: 11, weight: .semibold)).monospacedDigit().foregroundColor(.orange)
                detailButton("storage")
            }
        }.frame(maxWidth: .infinity, alignment: .leading).padding(12).overlay(alignment: .bottom) { Divider() }
    }
    private func section<Content: View>(_ icon: String, _ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label { Text(LocalizedStringKey(title)) } icon: { Image(systemName: icon) }
                .font(.system(size: 12, weight: .semibold))
            content()
        }.font(.system(size: 11)).frame(maxWidth: .infinity, alignment: .leading).padding(12).overlay(alignment: .bottom) { Divider() }
    }
    private func metric(_ icon: String, _ title: String, _ value: String, _ fraction: Double?, _ history: [Double], _ color: Color, _ page: String) -> some View {
        section(icon, title) {
            HStack { Image(systemName: page == "cpu" ? "info.circle" : "chart.bar.fill"); Text(value).font(.system(size: 11, weight: .semibold)).monospacedDigit(); Spacer(); ProgressView(value: fraction ?? 0).tint(color).frame(width: 60); detailButton(page) }
            GeometryReader { geometry in
                let points = history.enumerated().map { index, point in
                    CGPoint(x: history.count < 2 ? 0 : geometry.size.width * CGFloat(index) / CGFloat(history.count - 1), y: geometry.size.height * (1 - CGFloat(max(0, min(1, point)))))
                }
                ZStack {
                    if points.count > 1 {
                        Path { path in
                            path.move(to: CGPoint(x: points[0].x, y: geometry.size.height))
                            points.forEach { path.addLine(to: $0) }
                            path.addLine(to: CGPoint(x: points[points.count - 1].x, y: geometry.size.height))
                            path.closeSubpath()
                        }.fill(LinearGradient(colors: [color.opacity(0.27), color.opacity(0.015)], startPoint: .top, endPoint: .bottom))
                        Path { path in
                            path.move(to: points[0]); points.dropFirst().forEach { path.addLine(to: $0) }
                        }.stroke(color, lineWidth: 1)
                    }
                }
            }.frame(height: 20)
        }
    }
    private var health: IndicatorHealth.Status {
        let free = monitor.snapshot.diskFree.flatMap { $0 >= 0 ? UInt64($0) : nil }
        let total = monitor.snapshot.diskTotal.flatMap { $0 >= 0 ? UInt64($0) : nil }
        return IndicatorHealth.evaluate(cpu: monitor.snapshot.cpu, gpu: monitor.snapshot.gpu?.utilizationPercent.map { $0 / 100 }, memory: monitor.memoryMood, storageAvailable: free, storageTotal: total)
    }
    private func usageColor(_ fraction: Double?) -> Color {
        guard let fraction, fraction.isFinite else { return .secondary }
        return fraction >= 0.80 ? .red : (fraction >= 0.50 ? .orange : .green)
    }
    private func detailButton(_ page: String) -> some View {
        Button(action: { monitor.detailPage = page }) { Image(systemName: "chevron.right") }.buttonStyle(.plain)
            .help("Show details")
            .popover(isPresented: Binding(get: { monitor.detailPage == page }, set: { if !$0 && monitor.detailPage == page { monitor.detailPage = "" } }), arrowEdge: .trailing) { detailView(page) }
    }
    private func detailRow(_ name: String, _ value: String) -> some View {
        HStack { Text(LocalizedStringKey(name)); Spacer(); Text(value).font(.system(size: 11, weight: .semibold)).monospacedDigit() }.padding(.vertical, 4)
    }
    private func memoryDetailBytes(_ value: UInt64?) -> String {
        value.map { String(format: "%.2f GB", Double($0) / 1_073_741_824) } ?? tr("Unavailable")
    }
    private func memoryDetailRow(_ name: String, symbol: String, color: Color, bytes: UInt64?) -> some View {
        HStack(spacing: 8) {
            Image(systemName: symbol).font(.system(size: 11)).foregroundColor(color).frame(width: 14)
            Text(LocalizedStringKey(name))
            Spacer(minLength: 5)
            Text(memoryDetailBytes(bytes)).font(.system(size: 11, weight: .semibold)).monospacedDigit()
        }.padding(.vertical, 2)
    }
    private func usageRow(_ name: String, _ value: Double?) -> some View {
        HStack {
            Text(LocalizedStringKey(name)).frame(width: 75, alignment: .leading)
            if let value { ProgressView(value: max(0, min(1, value / 100))).tint(value >= 80 ? .red : value >= 50 ? .orange : .green).frame(width: 100) }
            else { Text("Unavailable").foregroundColor(.secondary).frame(width: 100) }
            Spacer(); Text(value.map { String(format: "%.1f%%", $0) } ?? "—").font(.system(size: 11)).monospacedDigit()
        }.padding(.vertical, 3)
    }
    @ViewBuilder private func detailView(_ page: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            switch page {
            case "cpu":
                Text("CPU Core Usage").fontWeight(.semibold)
                if let cores = monitor.snapshot.details?.cpuPercentages, !cores.isEmpty {
                    ForEach(coreDisplayOrder(count: cores.count), id: \.self) { index in usageRow(coreLabel(index, count: cores.count), cores[index]) }
                    Text("Core types use the Mac's performance-level counts when available.").font(.caption2).foregroundColor(.secondary)
                } else { Text("Unavailable").foregroundColor(.secondary) }
            case "gpu":
                Text("GPU Details").fontWeight(.semibold)
                usageRow("GPU", monitor.snapshot.gpu?.utilizationPercent)
                usageRow("Renderer", monitor.snapshot.gpu?.rendererUtilizationPercent)
                usageRow("Tiler", monitor.snapshot.gpu?.tilerUtilizationPercent)
                Divider(); detailRow("GPU cores", monitor.snapshot.gpu?.coreCount.map { "\($0) \(tr("cores"))" } ?? tr("Unavailable"))
                Divider(); Text(monitor.snapshot.gpu?.name ?? tr("Device unavailable"))
            case "memory":
                Text("Memory Details").fontWeight(.semibold)
                memoryDetailRow("Physical Memory", symbol: "memorychip", color: .blue, bytes: monitor.snapshot.details?.memory.physicalBytes)
                Divider()
                memoryDetailRow("Used Memory", symbol: "chart.bar.fill", color: .pink, bytes: monitor.snapshot.memoryUsed)
                memoryDetailRow("Cached Files", symbol: "doc.fill", color: .orange, bytes: monitor.snapshot.details?.memory.cachedBytes)
                memoryDetailRow("Swap Used", symbol: "arrow.up.arrow.down", color: .red, bytes: monitor.snapshot.details?.memory.swapUsedBytes)
                Divider()
                memoryDetailRow("App Memory", symbol: "square.fill", color: .green, bytes: monitor.snapshot.details?.memory.appBytes)
                memoryDetailRow("Wired Memory", symbol: "lock.fill", color: .yellow, bytes: monitor.snapshot.details?.memory.wiredBytes)
                memoryDetailRow("Compressed", symbol: "arrow.down.circle.fill", color: .cyan, bytes: monitor.snapshot.details?.memory.compressedBytes)
            default:
                Text("Storage Details").fontWeight(.semibold)
                detailRow("Volume", monitor.snapshot.storage?.volume.displayName ?? "—")
                Text(monitor.snapshot.storage?.volume.mountPath ?? "—").font(.caption2).foregroundColor(.secondary).lineLimit(2)
                Divider()
                detailRow("Total Capacity", diskBytes(monitor.snapshot.diskTotal))
                Divider()
                detailRow("Used capacity", diskBytes(diskUsed))
                detailRow("Available", diskBytes(monitor.snapshot.diskFree))
                Divider()
                detailRow("Format", monitor.snapshot.storage?.format ?? "—")
                detailRow("Location", monitor.snapshot.storage?.isLocal.map { tr($0 ? "Local" : "Network") } ?? "—")
                detailRow("Writable", monitor.snapshot.storage?.isReadOnly.map { tr($0 ? "No" : "Yes") } ?? "—")
                if monitor.snapshot.storage?.format == "APFS" {
                    Text("APFS volumes may share container capacity.").font(.caption2).foregroundColor(.secondary)
                }
                Divider()
                HStack {
                    Text("Folder estimates").fontWeight(.semibold)
                    Spacer()
                    if monitor.storageFolderScanInProgress {
                        Button("Stop") { monitor.cancelStorageFolderScan() }
                    } else {
                        Button("Estimate") { monitor.estimateStorageFolders() }
                    }
                }
                if monitor.storageFolderScanInProgress { ProgressView().controlSize(.small) }
                if !monitor.storageFolderScanMessage.isEmpty {
                    Text(monitor.storageFolderScanMessage).font(.caption2).foregroundColor(.secondary)
                }
                ForEach(monitor.storageFolderEstimates, id: \.category) { estimate in
                    HStack {
                        Text(LocalizedStringKey(estimate.label)).lineLimit(1)
                        Spacer(minLength: 4)
                        Text(storageEstimateText(estimate))
                            .font(.system(size: 11, weight: .semibold)).monospacedDigit()
                    }
                    if let note = estimate.note {
                        Text(note).font(.caption2).foregroundColor(.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                }
                Text("These are readable folder sizes, not macOS Storage category totals.")
                    .font(.caption2).foregroundColor(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }.font(.system(size: 12)).padding(14).frame(width: 260)
    }
    private func coreCounts(_ count: Int) -> (performance: Int, efficiency: Int)? {
        func readCount(_ name: String) -> Int? {
            var value: Int32 = 0, size = MemoryLayout<Int32>.size
            return sysctlbyname(name, &value, &size, nil, 0) == 0 && value >= 0 ? Int(value) : nil
        }
        guard let performance = readCount("hw.perflevel0.logicalcpu"),
              let efficiency = readCount("hw.perflevel1.logicalcpu"),
              performance > 0, efficiency > 0, performance + efficiency == count else { return nil }
        return (performance, efficiency)
    }
    private func coreDisplayOrder(count: Int) -> [Int] {
        guard let counts = coreCounts(count) else { return Array(0..<count) }
        // Mach exposes E cores first; the original details panel lists P cores first.
        return Array(counts.efficiency..<count) + Array(0..<counts.efficiency)
    }
    private func coreLabel(_ index: Int, count: Int) -> String {
        let japanese = ReplicaLocalization.languageCode(languageChoice) == "ja"
        guard let counts = coreCounts(count) else { return japanese ? "コア \(index + 1)" : "Core \(index + 1)" }
        return index < counts.efficiency
            ? (japanese ? "Eコア \(index + 1)" : "E-Core \(index + 1)")
            : (japanese ? "Pコア \(index - counts.efficiency + 1)" : "P-Core \(index - counts.efficiency + 1)")
    }
    private var diskUsed: Int64? {
        guard let total = monitor.snapshot.diskTotal, let free = monitor.snapshot.diskFree, total >= free else { return nil }
        return total - free
    }
    private func diskBytes(_ value: Int64?) -> String { value.map { ByteCountFormatter.string(fromByteCount: $0, countStyle: .file) } ?? "Unavailable" }
    private func storageEstimateText(_ estimate: StorageFolderEstimate) -> String {
        guard let bytes = estimate.bytes else { return "—" }
        let value = ByteCountFormatter.string(fromByteCount: Int64(clamping: bytes), countStyle: .file)
        return estimate.status == .complete ? value : "≥ \(value)"
    }
    private var caffeineDetails: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("Prevent Sleep", systemImage: "cup.and.saucer").font(.system(size: 12, weight: .semibold))
                Spacer()
                Toggle("", isOn: Binding(get: { monitor.caffeineActive }, set: { desired in if desired != monitor.caffeineActive { monitor.toggleCaffeine() } })).labelsHidden().toggleStyle(.switch)
            }
            Text(monitor.caffeineActive
                 ? (monitor.caffeineDuration == 0 ? tr("Idle sleep prevention is active (unlimited)")
                    : (ReplicaLocalization.languageCode(languageChoice) == "ja"
                       ? "無操作によるスリープ防止が有効です（\(monitor.caffeineDuration)分）"
                       : "Idle sleep prevention is active (\(monitor.caffeineDuration) minutes)"))
                 : tr("Idle sleep prevention is off"))
            Text("Prevents idle sleep only. It does not prevent lid-close, forced or low-battery sleep. Stop before changing mode.").font(.caption)
            Text(LocalizedStringKey(monitor.caffeineDisplay ? "System + Display" : "System only")).fontWeight(.semibold)
            Divider()
            DisclosureGroup(isExpanded: $monitor.additionalOptionsExpanded) {
                VStack(alignment: .leading, spacing: 12) {
            Picker("Run mode", selection: $monitor.caffeineProcessMode) {
                Text("Until stopped or timed").tag(false)
                Text("While process active").tag(true)
            }.disabled(monitor.caffeineActive)
                .onChange(of: monitor.caffeineProcessMode) { enabled in
                    if enabled { monitor.refreshCandidates() }
                }
            Toggle("Keep display awake", isOn: $monitor.caffeineDisplay).disabled(monitor.caffeineActive)
            if monitor.caffeineProcessMode {
                HStack {
                    Picker("Process", selection: $monitor.selectedProcess) {
                        Text("Select process").tag(Optional<ProcessIdentity>.none)
                        ForEach(monitor.candidates, id: \.identity) { candidate in Text("\(candidate.name) (\(candidate.identity.pid))").tag(Optional(candidate.identity)) }
                    }.disabled(monitor.caffeineActive)
                    Button("Refresh") { monitor.refreshCandidates() }.disabled(monitor.caffeineActive)
                }
                HStack { Text("CPU threshold (%)"); TextField("CPU %", value: $monitor.processThreshold, formatter: NumberFormatter()).frame(width: 60).disabled(monitor.caffeineActive) }
                if case let .watching(average, low)? = monitor.processWatchState {
                    Text("1-minute sample average: " + (average.map { String(format: "%.1f%%", $0) } ?? "Unavailable") + " · low checks: \(low)/5")
                }
                if !monitor.processMessage.isEmpty { Text(monitor.processMessage).foregroundColor(.secondary) }
                Text("Stops after five consecutive checks below the threshold or when the selected process exits. Average uses available samples from the last minute; unavailable samples reset the sequence.").font(.caption).foregroundColor(.secondary)
            }
            Picker("Duration", selection: $monitor.caffeineDuration) { Text("Until stopped").tag(0); Text("30 minutes").tag(30); Text("1 hour").tag(60); Text("2 hours").tag(120) }.disabled(monitor.caffeineActive)
            Text(LocalizedStringKey(monitor.caffeineDisplay ? "Prevents idle sleep of both the system and display." : "Prevents system idle sleep; the display may sleep.")).font(.caption)
            Text("Process mode follows the selected process only; child processes are not followed automatically.").font(.caption).foregroundColor(.secondary)
            Text("Prevents idle sleep only. It does not prevent lid-close, forced or low-battery sleep. Stop before changing mode.").font(.caption)
                }
            } label: {
                Text("Additional options").fontWeight(.semibold)
            }
            if let error = monitor.caffeineError { Text(error).foregroundColor(.red) }
        }.font(.system(size: 12)).padding(16).frame(width: 340, alignment: .leading).frame(minHeight: 360, alignment: .topLeading)
    }
    private var uptime: String {
        let minutes = Int(ProcessInfo.processInfo.systemUptime / 60)
        return "\(minutes / 60)h \(minutes % 60)m"
    }
    private func hardwareModel() -> String {
        var size = 0
        guard sysctlbyname("hw.model", nil, &size, nil, 0) == 0, size > 1 else { return "Mac" }
        var buffer = [CChar](repeating: 0, count: size)
        guard sysctlbyname("hw.model", &buffer, &size, nil, 0) == 0 else { return "Mac" }
        return String(cString: buffer)
    }
    private func share() {
        let snapshot = monitor.snapshot
        let safe = ShareCardData(
            cpuFraction: snapshot.cpu,
            memoryFraction: snapshot.memoryFraction,
            gpuPercent: snapshot.gpu?.utilizationPercent,
            batteryPercent: snapshot.details?.battery.isPresent == true
                ? snapshot.details?.battery.percentage : nil
        )
        guard let png = ShareImageRenderer.png(safe, languageChoice: languageChoice),
              let image = NSImage(data: png) else {
            monitor.shareFailed = true
            return
        }
        monitor.shareImage = image
        monitor.sharePresented = true
    }
    private var networkDescription: String {
        let network = monitor.snapshot.network
        guard let name = network.interfaceName else { return "Not available" }
        func rate(_ value: Double?) -> String {
            guard let value, value.isFinite, value >= 0, value < Double(Int64.max) else { return "—" }
            return ByteCountFormatter.string(fromByteCount: Int64(value), countStyle: .file) + "/s"
        }
        return "\(name): \(network.localIPv4 ?? "—")\n↑ \(rate(network.uploadBytesPerSecond))  ↓ \(rate(network.downloadBytesPerSecond))"
    }
    private var storage: String {
        guard let free = monitor.snapshot.diskFree, let total = monitor.snapshot.diskTotal else { return "—" }
        guard total > 0, free >= 0, free <= total else { return "—" }
        return String(format: "%.1f GB / %.1f GB", Double(total - free) / 1_000_000_000, Double(total) / 1_000_000_000)
    }
    private var storagePercent: String {
        guard let free = monitor.snapshot.diskFree, let total = monitor.snapshot.diskTotal,
              total > 0, free >= 0, free <= total else { return "—" }
        return String(format: "%.0f%%", Double(total - free) / Double(total) * 100)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSPopoverDelegate {
    let monitor = Monitor()
    let popover = NSPopover()
    var item: NSStatusItem!
    var subscriptions = Set<AnyCancellable>()
    func applicationDidFinishLaunching(_ notification: Notification) {
        ReplicaPreferences().migrateLegacyIcon()
        NSApp.setActivationPolicy(.accessory)
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.target = self; item.button?.action = #selector(togglePopover)
        let rightClick = NSClickGestureRecognizer(target: self, action: #selector(showStatusMenu(_:)))
        rightClick.buttonMask = 0x2
        item.button?.addGestureRecognizer(rightClick)
        popover.contentSize = NSSize(width: 280, height: monitor.desiredPopoverHeight)
        popover.behavior = .transient
        popover.delegate = self
        popover.contentViewController = NSHostingController(rootView: Dashboard(monitor: monitor))
        monitor.$snapshot.sink { [weak self] _ in DispatchQueue.main.async { self?.updateIcon() } }.store(in: &subscriptions)
        monitor.$caffeineActive.sink { [weak self] _ in DispatchQueue.main.async { self?.updateIcon() } }.store(in: &subscriptions)
        monitor.$memoryMood.sink { [weak self] _ in DispatchQueue.main.async { self?.updateIcon() } }.store(in: &subscriptions)
        monitor.objectWillChange.sink { [weak self] _ in
            DispatchQueue.main.async { self?.popover.contentSize = NSSize(width: 280, height: self?.monitor.desiredPopoverHeight ?? 680) }
        }.store(in: &subscriptions)
        NotificationCenter.default.publisher(for: UserDefaults.didChangeNotification).sink { [weak self] _ in DispatchQueue.main.async { self?.updateIcon() } }.store(in: &subscriptions)
        updateIcon()
        // Explicit one-time handover of an already-active display-sleep assertion.
        // This argument is never added to the login agent or persisted as enabled.
        if CommandLine.arguments.contains("--resume-display-awake") {
            monitor.caffeineProcessMode = false
            monitor.caffeineDisplay = true
            monitor.caffeineDuration = 0
            if !monitor.caffeineActive { monitor.toggleCaffeine() }
        }
    }
    func updateIcon() {
        guard let button = item?.button else { return }
        let choice = ReplicaPreferences().menuBarIconType
        // A representation change must clear the previous graph and its label.
        item.length = NSStatusItem.variableLength
        button.image = nil
        button.toolTip = nil
        button.setAccessibilityLabel(nil)
        let cpu = monitor.snapshot.cpu.map { "\(Int($0 * 100))%" } ?? "—"
        let memory = monitor.snapshot.memoryFraction.map { "\(Int($0 * 100))%" } ?? "—"
        switch choice {
        case ReplicaPreferences.cpuGraphIcon, ReplicaPreferences.cpuGraphMemoryIcon:
            let dark = button.effectiveAppearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            let scale = button.window?.backingScaleFactor ?? NSScreen.main?.backingScaleFactor ?? 1
            let includesMemory = choice == ReplicaPreferences.cpuGraphMemoryIcon
            CPUBarGraph.configure(button: button, percentages: monitor.snapshot.details?.cpuPercentages ?? [],
                                  memoryEmoji: includesMemory ? monitor.memoryMood.emoji : nil,
                                  dark: dark, scale: scale)
            let language = ReplicaPreferences.defaults.string(forKey: "language") ?? "System Default"
            let label = includesMemory ? "CPU usage per core and memory pressure" : "CPU usage per core"
            let description = ReplicaLocalization.text(label, choice: language)
            button.toolTip = description
            button.setAccessibilityLabel(description)
        case "CPU Emoji":
            if let value = monitor.snapshot.cpu { button.title = value < 0.6 ? "😊" : (value < 0.8 ? "😐" : "😰") } else { button.title = "❔" }
        case "CPU & Memory": button.title = "CPU \(cpu)  MEM \(memory)"
        case "CPU & Memory · Two Lines": button.title = "CPU \(cpu) · MEM \(memory)"
        case "CPU & Battery": button.title = "CPU \(cpu) · 🔋\(monitor.snapshot.battery.components(separatedBy: " · ").first ?? "—")"
        case "CPU & Fan": button.title = "CPU \(cpu) · Fan —"
        case "Animated Dots": button.title = ["•  ", "•• ", "•••"][monitor.animationFrame % 3]
        case "Animated Pulse": button.title = ["◦", "●"][monitor.animationFrame % 2]
        case "Car Animation": button.title = ["🚗", "🚙"][monitor.animationFrame % 2]
        default: button.title = monitor.memoryMood.emoji
        }
        if monitor.caffeineActive { button.title += " ☕️" }
    }
    func popoverDidClose(_ notification: Notification) { monitor.dashboardOpen = false }
    @objc private func showStatusMenu(_ gesture: NSClickGestureRecognizer) {
        guard let button = item.button else { return }
        let menu = NSMenu()
        let language = ReplicaPreferences.defaults.string(forKey: "language") ?? "System Default"
        let quit = NSMenuItem(title: ReplicaLocalization.text("Quit Simple Menu Status Replica", choice: language),
                              action: #selector(quitReplica), keyEquivalent: "")
        quit.target = self
        menu.addItem(quit)
        menu.popUp(positioning: nil, at: NSPoint(x: 0, y: button.bounds.minY), in: button)
    }
    @objc private func quitReplica() { NSApplication.shared.terminate(nil) }
    @objc func togglePopover() {
        if popover.isShown { popover.performClose(nil); monitor.dashboardOpen = false }
        else if let button = item.button {
            monitor.dashboardOpen = true
            monitor.refreshStorageVolumes()
            monitor.refresh()
            if monitor.showNetwork && monitor.selectedPreset != "Local AI" { monitor.fetchPublicIPIfNeeded() }
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            NSApp.activate(ignoringOtherApps: true)
        }
    }
}
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
