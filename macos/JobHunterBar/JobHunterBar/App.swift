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
    @Published var isSubmitting = false

    private var refreshTask: Task<Void, Never>?

    var menuBarLabel: String {
        if let stats, isOnline {
            return stats.menuBarTitle
        }
        return "⚠️ Offline"
    }

    init() {
        startPolling()
        GlobalHotKey.shared.install(keyCode: 49, modifiers: .option) { [weak self] in
            self?.toggleMenuBarWindow()
        }
    }

    deinit {
        refreshTask?.cancel()
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
            notes: notes.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        )

        do {
            _ = try await APIClient.shared.createApplication(payload)
            company = ""
            role = ""
            url = ""
            notes = ""
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

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
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
