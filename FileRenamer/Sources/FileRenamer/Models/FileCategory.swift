import Foundation

/// Categories of user files the app supports
enum FileCategory: String, CaseIterable, Identifiable, Hashable {
    case pdf
    case audio
    case video
    case document
    case image
    case spreadsheet
    case presentation

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .pdf: return "PDF"
        case .audio: return "Audio"
        case .video: return "Video"
        case .document: return "Document"
        case .image: return "Image"
        case .spreadsheet: return "Spreadsheet"
        case .presentation: return "Presentation"
        }
    }

    var icon: String {
        switch self {
        case .pdf: return "doc.richtext"
        case .audio: return "music.note"
        case .video: return "film"
        case .document: return "doc.text"
        case .image: return "photo"
        case .spreadsheet: return "tablecells"
        case .presentation: return "rectangle.on.rectangle"
        }
    }

    /// All file extensions belonging to this category
    var extensions: Set<String> {
        switch self {
        case .pdf:
            return ["pdf"]
        case .audio:
            return ["mp3", "wav", "aac", "flac", "m4a", "aiff", "ogg", "wma"]
        case .video:
            return ["mp4", "mov", "avi", "mkv", "wmv", "m4v", "webm"]
        case .document:
            return ["doc", "docx", "txt", "rtf", "odt", "pages"]
        case .image:
            return ["jpg", "jpeg", "png", "heic", "heif", "tiff", "tif", "bmp", "gif", "webp"]
        case .spreadsheet:
            return ["xls", "xlsx", "csv", "numbers", "ods"]
        case .presentation:
            return ["ppt", "pptx", "key", "odp"]
        }
    }

    /// All supported file extensions across all categories
    static var allExtensions: Set<String> {
        var all = Set<String>()
        for category in allCases {
            all.formUnion(category.extensions)
        }
        return all
    }

    /// Determine category from a file extension
    static func from(extension ext: String) -> FileCategory? {
        let lower = ext.lowercased()
        for category in allCases {
            if category.extensions.contains(lower) {
                return category
            }
        }
        return nil
    }
}
