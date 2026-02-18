import Foundation
import CoreGraphics

/// Metadata extracted from a file, used to generate rename suggestions
struct FileMetadata {
    var title: String?
    var author: String?
    var creationDate: Date?
    var modificationDate: Date?
    var keywords: [String] = []
    var contentSample: String?

    // Audio-specific
    var artist: String?
    var album: String?
    var trackNumber: Int?
    var genre: String?

    // Media
    var duration: TimeInterval?
    var resolution: CGSize?

    // Image-specific
    var cameraModel: String?
    var dateTaken: Date?

    // Document-specific
    var pageCount: Int?

    /// Whether any meaningful metadata was extracted
    var hasUsefulData: Bool {
        return title != nil || author != nil || artist != nil ||
               creationDate != nil || dateTaken != nil ||
               contentSample != nil || album != nil
    }

    /// The best available date from metadata
    var bestDate: Date? {
        return dateTaken ?? creationDate ?? modificationDate
    }
}
