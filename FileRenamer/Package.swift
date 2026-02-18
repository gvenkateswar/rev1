// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "FileRenamer",
    platforms: [
        .macOS(.v14)
    ],
    targets: [
        .executableTarget(
            name: "FileRenamer",
            path: "Sources/FileRenamer",
            linkerSettings: [
                .linkedFramework("PDFKit"),
                .linkedFramework("AVFoundation"),
                .linkedFramework("CoreServices"),
                .linkedFramework("QuartzCore"),
            ]
        )
    ]
)
