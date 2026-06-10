/**
 * Tauri command shim. Wraps `@tauri-apps/api/core` `invoke` so the same
 * call site works in browser dev mode (where it throws BridgeUnavailable)
 * and in the real Tauri shell.
 */

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export class BridgeUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BridgeUnavailable";
  }
}

export async function invoke<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri) {
    throw new BridgeUnavailable(`Tauri unavailable for ${cmd}`);
  }
  const mod = await import("@tauri-apps/api/core");
  return mod.invoke<T>(cmd, args);
}

export const tauriAvailable = (): boolean => isTauri;
