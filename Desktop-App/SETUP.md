# Macula Desktop — Setup

## Prerequisites

### 1. Rust
Install via rustup:
```
winget install Rustlang.Rustup
```
Then restart your terminal and run:
```
rustup default stable
rustup target add x86_64-pc-windows-msvc
```

### 2. Visual Studio Build Tools (Windows)
Required for compiling Rust on Windows:
```
winget install Microsoft.VisualStudio.2022.BuildTools
```
During install, select **"Desktop development with C++"**.

### 3. Node.js 18+
Already installed (v22). Confirmed.

### 4. WebView2
Pre-installed on Windows 10 (1803+) and Windows 11. No action needed.

---

## Install & Run

```bash
cd Desktop-App
npm install
npm run tauri dev
```

First run compiles all Rust dependencies — expect 2-5 minutes. Subsequent runs are fast.

---

## Build Installer

```bash
npm run tauri build
```
Output: `src-tauri/target/release/bundle/msi/Macula_0.1.0_x64_en-US.msi`

---

## Architecture

```
Desktop-App/
  src/                      React frontend (TypeScript + Tailwind)
    pages/
      Onboarding.tsx        First-run wizard (profile, device, done)
      Dashboard.tsx         Overview, recent regions, quick actions
      Maps.tsx              Leaflet region selector + tile download
      Models.tsx            SuperPoint/LightGlue weight management
      Devices.tsx           SSH device management (Pi5 + local)
      Upload.tsx            SCP upload to Pi5 or local path
      Settings.tsx          params.yaml editor
  src-tauri/
    src/
      commands/
        satellite.rs        Tile download (ports prepare_region.py to Rust)
        ssh.rs              SSH/SCP upload via ssh2 crate
        config_cmd.rs       YAML read/write
        profile.rs          Local profile + device persistence
```

## Data Storage

Profile and devices are stored in:
- Windows: `%LOCALAPPDATA%\Macula\profile.json` and `devices.json`

---

## Adding App Icons

Tauri needs icons in `src-tauri/icons/`. Generate from a 1024×1024 PNG:
```bash
npm run tauri icon path/to/icon-1024.png
```
This produces all required sizes automatically.
