import SwiftUI

/// Scrollable list of scanned files with their rename suggestions
struct FileListView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                // Header row
                headerRow

                Divider()

                // File rows
                ForEach(appState.filteredFiles) { file in
                    FileRowView(file: file)
                    Divider()
                }
            }
        }
        .background(Color(nsColor: .textBackgroundColor))
    }

    private var headerRow: some View {
        HStack(spacing: 0) {
            Text("Status")
                .frame(width: 50)

            Text("Type")
                .frame(width: 40)

            Text("Original Name")
                .frame(minWidth: 200, alignment: .leading)

            Image(systemName: "arrow.right")
                .frame(width: 30)
                .foregroundColor(.secondary)

            Text("Suggested Name")
                .frame(minWidth: 200, alignment: .leading)

            Text("Confidence")
                .frame(width: 90)

            Text("Actions")
                .frame(width: 100)
        }
        .font(.caption)
        .fontWeight(.semibold)
        .foregroundColor(.secondary)
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(Color(nsColor: .controlBackgroundColor))
    }
}
