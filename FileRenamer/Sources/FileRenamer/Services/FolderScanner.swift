import Foundation

/// Scans a directory for supported user files
struct FolderScanner {
    /// Scan a folder and return URLs of all supported files
    /// - Parameters:
    ///   - directory: The root directory to scan
    ///   - recursive: Whether to scan subdirectories
    /// - Returns: Array of file URLs that match supported categories
    func scan(directory: URL, recursive: Bool = true) throws -> [URL] {
        let keys: [URLResourceKey] = [.isRegularFileKey, .isHiddenKey, .nameKey]

        var options: FileManager.DirectoryEnumerationOptions = [.skipsPackageDescendants]
        if !recursive {
            options.insert(.skipsSubdirectoryDescendants)
        }

        guard let enumerator = FileManager.default.enumerator(
            at: directory,
            includingPropertiesForKeys: keys,
            options: options
        ) else {
            throw ScanError.cannotAccessDirectory(directory.path)
        }

        var results: [URL] = []

        for case let fileURL as URL in enumerator {
            // Skip hidden files and directories
            if let resourceValues = try? fileURL.resourceValues(forKeys: Set(keys)) {
                if resourceValues.isHidden == true {
                    continue
                }
                // Only include regular files
                guard resourceValues.isRegularFile == true else {
                    continue
                }
            }

            // Skip files starting with "."
            if fileURL.lastPathComponent.hasPrefix(".") {
                continue
            }

            // Check if the file has a supported extension
            if fileURL.isSupportedFile {
                results.append(fileURL)
            }
        }

        return results.sorted { $0.path < $1.path }
    }
}

enum ScanError: LocalizedError {
    case cannotAccessDirectory(String)

    var errorDescription: String? {
        switch self {
        case .cannotAccessDirectory(let path):
            return "Cannot access directory: \(path)"
        }
    }
}
