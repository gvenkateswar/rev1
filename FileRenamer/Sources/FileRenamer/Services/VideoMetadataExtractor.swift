import Foundation
import AVFoundation
import CoreGraphics

/// Extracts metadata from video files using AVFoundation
@available(macOS 13.0, *)
struct VideoMetadataExtractor: MetadataExtracting {
    func extract(from url: URL) async -> FileMetadata {
        var metadata = SpotlightMetadataReader.readMetadata(from: url)

        let asset = AVURLAsset(url: url)

        do {
            // Common metadata
            let commonMetadata = try await asset.load(.commonMetadata)

            for item in commonMetadata {
                guard let commonKey = item.commonKey else { continue }

                switch commonKey {
                case .commonKeyTitle:
                    if let value = try? await item.load(.stringValue), !value.isEmpty {
                        metadata.title = value
                    }
                case .commonKeyCreationDate:
                    if let value = try? await item.load(.stringValue), !value.isEmpty {
                        let formatter = ISO8601DateFormatter()
                        if let date = formatter.date(from: value) {
                            metadata.creationDate = date
                        }
                    }
                case .commonKeyArtist, .commonKeyAuthor:
                    if let value = try? await item.load(.stringValue), !value.isEmpty {
                        metadata.author = value
                    }
                default:
                    break
                }
            }

            // Duration
            let duration = try await asset.load(.duration)
            metadata.duration = CMTimeGetSeconds(duration)

            // Video resolution from tracks
            let videoTracks = try await asset.loadTracks(withMediaType: .video)
            if let videoTrack = videoTracks.first {
                let size = try await videoTrack.load(.naturalSize)
                metadata.resolution = size
            }

            // Get creation date from asset
            if metadata.creationDate == nil {
                let creationDate = try await asset.load(.creationDate)
                if let dateValue = try? await creationDate?.load(.dateValue) {
                    metadata.creationDate = dateValue
                }
            }

        } catch {
            // Metadata extraction failed; return what Spotlight gave us
        }

        return metadata
    }
}
