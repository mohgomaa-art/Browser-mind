# BrowserMind UI (Tauri 2)

Tauri 2 + React 19 + TypeScript desktop shell for BrowserMind.

## Prerequisites

- Node 20+ (or Bun)
- Rust toolchain (rustup, stable)
- Windows: MS C++ Build Tools + WebView2 Runtime
- macOS: Xcode Command Line Tools
- Linux: see https://tauri.app/start/prerequisites/

## Run

```sh
bun install   # or: npm install
bun run tauri:dev
```

Web-only dev (faster iteration, no native shell):

```sh
bun run dev
```

## Build

```sh
bun run tauri:build
```

## Notes

- App icons are not yet wired up. Add `src-tauri/icons/` and reference them in `tauri.conf.json` before release builds.
- Path alias `@/*` resolves to `src/*`.
- Dark theme only (for now). Token reference: `tailwind.config.ts` + `src/index.css`.
