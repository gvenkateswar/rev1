import Foundation

/// Protocol for extracting metadata from files
protocol MetadataExtracting {
    func extract(from url: URL) async -> FileMetadata
}

/// Factory that routes to the correct extractor based on file category
struct MetadataExtractorFactory {
    static func extractor(for category: FileCategory) -> MetadataExtracting {
        switch category {
        case .pdf:
            return PDFMetadataExtractor()
        case .audio:
            return AudioMetadataExtractor()
        case .video:
            return VideoMetadataExtractor()
        case .image:
            return ImageMetadataExtractor()
        case .document:
            return DocumentMetadataExtractor()
        case .spreadsheet:
            return DocumentMetadataExtractor()
        case .presentation:
            return DocumentMetadataExtractor()
        }
    }
}
