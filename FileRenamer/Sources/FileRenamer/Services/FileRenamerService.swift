import Foundation

/// Performs the actual file rename operations
class FileRenamerService {
    /// History of renames for undo support
    private(set) var renameHistory: [(oldURL: URL, newURL: URL)] = []

    /// Execute renames for all approved/edited files
    /// - Parameter files: Array of scanned files to process
    /// - Returns: Array of results for each file
    func execute(files: [ScannedFile]) -> [RenameResult] {
        var results: [RenameResult] = []
        var usedNames = Set<String>()
        renameHistory = []

        // First pass: collect all existing names in affected directories to prevent conflicts
        let directories = Set(files.map { $0.directory })
        for dir in directories {
            if let contents = try? FileManager.default.contentsOfDirectory(atPath: dir.path) {
                for name in contents {
                    usedNames.insert(name)
                }
            }
        }

        // Process files sequentially to avoid race conditions
        for file in files {
            guard file.action.isActive,
                  let proposedName = file.effectiveName,
                  file.needsRename else {
                results.append(.skipped(from: file.originalURL))
                continue
            }

            // Resolve conflicts
            let finalName = ConflictResolver.resolve(
                proposedName: proposedName,
                in: file.directory,
                existingNames: &usedNames,
                originalName: file.originalName
            )

            let newURL = file.directory.appendingPathComponent(finalName)

            // Verify source still exists
            guard FileManager.default.fileExists(atPath: file.originalURL.path) else {
                results.append(.failure(
                    from: file.originalURL,
                    error: "File no longer exists at original location"
                ))
                continue
            }

            // Perform the rename
            do {
                try FileManager.default.moveItem(at: file.originalURL, to: newURL)
                renameHistory.append((oldURL: file.originalURL, newURL: newURL))
                // Remove old name from used set, keep new name
                usedNames.remove(file.originalName)
                results.append(.success(from: file.originalURL, to: newURL))
            } catch {
                results.append(.failure(
                    from: file.originalURL,
                    error: error.localizedDescription
                ))
            }
        }

        return results
    }

    /// Undo all renames performed in the last execution
    /// - Returns: Number of successfully undone renames
    @discardableResult
    func undoAll() -> Int {
        var undoneCount = 0

        // Undo in reverse order
        for (oldURL, newURL) in renameHistory.reversed() {
            do {
                try FileManager.default.moveItem(at: newURL, to: oldURL)
                undoneCount += 1
            } catch {
                // Log but continue undoing remaining files
                print("Failed to undo rename: \(newURL.lastPathComponent) -> \(oldURL.lastPathComponent): \(error)")
            }
        }

        if undoneCount == renameHistory.count {
            renameHistory = []
        }

        return undoneCount
    }
}
