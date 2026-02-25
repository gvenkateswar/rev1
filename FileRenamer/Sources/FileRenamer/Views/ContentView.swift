import SwiftUI

/// Root view of the application
@available(macOS 14.0, *)
struct ContentView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar area
            toolbarArea

            Divider()

            // Main content
            if appState.isScanning {
                scanningView
            } else if appState.showingSummary, let results = appState.renameResults {
                SummaryView(results: results)
            } else if appState.scannedFiles.isEmpty {
                emptyStateView
            } else {
                VStack(spacing: 0) {
                    filterBar
                    Divider()
                    FileListView()
                    Divider()
                    bottomBar
                }
            }
        }
        .frame(minWidth: 900, minHeight: 600)
        .alert("Error", isPresented: .init(
            get: { appState.errorMessage != nil },
            set: { if !$0 { appState.errorMessage = nil } }
        )) {
            Button("OK") { appState.errorMessage = nil }
        } message: {
            Text(appState.errorMessage ?? "")
        }
    }

    // MARK: - Toolbar

    private var toolbarArea: some View {
        HStack(spacing: 12) {
            // Folder info
            if let folder = appState.selectedFolder {
                Image(systemName: "folder.fill")
                    .foregroundColor(.accentColor)
                Text(folder.lastPathComponent)
                    .font(.headline)
                Text(folder.path)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            } else {
                Text("No folder selected")
                    .font(.headline)
                    .foregroundColor(.secondary)
            }

            Spacer()

            Toggle("Recursive", isOn: $appState.scanRecursively)
                .toggleStyle(.checkbox)
                .help("Scan subdirectories")

            Button(action: { appState.selectFolder() }) {
                Label("Choose Folder", systemImage: "folder.badge.plus")
            }
            .controlSize(.large)

            if appState.selectedFolder != nil {
                Button(action: {
                    Task { await appState.scanFolder() }
                }) {
                    Label("Rescan", systemImage: "arrow.clockwise")
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.bar)
    }

    // MARK: - Filter bar

    private var filterBar: some View {
        HStack(spacing: 8) {
            // Category filter chips
            filterChip(label: "All", category: nil, count: appState.totalCount)

            ForEach(FileCategory.allCases) { category in
                let count = appState.categoryCounts[category] ?? 0
                if count > 0 {
                    filterChip(
                        label: category.displayName,
                        category: category,
                        count: count,
                        icon: category.icon
                    )
                }
            }

            Spacer()

            // Search field
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("Filter files...", text: $appState.searchText)
                    .textFieldStyle(.plain)
                    .frame(maxWidth: 200)
                if !appState.searchText.isEmpty {
                    Button(action: { appState.searchText = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color(nsColor: .controlBackgroundColor))
            .cornerRadius(6)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }

    private func filterChip(label: String, category: FileCategory?, count: Int, icon: String? = nil) -> some View {
        let isSelected = appState.filterCategory == category

        return Button(action: {
            withAnimation(.easeInOut(duration: 0.15)) {
                appState.filterCategory = category
            }
        }) {
            HStack(spacing: 4) {
                if let icon = icon {
                    Image(systemName: icon)
                        .font(.caption)
                }
                Text(label)
                    .font(.caption)
                Text("\(count)")
                    .font(.caption2)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 1)
                    .background(isSelected ? Color.white.opacity(0.3) : Color.secondary.opacity(0.2))
                    .cornerRadius(4)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(isSelected ? Color.accentColor : Color(nsColor: .controlBackgroundColor))
            .foregroundColor(isSelected ? .white : .primary)
            .cornerRadius(8)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Bottom bar

    private var bottomBar: some View {
        HStack {
            Button("Approve All") {
                appState.approveAll()
            }
            .help("Approve all visible suggestions")

            Button("Skip All") {
                appState.skipAll()
            }
            .help("Skip all visible files")

            Spacer()

            Text("\(appState.approvedCount) of \(appState.totalCount) files to rename")
                .font(.callout)
                .foregroundColor(.secondary)

            Button(action: { appState.renameApproved() }) {
                Label("Rename \(appState.approvedCount) Files", systemImage: "pencil")
            }
            .controlSize(.large)
            .disabled(appState.approvedCount == 0 || appState.isRenaming)
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.bar)
    }

    // MARK: - Scanning view

    private var scanningView: some View {
        VStack(spacing: 16) {
            Spacer()
            ProgressView(value: appState.scanProgress) {
                Text("Scanning files...")
                    .font(.headline)
            }
            .progressViewStyle(.linear)
            .frame(maxWidth: 300)

            Text("\(Int(appState.scanProgress * 100))%")
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Empty state

    private var emptyStateView: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "doc.text.magnifyingglass")
                .font(.system(size: 64))
                .foregroundColor(.secondary)

            Text("Select a Folder to Scan")
                .font(.title2)
                .fontWeight(.medium)

            Text("Choose a folder containing files you'd like to rename.\nSupported: PDFs, audio, video, images, documents, spreadsheets, and presentations.")
                .font(.body)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 450)

            Button(action: { appState.selectFolder() }) {
                Label("Choose Folder", systemImage: "folder.badge.plus")
            }
            .controlSize(.large)

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
