import Foundation

/// The numeral scripts the calculator can render results in.
///
/// Positional systems (Western, Eastern-Arabic, Devanagari) share the same
/// place-value math and differ only in the ten digit glyphs. Roman is special:
/// it is non-positional, has no zero, and only represents whole numbers in a
/// limited range, so it is rendered by converting the underlying value.
enum NumeralSystem: String, CaseIterable, Identifiable {
    case western
    case easternArabic
    case devanagari
    case roman

    var id: String { rawValue }

    /// Short label shown in the picker.
    var shortName: String {
        switch self {
        case .western: return "1 2 3"
        case .easternArabic: return "١ ٢ ٣"
        case .devanagari: return "१ २ ३"
        case .roman: return "I II III"
        }
    }

    /// The ten glyphs for digits 0...9, or `nil` for non-positional Roman.
    var digitGlyphs: [Character]? {
        switch self {
        case .western:       return Array("0123456789")
        case .easternArabic: return Array("٠١٢٣٤٥٦٧٨٩")   // U+0660…U+0669
        case .devanagari:    return Array("०१२३४५६७८९")   // U+0966…U+096F
        case .roman:         return nil
        }
    }

    /// Glyphs to paint on the keypad digit keys. Roman has no positional
    /// digits, so you still type with Western digits while the *result*
    /// renders as Roman.
    var keypadGlyphs: [Character] {
        digitGlyphs ?? Array("0123456789")
    }

    /// Render a value held as a plain Western digit string (e.g. "-12.5")
    /// into this numeral system for display.
    func format(westernDigits string: String) -> String {
        // Non-numeric sentinels like "Error" pass straight through.
        if string == "Error" { return string }

        guard let glyphs = digitGlyphs else {
            return NumeralSystem.roman(fromWesternDigits: string)
        }

        var out = ""
        for ch in string {
            if let value = ch.wholeNumberValue, ch.isASCII, ch.isNumber {
                out.append(glyphs[value])
            } else {
                out.append(ch) // '.', '-', etc.
            }
        }
        return out
    }

    // MARK: - Roman conversion

    /// Convert a Western digit string into a Roman numeral.
    ///
    /// Classic Roman numerals only express the integers 1...3999. For anything
    /// outside that range (zero, negatives, fractions, partial input) we fall
    /// back to the Western string so the display stays honest rather than wrong.
    static func roman(fromWesternDigits string: String) -> String {
        guard let value = Double(string) else {
            // Partial entry such as "-" or "" — nothing to convert yet.
            return string
        }
        if value == 0 { return "N" }            // medieval "nulla"
        let truncated = value.rounded(.towardZero)
        guard value == truncated, value > 0, value < 4000 else {
            return string                        // not representable in Roman
        }

        var n = Int(value)
        let table: [(Int, String)] = [
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        ]
        var result = ""
        for (magnitude, symbol) in table {
            while n >= magnitude {
                result += symbol
                n -= magnitude
            }
        }
        return result
    }
}
