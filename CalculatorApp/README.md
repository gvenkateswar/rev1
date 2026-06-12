# Numeral Calculator (iOS)

A SwiftUI four-function calculator that renders results in four numeral
systems — switchable live with the segmented control at the top:

| Mode          | Digits          | Example (2026) |
|---------------|-----------------|----------------|
| Western       | `0123456789`    | `2026`         |
| Arabic        | `٠١٢٣٤٥٦٧٨٩` (Eastern Arabic-Indic) | `٢٠٢٦` |
| Devanagari    | `०१२३४५६७८९`    | `२०२६`         |
| Roman         | `I V X L C D M` | `MMXXVI`       |

## How it works

- The engine always computes in plain Western digits; the chosen
  `NumeralSystem` only affects how the value is **displayed**. Switching
  systems mid-calculation is purely cosmetic and never changes the math.
- **Positional systems** (Western / Arabic / Devanagari) just remap the ten
  digit glyphs, so every value — including decimals and negatives — renders
  correctly.
- **Roman numerals** are non-positional and only express the integers
  `1…3999`. The display converts the live value on the fly; zero shows as
  `N` (medieval *nulla*), and anything Roman can't represent (negatives,
  fractions, ≥ 4000) gracefully falls back to the Western form. You still
  type with the digit keys — only the answer is rendered in Roman.

## Project layout

```
CalculatorApp/
  CalculatorApp.xcodeproj/        # Xcode project
  CalculatorApp/
    CalculatorAppApp.swift        # @main app entry
    ContentView.swift             # Keypad + display UI, button styling
    CalculatorViewModel.swift     # Calculator engine (Western-digit source of truth)
    NumeralSystem.swift           # The four scripts + Roman conversion
    Assets.xcassets/              # App icon + accent color slots
```

## Build & run

Requires a Mac with Xcode 15+ (deployment target iOS 16).

```sh
open CalculatorApp/CalculatorApp.xcodeproj
```

Pick an iPhone simulator and press ⌘R. No third-party dependencies.
