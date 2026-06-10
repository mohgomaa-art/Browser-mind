import { tauriAvailable } from "../tauri";
import { mockAdapter } from "./mock";
import { tauriAdapter } from "./tauri";

export const adapter = tauriAvailable() ? tauriAdapter : mockAdapter;
export type Adapter = typeof mockAdapter;

export type { SystemStatus } from "./mock";
