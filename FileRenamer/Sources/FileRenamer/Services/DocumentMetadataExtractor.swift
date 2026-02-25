import Foundation

/// Extracts metadata from document files (Word, text, RTF, spreadsheets, presentations)
/// Relies primarily on Spotlight metadata and direct file reading for plain text formats
@available(macOS 13.0, *)
struct DocumentMetadataExtractor: MetadataExtracting {
    func extract(from url: URL) async -> FileMetadata {
        var metadata = SpotlightMetadataReader.readMetadata(from: url)

        let ext = url.pathExtension.lowercased()

        // For plain text formats, read the content directly
        if ["txt", "csv", "rtf"].contains(ext) {
            metadata = extractFromTextFile(url: url, metadata: metadata)
        }

        // Fall back to file system dates if no metadata dates
        if metadata.creationDate == nil {
            if let attrs = try? FileManager.default.attributesOfItem(atPath: url.path) {
                metadata.creationDate = attrs[.creationDate] as? Date
                metadata.modificationDate = attrs[.modificationDate] as? Date
            }
        }

        return metadata
    }

    private func extractFromTextFile(url: URL, metadata: FileMetadata) -> FileMetadata {
        var meta = metadata

        guard let data = try? Data(contentsOf: url, options: .mappedIfSafe) else {
            return meta
        }

        // Read first 2KB for analysis
        let sampleData = data.prefix(2048)

        // Try UTF-8, then fallback encodings
        let content: String?
        if let text = String(data: sampleData, encoding: .utf8) {
            content = text
        } else if let text = String(data: sampleData, encoding: .macOSRoman) {
            content = text
        } else {
            content = nil
        }

        guard let text = content, !text.isEmpty else {
            return meta
        }

        meta.contentSample = String(text.prefix(500))

        // Try to extract title from first meaningful line
        if meta.title == nil {
            meta.title = text.firstMeaningfulLine()
        }

        // Look for date patterns in the content
        if meta.creationDate == nil {
            meta.creationDate = extractDateFromContent(text)
        }

        return meta
    }

    /// Try to find a date in the content text using common patterns
    private func extractDateFromContent(_ text: String) -> Date? {
        let patterns: [(String, String)] = [
            // 2024-03-15
            (#"\b(\d{4}-\d{2}-\d{2})\b"#, "yyyy-MM-dd"),
            // 03/15/2024
            (#"\b(\d{2}/\d{2}/\d{4})\b"#, "MM/dd/yyyy"),
            // 15/03/2024
            (#"\b(\d{2}/\d{2}/\d{4})\b"#, "dd/MM/yyyy"),
            // March 15, 2024
            (#"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b"#, "MMMM d, yyyy"),
        ]

        for (pattern, format) in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern, options: []),
                  let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
                  let range = Range(match.range(at: 1), in: text) else {
                continue
            }

            let dateString = String(text[range]).replacingOccurrences(of: ",", with: "")
            let formatter = DateFormatter()
            formatter.dateFormat = format
            formatter.locale = Locale(identifier: "en_US_POSIX")

            if let date = formatter.date(from: dateString) {
                return date
            }
        }

        return nil
    }
}
