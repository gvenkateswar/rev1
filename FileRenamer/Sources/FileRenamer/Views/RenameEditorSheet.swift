import SwiftUI

/// Modal sheet for manually editing a proposed filename
@available(macOS 14.0, *)
struct RenameEditorSheet: View {
    @ObservedObject var file: ScannedFile
    @Environment(\.dismiss) private var dismiss

    @State private var editedName: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Title
            Text("Edit Filename")
                .font(.title2)
                .fontWeight(.semibold)

            // Original name
            GroupBox("Original Name") {
                HStack {
                    Image(systemName: file.category.icon)
                        .foregroundColor(.secondary)
                    Text(file.originalName)
                        .font(.system(.body, design: .monospaced))
                        .textSelection(.enabled)
                    Spacer()
                }
                .padding(.vertical, 4)
            }

            // Metadata preview
            if file.metadata.hasUsefulData {
                GroupBox("Extracted Metadata") {
                    VStack(alignment: .leading, spacing: 4) {
                        if let title = file.metadata.title {
                            metadataRow(label: "Title", value: title)
                        }
                        if let author = file.metadata.author {
                            metadataRow(label: "Author", value: author)
                        }
                        if let artist = file.metadata.artist {
                            metadataRow(label: "Artist", value: artist)
                        }
                        if let album = file.metadata.album {
                            metadataRow(label: "Album", value: album)
                        }
                        if let date = file.metadata.bestDate {
                            metadataRow(label: "Date", value: DateFormatter.displayDateTime.string(from: date))
                        }
                        if let camera = file.metadata.cameraModel {
                            metadataRow(label: "Camera", value: camera)
                        }
                        if let pages = file.metadata.pageCount {
                            metadataRow(label: "Pages", value: "\(pages)")
                        }
                    }
                    .padding(.vertical, 4)
                }
            }

            // Editable name field
            GroupBox("New Filename") {
                VStack(alignment: .leading, spacing: 8) {
                    TextField("Enter new filename", text: $editedName)
                        .textFieldStyle(.roundedBorder)
                        .font(.system(.body, design: .monospaced))

                    if !editedName.isEmpty {
                        let sanitized = editedName.sanitizedForFilename()
                        if sanitized != editedName {
                            Text("Will be saved as: \(sanitized).\(file.fileExtension)")
                                .font(.caption)
                                .foregroundColor(.orange)
                        }
                    }
                }
                .padding(.vertical, 4)
            }

            // Buttons
            HStack {
                if file.suggestedName != nil {
                    Button("Reset to Suggestion") {
                        editedName = file.suggestedName.map {
                            ($0 as NSString).deletingPathExtension
                        } ?? ""
                    }
                }

                Spacer()

                Button("Cancel") {
                    dismiss()
                }
                .keyboardShortcut(.cancelAction)

                Button("Apply") {
                    applyEdit()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(editedName.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(20)
        .frame(width: 550)
        .onAppear {
            // Initialize with the current name (without extension)
            if case .edited(let name) = file.action {
                editedName = (name as NSString).deletingPathExtension
            } else if let suggested = file.suggestedName {
                editedName = (suggested as NSString).deletingPathExtension
            } else {
                editedName = file.originalURL.nameWithoutExtension
            }
        }
    }

    private func metadataRow(label: String, value: String) -> some View {
        HStack(alignment: .top) {
            Text(label + ":")
                .font(.caption)
                .fontWeight(.medium)
                .foregroundColor(.secondary)
                .frame(width: 60, alignment: .trailing)
            Text(value)
                .font(.caption)
                .lineLimit(2)
                .textSelection(.enabled)
        }
    }

    private func applyEdit() {
        let trimmed = editedName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }

        let sanitized = trimmed.sanitizedForFilename()
        let fullName = "\(sanitized).\(file.fileExtension)"

        file.action = .edited(fullName)
        file.confidence = .high
        dismiss()
    }
}
