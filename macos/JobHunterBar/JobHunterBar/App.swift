import AppKit
import SwiftUI

/*
 JobHunterBar — macOS menu-bar client for the local Job Tracker API.

 Run without Xcode (keeps running in the menu bar):
 1. Build once:  ./macos/JobHunterBar/install.sh
    (or Product → Archive in Xcode, then copy JobHunterBar.app to /Applications)
 2. Launch from /Applications — Dock icon stays hidden (LSUIElement).
 3. Open at login: System Settings → General → Login Items → add JobHunterBar
    (install.sh can do this with --login)
 4. Backend still needs to be up: docker compose up -d   (http://127.0.0.1:9000)

 Keyboard:
 - Return submits the form
 - ⌥ Space toggles the panel (Accessibility permission on first use)
 - ⌘⇧J also toggles while the panel is focused
*/

@main
struct JobHunterBarApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        MenuBarExtra {
            QuickLogView()
                .environmentObject(model)
                .frame(width: 360)
        } label: {
            Text(model.menuBarLabel)
        }
        .menuBarExtraStyle(.window)

        Settings {
            VStack(alignment: .leading, spacing: 8) {
                Text("Job Hunter Bar")
                    .font(.headline)
                Text("API: \(APIConfig.baseURL.absoluteString)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Install to /Applications and add Login Items so it survives logout.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()
            .frame(width: 320)
        }
    }

    init() {
        NSApplication.shared.setActivationPolicy(.accessory)
    }
}

@MainActor
final class AppModel: ObservableObject {
    @Published var stats: Stats?
    @Published var isOnline = false
    @Published var lastError: String?
    @Published var statusMessage: String?

    @Published var company = ""
    @Published var role = ""
    @Published var url = ""
    @Published var notes = ""
    @Published var source = ""
    @Published var workMode = "unknown"
    @Published var isSubmitting = false
    @Published var isStartingBackend = false

    private var refreshTask: Task<Void, Never>?
    private var activationObserver: NSObjectProtocol?
    private var lastBrowserApplication: NSRunningApplication?

    var menuBarLabel: String {
        if let stats, isOnline {
            return stats.menuBarTitle
        }
        return "⚠️ Offline"
    }

    init() {
        lastBrowserApplication = ActiveBrowserTabReader.supportedFrontmostApplication()
        activationObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard
                let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                ActiveBrowserTabReader.isSupported(app)
            else {
                return
            }
            self?.lastBrowserApplication = app
        }
        startPolling()
        GlobalHotKey.shared.install(keyCode: 49, modifiers: .option) { [weak self] in
            self?.toggleMenuBarWindow()
        }
    }

    deinit {
        refreshTask?.cancel()
        if let activationObserver {
            NSWorkspace.shared.notificationCenter.removeObserver(activationObserver)
        }
    }

    func startPolling() {
        refreshTask?.cancel()
        refreshTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refreshStats()
                try? await Task.sleep(for: .seconds(30))
            }
        }
    }

    func refreshStats() async {
        do {
            let stats = try await APIClient.shared.fetchStats()
            self.stats = stats
            self.isOnline = true
            if lastError?.contains("unreachable") == true {
                lastError = nil
            }
        } catch {
            self.isOnline = false
            self.stats = nil
            self.lastError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
        }
    }

    func submit() async {
        let trimmedCompany = company.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedRole = role.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedCompany.isEmpty, !trimmedRole.isEmpty else {
            lastError = "Company and Role are required."
            return
        }

        isSubmitting = true
        defer { isSubmitting = false }

        let payload = ApplicationPayload(
            company: trimmedCompany,
            role: trimmedRole,
            url: url.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
            status: "applied",
            notes: notes.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
            source: source.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
            workMode: workMode.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        )

        do {
            _ = try await APIClient.shared.createApplication(payload)
            company = ""
            role = ""
            url = ""
            notes = ""
            source = ""
            statusMessage = "Saved"
            lastError = nil
            await refreshStats()
        } catch {
            lastError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            statusMessage = nil
            if case .unreachable? = error as? APIError {
                isOnline = false
            }
        }
    }

    func startBackend() async {
        isStartingBackend = true
        defer { isStartingBackend = false }

        do {
            let message = try await BackendStarter.start()
            statusMessage = message
            lastError = nil
            try? await Task.sleep(for: .seconds(2))
            await refreshStats()
        } catch {
            lastError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            statusMessage = nil
        }
    }

    func useActiveTab() {
        let tab = ActiveBrowserTabReader.readTab(from: lastBrowserApplication)
            ?? ActiveBrowserTabReader.readFrontmostTab()
        guard let tab else {
            lastError = "Could not read the active browser tab."
            statusMessage = nil
            return
        }
        if url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            url = tab.url
        }
        let draft = Self.draftCompanyAndRole(from: tab.title)
        if company.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, let draftCompany = draft.company {
            company = draftCompany
        }
        if role.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, let draftRole = draft.role {
            role = draftRole
        }
        lastError = nil
        statusMessage = "Active tab loaded"
    }

    private static func draftCompanyAndRole(from title: String) -> (company: String?, role: String?) {
        for separator in [" | ", " - ", " at ", " @ "] {
            if title.contains(separator) {
                let parts = title
                    .components(separatedBy: separator)
                    .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                    .filter { !$0.isEmpty }
                if parts.count >= 2 {
                    return (parts.last, parts.first)
                }
            }
        }
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        return (nil, trimmed.isEmpty ? nil : trimmed)
    }

    private func toggleMenuBarWindow() {
        NSApp.activate(ignoringOtherApps: true)
        if let button = Self.statusItemButton() {
            button.performClick(nil)
            return
        }
        for window in NSApp.windows where window.frame.width >= 300 && window.canBecomeKey {
            if window.isVisible {
                window.orderOut(nil)
            } else {
                window.makeKeyAndOrderFront(nil)
            }
            return
        }
    }

    private static func statusItemButton() -> NSStatusBarButton? {
        for window in NSApp.windows where window.className == "NSStatusBarWindow" {
            if let button = findButton(in: window.contentView) {
                return button
            }
        }
        return nil
    }

    private static func findButton(in view: NSView?) -> NSStatusBarButton? {
        guard let view else { return nil }
        if let button = view as? NSStatusBarButton {
            return button
        }
        for subview in view.subviews {
            if let button = findButton(in: subview) {
                return button
            }
        }
        return nil
    }
}

enum BackendStartError: LocalizedError {
    case scriptMissing([String])
    case failed(Int32, String)

    var errorDescription: String? {
        switch self {
        case let .scriptMissing(paths):
            return "Could not find start-backend.sh. Checked: \(paths.joined(separator: ", "))"
        case let .failed(status, output):
            let trimmed = output.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty
                ? "Docker backend start failed with exit code \(status)."
                : "Docker backend start failed (\(status)): \(trimmed)"
        }
    }
}

struct BackendStarter {
    static func start() async throws -> String {
        try await Task.detached(priority: .userInitiated) {
            try runScript()
        }.value
    }

    private static func runScript() throws -> String {
        let scriptURL = try locateScript()
        let process = Process()
        let output = Pipe()

        process.executableURL = URL(fileURLWithPath: "/bin/bash")
        process.arguments = [scriptURL.path]
        process.standardOutput = output
        process.standardError = output

        try process.run()
        process.waitUntilExit()

        let data = output.fileHandleForReading.readDataToEndOfFile()
        let text = String(data: data, encoding: .utf8) ?? ""
        guard process.terminationStatus == 0 else {
            throw BackendStartError.failed(process.terminationStatus, text)
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? "Docker backend started"
            : "Docker backend started"
    }

    private static func locateScript() throws -> URL {
        let environment = ProcessInfo.processInfo.environment
        let home = NSHomeDirectory()
        let candidates = [
            environment["JOB_HUNTER_BACKEND_SCRIPT"],
            "\(home)/Codes/github/job-hunter/macos/launchd/start-backend.sh",
            "\(home)/Code/github/job-hunter/macos/launchd/start-backend.sh",
            "\(home)/Developer/job-hunter/macos/launchd/start-backend.sh",
        ].compactMap { $0 }

        let fileManager = FileManager.default
        for path in candidates where fileManager.isExecutableFile(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        throw BackendStartError.scriptMissing(candidates)
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}

struct ActiveBrowserTab {
    let title: String
    let url: String
}

enum ActiveBrowserTabReader {
    static func isSupported(_ app: NSRunningApplication) -> Bool {
        switch app.bundleIdentifier {
        case "com.apple.Safari",
             "com.google.Chrome",
             "com.google.Chrome.canary",
             "com.microsoft.edgemac",
             "com.brave.Browser",
             "company.thebrowser.Browser":
            return true
        default:
            return false
        }
    }

    static func supportedFrontmostApplication() -> NSRunningApplication? {
        guard let app = NSWorkspace.shared.frontmostApplication, isSupported(app) else {
            return nil
        }
        return app
    }

    static func readFrontmostTab() -> ActiveBrowserTab? {
        readTab(from: supportedFrontmostApplication())
    }

    static func readTab(from app: NSRunningApplication?) -> ActiveBrowserTab? {
        guard let app else { return nil }
        switch app.bundleIdentifier {
        case "com.apple.Safari":
            return readSafari()
        case "com.google.Chrome",
             "com.google.Chrome.canary",
             "com.microsoft.edgemac",
             "com.brave.Browser",
             "company.thebrowser.Browser":
            return readChromium(app.localizedName)
        default:
            return nil
        }
    }

    private static func readSafari() -> ActiveBrowserTab? {
        runScript("""
        tell application "Safari"
            if not (exists front window) then return ""
            set tabTitle to name of current tab of front window
            set tabUrl to URL of current tab of front window
            return tabTitle & linefeed & tabUrl
        end tell
        """)
    }

    private static func readChromium(_ appName: String?) -> ActiveBrowserTab? {
        guard let appName, !appName.isEmpty else {
            return nil
        }
        return runScript("""
        tell application "\(appName)"
            if not (exists front window) then return ""
            set tabTitle to title of active tab of front window
            set tabUrl to URL of active tab of front window
            return tabTitle & linefeed & tabUrl
        end tell
        """)
    }

    private static func runScript(_ source: String) -> ActiveBrowserTab? {
        var error: NSDictionary?
        guard let output = NSAppleScript(source: source)?.executeAndReturnError(&error).stringValue else {
            return nil
        }
        let lines = output.components(separatedBy: .newlines)
        guard lines.count >= 2 else {
            return nil
        }
        let title = lines[0].trimmingCharacters(in: .whitespacesAndNewlines)
        let url = lines[1].trimmingCharacters(in: .whitespacesAndNewlines)
        guard !url.isEmpty else {
            return nil
        }
        return ActiveBrowserTab(title: title, url: url)
    }
}

@MainActor
final class GlobalHotKey {
    static let shared = GlobalHotKey()

    private var localMonitor: Any?
    private var globalMonitor: Any?
    private var handler: (() -> Void)?

    func install(keyCode: UInt16, modifiers: NSEvent.ModifierFlags, handler: @escaping () -> Void) {
        self.handler = handler
        let mask: NSEvent.EventTypeMask = [.keyDown]

        localMonitor = NSEvent.addLocalMonitorForEvents(matching: mask) { event in
            if Self.matches(event, keyCode: keyCode, modifiers: modifiers) {
                handler()
                return nil
            }
            return event
        }

        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: mask) { event in
            if Self.matches(event, keyCode: keyCode, modifiers: modifiers) {
                handler()
            }
        }
    }

    private static func matches(_ event: NSEvent, keyCode: UInt16, modifiers: NSEvent.ModifierFlags) -> Bool {
        let relevant: NSEvent.ModifierFlags = [.command, .option, .control, .shift]
        return event.keyCode == keyCode
            && event.modifierFlags.intersection(relevant) == modifiers.intersection(relevant)
    }
}
