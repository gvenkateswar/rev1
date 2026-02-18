import Foundation
import CoreServices

/// Reads Spotlight metadata attributes from files using the MDItem API
struct SpotlightMetadataReader {
    /// Read common metadata from a file via Spotlight/MDItem
    static func readMetadata(from url: URL) -> FileMetadata {
        var metadata = FileMetadata()

        guard let mdItem = MDItemCreateWithURL(kCFAllocatorDefault, url as CFURL) else {
            return metadata
        }

        // Title
        if let title = MDItemCopyAttribute(mdItem, kMDItemTitle) as? String,
           !title.isEmpty {
            metadata.title = title
        }

        // Authors
        if let authors = MDItemCopyAttribute(mdItem, kMDItemAuthors) as? [String],
           let firstAuthor = authors.first,
           !firstAuthor.isEmpty {
            metadata.author = firstAuthor
        }

        // Creation date
        if let date = MDItemCopyAttribute(mdItem, kMDItemContentCreationDate) as? Date {
            metadata.creationDate = date
        }

        // Modification date
        if let date = MDItemCopyAttribute(mdItem, kMDItemContentModificationDate) as? Date {
            metadata.modificationDate = date
        }

        // Keywords
        if let keywords = MDItemCopyAttribute(mdItem, kMDItemKeywords) as? [String] {
            metadata.keywords = keywords
        }

        // Page count (for documents/PDFs)
        if let pages = MDItemCopyAttribute(mdItem, kMDItemNumberOfPages) as? Int {
            metadata.pageCount = pages
        }

        // Duration (for audio/video)
        if let duration = MDItemCopyAttribute(mdItem, kMDItemDurationSeconds) as? Double {
            metadata.duration = duration
        }

        // Music-specific
        if let artist = MDItemCopyAttribute(mdItem, kMDItemComposer) as? String {
            metadata.artist = artist
        }
        if let album = MDItemCopyAttribute(mdItem, kMDItemAlbum) as? String {
            metadata.album = album
        }
        if let genre = MDItemCopyAttribute(mdItem, kMDItemMusicalGenre) as? String {
            metadata.genre = genre
        }

        return metadata
    }
}
