import SwiftUI
import AppKit

struct QuickLogView: View {
    @EnvironmentObject private var model: AppModel
    @FocusState private var focusedField: Field?

    private enum Field: Hashable {
        case company, role, url, followUpDate, notes
    }

    private let sources = [
        ("", "Auto"),
        ("linkedin", "LinkedIn"),
        ("company_site", "Company site"),
        ("referral", "Referral"),
        ("job_board", "Job board"),
        ("recruiter", "Recruiter"),
        ("naukri", "Naukri"),
        ("indeed", "Indeed"),
        ("company_portal", "Company portal"),
        ("network", "Network"),
        ("other", "Other"),
    ]

    private let workModes = [
        ("unknown", "Unknown"),
        ("remote", "Remote"),
        ("hybrid", "Hybrid"),
        ("onsite", "Onsite"),
        ("freelance", "Freelance"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header

            VStack(alignment: .leading, spacing: 8) {
                Button("Use Active Tab") {
                    model.useActiveTab()
                }
                .buttonStyle(.bordered)

                TextField("Company", text: $model.company)
                    .focused($focusedField, equals: .company)
                    .textFieldStyle(.roundedBorder)

                TextField("Role", text: $model.role)
                    .focused($focusedField, equals: .role)
                    .textFieldStyle(.roundedBorder)

                TextField("Job Posting URL", text: $model.url)
                    .focused($focusedField, equals: .url)
                    .textFieldStyle(.roundedBorder)

                HStack(spacing: 8) {
                    Picker("Source", selection: $model.source) {
                        ForEach(sources, id: \.0) { value, label in
                            Text(label).tag(value)
                        }
                    }
                    .pickerStyle(.menu)

                    Picker("Mode", selection: $model.workMode) {
                        ForEach(workModes, id: \.0) { value, label in
                            Text(label).tag(value)
                        }
                    }
                    .pickerStyle(.menu)
                }

                TextField("Follow-up YYYY-MM-DD", text: $model.followUpDate)
                    .focused($focusedField, equals: .followUpDate)
                    .textFieldStyle(.roundedBorder)

                TextField("Notes", text: $model.notes, axis: .vertical)
                    .focused($focusedField, equals: .notes)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(3 ... 6)
            }

            HStack(spacing: 8) {
                Link("Open dashboard", destination: APIConfig.baseURL)
                    .font(.caption)

                Spacer()

                Button(model.isSubmitting ? "Saving…" : "Log Application") {
                    Task { await model.submit() }
                }
                .keyboardShortcut(.return, modifiers: [])
                .disabled(model.isSubmitting || !model.isOnline)
                .buttonStyle(.borderedProminent)
            }

            footer
        }
        .padding(14)
        .onAppear {
            focusedField = .company
            Task { await model.refreshStats() }
        }
        .background {
            Button("Toggle") { NSApp.activate(ignoringOtherApps: true) }
                .keyboardShortcut("j", modifiers: [.command, .shift])
                .opacity(0)
                .frame(width: 0, height: 0)
                .accessibilityHidden(true)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(model.isOnline ? "Job Tracker" : "Offline")
                    .font(.headline)
                Spacer()
                Circle()
                    .fill(model.isOnline ? Color.green : Color.orange)
                    .frame(width: 8, height: 8)
            }
            if let stats = model.stats, model.isOnline {
                Text("\(stats.applied) applied this hunt")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("This week: \(stats.submittedThisWeek)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                Button(model.isStartingBackend ? "Starting Docker…" : "Start Docker Backend") {
                    Task { await model.startBackend() }
                }
                .buttonStyle(.borderedProminent)
                .disabled(model.isStartingBackend)

                Text("Uses macos/launchd/start-backend.sh on port 9000.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var footer: some View {
        Group {
            if let statusMessage = model.statusMessage {
                Text(statusMessage)
                    .font(.caption)
                    .foregroundStyle(.green)
            }
            if let lastError = model.lastError {
                Text(lastError)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
