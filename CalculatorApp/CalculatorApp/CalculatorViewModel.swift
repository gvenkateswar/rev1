import SwiftUI

/// Drives a standard four-function calculator.
///
/// The source of truth is `rawDisplay`: a plain Western digit string the engine
/// always computes in. The view renders it through the selected `NumeralSystem`,
/// so the math never has to know which script the user is looking at.
@MainActor
final class CalculatorViewModel: ObservableObject {

    enum Operation: String, Equatable {
        case add = "+"
        case subtract = "−"
        case multiply = "×"
        case divide = "÷"

        func apply(_ a: Double, _ b: Double) -> Double {
            switch self {
            case .add:      return a + b
            case .subtract: return a - b
            case .multiply: return a * b
            case .divide:   return b == 0 ? .nan : a / b
            }
        }
    }

    @Published var system: NumeralSystem = .western
    @Published private(set) var rawDisplay: String = "0"

    private var accumulator: Double?
    private var pendingOperation: Operation?
    private var isTypingNumber = false

    private let maxDigits = 15

    /// What the screen shows, rendered in the active numeral system.
    var display: String { system.format(westernDigits: rawDisplay) }

    /// The operation currently armed (for highlighting its key), if any.
    var activeOperation: Operation? {
        isTypingNumber ? nil : pendingOperation
    }

    // MARK: - Button dispatch

    func handle(_ button: CalcButton) {
        switch button {
        case .digit(let d):  inputDigit(d)
        case .decimal:       inputDecimal()
        case .op(let op):    setOperation(op)
        case .equals:        equals()
        case .clear:         clear()
        case .sign:          toggleSign()
        case .percent:       percent()
        }
    }

    // MARK: - Input

    private func inputDigit(_ d: Int) {
        guard isErrorFree else { clear() ; return inputDigit(d) }
        if isTypingNumber {
            switch rawDisplay {
            case "0":  rawDisplay = String(d)
            case "-0": rawDisplay = "-" + String(d)
            default:
                if digitCount < maxDigits { rawDisplay += String(d) }
            }
        } else {
            rawDisplay = String(d)
            isTypingNumber = true
        }
    }

    private func inputDecimal() {
        guard isErrorFree else { clear(); return }
        if !isTypingNumber {
            rawDisplay = "0"
            isTypingNumber = true
        }
        if !rawDisplay.contains(".") { rawDisplay += "." }
    }

    // MARK: - Operations

    private func setOperation(_ op: Operation) {
        guard isErrorFree else { return }
        let value = Double(rawDisplay) ?? 0
        if let acc = accumulator, let pending = pendingOperation, isTypingNumber {
            let result = pending.apply(acc, value)
            accumulator = result
            rawDisplay = CalculatorViewModel.string(from: result)
        } else {
            accumulator = value
        }
        pendingOperation = op
        isTypingNumber = false
    }

    private func equals() {
        guard isErrorFree, let acc = accumulator, let pending = pendingOperation else { return }
        let value = Double(rawDisplay) ?? 0
        let result = pending.apply(acc, value)
        rawDisplay = CalculatorViewModel.string(from: result)
        accumulator = nil
        pendingOperation = nil
        isTypingNumber = false
    }

    private func clear() {
        rawDisplay = "0"
        accumulator = nil
        pendingOperation = nil
        isTypingNumber = false
    }

    private func toggleSign() {
        guard isErrorFree else { return }
        if rawDisplay.hasPrefix("-") {
            rawDisplay.removeFirst()
        } else if rawDisplay != "0" {
            rawDisplay = "-" + rawDisplay
        }
    }

    private func percent() {
        guard isErrorFree else { return }
        let value = Double(rawDisplay) ?? 0
        rawDisplay = CalculatorViewModel.string(from: value / 100)
        isTypingNumber = false
    }

    // MARK: - Helpers

    private var isErrorFree: Bool { rawDisplay != "Error" }

    private var digitCount: Int {
        rawDisplay.filter { $0.isNumber }.count
    }

    /// Format a `Double` back into a clean Western string, dropping a trailing
    /// ".0" for whole numbers and collapsing non-finite results to "Error".
    static func string(from value: Double) -> String {
        guard value.isFinite else { return "Error" }
        if value == value.rounded(.towardZero), abs(value) < 1e15 {
            return String(Int(value))
        }
        // Trim floating-point noise to a sensible number of significant digits.
        var s = String(format: "%.10g", value)
        if s.contains("."), !s.contains("e"), !s.contains("E") {
            while s.hasSuffix("0") { s.removeLast() }
            if s.hasSuffix(".") { s.removeLast() }
        }
        return s
    }
}
