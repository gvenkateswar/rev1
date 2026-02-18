import Foundation

extension URL {
    /// Determine the FileCategory for this URL based on its extension
    var fileCategory: FileCategory? {
        FileCategory.from(extension: self.pathExtension)
    }

    /// Whether this URL points to a supported user file
    var isSupportedFile: Bool {
        FileCategory.allExtensions.contains(self.pathExtension.lowercased())
    }

    /// The filename without its extension
    var nameWithoutExtension: String {
        self.deletingPathExtension().lastPathComponent
    }
}
