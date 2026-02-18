import Foundation

extension String {
    /// Sanitize a string for use as a filename
    func sanitizedForFilename() -> String {
        var result = self

        // Replace characters illegal in macOS filenames
        let illegalChars = CharacterSet(charactersIn: "/:\0")
        result = result.unicodeScalars
            .map { illegalChars.contains($0) ? "-" : String($0) }
            .joined()

        // Replace common problematic characters
        result = result.replacingOccurrences(of: "\\", with: "-")
        result = result.replacingOccurrences(of: "\"", with: "'")

        // Collapse multiple spaces into one
        while result.contains("  ") {
            result = result.replacingOccurrences(of: "  ", with: " ")
        }

        // Collapse multiple dashes into one
        while result.contains("--") {
            result = result.replacingOccurrences(of: "--", with: "-")
        }

        // Trim whitespace and dashes from edges
        result = result.trimmingCharacters(in: .whitespacesAndNewlines)
        result = result.trimmingCharacters(in: CharacterSet(charactersIn: "-"))

        // Don't start with a dot (hidden file)
        if result.hasPrefix(".") {
            result = String(result.dropFirst())
        }

        // Truncate to 200 characters (before extension) to stay well within the 255-byte APFS limit
        if result.count > 200 {
            result = String(result.prefix(200))
        }

        // If nothing remains, use a fallback
        if result.isEmpty {
            result = "Untitled"
        }

        return result
    }

    /// Capitalize the first letter of each word, lowercasing the rest
    func titleCased() -> String {
        self.lowercased()
            .split(separator: " ")
            .map { word in
                guard let first = word.first else { return String(word) }
                return String(first).uppercased() + word.dropFirst()
            }
            .joined(separator: " ")
    }

    /// Extract the first meaningful line from a text sample (skipping blanks)
    func firstMeaningfulLine() -> String? {
        let lines = self.components(separatedBy: .newlines)
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty && trimmed.count >= 3 && trimmed.count <= 150 {
                return trimmed
            }
        }
        return nil
    }
}
