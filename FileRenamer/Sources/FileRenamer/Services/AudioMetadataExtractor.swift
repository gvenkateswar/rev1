import Foundation
import AVFoundation

/// Extracts metadata from audio files using AVFoundation
struct AudioMetadataExtractor: MetadataExtracting {
    func extract(from url: URL) async -> FileMetadata {
        var metadata = SpotlightMetadataReader.readMetadata(from: url)

        let asset = AVURLAsset(url: url)

        do {
            let commonMetadata = try await asset.load(.commonMetadata)

            for item in commonMetadata {
                guard let commonKey = item.commonKey else { continue }

                switch commonKey {
                case .commonKeyTitle:
                    if let value = try? await item.load(.stringValue), !value.isEmpty {
                        metadata.title = value
                    }
                case .commonKeyArtist:
                    if let value = try? await item.load(.stringValue), !value.isEmpty {
                        metadata.artist = value
                    }
                case .commonKeyAlbumName:
                    if let value = try? await item.load(.stringValue), !value.isEmpty {
                        metadata.album = value
                    }
                case .commonKeyCreationDate:
                    if let value = try? await item.load(.stringValue), !value.isEmpty {
                        // Try to parse the date string
                        let formatter = ISO8601DateFormatter()
                        if let date = formatter.date(from: value) {
                            metadata.creationDate = date
                        } else {
                            // Try year-only format
                            let yearFormatter = DateFormatter()
                            yearFormatter.dateFormat = "yyyy"
                            if let date = yearFormatter.date(from: value) {
                                metadata.creationDate = date
                            }
                        }
                    }
                case .commonKeyAuthor:
                    if let value = try? await item.load(.stringValue), !value.isEmpty {
                        metadata.author = value
                    }
                default:
                    break
                }
            }

            // Try to get track number from iTunes metadata
            let formats = try await asset.load(.availableMetadataFormats)
            for format in formats {
                let formatMetadata = try await asset.loadMetadata(for: format)
                for item in formatMetadata {
                    if let key = item.key as? String {
                        if key.contains("trackNumber") || key.contains("TRCK") {
                            if let value = try? await item.load(.numberValue) {
                                metadata.trackNumber = value.intValue
                            }
                        }
                        if key.contains("genre") || key.contains("TCON") {
                            if let value = try? await item.load(.stringValue) {
                                metadata.genre = value
                            }
                        }
                    }
                }
            }

            // Get duration
            let duration = try await asset.load(.duration)
            metadata.duration = CMTimeGetSeconds(duration)

        } catch {
            // Metadata extraction failed; return what Spotlight gave us
        }

        return metadata
    }
}
