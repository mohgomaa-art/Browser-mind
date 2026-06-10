import { useEffect, useState } from "react";
import { invoke, tauriAvailable } from "./tauri";

const SIDECAR_URL = "http://127.0.0.1:8766";

let _ready = false;
let _startPromise: Promise<void> | null = null;

export function getSidecarUrl(): string {
  return SIDECAR_URL;
}

async function ensureSidecarStarted(): Promise<void> {
  if (_ready) return;
  if (!tauriAvailable()) {
    _ready = true;
    return;
  }
  if (_startPromise) return _startPromise;
  _startPromise = invoke<number>("bm_sidecar_start")
    .then(() => {
      _ready = true;
    })
    .catch(() => {
      _ready = false;
      _startPromise = null;
    });
  return _startPromise;
}

export function useSidecar(): { ready: boolean; url: string } {
  const [ready, setReady] = useState(_ready);

  useEffect(() => {
    ensureSidecarStarted()
      .then(() => setReady(true))
      .catch(() => setReady(false));
  }, []);

  return { ready, url: SIDECAR_URL };
}
