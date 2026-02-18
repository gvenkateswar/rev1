import Foundation

/// Confidence level for a rename suggestion
enum SuggestionConfidence: Comparable {
    case none
    case low
    case medium
    case high

    var displayName: String {
        switch self {
        case .none: return "No suggestion"
        case .low: return "Low"
        case .medium: return "Medium"
        case .high: return "High"
        }
    }

    var color: String {
        switch self {
        case .none: return "gray"
        case .low: return "orange"
        case .medium: return "yellow"
        case .high: return "green"
        }
    }
}

/// What action the user wants for this file
enum RenameAction: Equatable {
    case approved
    case edited(String)
    case skipped

    var isActive: Bool {
        switch self {
        case .approved, .edited: return true
        case .skipped: return false
        }
    }

    /// The final name to use (either suggested or user-edited)
    func finalName(suggestedName: String?) -> String? {
        switch self {
        case .approved: return suggestedName
        case .edited(let name): return name
        case .skipped: return nil
        }
    }
}

/// A file discovered during scanning, with its metadata and rename suggestion
class ScannedFile: Identifiable, ObservableObject {
    let id = UUID()
    let originalURL: URL
    let category: FileCategory
    let metadata: FileMetadata

    @Published var suggestedName: String?
    @Published var confidence: SuggestionConfidence
    @Published var action: RenameAction

    var originalName: String {
        originalURL.lastPathComponent
    }

    var fileExtension: String {
        originalURL.pathExtension
    }

    var directory: URL {
        originalURL.deletingLastPathComponent()
    }

    /// The effective new name based on the current action
    var effectiveName: String? {
        action.finalName(suggestedName: suggestedName)
    }

    /// Whether this file actually needs renaming
    var needsRename: Bool {
        guard let newName = effectiveName else { return false }
        return newName != originalName
    }

    init(
        originalURL: URL,
        category: FileCategory,
        metadata: FileMetadata,
        suggestedName: String? = nil,
        confidence: SuggestionConfidence = .none
    ) {
        self.originalURL = originalURL
        self.category = category
        self.metadata = metadata
        self.suggestedName = suggestedName
        self.confidence = confidence
        self.action = suggestedName != nil ? .approved : .skipped
    }
}
