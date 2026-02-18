import Foundation

extension DateFormatter {
    /// Standard date format for filenames: "2024-03-15"
    static let filenameDateOnly: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }()

    /// Date and time format for filenames: "2024-03-15_143022"
    static let filenameDateAndTime: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd_HHmmss"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter
    }()

    /// Human-readable date: "Mar 15, 2024"
    static let displayDate: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .none
        return formatter
    }()

    /// Human-readable date and time: "Mar 15, 2024 at 2:30 PM"
    static let displayDateTime: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter
    }()
}

extension Date {
    /// Format for use in a filename (date only)
    var filenameDate: String {
        DateFormatter.filenameDateOnly.string(from: self)
    }

    /// Format for use in a filename (date and time)
    var filenameDateAndTime: String {
        DateFormatter.filenameDateAndTime.string(from: self)
    }
}
