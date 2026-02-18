import Foundation

/// Core heuristic engine that generates standardized filename suggestions from metadata
struct RenameSuggestionEngine {

    /// Generate a rename suggestion for a file
    /// - Parameters:
    ///   - metadata: Extracted metadata for the file
    ///   - originalURL: The file's current URL
    ///   - category: The file's category
    /// - Returns: A tuple of (suggested filename with extension, confidence level)
    func suggest(
        metadata: FileMetadata,
        originalURL: URL,
        category: FileCategory
    ) -> (name: String?, confidence: SuggestionConfidence) {

        let ext = originalURL.pathExtension.lowercased()
        let originalName = originalURL.nameWithoutExtension

        // Try strategies in priority order
        if let result = tryAudioPattern(metadata: metadata, ext: ext, category: category) {
            return result
        }

        if let result = tryTitleAndAuthor(metadata: metadata, ext: ext, category: category) {
            return result
        }

        if let result = tryTitleOnly(metadata: metadata, ext: ext, category: category) {
            return result
        }

        if let result = tryDateBasedPattern(metadata: metadata, ext: ext, category: category) {
            return result
        }

        if let result = tryContentExtraction(metadata: metadata, ext: ext, category: category) {
            return result
        }

        if let result = tryFilenameNormalization(originalName: originalName, ext: ext, category: category) {
            return result
        }

        return (nil, .none)
    }

    // MARK: - Strategy: Audio-specific pattern (Artist - Album - Track Title)

    private func tryAudioPattern(
        metadata: FileMetadata, ext: String, category: FileCategory
    ) -> (name: String, confidence: SuggestionConfidence)? {
        guard category == .audio else { return nil }
        guard let title = metadata.title, !title.isEmpty else { return nil }

        var parts: [String] = []

        if let artist = metadata.artist, !artist.isEmpty {
            parts.append(artist)
        }

        if let trackNumber = metadata.trackNumber, trackNumber > 0 {
            parts.append(String(format: "%02d", trackNumber))
        }

        parts.append(title)

        let name = parts.joined(separator: " - ").sanitizedForFilename()
        return ("\(name).\(ext)", .high)
    }

    // MARK: - Strategy: Title + Author (documents, PDFs)

    private func tryTitleAndAuthor(
        metadata: FileMetadata, ext: String, category: FileCategory
    ) -> (name: String, confidence: SuggestionConfidence)? {
        guard category == .pdf || category == .document ||
              category == .spreadsheet || category == .presentation else { return nil }
        guard let title = metadata.title, !title.isEmpty,
              let author = metadata.author, !author.isEmpty else { return nil }

        let datePrefix: String
        if let date = metadata.bestDate {
            datePrefix = "\(date.filenameDate) "
        } else {
            datePrefix = ""
        }

        let name = "\(datePrefix)\(author) - \(title)".sanitizedForFilename()
        return ("\(name).\(ext)", .high)
    }

    // MARK: - Strategy: Title only

    private func tryTitleOnly(
        metadata: FileMetadata, ext: String, category: FileCategory
    ) -> (name: String, confidence: SuggestionConfidence)? {
        guard let title = metadata.title, !title.isEmpty else { return nil }

        // For images/video with just a title, prepend date if available
        if category == .image || category == .video {
            if let date = metadata.bestDate {
                let name = "\(date.filenameDate) \(title)".sanitizedForFilename()
                return ("\(name).\(ext)", .high)
            }
        }

        let datePrefix: String
        if let date = metadata.bestDate {
            datePrefix = "\(date.filenameDate) "
        } else {
            datePrefix = ""
        }

        let name = "\(datePrefix)\(title)".sanitizedForFilename()
        return ("\(name).\(ext)", .medium)
    }

    // MARK: - Strategy: Date-based pattern (photos, videos, screenshots)

    private func tryDateBasedPattern(
        metadata: FileMetadata, ext: String, category: FileCategory
    ) -> (name: String, confidence: SuggestionConfidence)? {
        guard let date = metadata.bestDate else { return nil }

        switch category {
        case .image:
            // Photos: "2024-03-15_143022.jpg"
            let dateStr = date.filenameDateAndTime
            if let camera = metadata.cameraModel {
                let shortCamera = abbreviateCamera(camera)
                let name = "\(dateStr) \(shortCamera)".sanitizedForFilename()
                return ("\(name).\(ext)", .medium)
            }
            return ("\(dateStr).\(ext)", .medium)

        case .video:
            // Videos: "2024-03-15_143022.mp4"
            let dateStr = date.filenameDateAndTime
            return ("\(dateStr).\(ext)", .medium)

        case .pdf, .document, .spreadsheet, .presentation:
            // Documents: just date prefix isn't very useful alone
            return nil

        case .audio:
            return nil
        }
    }

    // MARK: - Strategy: Content-based extraction (PDFs, text docs)

    private func tryContentExtraction(
        metadata: FileMetadata, ext: String, category: FileCategory
    ) -> (name: String, confidence: SuggestionConfidence)? {
        guard let content = metadata.contentSample, !content.isEmpty else { return nil }
        guard category == .pdf || category == .document else { return nil }

        // Try to identify document type from content
        let contentLower = content.lowercased()
        let documentTypes = [
            "invoice", "receipt", "contract", "agreement", "resume",
            "report", "statement", "letter", "memo", "proposal",
            "certificate", "license", "permit", "application", "form"
        ]

        var docType: String?
        for type in documentTypes {
            if contentLower.contains(type) {
                docType = type.capitalized
                break
            }
        }

        // Get the first meaningful line as a potential title
        let firstLine = content.firstMeaningfulLine()

        // Build the suggestion
        let datePrefix: String
        if let date = metadata.bestDate {
            datePrefix = "\(date.filenameDate) "
        } else {
            datePrefix = ""
        }

        if let docType = docType {
            if let firstLine = firstLine, firstLine.count < 60,
               !firstLine.lowercased().contains(docType.lowercased()) {
                let name = "\(datePrefix)\(docType) - \(firstLine)".sanitizedForFilename()
                return ("\(name).\(ext)", .medium)
            } else {
                let name = "\(datePrefix)\(docType)".sanitizedForFilename()
                return ("\(name).\(ext)", .low)
            }
        }

        if let firstLine = firstLine, firstLine.count <= 80 {
            let name = "\(datePrefix)\(firstLine)".sanitizedForFilename()
            return ("\(name).\(ext)", .low)
        }

        return nil
    }

    // MARK: - Strategy: Filename pattern normalization

    private func tryFilenameNormalization(
        originalName: String, ext: String, category: FileCategory
    ) -> (name: String, confidence: SuggestionConfidence)? {
        let name = originalName

        // IMG_20240315_142030 or IMG-20240315-WA0001 (WhatsApp)
        if let result = parseIMGPattern(name: name, ext: ext) {
            return result
        }

        // DSC_0042, DSCF0042, P1000042 (camera default names)
        if isCameraDefaultName(name) {
            return nil // Can't improve without metadata
        }

        // Screenshot 2024-03-15 at 2.30.00 PM
        if let result = parseScreenshotPattern(name: name, ext: ext) {
            return result
        }

        // Screen Recording 2024-03-15 at 2.30.00 PM
        if let result = parseScreenRecordingPattern(name: name, ext: ext) {
            return result
        }

        // Names with underscores or excessive formatting that could be cleaned up
        if let result = cleanupMessyName(name: name, ext: ext) {
            return result
        }

        return nil
    }

    // MARK: - Pattern parsers

    private func parseIMGPattern(name: String, ext: String) -> (String, SuggestionConfidence)? {
        // Match patterns like IMG_20240315_142030 or IMG-20240315-WA0001
        let pattern = #"^(?:IMG|VID|MVIMG|PANO)[_-](\d{4})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})"#
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)) else {
            return nil
        }

        let components = (1...6).compactMap { i -> String? in
            guard let range = Range(match.range(at: i), in: name) else { return nil }
            return String(name[range])
        }
        guard components.count == 6 else { return nil }

        let dateStr = "\(components[0])-\(components[1])-\(components[2])_\(components[3])\(components[4])\(components[5])"
        return ("\(dateStr).\(ext)", .medium)
    }

    private func isCameraDefaultName(_ name: String) -> Bool {
        let cameraPatterns = [
            #"^DSC[_F]?\d+"#,
            #"^P\d{7}"#,
            #"^DCIM\d+"#,
        ]
        for pattern in cameraPatterns {
            if let regex = try? NSRegularExpression(pattern: pattern),
               regex.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)) != nil {
                return true
            }
        }
        return false
    }

    private func parseScreenshotPattern(name: String, ext: String) -> (String, SuggestionConfidence)? {
        // "Screenshot 2024-03-15 at 2.30.00 PM" or "Screenshot 2024-03-15 at 14.30.00"
        let pattern = #"^Screenshot\s+(\d{4}-\d{2}-\d{2})\s+at\s+(\d{1,2})\.(\d{2})\.(\d{2})\s*(AM|PM)?"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
              let match = regex.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)) else {
            return nil
        }

        guard let dateRange = Range(match.range(at: 1), in: name),
              let hourRange = Range(match.range(at: 2), in: name),
              let minRange = Range(match.range(at: 3), in: name),
              let secRange = Range(match.range(at: 4), in: name) else {
            return nil
        }

        let datePart = String(name[dateRange])
        var hour = Int(String(name[hourRange])) ?? 0
        let min = String(name[minRange])
        let sec = String(name[secRange])

        // Handle AM/PM
        if match.range(at: 5).location != NSNotFound,
           let ampmRange = Range(match.range(at: 5), in: name) {
            let ampm = String(name[ampmRange])
            if ampm.uppercased() == "PM" && hour != 12 {
                hour += 12
            } else if ampm.uppercased() == "AM" && hour == 12 {
                hour = 0
            }
        }

        let timeStr = String(format: "%02d%@%@", hour, min, sec)
        let result = "\(datePart)_\(timeStr) Screenshot".sanitizedForFilename()
        return ("\(result).\(ext)", .medium)
    }

    private func parseScreenRecordingPattern(name: String, ext: String) -> (String, SuggestionConfidence)? {
        let pattern = #"^Screen\s+Recording\s+(\d{4}-\d{2}-\d{2})\s+at\s+(\d{1,2})\.(\d{2})\.(\d{2})\s*(AM|PM)?"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
              let match = regex.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)) else {
            return nil
        }

        guard let dateRange = Range(match.range(at: 1), in: name),
              let hourRange = Range(match.range(at: 2), in: name),
              let minRange = Range(match.range(at: 3), in: name),
              let secRange = Range(match.range(at: 4), in: name) else {
            return nil
        }

        let datePart = String(name[dateRange])
        var hour = Int(String(name[hourRange])) ?? 0
        let min = String(name[minRange])
        let sec = String(name[secRange])

        if match.range(at: 5).location != NSNotFound,
           let ampmRange = Range(match.range(at: 5), in: name) {
            let ampm = String(name[ampmRange])
            if ampm.uppercased() == "PM" && hour != 12 {
                hour += 12
            } else if ampm.uppercased() == "AM" && hour == 12 {
                hour = 0
            }
        }

        let timeStr = String(format: "%02d%@%@", hour, min, sec)
        let result = "\(datePart)_\(timeStr) Screen Recording".sanitizedForFilename()
        return ("\(result).\(ext)", .medium)
    }

    private func cleanupMessyName(name: String, ext: String) -> (String, SuggestionConfidence)? {
        var cleaned = name

        // Replace underscores with spaces (common in downloaded files)
        if cleaned.contains("_") && !cleaned.contains(" ") {
            cleaned = cleaned.replacingOccurrences(of: "_", with: " ")
        }

        // Remove common junk suffixes
        let junkPatterns = [
            #"\s*\(\d+\)$"#,           // " (1)" duplicate suffixes
            #"\s*-\s*Copy(\s+\d+)?$"#, // "- Copy" or "- Copy 2"
            #"\s+copy\s*\d*$"#,         // "copy" or "copy 2"
        ]

        for pattern in junkPatterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive) {
                cleaned = regex.stringByReplacingMatches(
                    in: cleaned,
                    range: NSRange(cleaned.startIndex..., in: cleaned),
                    withTemplate: ""
                )
            }
        }

        cleaned = cleaned.sanitizedForFilename()

        // Only suggest if we actually changed something meaningful
        if cleaned != name && cleaned != name.sanitizedForFilename() {
            return ("\(cleaned).\(ext)", .low)
        }

        return nil
    }

    // MARK: - Helpers

    private func abbreviateCamera(_ camera: String) -> String {
        // Shorten common camera names
        var short = camera
            .replacingOccurrences(of: "NIKON CORPORATION", with: "Nikon")
            .replacingOccurrences(of: "Canon EOS", with: "Canon")
            .replacingOccurrences(of: "SONY", with: "Sony")
            .replacingOccurrences(of: "Apple", with: "")
            .trimmingCharacters(in: .whitespaces)

        // Cap length
        if short.count > 30 {
            short = String(short.prefix(30))
        }

        return short
    }
}
