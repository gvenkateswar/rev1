import Foundation
import ImageIO
import CoreGraphics

/// Extracts metadata from image files using ImageIO (EXIF, TIFF, etc.)
@available(macOS 13.0, *)
struct ImageMetadataExtractor: MetadataExtracting {
    func extract(from url: URL) async -> FileMetadata {
        var metadata = SpotlightMetadataReader.readMetadata(from: url)

        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
            return metadata
        }

        guard let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [String: Any] else {
            return metadata
        }

        // EXIF data
        if let exif = properties[kCGImagePropertyExifDictionary as String] as? [String: Any] {
            // Date taken
            if let dateString = exif[kCGImagePropertyExifDateTimeOriginal as String] as? String {
                let formatter = DateFormatter()
                formatter.dateFormat = "yyyy:MM:dd HH:mm:ss"
                formatter.locale = Locale(identifier: "en_US_POSIX")
                if let date = formatter.date(from: dateString) {
                    metadata.dateTaken = date
                    if metadata.creationDate == nil {
                        metadata.creationDate = date
                    }
                }
            }

            // Image dimensions from EXIF
            if let width = exif[kCGImagePropertyExifPixelXDimension as String] as? Int,
               let height = exif[kCGImagePropertyExifPixelYDimension as String] as? Int {
                metadata.resolution = CGSize(width: width, height: height)
            }
        }

        // TIFF data (camera info)
        if let tiff = properties[kCGImagePropertyTIFFDictionary as String] as? [String: Any] {
            if let model = tiff[kCGImagePropertyTIFFModel as String] as? String {
                metadata.cameraModel = model.trimmingCharacters(in: .whitespacesAndNewlines)
            }

            if let make = tiff[kCGImagePropertyTIFFMake as String] as? String {
                let maker = make.trimmingCharacters(in: .whitespacesAndNewlines)
                if let existingModel = metadata.cameraModel {
                    // Avoid duplication like "Apple iPhone 15"
                    if !existingModel.lowercased().contains(maker.lowercased()) {
                        metadata.cameraModel = "\(maker) \(existingModel)"
                    }
                } else {
                    metadata.cameraModel = maker
                }
            }

            // Date from TIFF
            if metadata.dateTaken == nil,
               let dateString = tiff[kCGImagePropertyTIFFDateTime as String] as? String {
                let formatter = DateFormatter()
                formatter.dateFormat = "yyyy:MM:dd HH:mm:ss"
                formatter.locale = Locale(identifier: "en_US_POSIX")
                if let date = formatter.date(from: dateString) {
                    metadata.dateTaken = date
                }
            }
        }

        // Image dimensions from top-level properties (fallback)
        if metadata.resolution == nil {
            if let width = properties[kCGImagePropertyPixelWidth as String] as? Int,
               let height = properties[kCGImagePropertyPixelHeight as String] as? Int {
                metadata.resolution = CGSize(width: width, height: height)
            }
        }

        // GPS data could be used for location-based naming in the future
        // Skipping for now to keep scope manageable

        return metadata
    }
}
