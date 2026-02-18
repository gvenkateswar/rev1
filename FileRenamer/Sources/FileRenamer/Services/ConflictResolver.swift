import Foundation

/// Handles naming conflicts when proposed filenames already exist
struct ConflictResolver {
    /// Resolve a filename to ensure it doesn't conflict with existing files or other pending renames
    /// - Parameters:
    ///   - proposedName: The desired filename (with extension)
    ///   - directory: The directory where the file will be placed
    ///   - existingNames: Set of names already taken (including other pending renames in the batch)
    ///   - originalName: The file's current name (no conflict if proposed == original)
    /// - Returns: A unique filename, potentially with a numeric suffix
    static func resolve(
        proposedName: String,
        in directory: URL,
        existingNames: inout Set<String>,
        originalName: String
    ) -> String {
        // If the proposed name is the same as the original, no conflict
        if proposedName == originalName {
            return proposedName
        }

        var candidate = proposedName
        var counter = 2

        while existingNames.contains(candidate) ||
              (candidate != originalName && FileManager.default.fileExists(atPath: directory.appendingPathComponent(candidate).path)) {
            let nameWithoutExt = (proposedName as NSString).deletingPathExtension
            let ext = (proposedName as NSString).pathExtension

            if ext.isEmpty {
                candidate = "\(nameWithoutExt) (\(counter))"
            } else {
                candidate = "\(nameWithoutExt) (\(counter)).\(ext)"
            }

            counter += 1

            // Safety valve
            if counter > 999 {
                let uuid = UUID().uuidString.prefix(8)
                if ext.isEmpty {
                    candidate = "\(nameWithoutExt) \(uuid)"
                } else {
                    candidate = "\(nameWithoutExt) \(uuid).\(ext)"
                }
                break
            }
        }

        existingNames.insert(candidate)
        return candidate
    }
}
