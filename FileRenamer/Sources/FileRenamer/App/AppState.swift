import Foundation
import SwiftUI

/// Central application state that orchestrates scanning, extraction, suggestion, and renaming
@MainActor
class AppState: ObservableObject {
    // MARK: - Published state

    @Published var selectedFolder: URL?
    @Published var scannedFiles: [ScannedFile] = []
    @Published var isScanning = false
    @Published var isRenaming = false
    @Published var scanProgress: Double = 0
    @Published var renameResults: [RenameResult]?
    @Published var errorMessage: String?
    @Published var showingSummary = false
    @Published var filterCategory: FileCategory?
    @Published var searchText = ""
    @Published var scanRecursively = true

    // MARK: - Services

    private let scanner = FolderScanner()
    private let suggestionEngine = RenameSuggestionEngine()
    let renamerService = FileRenamerService()

    // MARK: - Computed properties

    var filteredFiles: [ScannedFile] {
        var files = scannedFiles

        if let category = filterCategory {
            files = files.filter { $0.category == category }
        }

        if !searchText.isEmpty {
            let query = searchText.lowercased()
            files = files.filter {
                $0.originalName.lowercased().contains(query) ||
                ($0.suggestedName?.lowercased().contains(query) ?? false)
            }
        }

        return files
    }

    var approvedCount: Int {
        scannedFiles.filter { $0.action.isActive && $0.needsRename }.count
    }

    var totalCount: Int {
        scannedFiles.count
    }

    var categoryCounts: [FileCategory: Int] {
        var counts: [FileCategory: Int] = [:]
        for file in scannedFiles {
            counts[file.category, default: 0] += 1
        }
        return counts
    }

    var successCount: Int {
        renameResults?.filter { $0.success && $0.newURL != nil }.count ?? 0
    }

    var failureCount: Int {
        renameResults?.filter { !$0.success }.count ?? 0
    }

    // MARK: - Actions

    func selectFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.message = "Choose a folder to scan for files to rename"
        panel.prompt = "Scan Folder"

        if panel.runModal() == .OK, let url = panel.url {
            selectedFolder = url
            Task {
                await scanFolder()
            }
        }
    }

    func scanFolder() async {
        guard let folder = selectedFolder else { return }

        isScanning = true
        scanProgress = 0
        scannedFiles = []
        errorMessage = nil
        renameResults = nil
        showingSummary = false

        do {
            // Phase 1: Scan for files
            let urls = try scanner.scan(directory: folder, recursive: scanRecursively)

            if urls.isEmpty {
                errorMessage = "No supported files found in the selected folder."
                isScanning = false
                return
            }

            let total = Double(urls.count)

            // Phase 2: Extract metadata and generate suggestions
            var files: [ScannedFile] = []

            for (index, url) in urls.enumerated() {
                guard let category = url.fileCategory else { continue }

                let extractor = MetadataExtractorFactory.extractor(for: category)
                let metadata = await extractor.extract(from: url)

                let (suggestedName, confidence) = suggestionEngine.suggest(
                    metadata: metadata,
                    originalURL: url,
                    category: category
                )

                let scannedFile = ScannedFile(
                    originalURL: url,
                    category: category,
                    metadata: metadata,
                    suggestedName: suggestedName,
                    confidence: confidence
                )

                files.append(scannedFile)
                scanProgress = Double(index + 1) / total
            }

            scannedFiles = files

        } catch {
            errorMessage = "Scan failed: \(error.localizedDescription)"
        }

        isScanning = false
    }

    func renameApproved() {
        guard !isRenaming else { return }

        isRenaming = true
        let filesToRename = scannedFiles.filter { $0.action.isActive && $0.needsRename }
        renameResults = renamerService.execute(files: filesToRename)
        isRenaming = false
        showingSummary = true
    }

    func undoRenames() {
        let undone = renamerService.undoAll()
        if undone > 0 {
            // Re-scan to refresh the file list
            Task {
                await scanFolder()
            }
        }
    }

    func approveAll() {
        for file in filteredFiles {
            if file.suggestedName != nil {
                file.action = .approved
            }
        }
        objectWillChange.send()
    }

    func skipAll() {
        for file in filteredFiles {
            file.action = .skipped
        }
        objectWillChange.send()
    }
}
