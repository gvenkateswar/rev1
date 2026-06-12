import SwiftUI

/// A single key on the keypad.
enum CalcButton: Hashable {
    case digit(Int)
    case decimal
    case op(CalculatorViewModel.Operation)
    case equals
    case clear
    case sign
    case percent

    func label(for system: NumeralSystem) -> String {
        switch self {
        case .digit(let d): return String(system.keypadGlyphs[d])
        case .decimal:      return "."
        case .op(let op):   return op.rawValue
        case .equals:       return "="
        case .clear:        return "AC"
        case .sign:         return "±"
        case .percent:      return "%"
        }
    }

    var background: Color {
        switch self {
        case .clear, .sign, .percent:
            return Color(white: 0.40)
        case .op, .equals:
            return .orange
        case .digit, .decimal:
            return Color(white: 0.20)
        }
    }

    var foreground: Color {
        switch self {
        case .clear, .sign, .percent: return .black
        default: return .white
        }
    }
}

struct ContentView: View {
    @StateObject private var vm = CalculatorViewModel()

    private let rows: [[CalcButton]] = [
        [.clear, .sign, .percent, .op(.divide)],
        [.digit(7), .digit(8), .digit(9), .op(.multiply)],
        [.digit(4), .digit(5), .digit(6), .op(.subtract)],
        [.digit(1), .digit(2), .digit(3), .op(.add)],
        [.digit(0), .decimal, .equals],
    ]

    var body: some View {
        VStack(spacing: 16) {
            Picker("Numerals", selection: $vm.system) {
                ForEach(NumeralSystem.allCases) { system in
                    Text(system.shortName).tag(system)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 8)

            Spacer(minLength: 0)

            HStack {
                Spacer()
                Text(vm.display)
                    .font(.system(size: 80, weight: .light))
                    .foregroundColor(.white)
                    .lineLimit(1)
                    .minimumScaleFactor(0.25)
            }
            .padding(.horizontal, 24)

            keypad
        }
        .background(Color.black.ignoresSafeArea())
        .preferredColorScheme(.dark)
    }

    private var keypad: some View {
        GeometryReader { geo in
            let spacing: CGFloat = 12
            let size = (geo.size.width - spacing * 5) / 4
            VStack(spacing: spacing) {
                ForEach(rows.indices, id: \.self) { r in
                    HStack(spacing: spacing) {
                        ForEach(rows[r].indices, id: \.self) { c in
                            keyView(rows[r][c], size: size, spacing: spacing)
                        }
                    }
                }
            }
            .frame(maxHeight: .infinity, alignment: .bottom)
            .padding(.horizontal, spacing)
            .padding(.bottom, spacing)
        }
        .frame(height: 5 * (UIScreen.main.bounds.width - 60) / 4 + 6 * 12)
    }

    private func keyView(_ button: CalcButton, size: CGFloat, spacing: CGFloat) -> some View {
        let isZero = button == .digit(0)
        let width = isZero ? size * 2 + spacing : size
        let isActive = isOperation(button) && vm.activeOperation == operation(of: button)

        return Button {
            vm.handle(button)
        } label: {
            Text(button.label(for: vm.system))
                .font(.system(size: 34, weight: .medium))
                .frame(width: width, height: size, alignment: isZero ? .leading : .center)
                .padding(.leading, isZero ? size * 0.36 : 0)
                .background(isActive ? Color.white : button.background)
                .foregroundColor(isActive ? .orange : button.foreground)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private func isOperation(_ button: CalcButton) -> Bool {
        if case .op = button { return true }
        return false
    }

    private func operation(of button: CalcButton) -> CalculatorViewModel.Operation? {
        if case .op(let op) = button { return op }
        return nil
    }
}

#Preview {
    ContentView()
}
