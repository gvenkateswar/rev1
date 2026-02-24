# Mac EXE Runner

Run Windows `.exe` files on macOS — no Windows installation required.

Uses [Wine](https://www.winehq.org), an open-source compatibility layer that translates Windows API calls into macOS equivalents in real-time.

## Quick Start

```bash
# 1. First-time setup (installs Homebrew + Wine if needed)
./setup.sh

# 2. Run any .exe file
./mac-exe-runner.sh run MyApp.exe
```

That's it. The setup handles everything automatically.

## Commands

| Command | Description |
|---------|-------------|
| `./mac-exe-runner.sh run <file.exe> [args]` | Run a Windows .exe file |
| `./mac-exe-runner.sh setup` | Install all dependencies |
| `./mac-exe-runner.sh status` | Check what's installed |
| `./mac-exe-runner.sh config winecfg` | Configure Wine (Windows version, etc.) |
| `./mac-exe-runner.sh config regedit` | Open Windows registry editor |
| `./mac-exe-runner.sh kill` | Stop all Wine processes |
| `./mac-exe-runner.sh reset` | Delete Wine prefix and start fresh |
| `./mac-exe-runner.sh help` | Show full help |

## Examples

```bash
# Run an exe
./mac-exe-runner.sh run ~/Downloads/installer.exe

# Run with arguments
./mac-exe-runner.sh run setup.exe /S /D=C:\\MyApp

# Shortcut: pass .exe directly (auto-detected)
./mac-exe-runner.sh game.exe

# Use a separate Wine prefix for an app
WINE_PREFIX=~/my-app-wine ./mac-exe-runner.sh run app.exe

# Change the emulated Windows version
./mac-exe-runner.sh config winecfg
```

## What Gets Installed

The setup script installs via [Homebrew](https://brew.sh):

1. **Homebrew** (if not present) — the macOS package manager
2. **Rosetta 2** (Apple Silicon only) — Apple's x86 translation layer
3. **Wine CrossOver** (Apple Silicon) or **Wine Stable** (Intel) — the Windows compatibility layer (~1-2 GB)

On Apple Silicon Macs, the script automatically installs **wine-crossover** instead of wine-stable. This is required because standard Wine cannot run 32-bit Windows apps through Rosetta 2 (it hits an unsupported CPU feature called LDT). Wine CrossOver includes a special `wine32on64` thunking layer that solves this.

A **Wine prefix** (`~/.wine`) is also created, which acts as a virtual `C:\` drive (~500 MB). You can delete it anytime with `./mac-exe-runner.sh reset`.

## How It Works

Wine is **not** an emulator or virtual machine. It implements the Windows API (Win32) natively on macOS, translating Windows system calls to macOS equivalents on the fly. This means:

- No Windows license needed
- No performance overhead from virtualization
- Most Windows apps run at near-native speed
- ~80% of Windows applications work (check [Wine AppDB](https://appdb.winehq.org) for compatibility)

## Compatibility

- **macOS**: Intel and Apple Silicon (M1/M2/M3/M4) Macs
- **Works well with**: Most desktop apps, games, installers, utilities
- **May not work with**: Apps requiring very recent Windows APIs, kernel-level drivers, or anti-cheat software

## Troubleshooting

**"rosetta error: LDT not supported" on Apple Silicon?**
- You're using `wine-stable` which can't run 32-bit apps on Apple Silicon. Run setup to switch:
  ```bash
  ./mac-exe-runner.sh reset
  ./mac-exe-runner.sh setup
  ```
  This will install `wine-crossover` which supports 32-bit apps.

**App won't start?**
- Try changing the Windows version: `./mac-exe-runner.sh config winecfg` → set to Windows 10
- Check the log file: `.exe-runner.log` in this directory

**Graphics issues?**
- Some apps need specific DLLs. Consider installing [Winetricks](https://github.com/Winetricks/winetricks) for additional libraries:
  ```bash
  brew install winetricks
  winetricks vcrun2019 dotnet48
  ```

**Want a completely fresh start?**
```bash
./mac-exe-runner.sh reset
./mac-exe-runner.sh setup
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WINE_PREFIX` | `~/.wine` | Path to Wine prefix (virtual Windows environment) |
