import { useSystemStatus } from "@/lib/queries";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/utils";
import { tauriAvailable } from "@/lib/tauri";

type ReplayStatus = "idle" | "recording" | "replaying";

const REPLAY_DOT: Record<ReplayStatus, string> = {
  idle: "bg-text-subtle",
  recording: "bg-state-error",
  replaying: "bg-state-success",
};

const REPLAY_LABEL: Record<ReplayStatus, string> = {
  idle: "Idle",
  recording: "Recording",
  replaying: "Replaying",
};

export function StatusBar() {
  const { data } = useSystemStatus();

  const replayStatus: ReplayStatus =
    (data?.replayStatus as ReplayStatus | undefined) ?? "idle";
  const activeSessions = data?.activeSessions ?? 0;
  const backgroundJobs = data?.backgroundJobs ?? 0;
  const memoryMb = data?.memoryMb ?? 0;
  const tauriConnected = tauriAvailable();

  return (
    <footer
      className="flex h-6 items-center gap-4 border-t border-border-default bg-bg-panel px-3 text-[11px] text-text-muted"
      role="contentinfo"
    >
      <span className="flex items-center gap-1.5">
        <span
          className={cn(
            "inline-block h-1.5 w-1.5 rounded-full",
            REPLAY_DOT[replayStatus],
          )}
          aria-hidden
        />
        <span>{REPLAY_LABEL[replayStatus]}</span>
      </span>

      <span>Sessions {formatNumber(activeSessions)}</span>
      <span>Jobs {formatNumber(backgroundJobs)}</span>
      <span>Mem {formatNumber(memoryMb)} MB</span>

      <span className="flex-1" />

      <span className="flex items-center gap-1.5">
        <span
          className={cn(
            "inline-block h-1.5 w-1.5 rounded-full",
            tauriConnected ? "bg-state-success" : "bg-state-warning",
          )}
          aria-hidden
        />
        <span>
          Tauri: {tauriConnected ? "connected" : "dev (mock)"}
        </span>
      </span>
    </footer>
  );
}
