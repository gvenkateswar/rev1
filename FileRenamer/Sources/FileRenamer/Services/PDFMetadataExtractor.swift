import Foundation
import PDFKit

/// Extracts metadata from PDF files using PDFKit
@available(macOS 13.0, *)
struct PDFMetadataExtractor: MetadataExtracting {
    func extract(from url: URL) async -> FileMetadata {
        // Start with Spotlight metadata as a baseline
        var metadata = SpotlightMetadataReader.readMetadata(from: url)

        guard let document = PDFDocument(url: url) else {
            return metadata
        }

        // Extract from PDF document attributes
        if let attributes = document.documentAttributes {
            if let title = attributes[PDFDocumentAttribute.titleAttribute] as? String,
               !title.isEmpty {
                metadata.title = title
            }

            if let author = attributes[PDFDocumentAttribute.authorAttribute] as? String,
               !author.isEmpty {
                metadata.author = author
            }

            if let subject = attributes[PDFDocumentAttribute.subjectAttribute] as? String,
               !subject.isEmpty,
               metadata.title == nil {
                // Use subject as fallback title
                metadata.title = subject
            }

            if let keywords = attributes[PDFDocumentAttribute.keywordsAttribute] as? [String] {
                metadata.keywords = keywords
            }

            if let creationDate = attributes[PDFDocumentAttribute.creationDateAttribute] as? Date {
                metadata.creationDate = creationDate
            }
        }

        // Page count
        metadata.pageCount = document.pageCount

        // Extract text content sample from first page for keyword analysis
        if let firstPage = document.page(at: 0) {
            if let text = firstPage.string {
                let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                if !trimmed.isEmpty {
                    // Take first 500 characters as a content sample
                    metadata.contentSample = String(trimmed.prefix(500))
                }
            }
        }

        // If no title from attributes, try to get it from first page text
        if metadata.title == nil, let content = metadata.contentSample {
            metadata.title = content.firstMeaningfulLine()
        }

        return metadata
    }
}
