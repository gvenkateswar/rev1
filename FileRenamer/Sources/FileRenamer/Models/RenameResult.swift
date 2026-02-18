import Foundation

/// Outcome of a single file rename operation
struct RenameResult: Identifiable {
    let id = UUID()
    let originalURL: URL
    let newURL: URL?
    let success: Bool
    let error: String?

    var originalName: String {
        originalURL.lastPathComponent
    }

    var newName: String? {
        newURL?.lastPathComponent
    }

    static func success(from originalURL: URL, to newURL: URL) -> RenameResult {
        RenameResult(originalURL: originalURL, newURL: newURL, success: true, error: nil)
    }

    static func failure(from originalURL: URL, error: String) -> RenameResult {
        RenameResult(originalURL: originalURL, newURL: nil, success: false, error: error)
    }

    static func skipped(from originalURL: URL) -> RenameResult {
        RenameResult(originalURL: originalURL, newURL: nil, success: true, error: nil)
    }
}
