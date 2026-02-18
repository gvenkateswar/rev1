import SwiftUI

/// Main entry point for the FileRenamer application
@main
struct FileRenamerApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 1000, height: 700)
        .commands {
            // File menu
            CommandGroup(replacing: .newItem) {
                Button("Open Folder...") {
                    appState.selectFolder()
                }
                .keyboardShortcut("o")

                if appState.selectedFolder != nil {
                    Button("Rescan") {
                        Task {
                            await appState.scanFolder()
                        }
                    }
                    .keyboardShortcut("r")
                }
            }

            // Edit menu additions
            CommandGroup(after: .pasteboard) {
                Divider()

                Button("Approve All") {
                    appState.approveAll()
                }
                .keyboardShortcut("a", modifiers: [.command, .shift])
                .disabled(appState.scannedFiles.isEmpty)

                Button("Skip All") {
                    appState.skipAll()
                }
                .disabled(appState.scannedFiles.isEmpty)

                Divider()

                Button("Rename Approved Files") {
                    appState.renameApproved()
                }
                .keyboardShortcut(.return, modifiers: .command)
                .disabled(appState.approvedCount == 0)

                if !appState.renamerService.renameHistory.isEmpty {
                    Button("Undo All Renames") {
                        appState.undoRenames()
                    }
                    .keyboardShortcut("z", modifiers: [.command, .shift])
                }
            }
        }
    }
}
