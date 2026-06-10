/**
 * BrowserMind Studio — live 6-panel monitoring UI.
 *
 * Panels:
 *   1. Live Browser      — iframe/screenshot + LIVE overlay (#51, #52)
 *   2. Mission Control   — Start/Stop, current site stats, progress (#53)
 *   3. Queue Panel       — filterable by status + tag (#56), bulk-add (#57)
 *   4. Human Intervention Banner (#83)
 *   5. Discovery Feed    — ledger top patterns (#64)
 *   6. Live Timeline     — horizontal step strip (#54)
 *
 * Also:
 *   - Mission detail drawer (#58) — click any site to see full history
 *   - WebSocket live state (#66) — replaces 1.5s polling
 *   - Screenshot fallback (#52) — when iframe is blocked
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Play,
  Square,
  RefreshCw,
  AlertTriangle,
  Monitor,
  Zap,
  Plus,
  Loader2,
  Radio,
  Activity,
  ChevronRight,
  X,
  Image,
  BarChart2,
  Clock,
  ChevronDown,
  Tag,
} from "lucide-react";
import { adapter } from "@/lib/adapters";
import { cn } from "@/lib/cn";
import { SIDECAR_BASE } from "@/lib/adapters/tauri";
import { tauriAvailable } from "@/lib/tauri";
import type { MissionEntry, MissionStatus, MissionLiveState } from "@/types";

// True only when running inside the Tauri shell (sidecar will be up)
const IS_SIDECAR_MODE = tauriAvailable();

// ── Helpers ──────────────────────────────────────────────────────────────────

function rel(ts: number | null | string): string {
  if (!ts) return "—";
  const t = typeof ts === "number" ? ts * 1000 : new Date(ts).getTime();
  const diff = Math.floor((Date.now() - t) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const STATUS_COLOR: Record<MissionStatus, string> = {
  pending: "text-text-muted",
  running: "text-yellow-400",
  done: "text-green-400",
  failed: "text-red-400",
  paused: "text-violet-400",
  skipped: "text-text-subtle",
};

function StatusDot({ status }: { status: MissionStatus }) {
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-1.5 rounded-full shrink-0",
        STATUS_COLOR[status].replace("text-", "bg-"),
        status === "running" && "animate-pulse",
      )}
    />
  );
}

// ── WebSocket hook for live state (#66) ──────────────────────────────────────
// Only active when running inside Tauri (sidecar guaranteed).
// Falls back to HTTP polling (livePoll) in browser dev mode.

function useLiveStateWS(): MissionLiveState | undefined {
  const [live, setLive] = useState<MissionLiveState | undefined>();

  useEffect(() => {
    if (!IS_SIDECAR_MODE) return; // no sidecar in browser dev mode
    const wsUrl = SIDECAR_BASE.replace(/^http/, "ws") + "/ws/live";
    let ws: WebSocket;
    let retryTimer: ReturnType<typeof setTimeout>;
    let retryDelay = 2000;

    const connect = () => {
      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => { retryDelay = 2000; }; // reset on success
        ws.onmessage = (ev) => {
          try { setLive(JSON.parse(ev.data)); } catch {}
        };
        ws.onclose = () => {
          // Exponential backoff: 2s → 4s → 8s → … capped at 30s
          retryDelay = Math.min(retryDelay * 2, 30_000);
          retryTimer = setTimeout(connect, retryDelay);
        };
        ws.onerror = () => { ws.close(); };
      } catch {
        retryDelay = Math.min(retryDelay * 2, 30_000);
        retryTimer = setTimeout(connect, retryDelay);
      }
    };

    connect();
    return () => {
      clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  return live;
}

// ── Screenshot fallback (#52) ─────────────────────────────────────────────────
// Only polls when: (a) inside Tauri sidecar mode AND (b) iframe is blocked.
// Stops after 3 consecutive network failures to prevent console spam.

function useScreenshot(iframeBlocked: boolean) {
  const [screenshot, setScreenshot] = useState<string | null>(null);

  useEffect(() => {
    if (!IS_SIDECAR_MODE || !iframeBlocked) { setScreenshot(null); return; }
    let consecutiveFails = 0;
    let id: ReturnType<typeof setInterval>;

    const fetch_ = async () => {
      try {
        const r = await fetch(`${SIDECAR_BASE}/api/screenshot/current`);
        if (r.ok) {
          const { data, mime } = await r.json();
          setScreenshot(`data:${mime};base64,${data}`);
          consecutiveFails = 0;
        } else {
          setScreenshot(null);
          consecutiveFails++;
        }
      } catch {
        setScreenshot(null);
        consecutiveFails++;
        if (consecutiveFails >= 3) clearInterval(id); // stop hammering
      }
    };
    fetch_();
    id = setInterval(fetch_, 3000);
    return () => clearInterval(id);
  }, [iframeBlocked]);

  return screenshot;
}

// ── Live Browser Panel (#51, #52) ─────────────────────────────────────────────

function LiveBrowserPanel({ live }: { live: MissionLiveState | undefined }) {
  const [iframeBlocked, setIframeBlocked] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const screenshot = useScreenshot(iframeBlocked);
  // Only show live iframe in sidecar mode — in dev/browser mode the mock currentSite
  // would immediately fail cross-origin checks and trigger screenshot polling spam.
  const targetUrl = (IS_SIDECAR_MODE && live?.currentSite) ? `https://${live.currentSite}` : null;

  // Detect iframe block via load error
  const handleIframeError = useCallback(() => setIframeBlocked(true), []);
  const handleIframeLoad = useCallback(() => {
    try {
      // If we can access contentDocument, it loaded (same-origin test)
      const doc = iframeRef.current?.contentDocument;
      setIframeBlocked(!doc || doc.location.href === "about:blank");
    } catch {
      setIframeBlocked(true);
    }
  }, []);

  return (
    <div className="relative flex flex-col flex-1 min-w-0 bg-bg-base border border-border-default rounded-lg overflow-hidden">
      {/* Browser chrome */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-bg-panel border-b border-border-default shrink-0">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-500/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-green-500/60" />
        </div>
        <div className="flex-1 mx-2">
          <div className="h-5 rounded bg-bg-elevated px-2 flex items-center gap-1.5">
            {iframeBlocked && screenshot && (
              <Image size={10} className="text-text-subtle shrink-0" />
            )}
            <span className="text-[10px] text-text-muted truncate">
              {targetUrl ?? "No active session"}
              {iframeBlocked ? " (screenshot mode)" : ""}
            </span>
          </div>
        </div>
        {live?.isWorkerRunning && (
          <span className="flex items-center gap-1 text-[10px] text-yellow-400">
            <Radio size={10} className="animate-pulse" />
            LIVE
          </span>
        )}
      </div>

      {/* Viewport */}
      {targetUrl && !iframeBlocked ? (
        <iframe
          ref={iframeRef}
          src={targetUrl}
          title="live-browser"
          className="flex-1 w-full border-0"
          sandbox="allow-scripts allow-same-origin allow-forms"
          onError={handleIframeError}
          onLoad={handleIframeLoad}
        />
      ) : screenshot ? (
        <div className="flex-1 relative overflow-hidden">
          <img
            src={screenshot}
            alt="browser screenshot"
            className="w-full h-full object-cover object-top"
          />
          <div className="absolute top-2 right-2 flex items-center gap-1 bg-bg-panel/80 rounded px-2 py-1 text-[10px] text-text-subtle">
            <Image size={10} />
            screenshot mode
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-text-subtle">
          <Monitor size={48} className="opacity-20" />
          <p className="text-sm">No active mission</p>
          <p className="text-xs opacity-50">Start the worker to see live browsing</p>
        </div>
      )}

      {/* Action overlay */}
      {live?.currentAction && (
        <div className="absolute bottom-3 left-3 right-3 flex items-center gap-2 bg-bg-panel/90 backdrop-blur-sm border border-border-default rounded-md px-3 py-2 text-xs pointer-events-none">
          <Activity size={12} className="text-yellow-400 shrink-0 animate-pulse" />
          <span className="text-text-muted">
            {live.currentAction}
            {live.currentRole && <span className="text-text-primary"> → {live.currentRole}</span>}
            {live.currentName && <span className="text-text-subtle"> "{live.currentName}"</span>}
          </span>
          <span className="ml-auto text-text-subtle">
            step {live.stepSeq}/{live.totalSteps}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Mission Control Panel ─────────────────────────────────────────────────────

function MissionControlPanel({
  live,
  onStop,
  onRun,
  isMutating,
}: {
  live: MissionLiveState | undefined;
  onStop: () => void;
  onRun: () => void;
  isMutating: boolean;
}) {
  const counts = live?.queueCounts;

  return (
    <div className="flex flex-col gap-3 w-[268px] shrink-0">
      <div className="bg-bg-panel border border-border-default rounded-lg p-3">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-medium text-text-primary">Mission Control</span>
          {live?.isWorkerRunning ? (
            <span className="flex items-center gap-1 text-[10px] text-yellow-400">
              <span className="h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse" />
              Running
            </span>
          ) : (
            <span className="text-[10px] text-text-subtle">Stopped</span>
          )}
        </div>
        <div className="flex gap-2">
          {live?.isWorkerRunning ? (
            <button
              type="button" onClick={onStop} disabled={isMutating}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 h-7 rounded-md text-xs",
                "bg-red-500/10 border border-red-500/20 text-red-400",
                "hover:bg-red-500/20 transition-colors disabled:opacity-50",
              )}
            >
              {isMutating ? <Loader2 size={12} className="animate-spin" /> : <Square size={12} />}
              Stop Worker
            </button>
          ) : (
            <button
              type="button" onClick={onRun} disabled={isMutating}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 h-7 rounded-md text-xs",
                "bg-green-500/10 border border-green-500/20 text-green-400",
                "hover:bg-green-500/20 transition-colors disabled:opacity-50",
              )}
            >
              {isMutating ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
              Start Worker
            </button>
          )}
        </div>
      </div>

      {live?.isWorkerRunning && live.currentSite && (
        <div className="bg-bg-panel border border-border-default rounded-lg p-3 space-y-2">
          <div className="text-[10px] text-text-subtle uppercase tracking-wider">Current</div>
          <div className="space-y-1.5">
            <Row label="Site" value={live.currentSite} highlight />
            <Row label="Persona" value={live.currentPersona ?? "—"} />
            <Row label="Progress" value={`${live.stepsSoFar}/${live.currentBudget ?? "?"}`} />
            <Row label="Success" value={`${live.successSoFar} ok / ${live.failedSoFar} fail`} />
          </div>
          {live.currentBudget && live.currentBudget > 0 && (
            <div className="h-1 rounded-full bg-bg-elevated overflow-hidden">
              <div
                className="h-full rounded-full bg-yellow-400/60 transition-all duration-500"
                style={{ width: `${Math.min(100, (live.stepsSoFar / live.currentBudget) * 100)}%` }}
              />
            </div>
          )}
        </div>
      )}

      {counts && (
        <div className="bg-bg-panel border border-border-default rounded-lg p-3">
          <div className="text-[10px] text-text-subtle uppercase tracking-wider mb-2">Queue</div>
          <div className="grid grid-cols-3 gap-1">
            {(["pending", "running", "done", "failed", "paused", "skipped"] as MissionStatus[]).map((s) => (
              <div key={s} className="flex flex-col items-center py-1 rounded bg-bg-elevated">
                <span className={cn("text-sm font-mono font-medium", STATUS_COLOR[s])}>
                  {counts[s] ?? 0}
                </span>
                <span className="text-[9px] text-text-subtle capitalize">{s}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="flex justify-between items-baseline">
      <span className="text-[10px] text-text-subtle">{label}</span>
      <span className={cn("text-xs font-mono", highlight ? "text-text-primary" : "text-text-muted")}>
        {value}
      </span>
    </div>
  );
}

// ── Mission Detail Drawer (#58) ───────────────────────────────────────────────

function MissionDetailDrawer({
  entry,
  onClose,
  onResume,
}: {
  entry: MissionEntry;
  onClose: () => void;
  onResume: (site: string) => void;
}) {
  return (
    <div className="absolute inset-0 z-50 flex justify-end pointer-events-none">
      <div
        className="w-80 h-full bg-bg-panel border-l border-border-default shadow-xl pointer-events-auto overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-default">
          <div>
            <div className="flex items-center gap-2">
              <StatusDot status={entry.status} />
              <span className="text-sm font-medium text-text-primary">{entry.site_key}</span>
            </div>
            <span className={cn("text-[10px] capitalize", STATUS_COLOR[entry.status])}>
              {entry.status}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="h-6 w-6 flex items-center justify-center rounded hover:bg-bg-elevated text-text-subtle"
          >
            <X size={14} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Basic info */}
          <div className="space-y-1.5">
            <div className="text-[10px] text-text-subtle uppercase tracking-wider">Details</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
              {([
                ["Persona", entry.persona],
                ["Budget", String(entry.budget)],
                ["Attempts", `${entry.attempts}/${entry.max_retries}`],
                ["Priority", String(entry.priority ?? 0)],
                ["Added", rel(entry.added_at)],
                ["Last run", rel(entry.last_run_ts)],
              ] as const).map(([l, v]) => (
                <div key={l}>
                  <div className="text-[9px] text-text-subtle">{l}</div>
                  <div className="text-xs text-text-primary font-mono">{v}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Tags */}
          {entry.tags?.length > 0 && (
            <div>
              <div className="text-[10px] text-text-subtle uppercase tracking-wider mb-1">Tags</div>
              <div className="flex flex-wrap gap-1">
                {entry.tags.map((t) => (
                  <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Last error */}
          {entry.last_error && (
            <div>
              <div className="text-[10px] text-text-subtle uppercase tracking-wider mb-1">Last Error</div>
              <div className="text-[10px] text-red-400/80 font-mono bg-red-500/5 rounded p-2 break-all">
                {entry.last_error}
              </div>
            </div>
          )}

          {/* Metrics */}
          {(entry.last_steps != null || entry.last_hypotheses != null) && (
            <div>
              <div className="text-[10px] text-text-subtle uppercase tracking-wider mb-2">Last Run Metrics</div>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: "Steps", value: entry.last_steps ?? 0, icon: Activity },
                  { label: "Hypotheses", value: entry.last_hypotheses ?? 0, icon: Zap },
                  { label: "Duration", value: entry.last_duration ? `${entry.last_duration.toFixed(1)}s` : "—", icon: Clock },
                ].map(({ label, value, icon: Icon }) => (
                  <div key={label} className="flex flex-col items-center p-2 rounded bg-bg-elevated">
                    <Icon size={12} className="text-text-subtle mb-1" />
                    <span className="text-sm font-mono text-text-primary">{value}</span>
                    <span className="text-[9px] text-text-subtle">{label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Run history */}
          {(entry as any).run_history?.length > 0 && (
            <div>
              <div className="text-[10px] text-text-subtle uppercase tracking-wider mb-2">
                Run History ({(entry as any).run_history.length})
              </div>
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {((entry as any).run_history as Array<{ts: number; status: string; steps: number; hypotheses: number; duration: number}>)
                  .slice()
                  .reverse()
                  .map((r, i) => (
                    <div key={i} className="flex items-center gap-2 text-[10px]">
                      <StatusDot status={r.status as MissionStatus} />
                      <span className="text-text-subtle">{rel(r.ts)}</span>
                      <span className="text-text-muted ml-auto">
                        {r.steps}s / {r.hypotheses}h / {r.duration?.toFixed(1)}s
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-2 border-t border-border-default">
            {entry.status === "paused" && (
              <button
                type="button"
                onClick={() => { onResume(entry.site_key); onClose(); }}
                className={cn(
                  "flex-1 flex items-center justify-center gap-1.5 h-7 rounded text-xs",
                  "bg-violet-500/10 border border-violet-500/20 text-violet-400",
                  "hover:bg-violet-500/20 transition-colors",
                )}
              >
                <RefreshCw size={11} />
                Resume
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Queue List Panel (#56, #57) ───────────────────────────────────────────────

function QueuePanel({
  entries,
  live,
  onResume,
  isResuming,
  onSelectEntry,
}: {
  entries: MissionEntry[];
  live: MissionLiveState | undefined;
  onResume: (siteKey: string) => void;
  isResuming: string | null;
  onSelectEntry: (entry: MissionEntry) => void;
}) {
  const [statusFilter, setStatusFilter] = useState<MissionStatus | "all">("all");
  const [tagFilter, setTagFilter] = useState<string>("");

  // Collect all unique tags from entries (#56)
  const allTags = Array.from(new Set(entries.flatMap((e) => e.tags ?? []))).sort();

  const filtered = entries.filter((e) => {
    if (statusFilter !== "all" && e.status !== statusFilter) return false;
    if (tagFilter && !(e.tags ?? []).includes(tagFilter)) return false;
    return true;
  });

  return (
    <div className="flex flex-col flex-1 min-h-0 overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border-default shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-text-primary">Missions</span>
          <span className="text-[10px] text-text-subtle">{entries.length}</span>
        </div>
        {/* Status filter tabs */}
        <div className="flex gap-1 flex-wrap mb-1.5">
          {(["all", "pending", "running", "paused", "done", "failed"] as const).map((s) => (
            <button
              key={s} type="button" onClick={() => setStatusFilter(s)}
              className={cn(
                "h-4 px-1.5 rounded text-[9px] capitalize transition-colors",
                statusFilter === s ? "bg-accent text-white" : "text-text-subtle hover:text-text-primary",
              )}
            >
              {s}
            </button>
          ))}
        </div>
        {/* Tag filter (#56) */}
        {allTags.length > 0 && (
          <div className="flex items-center gap-1.5">
            <Tag size={9} className="text-text-subtle shrink-0" />
            <div className="flex gap-1 flex-wrap">
              <button
                type="button"
                onClick={() => setTagFilter("")}
                className={cn(
                  "h-4 px-1.5 rounded text-[9px]",
                  tagFilter === "" ? "bg-accent/30 text-accent" : "text-text-subtle hover:text-text-primary",
                )}
              >
                all
              </button>
              {allTags.map((t) => (
                <button
                  key={t} type="button" onClick={() => setTagFilter(tagFilter === t ? "" : t)}
                  className={cn(
                    "h-4 px-1.5 rounded text-[9px]",
                    tagFilter === t ? "bg-accent/30 text-accent" : "text-text-subtle hover:text-text-primary",
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto divide-y divide-border-default/50">
        {filtered.length === 0 && (
          <div className="p-4 text-center text-text-subtle text-xs">No missions</div>
        )}
        {filtered.map((e) => {
          const isCurrentSite = live?.currentSite === e.site_key;
          return (
            <div
              key={e.id}
              className={cn(
                "px-3 py-2 transition-colors cursor-pointer hover:bg-bg-elevated/50",
                isCurrentSite && "bg-yellow-500/5",
              )}
              onClick={() => onSelectEntry(e)}
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <StatusDot status={e.status} />
                <span className={cn(
                  "text-xs font-medium truncate",
                  isCurrentSite ? "text-yellow-400" : "text-text-primary",
                )}>
                  {e.site_key}
                </span>
                {isCurrentSite && (
                  <ChevronRight size={10} className="text-yellow-400 shrink-0 ml-auto animate-pulse" />
                )}
                {e.priority > 0 && !isCurrentSite && (
                  <span className="text-[9px] text-accent ml-auto">P{e.priority}</span>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className={cn("text-[10px] capitalize", STATUS_COLOR[e.status])}>
                  {e.status}
                </span>
                {e.last_run_ts && (
                  <span className="text-[10px] text-text-subtle">{rel(e.last_run_ts)}</span>
                )}
              </div>
              {e.status === "paused" && (
                <button
                  type="button"
                  onClick={(ev) => { ev.stopPropagation(); onResume(e.site_key); }}
                  disabled={isResuming === e.site_key}
                  className="mt-1 w-full flex items-center justify-center gap-1 h-5 rounded bg-violet-500/10 border border-violet-500/20 text-[10px] text-violet-400 hover:bg-violet-500/20 transition-colors disabled:opacity-50"
                >
                  {isResuming === e.site_key ? <Loader2 size={9} className="animate-spin" /> : <RefreshCw size={9} />}
                  Resume
                </button>
              )}
              {e.last_error && e.status !== "done" && (
                <p className="text-[9px] text-red-400/70 truncate mt-0.5">{e.last_error}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Bulk-Add Row (#57) ────────────────────────────────────────────────────────

function AddSiteRow({ onAdd }: { onAdd: (siteKeys: string[]) => void }) {
  const [val, setVal] = useState("");
  const [expanded, setExpanded] = useState(false);

  const submit = () => {
    const keys = val
      .split(/[\n,\s]+/)
      .map((k) => k.trim())
      .filter(Boolean);
    if (keys.length) { onAdd(keys); setVal(""); setExpanded(false); }
  };

  return (
    <div className="px-3 py-2 border-t border-border-default shrink-0">
      {expanded ? (
        <div className="space-y-1.5">
          <textarea
            placeholder={"site_key1\nsite_key2\nor comma-separated"}
            value={val}
            onChange={(e) => setVal(e.target.value)}
            rows={3}
            className={cn(
              "w-full rounded bg-bg-elevated border border-border-default px-2 py-1.5 text-xs",
              "text-text-primary placeholder:text-text-subtle resize-none",
              "focus:outline-none focus:border-accent",
            )}
          />
          <div className="flex gap-1.5">
            <button type="button" onClick={submit}
              className="flex-1 h-6 rounded bg-accent/10 border border-accent/20 text-accent text-xs hover:bg-accent/20">
              Add All
            </button>
            <button type="button" onClick={() => { setExpanded(false); setVal(""); }}
              className="h-6 w-6 flex items-center justify-center rounded bg-bg-elevated border border-border-default text-text-subtle">
              <X size={11} />
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-1.5">
          <input
            type="text" placeholder="site_key…" value={val}
            onChange={(e) => setVal(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && val.trim()) { onAdd([val.trim()]); setVal(""); }
            }}
            className={cn(
              "flex-1 h-6 rounded bg-bg-elevated border border-border-default px-2 text-xs",
              "text-text-primary placeholder:text-text-subtle",
              "focus:outline-none focus:border-accent",
            )}
          />
          <button type="button" onClick={() => { if (val.trim()) { onAdd([val.trim()]); setVal(""); } }}
            className="h-6 w-6 flex items-center justify-center rounded bg-accent/10 border border-accent/20 text-accent hover:bg-accent/20">
            <Plus size={12} />
          </button>
          <button type="button" onClick={() => setExpanded(true)} title="Bulk add"
            className="h-6 w-6 flex items-center justify-center rounded bg-bg-elevated border border-border-default text-text-subtle hover:text-text-primary">
            <ChevronDown size={11} />
          </button>
        </div>
      )}
    </div>
  );
}

// ── Human Intervention Banner ─────────────────────────────────────────────────

function HumanInterventionBanner({
  pausedSites, onResume, isResuming,
}: {
  pausedSites: string[];
  onResume: (site: string) => void;
  isResuming: string | null;
}) {
  if (pausedSites.length === 0) return null;
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 bg-violet-500/10 border border-violet-500/20 rounded-lg text-sm shrink-0">
      <AlertTriangle size={16} className="text-violet-400 shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="font-medium text-violet-300">Human required — </span>
        <span className="text-text-muted">
          {pausedSites.length === 1
            ? `${pausedSites[0]} hit a bot wall or auth gate`
            : `${pausedSites.length} sites need attention`}
        </span>
      </div>
      <div className="flex gap-2 shrink-0">
        {pausedSites.slice(0, 3).map((site) => (
          <button
            key={site} type="button" onClick={() => onResume(site)}
            disabled={isResuming === site}
            className={cn(
              "flex items-center gap-1 h-6 px-2 rounded text-xs",
              "bg-violet-500/20 border border-violet-500/30 text-violet-300",
              "hover:bg-violet-500/30 transition-colors disabled:opacity-50",
            )}
          >
            {isResuming === site ? <Loader2 size={10} className="animate-spin" /> : <RefreshCw size={10} />}
            Resume {site}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Live Timeline ─────────────────────────────────────────────────────────────

interface TimelineEvent { seq: number; action: string; role: string; success: boolean; }

function LiveTimeline({ live }: { live: MissionLiveState | undefined }) {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!live?.isWorkerRunning || !live.currentAction) return;
    setEvents((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.seq === live.stepSeq) return prev;
      return [...prev.slice(-49), {
        seq: live.stepSeq,
        action: live.currentAction ?? "",
        role: live.currentRole ?? "",
        success: live.successSoFar > (last?.success ? 1 : 0),
      }];
    });
  }, [live?.stepSeq, live?.currentAction]);

  useEffect(() => {
    if (containerRef.current) containerRef.current.scrollLeft = containerRef.current.scrollWidth;
  }, [events]);

  return (
    <div className="bg-bg-panel border border-border-default rounded-lg px-3 py-2 shrink-0">
      <div className="flex items-center gap-2 mb-2">
        <BarChart2 size={11} className="text-text-subtle" />
        <span className="text-[10px] text-text-subtle uppercase tracking-wider">Live Timeline</span>
        {live?.isWorkerRunning && (
          <span className="ml-auto text-[10px] text-text-subtle">
            {live.successSoFar} ok / {live.failedSoFar} fail
          </span>
        )}
      </div>
      <div ref={containerRef} className="flex items-end gap-1.5 overflow-x-auto pb-1 min-h-[36px]"
           style={{ scrollbarWidth: "none" }}>
        {events.length === 0 && (
          <span className="text-[10px] text-text-subtle italic">
            {live?.isWorkerRunning ? "Waiting for first step…" : "No active session"}
          </span>
        )}
        {events.map((ev) => (
          <div key={ev.seq} className="flex flex-col items-center gap-0.5 shrink-0" title={`${ev.action} → ${ev.role}`}>
            <span className="text-[8px] text-text-subtle max-w-[56px] truncate text-center">
              {ev.role || ev.action}
            </span>
            <div className={cn("h-3 w-3 rounded-sm", ev.success ? "bg-green-500/60" : "bg-red-500/60")} />
          </div>
        ))}
        {live?.isWorkerRunning && (
          <div className="flex flex-col items-center gap-0.5 shrink-0">
            <span className="text-[8px] text-yellow-400">now</span>
            <div className="h-3 w-3 rounded-sm bg-yellow-400/60 animate-pulse" />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Discovery Feed ────────────────────────────────────────────────────────────

function DiscoveryFeed({ live }: { live: MissionLiveState | undefined }) {
  const { data: ledger } = useQuery({
    queryKey: ["ledger-stats"],
    queryFn: () => adapter.explore.ledgerStats(),
    refetchInterval: 15000,
  });
  const frags = ledger?.topFragments?.slice(0, 8) ?? [];

  return (
    <div className="bg-bg-panel border border-border-default rounded-lg p-3 w-[268px] shrink-0 flex-1 min-h-0 overflow-y-auto">
      <div className="flex items-center gap-2 mb-2">
        <Zap size={12} className="text-yellow-400" />
        <span className="text-xs font-medium text-text-primary">Discovery Feed</span>
        {ledger && (
          <span className="ml-auto text-[10px] text-text-subtle">{ledger.uniqueFragments ?? 0} patterns</span>
        )}
      </div>
      <div className="space-y-1.5">
        {frags.length === 0 && (
          <p className="text-[10px] text-text-subtle italic">No patterns yet — start a mission</p>
        )}
        {frags.map((f: { fragment: string; freq?: number; count?: number }, i: number) => (
          <div key={i} className="flex items-center gap-2">
            <span className="text-[10px] text-text-muted font-mono truncate flex-1">{f.fragment}</span>
            <span className="text-[10px] text-text-subtle shrink-0">×{f.freq ?? f.count ?? 0}</span>
          </div>
        ))}
        {live?.isWorkerRunning && live.currentRole && (
          <div className="flex items-center gap-2 border-t border-border-default/50 pt-1.5 mt-1.5">
            <span className="text-[9px] text-yellow-400/70">LIVE</span>
            <span className="text-[10px] text-yellow-400 font-mono truncate">{live.currentRole}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Studio Page ──────────────────────────────────────────────────────────

export default function StudioPage() {
  const qc = useQueryClient();
  const [isResuming, setIsResuming] = useState<string | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<MissionEntry | null>(null);

  // In sidecar mode: WS push. In dev/browser mode: adapter polling (mock data).
  const liveWS = useLiveStateWS(); // only active in sidecar mode
  const { data: livePoll } = useQuery({
    queryKey: ["mission-live"],
    queryFn: () => adapter.mission.live(),
    // In sidecar mode poll only when WS is down; in dev mode poll always (mock)
    refetchInterval: IS_SIDECAR_MODE ? (liveWS ? false : 1500) : 3000,
  });
  const live = liveWS ?? livePoll;

  const { data: entries = [] } = useQuery({
    queryKey: ["mission-list"],
    queryFn: () => adapter.mission.list(),
    refetchInterval: 3000,
  });

  const startMutation = useMutation({
    mutationFn: () => adapter.mission.run({ headless: false }),
    onMutate: () => setIsMutating(true),
    onSettled: () => {
      setIsMutating(false);
      qc.invalidateQueries({ queryKey: ["mission-live"] });
      qc.invalidateQueries({ queryKey: ["mission-list"] });
    },
  });

  const stopMutation = useMutation({
    mutationFn: () => adapter.mission.stop(),
    onMutate: () => setIsMutating(true),
    onSettled: () => { setIsMutating(false); qc.invalidateQueries({ queryKey: ["mission-live"] }); },
  });

  const addMutation = useMutation({
    mutationFn: (siteKeys: string[]) =>
      siteKeys.length === 1
        ? adapter.mission.add(siteKeys[0]).then(() => undefined)
        : adapter.mission.addBulk(siteKeys).then(() => undefined),
    onSettled: () => qc.invalidateQueries({ queryKey: ["mission-list"] }),
  });

  const resumeMutation = useMutation({
    mutationFn: async (siteKey: string) => {
      setIsResuming(siteKey);
      return adapter.mission.resume(siteKey);
    },
    onSettled: () => {
      setIsResuming(null);
      qc.invalidateQueries({ queryKey: ["mission-list"] });
      qc.invalidateQueries({ queryKey: ["mission-live"] });
    },
  });

  const pausedSites = live?.pausedSites ?? [];

  return (
    <div className="relative flex flex-col h-full gap-2 p-3 bg-bg-base overflow-hidden">
      {/* Dev-mode notice — shown only in browser (no sidecar) */}
      {!IS_SIDECAR_MODE && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-500/8 border border-yellow-500/20 rounded text-[10px] text-yellow-500/80 shrink-0">
          <span className="font-medium">Dev mode</span>
          <span className="text-yellow-500/60">— mock data, no sidecar. Run</span>
          <code className="font-mono bg-yellow-500/10 px-1 rounded">bm sidecar start</code>
          <span className="text-yellow-500/60">then open in Tauri for live data.</span>
        </div>
      )}

      {/* Human Intervention Banner */}
      {live?.needsHuman && (
        <HumanInterventionBanner
          pausedSites={pausedSites}
          onResume={(s) => resumeMutation.mutate(s)}
          isResuming={isResuming}
        />
      )}

      {/* Main area */}
      <div className="flex gap-2 flex-1 min-h-0">
        {/* Queue Panel (left) */}
        <div className="flex flex-col w-[220px] shrink-0 min-h-0 bg-bg-panel border border-border-default rounded-lg overflow-hidden">
          <QueuePanel
            entries={entries}
            live={live}
            onResume={(s) => resumeMutation.mutate(s)}
            isResuming={isResuming}
            onSelectEntry={setSelectedEntry}
          />
          <AddSiteRow onAdd={(keys) => addMutation.mutate(keys)} />
        </div>

        {/* Live Browser (center) */}
        <LiveBrowserPanel live={live} />

        {/* Right column */}
        <div className="flex flex-col gap-2 shrink-0 w-[268px]">
          <MissionControlPanel
            live={live}
            onRun={() => startMutation.mutate()}
            onStop={() => stopMutation.mutate()}
            isMutating={isMutating}
          />
          <DiscoveryFeed live={live} />
        </div>
      </div>

      {/* Live Timeline (bottom) */}
      <LiveTimeline live={live} />

      {/* Mission Detail Drawer (#58) */}
      {selectedEntry && (
        <MissionDetailDrawer
          entry={selectedEntry}
          onClose={() => setSelectedEntry(null)}
          onResume={(s) => resumeMutation.mutate(s)}
        />
      )}
    </div>
  );
}
