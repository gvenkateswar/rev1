import SwiftUI

/// A single row displaying a file with its original name, suggested name, and action controls
struct FileRowView: View {
    @ObservedObject var file: ScannedFile
    @State private var showingEditor = false
    @State private var isHovering = false

    var body: some View {
        HStack(spacing: 0) {
            // Action checkbox
            actionIndicator
                .frame(width: 50)

            // File type icon
            Image(systemName: file.category.icon)
                .foregroundColor(categoryColor)
                .frame(width: 40)
                .help(file.category.displayName)

            // Original name
            VStack(alignment: .leading, spacing: 2) {
                Text(file.originalName)
                    .font(.system(.body, design: .monospaced))
                    .lineLimit(1)
                    .truncationMode(.middle)
                if let metadata = metadataPreview {
                    Text(metadata)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
            .frame(minWidth: 200, alignment: .leading)

            // Arrow
            Image(systemName: file.needsRename ? "arrow.right" : "equal")
                .foregroundColor(file.needsRename ? .accentColor : .secondary)
                .frame(width: 30)

            // Suggested name
            VStack(alignment: .leading, spacing: 2) {
                if let name = file.effectiveName {
                    Text(name)
                        .font(.system(.body, design: .monospaced))
                        .foregroundColor(file.needsRename ? .primary : .secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                } else {
                    Text("No suggestion")
                        .font(.body)
                        .foregroundColor(.secondary)
                        .italic()
                }
            }
            .frame(minWidth: 200, alignment: .leading)

            // Confidence badge
            confidenceBadge
                .frame(width: 90)

            // Action buttons
            actionButtons
                .frame(width: 100)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(isHovering ? Color(nsColor: .selectedContentBackgroundColor).opacity(0.1) : Color.clear)
        .onHover { hovering in
            isHovering = hovering
        }
        .sheet(isPresented: $showingEditor) {
            RenameEditorSheet(file: file)
        }
    }

    // MARK: - Subviews

    private var actionIndicator: some View {
        Group {
            if file.suggestedName != nil || file.action != .skipped {
                Image(systemName: file.action.isActive ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(file.action.isActive ? .green : .secondary)
                    .font(.title3)
                    .onTapGesture {
                        toggleAction()
                    }
            } else {
                Image(systemName: "minus.circle")
                    .foregroundColor(.secondary.opacity(0.5))
                    .font(.title3)
            }
        }
    }

    private var confidenceBadge: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(confidenceColor)
                .frame(width: 8, height: 8)
            Text(file.confidence.displayName)
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }

    private var actionButtons: some View {
        HStack(spacing: 4) {
            // Edit button
            Button(action: { showingEditor = true }) {
                Image(systemName: "pencil")
                    .font(.caption)
            }
            .buttonStyle(.borderless)
            .help("Edit rename suggestion")

            // Approve/Skip toggle
            if file.suggestedName != nil {
                Button(action: { toggleAction() }) {
                    Image(systemName: file.action.isActive ? "xmark" : "checkmark")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
                .help(file.action.isActive ? "Skip this file" : "Approve this rename")
            }
        }
    }

    // MARK: - Helpers

    private var categoryColor: Color {
        switch file.category {
        case .pdf: return .red
        case .audio: return .purple
        case .video: return .blue
        case .document: return .orange
        case .image: return .green
        case .spreadsheet: return .teal
        case .presentation: return .pink
        }
    }

    private var confidenceColor: Color {
        switch file.confidence {
        case .none: return .gray
        case .low: return .orange
        case .medium: return .yellow
        case .high: return .green
        }
    }

    private var metadataPreview: String? {
        var parts: [String] = []

        if let title = file.metadata.title, !title.isEmpty {
            parts.append("Title: \(String(title.prefix(40)))")
        }
        if let author = file.metadata.author ?? file.metadata.artist {
            parts.append(author)
        }
        if let date = file.metadata.bestDate {
            parts.append(DateFormatter.displayDate.string(from: date))
        }

        return parts.isEmpty ? nil : parts.joined(separator: " | ")
    }

    private func toggleAction() {
        if file.action.isActive {
            file.action = .skipped
        } else if file.suggestedName != nil {
            file.action = .approved
        }
    }
}
