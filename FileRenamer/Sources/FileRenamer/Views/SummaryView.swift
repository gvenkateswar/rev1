import SwiftUI

/// Post-rename summary showing results
struct SummaryView: View {
    let results: [RenameResult]
    @EnvironmentObject var appState: AppState

    var successResults: [RenameResult] {
        results.filter { $0.success && $0.newURL != nil }
    }

    var failedResults: [RenameResult] {
        results.filter { !$0.success }
    }

    var skippedResults: [RenameResult] {
        results.filter { $0.success && $0.newURL == nil }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Summary header
            VStack(spacing: 12) {
                Image(systemName: failedResults.isEmpty ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                    .font(.system(size: 48))
                    .foregroundColor(failedResults.isEmpty ? .green : .orange)

                Text("Rename Complete")
                    .font(.title2)
                    .fontWeight(.semibold)

                HStack(spacing: 24) {
                    statBadge(count: successResults.count, label: "Renamed", color: .green)
                    statBadge(count: skippedResults.count, label: "Skipped", color: .secondary)
                    statBadge(count: failedResults.count, label: "Failed", color: .red)
                }
            }
            .padding(.vertical, 24)

            Divider()

            // Results list
            ScrollView {
                LazyVStack(spacing: 0) {
                    if !successResults.isEmpty {
                        sectionHeader("Renamed Successfully", icon: "checkmark.circle", color: .green)
                        ForEach(successResults) { result in
                            resultRow(result)
                            Divider()
                        }
                    }

                    if !failedResults.isEmpty {
                        sectionHeader("Failed", icon: "xmark.circle", color: .red)
                        ForEach(failedResults) { result in
                            resultRow(result)
                            Divider()
                        }
                    }
                }
            }

            Divider()

            // Actions
            HStack {
                if !successResults.isEmpty {
                    Button("Undo All Renames") {
                        appState.undoRenames()
                    }
                    .help("Revert all renamed files to their original names")
                }

                Spacer()

                Button("Rescan Folder") {
                    appState.showingSummary = false
                    Task {
                        await appState.scanFolder()
                    }
                }

                Button("Done") {
                    appState.showingSummary = false
                    appState.renameResults = nil
                    appState.scannedFiles = []
                }
                .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(.bar)
        }
    }

    private func statBadge(count: Int, label: String, color: Color) -> some View {
        VStack(spacing: 4) {
            Text("\(count)")
                .font(.title)
                .fontWeight(.bold)
                .foregroundColor(color)
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private func sectionHeader(_ title: String, icon: String, color: Color) -> some View {
        HStack {
            Image(systemName: icon)
                .foregroundColor(color)
            Text(title)
                .font(.headline)
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color(nsColor: .controlBackgroundColor))
    }

    private func resultRow(_ result: RenameResult) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(result.originalName)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundColor(.secondary)

                if let newName = result.newName {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.right")
                            .font(.caption2)
                            .foregroundColor(.accentColor)
                        Text(newName)
                            .font(.system(.body, design: .monospaced))
                    }
                }

                if let error = result.error {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(.red)
                }
            }

            Spacer()

            Image(systemName: result.success ? "checkmark" : "xmark")
                .foregroundColor(result.success ? .green : .red)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
    }
}
