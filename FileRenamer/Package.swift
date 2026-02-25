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
            exclude: ["Resources/Info.plist"],
            linkerSettings: [
                .linkedFramework("PDFKit"),
                .linkedFramework("AVFoundation"),
                .linkedFramework("CoreServices"),
                .linkedFramework("QuartzCore"),
                .unsafeFlags([
                    "-Xlinker", "-sectcreate",
                    "-Xlinker", "__TEXT",
                    "-Xlinker", "__info_plist",
                    "-Xlinker", "Sources/FileRenamer/Resources/Info.plist",
                ]),
            ]
        )
    ]
)
